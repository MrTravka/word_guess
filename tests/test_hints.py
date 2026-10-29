"""Hint targets, limits, idempotency, inventories and reward penalties."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from backend.app.economy_models import HintUse
from backend.app.economy_rules import ALPHABET
from backend.app.game_models import GameOperation
from backend.app.hint_logic import hint_state, unknown_absent_letters
from backend.app.security import COOKIE
from test_economy import buy, snapshot
from test_games import HEADERS, app, attempt, client, settings, start, surrender


def hint(client, game, kind="random_letter", key=None, position=None):
    body = {"operation_id": key or str(uuid4()), "version": game["version"], "kind": kind}
    if position is not None:
        body["position"] = position
    return client.post(f"/api/games/{game['id']}/hints", json=body)


def test_random_hint_is_saved_without_consuming_attempt_and_retry_is_identical(client):
    game = start(client)
    key = str(uuid4())
    result = hint(client, game, key=key).json()
    assert result["version"] == 1 and result["guesses"] == [] and "answer" not in result
    assert len(result["hints"]["revealed"]) == 1
    position, letter = next(iter(result["hints"]["revealed"].items()))
    assert "касса"[int(position)] == letter
    assert result["economy"]["inventory"]["random_letter"] == 0
    assert result["hints"]["next_win"] == {"points": 112, "coins": 37}
    assert hint(client, game, key=key).json() == result
    assert client.get(f"/api/games/{game['id']}").json() == result


def test_targeted_hint_rejects_known_position_and_preserves_inventory(client):
    assert buy(client, "position_letter").status_code == 200
    game = attempt(client, start(client), "маска").json()
    assert hint(client, game, "position_letter", position=2).status_code == 422
    assert snapshot(client)["inventory"]["position_letter"] == 1
    result = hint(client, game, "position_letter", position=0).json()
    assert result["hints"]["revealed"] == {"0": "к"}
    assert result["keyboard"]["к"] == "correct"
    assert result["economy"]["inventory"]["position_letter"] == 0


def test_last_unknown_position_is_never_opened_or_charged(client):
    game = attempt(client, start(client), "каска").json()
    assert game["hints"]["unknown_positions"] == [3]
    assert hint(client, game).status_code == 422
    assert snapshot(client)["inventory"]["random_letter"] == 1
    assert buy(client, "position_letter").status_code == 200
    assert hint(client, game, "position_letter", position=3).status_code == 422
    assert snapshot(client)["inventory"]["position_letter"] == 1


def test_two_letter_limit_and_one_elimination_limit_and_three_hint_penalty(client):
    assert buy(client, "random_letter").status_code == 200
    assert buy(client, "eliminate").status_code == 200
    game = start(client)
    game = hint(client, game).json()
    game = hint(client, game).json()
    assert len(game["hints"]["revealed"]) == 2
    assert hint(client, game).status_code == 422
    game = hint(client, game, "eliminate").json()
    assert hint(client, game, "eliminate").status_code == 422
    result = attempt(client, game, "касса").json()
    assert result["reward"] == {"points": 63, "coins": 37, "hints": 3}
    assert result["economy"]["coins"] == 102


def test_elimination_marks_only_three_unknown_absent_keys_and_persists(client):
    assert buy(client, "eliminate").status_code == 200
    game = attempt(client, start(client), "маска").json()
    result = hint(client, game, "eliminate").json()
    removed = result["hints"]["uses"][0]["removed"]
    assert len(set(removed)) == 3
    assert not set(removed).intersection("касса" + "маска")
    assert all(result["keyboard"][letter] == "absent" for letter in removed)
    assert client.get(f"/api/games/{game['id']}").json() == result
    assert "elimination_candidates" not in str(result)


def test_less_than_three_valid_elimination_targets_is_unavailable(client, app):
    game = start(client)
    with app.state.engine.connect() as connection:
        internal = {"id": game["id"], "answer": "касса", "status": "active"}
        guesses = [{"word": ALPHABET[:-2], "marks": ["absent"] * len(ALPHABET[:-2])}]
        state = hint_state(connection, internal, guesses, {"eliminate": 1})
    option = next(option for option in state["options"] if option["kind"] == "eliminate")
    assert not option["available"] and "трёх" in option["reason"]
    assert len(unknown_absent_letters("касса", ALPHABET[:-2])) <= 2


def test_invalid_target_shape_and_out_of_range_target_never_spend(client):
    buy(client, "position_letter")
    game = start(client, "4")
    assert hint(client, game, "position_letter", position=5).status_code == 422
    assert hint(client, game, "position_letter").status_code == 422
    assert hint(client, game, "random_letter", position=0).status_code == 422
    assert snapshot(client)["inventory"]["position_letter"] == 1


def test_failed_hint_write_rolls_back_inventory_operation_and_version(client, app):
    game = start(client)
    original = snapshot(client)
    key = str(uuid4())
    with app.state.engine.begin() as connection:
        connection.execute(text("CREATE TRIGGER fail_hint BEFORE INSERT ON hint_uses BEGIN SELECT RAISE(ABORT, 'test'); END"))
    with TestClient(app, headers=HEADERS, raise_server_exceptions=False) as failing:
        failing.cookies.set(COOKIE, client.cookies.get(COOKIE))
        assert hint(failing, game, key=key).status_code == 500
    assert snapshot(client) == original
    assert client.get(f"/api/games/{game['id']}").json() == game
    with app.state.engine.begin() as connection:
        assert connection.execute(select(func.count()).select_from(GameOperation)).scalar_one() == 0
        connection.execute(text("DROP TRIGGER fail_hint"))
    assert hint(client, game, key=key).status_code == 200


def test_parallel_hint_retries_consume_one_and_cannot_reuse_key_for_other_action(app, client):
    game = start(client)
    token, key = client.cookies.get(COOKIE), str(uuid4())
    def use(_):
        with TestClient(app, headers=HEADERS) as tab:
            tab.cookies.set(COOKIE, token)
            return hint(tab, game, key=key)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(use, range(2)))
    assert [result.status_code for result in results] == [200, 200]
    assert results[0].json() == results[1].json()
    assert snapshot(client)["inventory"]["random_letter"] == 0
    assert attempt(client, game, "маска", key).status_code == 409
    assert hint(client, game, "eliminate", key).status_code == 409
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(HintUse)).scalar_one() == 1


def test_hint_guess_contention_cannot_spend_against_stale_game(app, client):
    game = start(client)
    token = client.cookies.get(COOKIE)
    def action(kind):
        with TestClient(app, headers=HEADERS) as tab:
            tab.cookies.set(COOKIE, token)
            return hint(tab, game) if kind == "hint" else attempt(tab, game, "касса")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(action, ["hint", "guess"]))
    assert sorted(result.status_code for result in results) == [200, 409]
    current = client.get(f"/api/games/{game['id']}").json()
    assert current["version"] == 1
    assert snapshot(client)["inventory"]["random_letter"] == (0 if current["status"] == "active" else 1)


def test_completed_and_foreign_games_cannot_consume_hints(client, app):
    game = start(client)
    finished = surrender(client, game).json()
    assert hint(client, finished).status_code == 409
    assert snapshot(client)["inventory"]["random_letter"] == 1
    with TestClient(app, headers=HEADERS) as other:
        other.post("/api/auth/register", json={"login": "other", "display_name": "Другой", "password": "password-123"})
        assert hint(other, game).status_code == 404
        assert snapshot(other)["inventory"]["random_letter"] == 1
