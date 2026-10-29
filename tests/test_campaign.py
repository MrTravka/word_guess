"""Campaign acceptance: real SQLite cycles, progress, milestones and concurrent retries."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text, update

from backend.app.bootstrap import migrate, migration_config
from backend.app.campaign_models import CampaignCompletion, CampaignHistory, CampaignProgress, Chest
from backend.app.campaign_rules import hard_percent, level_length, preferred_difficulty, victory_stars
from backend.app.economy_models import GameReward
from backend.app.game_models import Game
from backend.app.main import create_app
from backend.app.models import Word
from backend.app.security import COOKIE
from test_games import HEADERS, app, attempt, client, settings, start, surrender
from test_hints import hint


@pytest.fixture(autouse=True)
def answer_pool(app):
    with app.state.engine.begin() as connection:
        connection.execute(update(Word).values(enabled_as_answer=True))


def answer(app, game):
    with app.state.engine.connect() as connection:
        return connection.execute(select(Game.answer).where(Game.id == game["id"])).scalar_one()


def page(client, chapter=None):
    response = client.get("/api/campaign", params={} if chapter is None else {"chapter": chapter})
    assert response.status_code == 200, response.text
    return response.json()


def set_level(app, level):
    # A test fixture for late levels; production accepts no client-supplied level.
    with app.state.engine.begin() as connection:
        connection.execute(text("INSERT OR REPLACE INTO campaign_progress(user_id,current_level) VALUES (1,:level)"), {"level": level})


def test_levels_1_to_21_award_two_chests_once_and_separate_points(client, app):
    for level in range(1, 22):
        key = str(uuid4())
        game = start(client, "campaign", key)
        assert game["mode"] == "campaign" and game["campaign"]["level"] == level
        assert "answer" not in game and "word_id" not in game and "cycle" not in game
        win_key = str(uuid4())
        word = answer(app, game)
        result = attempt(client, game, word, win_key).json()
        assert result["status"] == "won"
        assert result["campaign"]["stars"] == 3
        assert bool(result["campaign"]["chest_id"]) == (level % 10 == 0)
        assert result["campaign"]["current_level"] == level + 1
        assert attempt(client, game, word, win_key).json() == result
        assert start(client, "campaign", key)["id"] == game["id"]
    assert page(client)["current_level"] == 22 and page(client)["chests"] == 2
    assert page(client, 1)["levels"][9]["chest_id"]
    inventory = client.get("/api/inventory").json()
    assert inventory["coins"] == 150 + 21 * 30
    assert inventory["points"] == {"4": 0, "5": 0, "6": 0, "campaign": 21 * 120}
    with app.state.engine.connect() as connection:
        for model, count in ((Chest, 2), (CampaignCompletion, 21), (GameReward, 21)):
            assert connection.execute(select(func.count()).select_from(model)).scalar_one() == count


def test_losses_cycle_all_words_before_reuse_and_never_repeat_previous(client, app):
    with app.state.engine.begin() as connection:
        connection.execute(update(Word).where(Word.length == 4).values(enabled_as_answer=False))
        connection.execute(update(Word).where(Word.canonical_word.in_(["елка", "аист", "мама"])).values(enabled_as_answer=True))
    answers = []
    for index in range(8):
        game = start(client, "campaign")
        answers.append(answer(app, game))
        assert game["campaign"]["level"] == 1
        # Exhaust all six guesses for the first failure; surrender on later ones.
        if index == 0:
            with app.state.engine.connect() as connection:
                guesses = connection.execute(select(Word.canonical_word).where(
                    Word.length == 4, Word.canonical_word != answers[-1],
                ).limit(6)).scalars().all()
            for word in guesses:
                game = attempt(client, game, word).json()
            assert game["status"] == "lost"
        else:
            assert surrender(client, game).json()["reward"]["coins"] == 0
    assert len(set(answers[:3])) == 3 and len(set(answers[3:6])) == 3
    assert all(before != after for before, after in zip(answers, answers[1:]))
    assert page(client)["current_level"] == 1
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.max(CampaignHistory.cycle))).scalar_one() == 3


def test_active_game_restores_and_all_four_modes_are_independent(client, app, settings):
    campaign = start(client, "campaign")
    free = {mode: start(client, mode) for mode in ("4", "5", "6")}
    assert start(client, "campaign")["id"] == campaign["id"]
    token = client.cookies.get(COOKIE)
    with TestClient(create_app(settings), headers=HEADERS) as restored:
        restored.cookies.set(COOKIE, token)
        assert restored.get("/api/games?mode=campaign").json() == campaign
        assert page(restored)["current_level"] == 1
        for mode, game in free.items():
            assert restored.get(f"/api/games?mode={mode}").json()["id"] == game["id"]


def test_concurrent_start_and_milestone_win_are_atomic(client, app):
    set_level(app, 10)
    token = client.cookies.get(COOKIE)
    def request(action):
        with TestClient(app, headers=HEADERS) as tab:
            tab.cookies.set(COOKIE, token)
            return action(tab)
    with ThreadPoolExecutor(max_workers=2) as pool:
        games = list(pool.map(lambda _: request(lambda tab: start(tab, "campaign")), range(2)))
    assert games[0] == games[1]
    game, key = games[0], str(uuid4())
    word = answer(app, game)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: request(lambda tab: attempt(tab, game, word, key)), range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json()
    assert attempt(client, game, word).status_code == 409
    assert page(client)["current_level"] == 11 and page(client)["chests"] == 1
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(CampaignHistory)).scalar_one() == 1
        assert connection.execute(select(func.count()).select_from(CampaignCompletion)).scalar_one() == 1


def test_chest_failure_rolls_back_win_money_stars_and_level(client, app):
    set_level(app, 20)
    game = start(client, "campaign")
    word = answer(app, game)
    with app.state.engine.begin() as connection:
        connection.execute(text("CREATE TRIGGER fail_chest BEFORE INSERT ON chests BEGIN SELECT RAISE(ABORT, 'test'); END"))
    key = str(uuid4())
    with TestClient(app, headers=HEADERS, raise_server_exceptions=False) as failing:
        failing.cookies.set(COOKIE, client.cookies.get(COOKIE))
        assert attempt(failing, game, word, key).status_code == 500
    assert client.get(f"/api/games/{game['id']}").json() == game
    assert page(client)["current_level"] == 20 and page(client)["chests"] == 0
    with app.state.engine.begin() as connection:
        assert connection.execute(select(func.count()).select_from(CampaignCompletion)).scalar_one() == 0
        assert connection.execute(select(func.count()).select_from(GameReward)).scalar_one() == 0
        connection.execute(text("DROP TRIGGER fail_chest"))
    assert attempt(client, game, word, key).json()["campaign"]["current_level"] == 21


@pytest.mark.parametrize("level,length", [(21, 4), (22, 5), (41, 5), (61, 5), (62, 6), (300, 6), (1000000, 6)])
def test_high_levels_and_length_transitions(client, app, level, length):
    set_level(app, level)
    game = start(client, "campaign")
    assert game["length"] == length
    assert attempt(client, game, answer(app, game)).json()["campaign"]["current_level"] == level + 1
    assert len(page(client)["levels"]) == 20


def test_map_is_bounded_private_and_rejects_forged_level(client, app):
    assert page(client)["chapter"] == 1
    assert page(client, 2)["levels"][0]["status"] == "locked"
    for chapter, status in ((0, 422), (-1, 422), (3, 404), (10**12, 404)):
        assert client.get("/api/campaign", params={"chapter": chapter}).status_code == status
    game = start(client, "campaign")
    assert client.post("/api/games", json={"mode": "campaign", "level": 10, "operation_id": str(uuid4())}).status_code == 422
    with TestClient(app, headers=HEADERS) as other:
        assert other.get("/api/campaign").status_code == 401
        assert other.post("/api/auth/register", json={"login": "other", "display_name": "Другой", "password": "password-123"}).status_code == 201
        assert other.get(f"/api/games/{game['id']}").status_code == 404
        assert page(other)["chests"] == 0


def test_campaign_hints_use_word_length_and_reduce_stars(client, app):
    game = start(client, "campaign")
    hinted = hint(client, game).json()
    result = attempt(client, hinted, answer(app, game)).json()
    assert result["reward"] == {"points": 90, "coins": 30, "hints": 1}
    assert result["campaign"]["stars"] == 1


@pytest.mark.parametrize("attempts,hints,stars", [(1, 0, 3), (2, 0, 3), (3, 0, 2), (4, 0, 2), (5, 0, 1), (6, 0, 1), (1, 1, 1)])
def test_stars(attempts, hints, stars):
    assert victory_stars(attempts, hints) == stars


def test_length_distribution_and_difficulty_cap():
    assert Counter(map(level_length, range(21, 41))) == {4: 10, 5: 10}
    assert Counter(map(level_length, range(61, 101))) == {5: 20, 6: 20}
    assert Counter(map(level_length, range(101, 10101))) == {4: 2000, 5: 3500, 6: 4500}
    assert [hard_percent(level) for level in (100, 101, 180, 300, 1000000)] == [0, 10, 20, 35, 35]


def test_migration_preserves_active_games_hints_and_saved_rewards(client, app):
    # Return to the previous release schema, then upgrade with actual saved data.
    with app.state.engine.begin() as connection:
        connection.execute(update(Word).values(enabled_as_answer=Word.canonical_word.in_(["елка", "касса", "ворона"])))
    win = attempt(client, start(client, "4"), "елка").json()
    active = hint(client, start(client, "5")).json()
    win = client.get(f"/api/games/{win['id']}").json()
    config = migration_config()
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0004_economy")
    migrate(app.state.engine)
    migrate(app.state.engine)
    assert client.get(f"/api/games/{win['id']}").json() == win
    assert client.get(f"/api/games/{active['id']}").json() == active
    with app.state.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1


def test_difficulty_distribution_for_every_roll_and_growth_limit(monkeypatch):
    for level, expected in ((1, {1: 100}), (41, {1: 50, 2: 50}), (61, {1: 25, 2: 75}),
                            (101, {1: 25, 2: 65, 3: 10}), (300, {1: 25, 2: 40, 3: 35}),
                            (1000000, {1: 25, 2: 40, 3: 35})):
        distribution = Counter()
        for roll in range(100):
            monkeypatch.setattr("backend.app.campaign_rules.secrets.randbelow", lambda limit, roll=roll: roll)
            distribution[preferred_difficulty(level)] += 1
        assert distribution == expected


def test_recency_relaxes_before_difficulty_and_then_length_pool(client, app, monkeypatch):
    monkeypatch.setattr("backend.app.campaign_service.secrets.choice", lambda words: words[0])
    monkeypatch.setattr("backend.app.campaign_service.preferred_difficulty", lambda level: 1)
    with app.state.engine.begin() as connection:
        connection.execute(update(Word).where(Word.length == 4).values(difficulty=2))
        connection.execute(update(Word).where(Word.canonical_word == "аист").values(difficulty=1))
    # First use the easy word in free play; campaign relaxes recency to keep difficulty.
    with app.state.engine.begin() as connection:
        connection.execute(update(Word).where(Word.length == 4).values(enabled_as_answer=Word.canonical_word == "аист"))
    free = start(client, "4")
    surrender(client, free)
    with app.state.engine.begin() as connection:
        connection.execute(update(Word).where(Word.length == 4).values(enabled_as_answer=True))
    first = start(client, "campaign")
    assert answer(app, first) == "аист"
    surrender(client, first)
    second = start(client, "campaign")
    assert answer(app, second) != "аист"


def test_start_key_cannot_cross_campaign_and_free_play(client):
    key = str(uuid4())
    start(client, "4", key)
    assert client.post("/api/games", json={"mode": "campaign", "operation_id": key}).status_code == 409
