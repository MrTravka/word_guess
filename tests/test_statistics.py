"""Real history-derived ratings: ties, mode isolation, private metrics and retries."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, text, update

from backend.app.bootstrap import migrate, migration_config
from backend.app.economy_service import seed_economy
from backend.app.game_models import Game
from backend.app.main import create_app
from backend.app.security import COOKIE
from test_games import HEADERS, WORDS, app, attempt, client, settings, start, surrender
from test_hints import hint


def stats(client, mode="5"):
    response = client.get("/api/profile/stats", params={"mode": mode})
    assert response.status_code == 200, response.text
    return response.json()


def board(client, mode="5", page=1):
    response = client.get("/api/leaderboards", params={"mode": mode, "page": page})
    assert response.status_code == 200, response.text
    return response.json()


def win(client, mode="5", attempts=1, with_hint=False):
    game = start(client, mode)
    if with_hint:
        game = hint(client, game).json()
    length = str(game["length"])
    for word in WORDS[length][1:attempts]:
        game = attempt(client, game, word).json()
    response = attempt(client, game, WORDS[length][0])
    assert response.status_code == 200, response.text
    return response.json()


def register(client, login):
    response = client.post("/api/auth/register", json={"login": login, "display_name": login, "password": "password-123"})
    assert response.status_code == 201, response.text


def test_empty_and_active_games_do_not_count(client):
    expected = {"mode": "5", "games": 0, "wins": 0, "losses": 0, "surrendered": 0, "points": 0,
                "win_rate": 0, "average_attempts": None, "best_streak": 0, "current_level": None,
                "attempt_distribution": [{"attempt": index, "wins": 0} for index in range(1, 7)]}
    assert stats(client) == expected
    game = start(client)
    attempt(client, game, "маска")
    assert stats(client) == expected
    result = board(client)
    assert result["entries"] == [] and result["self"]["rank"] is None
    assert result["self_page"] is None and result["total"] == 0
    assert result["statistics"] == expected


def test_wins_losses_surrenders_average_distribution_and_streak(client):
    win(client, attempts=1)
    win(client, attempts=3)
    failed = start(client)
    for word in WORDS["5"][1:7]:
        failed = attempt(client, failed, word).json()
    assert failed["status"] == "lost"
    for attempts in (2, 4, 6):
        win(client, attempts=attempts)
    surrender(client, start(client))
    win(client, attempts=5)
    # A new unfinished game neither interrupts the completed sequence nor adds attempts.
    start(client)
    result = stats(client)
    assert result["games"] == 8 and result["wins"] == 6 and result["losses"] == 2
    assert result["surrendered"] == 1 and result["win_rate"] == 75
    assert result["average_attempts"] == 3.5 and result["best_streak"] == 3
    assert result["attempt_distribution"] == [{"attempt": index, "wins": 1} for index in range(1, 7)]
    assert result["points"] == sum((150, 100, 125, 75, 25, 50))
    assert result["points"] == client.get("/api/inventory").json()["points"]["5"]


def test_all_four_modes_use_saved_rewards_and_keep_campaign_separate(client):
    rewards = {mode: win(client, mode)["reward"]["points"] for mode in ("4", "5", "6", "campaign")}
    for mode, points in rewards.items():
        result = board(client, mode)
        assert result["self"]["points"] == points
        assert result["statistics"]["games"] == result["self"]["wins"] == 1
        assert result["self"]["current_level"] == (2 if mode == "campaign" else None)
        assert result["statistics"] == stats(client, mode)
    assert rewards == client.get("/api/inventory").json()["points"]
    # Spending currency does not change points or rank.
    before = board(client)
    client.post("/api/shop/purchases", json={"item": "eliminate", "operation_id": str(uuid4())})
    assert board(client) == before


def test_hint_penalty_is_not_recomputed_or_lost(client):
    game = win(client, with_hint=True)
    assert game["reward"]["points"] == 112
    assert stats(client)["points"] == board(client)["self"]["points"] == 112
    assert stats(client)["attempt_distribution"][0]["wins"] == 1


def test_points_then_wins_then_earlier_result_resolve_ties(client, app):
    # Two late-attempt wins give 150 points and outrank one first-attempt win.
    win(client, attempts=3)
    win(client, attempts=5)
    with TestClient(app, headers=HEADERS) as other:
        register(other, "other")
        win(other)
        assert [row["display_name"] for row in board(other)["entries"]] == ["Игрок", "other"]
    # A later loss never postpones achievement of the accumulated points.
    before = board(client)["self"]["rank"]
    surrender(client, start(client))
    assert board(client)["self"]["rank"] == before


def test_completion_order_wins_over_registration_and_start_order(client, app):
    # User 1 starts first, user 2 finishes first; registration/start order must not win.
    earlier_start = start(client)
    with TestClient(app, headers=HEADERS) as other:
        register(other, "other")
        win(other)
        assert attempt(client, earlier_start, "касса").status_code == 200
        result = board(client)
        assert [row["display_name"] for row in result["entries"]] == ["other", "Игрок"]
        assert result["self"]["rank"] == 2
        surrender(other, start(other))
        assert board(client)["self"]["rank"] == 2
    with app.state.engine.begin() as connection:
        games = connection.execute(select(Game.finished_at, Game.finished_at_ns).where(Game.status == "won")).all()
        assert all(game.finished_at_ns // 1000000000 == game.finished_at for game in games)
        # Controlled completions within one second preserve the earlier winner.
        connection.execute(update(Game).where(Game.user_id == 2, Game.status == "won").values(finished_at=100, finished_at_ns=100000000001))
        connection.execute(update(Game).where(Game.user_id == 1).values(finished_at=100, finished_at_ns=100000000002))
    assert board(client)["self"]["rank"] == 2
    with app.state.engine.begin() as connection:
        # Exactly equal historical timestamps still have stable, unique places.
        connection.execute(update(Game).values(finished_at_ns=1000000000))
    assert [row["rank"] for row in board(client)["entries"]] == [1, 2]
    assert board(client)["self"]["rank"] == 1


def test_own_place_outside_top_page_and_pagination(client, app):
    for index in range(22):
        with TestClient(app, headers=HEADERS) as other:
            register(other, f"player_{index:02}")
            win(other)
    win(client)
    first, second = board(client), board(client, page=2)
    assert first["total"] == 23 and first["pages"] == 2 and len(first["entries"]) == 20
    assert first["self"]["rank"] == 23 and first["self_page"] == 2
    assert not any(row["is_self"] for row in first["entries"])
    assert [row["rank"] for row in second["entries"]] == [21, 22, 23]
    assert second["entries"][-1]["is_self"]
    assert {row["rank"] for row in first["entries"]}.isdisjoint(row["rank"] for row in second["entries"])
    assert client.get("/api/leaderboards?page=3").status_code == 404


def test_only_losses_have_statistics_and_no_leaderboard_place(client):
    surrender(client, start(client))
    result = board(client)
    assert result["self"]["rank"] is None and result["total"] == 0
    assert result["statistics"]["losses"] == 1
    assert result["statistics"]["average_attempts"] is None


def test_concurrent_winning_retries_leave_one_result_and_no_partial_statistics(client, app):
    game, key, token = start(client), str(uuid4()), client.cookies.get(COOKIE)
    def request(index):
        with TestClient(app, headers=HEADERS) as tab:
            tab.cookies.set(COOKIE, token)
            return attempt(tab, game, "касса", key) if index < 2 else tab.get("/api/leaderboards")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(request, range(3)))
    assert all(response.status_code == 200 for response in results)
    during = results[2].json()
    assert during["self"]["points"] == during["statistics"]["points"]
    assert during["self"]["wins"] == during["statistics"]["wins"]
    after = board(client)
    assert after["statistics"]["games"] == after["self"]["wins"] == 1
    assert after["self"]["points"] == 150
    assert attempt(client, game, "касса", key).status_code == 200
    assert board(client) == after


def test_api_privacy_and_read_only_validation(client, app):
    game = start(client)
    win(client, "4")
    encoded = client.get("/api/leaderboards?mode=4").text
    for forbidden in (game["id"], "answer", "word_id", "password", "login", "session", "operation_key"):
        assert forbidden not in encoded
    with TestClient(app, headers=HEADERS) as other:
        assert other.get("/api/leaderboards").status_code == 401
        assert other.get("/api/profile/stats").status_code == 401
        register(other, "other")
        assert stats(other, "4")["games"] == 0
        assert board(other, "4")["self"]["rank"] is None
        assert board(other, "4")["entries"][0]["display_name"] == "Игрок"
    for query in ("mode=7", "mode=4&page=0", "mode=5&page=1.5", "mode=5&page=1000000001"):
        assert client.get(f"/api/leaderboards?{query}").status_code == 422
    assert client.get("/api/profile/stats?mode=7").status_code == 422
    assert client.post("/api/leaderboards", json={"points": 999999}).status_code == 405
    assert client.get("/api/leaderboards").headers["cache-control"] == "no-store"


def test_migration_and_restart_preserve_old_results_and_backfill_order(client, app, settings):
    won = win(client)
    active = start(client, "6")
    before = board(client)
    config = migration_config()
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0006_chests")
    migrate(app.state.engine)
    migrate(app.state.engine)
    seed_economy(app.state.engine)
    assert board(client) == before
    with app.state.engine.connect() as connection:
        completed = connection.execute(select(Game.finished_at, Game.finished_at_ns).where(Game.id == won["id"])).one()
        assert completed.finished_at_ns == completed.finished_at * 1000000000
        assert connection.execute(select(Game.finished_at_ns).where(Game.id == active["id"])).scalar_one() is None
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
    with TestClient(create_app(settings), headers=HEADERS) as restored:
        restored.cookies.set(COOKIE, client.cookies.get(COOKIE))
        assert board(restored) == before
