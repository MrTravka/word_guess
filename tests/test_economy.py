"""Reward arithmetic, starter grants, purchases and legacy backfill integrity."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, func, select, text

from backend.app.economy_models import GameReward, Inventory, Wallet, WalletTransaction
from backend.app.economy_rules import reward
from backend.app.economy_service import seed_economy
from backend.app.security import COOKIE
from test_games import HEADERS, app, attempt, client, settings, start, surrender


def snapshot(client):
    response = client.get("/api/inventory")
    assert response.status_code == 200, response.text
    return response.json()


def buy(client, kind, key=None):
    return client.post("/api/shop/purchases", json={"item": kind, "operation_id": key or str(uuid4())})


@pytest.mark.parametrize("length,attempt,hints,expected", [
    (4, 1, 0, {"points": 120, "coins": 30}),
    (5, 3, 0, {"points": 100, "coins": 25}),
    (5, 3, 1, {"points": 75, "coins": 25}),
    (6, 6, 3, {"points": 12, "coins": 7}),
    (4, 6, 10, {"points": 5, "coins": 5}),
])
def test_reward_is_floored_and_hints_only_reduce_points(length, attempt, hints, expected):
    assert reward(length, attempt, hints) == expected


def test_starter_is_atomic_and_never_repeated_by_login_or_seed(client, app):
    expected = {"coins": 150, "inventory": {"random_letter": 1, "position_letter": 0, "eliminate": 0}, "points": {"4": 0, "5": 0, "6": 0, "campaign": 0}}
    assert snapshot(client) == expected
    seed_economy(app.state.engine)
    seed_economy(app.state.engine)
    client.post("/api/auth/login", json={"login": "player", "password": "password-123"})
    assert snapshot(client) == expected
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(WalletTransaction)).scalar_one() == 1


def test_purchase_retry_same_key_spends_once_and_rejects_changed_payload(client):
    key = str(uuid4())
    first = buy(client, "random_letter", key)
    assert first.status_code == 200
    assert first.json()["economy"]["coins"] == 90
    assert first.json()["economy"]["inventory"]["random_letter"] == 2
    assert buy(client, "random_letter", key).json() == first.json()
    assert buy(client, "eliminate", key).status_code == 409
    assert snapshot(client)["coins"] == 90
    assert client.post("/api/shop/purchases", json={"item": "eliminate", "operation_id": str(uuid4()), "price": 0}).status_code == 422


def test_parallel_purchases_cannot_overspend_or_duplicate(app, client):
    token = client.cookies.get(COOKIE)
    def purchase(key):
        with TestClient(app, headers=HEADERS) as tab:
            tab.cookies.set(COOKIE, token)
            return buy(tab, "position_letter", key)
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(purchase, [key, key]))
    assert [result.status_code for result in results] == [200, 200]
    assert snapshot(client)["coins"] == 50
    assert snapshot(client)["inventory"]["position_letter"] == 1
    # A 25-coin remainder must reject every new 100-coin purchase.
    assert buy(client, "eliminate").status_code == 200
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: purchase(str(uuid4())), range(2)))
    assert [result.status_code for result in results] == [409, 409]
    assert snapshot(client)["coins"] == 25


def test_competing_distinct_purchases_allow_only_one_when_balance_is_insufficient(app, client):
    token = client.cookies.get(COOKIE)
    def purchase(_):
        with TestClient(app, headers=HEADERS) as tab:
            tab.cookies.set(COOKIE, token)
            return buy(tab, "position_letter").status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(purchase, range(2))) == [200, 409]
    assert snapshot(client)["coins"] == 50 and snapshot(client)["inventory"]["position_letter"] == 1


def test_failed_inventory_write_rolls_back_purchase_debit_and_ledger(app, client):
    original = snapshot(client)
    with app.state.engine.begin() as connection:
        connection.execute(text("CREATE TRIGGER fail_inventory BEFORE UPDATE ON inventory BEGIN SELECT RAISE(ABORT, 'test'); END"))
    with TestClient(app, headers=HEADERS, raise_server_exceptions=False) as failing:
        failing.cookies.set(COOKIE, client.cookies.get(COOKIE))
        assert buy(failing, "random_letter").status_code == 500
    assert snapshot(client) == original
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(WalletTransaction)).scalar_one() == 1


def test_win_awards_once_and_modes_do_not_mix(client, app):
    game = start(client)
    key = str(uuid4())
    won = attempt(client, game, "касса", key).json()
    assert won["reward"] == {"points": 150, "coins": 37, "hints": 0}
    assert won["economy"]["coins"] == 187
    assert attempt(client, game, "касса", key).json() == won
    assert snapshot(client)["points"] == {"4": 0, "5": 150, "6": 0, "campaign": 0}
    game4 = start(client, "4")
    lost = surrender(client, game4).json()
    assert lost["reward"] == {"points": 0, "coins": 0, "hints": 0}
    assert snapshot(client)["coins"] == 187
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(GameReward)).scalar_one() == 2
        assert connection.execute(select(func.count()).select_from(WalletTransaction)).scalar_one() == 2


def test_reward_failure_rolls_back_winning_guess_and_all_money(app, client):
    game = start(client)
    original = snapshot(client)
    with app.state.engine.begin() as connection:
        connection.execute(text("CREATE TRIGGER fail_reward BEFORE INSERT ON game_rewards BEGIN SELECT RAISE(ABORT, 'test'); END"))
    with TestClient(app, headers=HEADERS, raise_server_exceptions=False) as failing:
        failing.cookies.set(COOKIE, client.cookies.get(COOKIE))
        assert attempt(failing, game, "касса").status_code == 500
    assert client.get(f"/api/games/{game['id']}").json() == game
    assert snapshot(client) == original


def test_two_simultaneous_winning_retries_award_one_reward(app, client):
    game, key, token = start(client), str(uuid4()), client.cookies.get(COOKIE)
    def win(_):
        with TestClient(app, headers=HEADERS) as tab:
            tab.cookies.set(COOKIE, token)
            return attempt(tab, game, "касса", key)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(win, range(2)))
    assert [result.status_code for result in results] == [200, 200]
    assert snapshot(client)["coins"] == 187
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(GameReward)).scalar_one() == 1
        assert connection.execute(select(func.count()).select_from(WalletTransaction)).scalar_one() == 2


def test_legacy_backfill_grants_existing_account_and_saved_wins_once(app, client):
    game = start(client)
    attempt(client, game, "касса")
    # Simulate the pre-economy snapshot, keeping its account/game/guesses.
    with app.state.engine.begin() as connection:
        for model in (WalletTransaction, GameReward, Inventory, Wallet):
            connection.execute(delete(model))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: seed_economy(app.state.engine), range(2)))
    result = snapshot(client)
    assert result["coins"] == 187 and result["inventory"]["random_letter"] == 1
    assert result["points"]["5"] == 150
    seed_economy(app.state.engine)
    assert snapshot(client) == result


def test_wallets_and_inventory_are_private(client, app):
    buy(client, "eliminate")
    with TestClient(app, headers=HEADERS) as other:
        assert other.get("/api/inventory").status_code == 401
        other.post("/api/auth/register", json={"login": "other", "display_name": "Другой", "password": "password-123"})
        assert snapshot(other)["coins"] == 150 and snapshot(other)["inventory"]["eliminate"] == 0
    assert snapshot(client)["coins"] == 125
