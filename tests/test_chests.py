"""Saved prize integrity, contention, monetary rollback and owned cosmetic selection."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from backend.app.bootstrap import migrate, migration_config
from backend.app.chest_models import ChestOpening, Skin, SkinSelection, UserSkin
from backend.app.chest_rules import PRIZES, roll_prize
from backend.app.economy_models import WalletTransaction
from backend.app.main import create_app
from backend.app.security import COOKIE
from test_campaign import answer, set_level
from test_games import HEADERS, app, attempt, client, settings, start


def grant(client, app, level=10):
    set_level(app, level)
    game = start(client, "campaign")
    result = attempt(client, game, answer(app, game)).json()
    assert result["status"] == "won"
    return result["campaign"]["chest_id"]


@pytest.fixture
def chests(client, app):
    return [grant(client, app, level) for level in (10, 20, 30)]


def open_chest(client, chest, key=None):
    return client.post(f"/api/chests/{chest}/open", json={"operation_id": key or str(uuid4())})


def force(monkeypatch, roll=0, skin=0):
    monkeypatch.setattr("backend.app.chest_rules.secrets.randbelow", lambda limit: roll)
    monkeypatch.setattr("backend.app.chest_service.secrets.choice", lambda skins: skins[skin])


def test_exact_odds_and_all_prizes_on_every_possible_roll(monkeypatch):
    assert sum(prize["weight"] for prize in PRIZES) == 10000
    counts = Counter()
    rarity = Counter()
    for roll in range(10000):
        monkeypatch.setattr("backend.app.chest_rules.secrets.randbelow", lambda limit, roll=roll: roll)
        prize = roll_prize()
        counts[prize["title"]] += 1
        rarity[prize["rarity"]] += 1
    assert list(counts.values()) == [5000, 3000, 1200, 600, 100, 100]
    assert rarity == {"common": 8000, "rare": 1800, "very_rare": 200}
    assert sum(prize["coins"] * prize["weight"] for prize in PRIZES) / 10000 == 84


@pytest.mark.parametrize("roll,coins,kind", [(0, 40, "coins"), (5000, 70, "coins"), (8000, 150, "coins"),
                                          (9200, 250, "coins"), (9800, 0, "skin"), (9900, 1000, "coins")])
def test_all_outcomes_are_saved_and_retries_never_reroll(client, app, chests, monkeypatch, roll, coins, kind):
    before = client.get("/api/inventory").json()
    force(monkeypatch, roll)
    key = str(uuid4())
    response = open_chest(client, chests[0], key)
    assert response.status_code == 200, response.text
    result = response.json()
    prize = result["chest"]["opening"]["result"]["prize"]
    assert prize["kind"] == kind and prize["coins"] == coins
    assert result["economy"]["coins"] == before["coins"] + coins
    assert result["economy"]["points"] == before["points"]
    presentation = result["chest"]["opening"]["result"]
    assert presentation["reel"][presentation["winner_index"]] == prize
    monkeypatch.setattr("backend.app.chest_service.roll_prize", lambda: pytest.fail("Rerolled a saved prize"))
    assert open_chest(client, chests[0], key).json() == result
    assert open_chest(client, chests[0]).json() == result
    assert client.get(f"/api/chests/{chests[0]}").json() == result


def test_duplicate_skin_compensates_once_and_selection_requires_ownership(client, app, chests, monkeypatch, settings):
    assert client.put("/api/collection/selection", json={"skin_id": "linen"}).status_code == 409
    force(monkeypatch, 9800)
    first = open_chest(client, chests[0]).json()
    skin = first["chest"]["opening"]["result"]["prize"]["skin"]["id"]
    assert first["chest"]["opening"]["result"]["prize"]["kind"] == "skin"
    coins = first["economy"]["coins"]
    key = str(uuid4())
    duplicate = open_chest(client, chests[1], key).json()
    assert duplicate["chest"]["opening"]["result"]["prize"]["kind"] == "duplicate"
    assert duplicate["economy"]["coins"] == coins + 350
    assert open_chest(client, chests[1], key).json() == duplicate
    selected = client.put("/api/collection/selection", json={"skin_id": skin}).json()
    assert selected["selected_skin"] == skin
    assert sum(item["owned"] for item in selected["skins"]) == 1
    assert client.put("/api/collection/selection", json={"skin_id": skin}).json() == selected
    with TestClient(create_app(settings), headers=HEADERS) as restored:
        restored.cookies.set(COOKIE, client.cookies.get(COOKIE))
        assert restored.get("/api/collection").json() == selected
        assert restored.get(f"/api/chests/{chests[1]}").json() == duplicate
    assert client.put("/api/collection/selection", json={"skin_id": None}).json()["selected_skin"] is None
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(UserSkin)).scalar_one() == 1
        ledger = connection.execute(select(WalletTransaction.amount).where(WalletTransaction.reason == "chest")).scalars().all()
        assert ledger == [350]


@pytest.mark.parametrize("skin_index", range(6))
def test_each_of_six_skins_is_reachable_and_can_be_selected(client, app, chests, monkeypatch, skin_index):
    force(monkeypatch, 9800, skin_index)
    skin = open_chest(client, chests[0]).json()["chest"]["opening"]["result"]["prize"]["skin"]["id"]
    assert client.put("/api/collection/selection", json={"skin_id": skin}).json()["selected_skin"] == skin
    assert len(client.get("/api/collection").json()["skins"]) == 6


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_openings_only_award_once(client, app, chests, monkeypatch, same_key):
    force(monkeypatch, 9900)
    before = client.get("/api/inventory").json()["coins"]
    token, key = client.cookies.get(COOKIE), str(uuid4())
    def request(index):
        with TestClient(app, headers=HEADERS) as tab:
            tab.cookies.set(COOKIE, token)
            return open_chest(tab, chests[0], key if same_key else str(uuid4()))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(request, range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json()
    assert client.get("/api/inventory").json()["coins"] == before + 1000
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(ChestOpening)).scalar_one() == 1
        assert connection.execute(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.reason == "chest")).scalar_one() == 1


@pytest.mark.parametrize("roll", [0, 9800])
def test_opening_save_failure_rolls_back_money_and_cosmetics(client, app, chests, monkeypatch, roll):
    force(monkeypatch, roll)
    before = client.get("/api/inventory").json()
    with app.state.engine.begin() as connection:
        connection.execute(text("CREATE TRIGGER fail_open BEFORE INSERT ON chest_openings BEGIN SELECT RAISE(ABORT, 'test'); END"))
    key = str(uuid4())
    with TestClient(app, headers=HEADERS, raise_server_exceptions=False) as failing:
        failing.cookies.set(COOKIE, client.cookies.get(COOKIE))
        assert open_chest(failing, chests[0], key).status_code == 500
    assert client.get("/api/inventory").json() == before
    assert client.get(f"/api/chests/{chests[0]}").json()["chest"]["opening"] is None
    assert not any(skin["owned"] for skin in client.get("/api/collection").json()["skins"])
    with app.state.engine.begin() as connection:
        assert connection.execute(select(func.count()).select_from(WalletTransaction).where(WalletTransaction.reason == "chest")).scalar_one() == 0
        connection.execute(text("DROP TRIGGER fail_open"))
    assert open_chest(client, chests[0], key).status_code == 200


def test_ownership_request_validation_and_key_conflicts(client, app, chests):
    key = str(uuid4())
    assert open_chest(client, chests[0], key).status_code == 200
    assert open_chest(client, chests[1], key).status_code == 409
    assert client.post(f"/api/chests/{chests[1]}/open", json={"operation_id": str(uuid4()), "coins": 1000}).status_code == 422
    for path in ("/api/chests?page=0", "/api/chests?state=wrong", "/api/chests/bad-id"):
        assert client.get(path).status_code == 422
    with TestClient(app, headers=HEADERS) as other:
        assert other.get("/api/chests").status_code == 401
        assert other.get("/api/collection").status_code == 401
        assert other.post("/api/auth/register", json={"login": "other", "display_name": "Другой", "password": "password-123"}).status_code == 201
        assert other.get(f"/api/chests/{chests[0]}").status_code == 404
        assert open_chest(other, chests[1]).status_code == 404
        assert other.get("/api/chests").json()["unopened"] == 0
        assert other.put("/api/collection/selection", json={"skin_id": "linen"}).status_code == 409
    with app.state.engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(text("INSERT INTO skin_selection(user_id,skin_id) VALUES (2,'linen')"))


def test_chest_list_moves_openings_to_history_and_has_explicit_odds(client, chests, monkeypatch):
    force(monkeypatch)
    page = client.get("/api/chests").json()
    assert page["unopened"] == 3 and page["opened"] == 0
    assert sum(item["percent"] for item in page["odds"]["prizes"]) == 100
    assert page["odds"]["duplicate_coins"] == 350 and page["odds"]["skin_count"] == 6
    open_chest(client, chests[0])
    assert len(client.get("/api/chests").json()["items"]) == 2
    history = client.get("/api/chests?state=opened").json()
    assert history["unopened"] == 2 and history["opened"] == 1
    assert history["items"][0]["opening"]["result"]["prize"]["coins"] == 40
    assert client.get("/api/chests?page=2").json()["items"] == []


def test_migration_preserves_previously_earned_unopened_chests(client, app, chests):
    config = migration_config()
    before = client.get("/api/inventory").json()
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0005_campaign")
    migrate(app.state.engine)
    migrate(app.state.engine)
    assert client.get("/api/inventory").json() == before
    assert {chest["id"] for chest in client.get("/api/chests").json()["items"]} == set(chests)
    with app.state.engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(Skin)).scalar_one() == 6
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


@pytest.mark.parametrize("roll,coins", [(0, 80), (9800, 350)])
def test_parallel_different_chests_preserve_wallet_and_skin_duplicates(client, app, chests, monkeypatch, roll, coins):
    force(monkeypatch, roll)
    before = client.get("/api/inventory").json()["coins"]
    token = client.cookies.get(COOKIE)
    def request(chest):
        with TestClient(app, headers=HEADERS) as tab:
            tab.cookies.set(COOKIE, token)
            return open_chest(tab, chest)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(request, chests[:2]))
    assert all(response.status_code == 200 for response in responses)
    assert client.get("/api/inventory").json()["coins"] == before + coins
    if roll == 9800:
        kinds = [response.json()["chest"]["opening"]["result"]["prize"]["kind"] for response in responses]
        assert sorted(kinds) == ["duplicate", "skin"]


def test_history_pagination_is_bounded(client, app):
    for level in range(10, 221, 10):
        grant(client, app, level)
    first = client.get("/api/chests").json()
    second = client.get("/api/chests?page=2").json()
    assert first["unopened"] == 22 and first["pages"] == 2
    assert len(first["items"]) == 20 and len(second["items"]) == 2
    assert not ({item["id"] for item in first["items"]} & {item["id"] for item in second["items"]})
