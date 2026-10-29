"""Real SQLite/API tests: ownership, retries, contention and transactional endings."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, insert, select, text, update

from backend.app.bootstrap import migrate, migration_config
from backend.app.config import Settings
from backend.app.game_models import Game, GameOperation, GameStart, Guess
from backend.app.main import create_app
from backend.app.models import DictionaryVersion, Word
from backend.app.security import COOKIE
from backend.app.economy_service import seed_economy

HEADERS = {"X-Requested-With": "word_guess", "Origin": "http://testserver"}
WORDS = {"4": ["елка", "аист", "мама", "тест", "кофе", "рука", "лиса", "мука"],
         "5": ["касса", "маска", "сосна", "слово", "парта", "лампа", "банка", "атака", "каска", "масса"],
         "6": ["ворона", "машина", "голова", "собака", "корова", "лопата", "береза", "молоко"]}


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'games.db').as_posix()}")


@pytest.fixture
def app(settings, monkeypatch):
    from datetime import datetime, timezone
    app = create_app(settings)
    monkeypatch.setattr("backend.app.game_service.definition_for", lambda word: None)
    migrate(app.state.engine)
    with app.state.engine.begin() as connection:
        version = connection.execute(insert(DictionaryVersion).values(
            checksum="test", source="test", imported_at=datetime.now(timezone.utc),
        )).inserted_primary_key[0]
        for group in WORDS.values():
            for word in group:
                connection.execute(insert(Word).values(
                    canonical_word=word, display_word="ёлка" if word == "елка" else word,
                    length=len(word), difficulty=1, familiarity="common", source="test",
                    enabled_as_answer=word == group[0], enabled_as_guess=True, dictionary_version_id=version,
                ))
    yield app
    app.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app, headers=HEADERS) as client:
        assert client.post("/api/auth/register", json={"login": "player", "display_name": "Игрок", "password": "password-123"}).status_code == 201
        yield client


def start(client, mode="5", key=None):
    response = client.post("/api/games", json={"mode": mode, "operation_id": key or str(uuid4())})
    assert response.status_code == 200, response.text
    return response.json()


def attempt(client, game, word, key=None, version=None):
    return client.post(f"/api/games/{game['id']}/guesses", json={
        "word": word, "version": game["version"] if version is None else version,
        "operation_id": key or str(uuid4()),
    })


def surrender(client, game, key=None):
    return client.post(f"/api/games/{game['id']}/surrender", json={"version": game["version"], "operation_id": key or str(uuid4())})


@pytest.mark.parametrize("mode", ["4", "5", "6"])
def test_six_failures_reveal_answer_then_immediate_new_game(client, mode):
    game = start(client, mode)
    for index, word in enumerate(WORDS[mode][1:7]):
        assert "answer" not in game and "word_id" not in game
        response = attempt(client, game, word)
        assert response.status_code == 200
        game = response.json()
        assert game["version"] == index + 1 and len(game["guesses"]) == index + 1
    assert game["status"] == "lost"
    assert game["answer"]["word"].replace("ё", "е") == WORDS[mode][0]
    assert attempt(client, game, WORDS[mode][0]).status_code == 409
    assert start(client, mode)["id"] != game["id"]


def test_win_normalizes_yo_and_discloses_only_after_completion(client):
    game = start(client, "4")
    assert "answer" not in game and "definition" not in str(game)
    result = attempt(client, game, " ЁЛКА ").json()
    assert result["status"] == "won"
    assert result["guesses"][0]["word"] == "елка"
    assert result["guesses"][0]["marks"] == ["correct"] * 4
    assert result["answer"]["word"] == "ёлка"
    assert attempt(client, result, "аист").status_code == 409


def test_definitions_are_not_even_looked_up_before_completion(client, monkeypatch):
    requested = []
    def definition(word):
        requested.append(word)
        return {"text": "Тестовое толкование", "url": "https://ru.wiktionary.org/wiki/test", "license": "CC BY-SA 4.0"}
    monkeypatch.setattr("backend.app.game_service.definition_for", definition)
    game = start(client)
    assert requested == []
    game = attempt(client, game, "маска").json()
    assert requested == [] and "answer" not in game
    result = surrender(client, game).json()
    assert requested == ["касса"]
    assert result["answer"]["definition"]["text"] == "Тестовое толкование"


def test_invalid_unknown_and_duplicate_do_not_consume_attempts(client):
    game = start(client)
    for word in ("ааааа", "кот", "маска!", "маскa", "12345"):
        assert attempt(client, game, word).status_code == 422
        assert client.get(f"/api/games/{game['id']}").json()["version"] == 0
    game = attempt(client, game, "МАСКА").json()
    assert attempt(client, game, " маска ").status_code == 422
    assert client.get(f"/api/games/{game['id']}").json()["version"] == 1


def test_modes_restore_independently_after_app_restart(client, settings):
    games = {mode: start(client, mode) for mode in WORDS}
    game = attempt(client, games["5"], "маска").json()
    token = client.cookies.get(COOKIE)
    with TestClient(create_app(settings), headers=HEADERS) as restored:
        restored.cookies.set(COOKIE, token)
        assert restored.get("/api/games?mode=5").json() == game
        assert start(restored, "5") == game
        assert restored.get("/api/games?mode=4").json()["id"] == games["4"]["id"]
        assert restored.get("/api/games?mode=6").json()["id"] == games["6"]["id"]


def test_guess_retry_is_idempotent_even_after_another_guess_and_completion(client):
    game = start(client)
    key = str(uuid4())
    first = attempt(client, game, "маска", key).json()
    assert attempt(client, game, " МАСКА ", key).json() == first
    assert attempt(client, game, "сосна", key).status_code == 409
    finished = attempt(client, first, "касса").json()
    assert attempt(client, game, "маска", key).json() == finished
    assert len(finished["guesses"]) == 2


def test_start_retries_and_surrender_are_idempotent_after_completion(client):
    key, resumed_key, end_key = (str(uuid4()) for _ in range(3))
    game = start(client, key=key)
    assert start(client, key=resumed_key)["id"] == game["id"]
    finished = surrender(client, game, end_key).json()
    assert finished["status"] == "surrendered" and not finished["guesses"]
    assert surrender(client, game, end_key).json() == finished
    new_game = start(client)
    assert new_game["id"] != game["id"]
    assert start(client, key=key) == start(client, key=resumed_key) == finished
    assert client.post("/api/games", json={"mode": "4", "operation_id": key}).status_code == 409
    assert attempt(client, game, "маска", end_key).status_code == 409


def test_other_user_and_anonymous_cannot_read_or_mutate_game(client, app):
    game = start(client)
    with TestClient(app, headers=HEADERS) as other:
        assert other.get(f"/api/games/{game['id']}").status_code == 401
        other.post("/api/auth/register", json={"login": "other", "display_name": "Другой", "password": "password-123"})
        assert other.get("/api/games?mode=5").json() is None
        assert other.get(f"/api/games/{game['id']}").status_code == 404
        assert attempt(other, game, "касса").status_code == 404
        assert surrender(other, game).status_code == 404
    assert client.get(f"/api/games/{game['id']}").json() == game


def test_concurrent_creation_and_guesses_are_serialized(app, client):
    token = client.cookies.get(COOKIE)
    def request(action):
        with TestClient(app, headers=HEADERS) as tab:
            tab.cookies.set(COOKIE, token)
            return action(tab)
    with ThreadPoolExecutor(max_workers=2) as pool:
        games = list(pool.map(lambda _: request(start), range(2)))
    assert games[0] == games[1]
    game = games[0]
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: request(lambda tab: attempt(tab, game, "маска", key)), range(2)))
    assert [response.status_code for response in results] == [200, 200]
    game = results[0].json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda word: request(lambda tab: attempt(tab, game, word)), ["сосна", "слово"]))
    assert sorted(response.status_code for response in results) == [200, 409]
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(Game)).scalar_one() == 1
        assert connection.execute(select(func.count()).select_from(GameStart)).scalar_one() == 2
        assert connection.execute(select(func.count()).select_from(Guess)).scalar_one() == 2
        assert connection.execute(select(func.count()).select_from(GameOperation)).scalar_one() == 2


def test_failure_rolls_back_guess_operation_and_completion(app, client):
    game = start(client)
    with app.state.engine.begin() as connection:
        connection.execute(text("""CREATE TRIGGER fail_finish BEFORE UPDATE ON games
            BEGIN SELECT RAISE(ABORT, 'test rollback'); END"""))
    with TestClient(app, headers=HEADERS, raise_server_exceptions=False) as failing:
        failing.cookies.set(COOKIE, client.cookies.get(COOKIE))
        assert attempt(failing, game, "касса").status_code == 500
    assert client.get(f"/api/games/{game['id']}").json() == game
    with app.state.engine.begin() as connection:
        assert connection.execute(select(func.count()).select_from(Guess)).scalar_one() == 0
        assert connection.execute(select(func.count()).select_from(GameOperation)).scalar_one() == 0
        connection.execute(text("DROP TRIGGER fail_finish"))
    assert attempt(client, game, "касса").json()["status"] == "won"


def test_current_answer_remains_valid_after_dictionary_flags_change(client, app):
    game = start(client)
    with app.state.engine.begin() as connection:
        connection.execute(update(Word).where(Word.canonical_word == "касса").values(enabled_as_answer=False, enabled_as_guess=False, display_word="changed"))
    result = attempt(client, game, "касса").json()
    assert result["status"] == "won" and result["answer"]["word"] == "касса"


def test_game_migration_preserves_accounts_and_settings(client, app):
    config = migration_config()
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0002_accounts")
    migrate(app.state.engine)
    assert client.get("/api/auth/me").json()["user"]["login"] == "player"
    seed_economy(app.state.engine)
    assert start(client)["status"] == "active"
