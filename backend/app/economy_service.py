"""Atomic account grants, purchases and saved rewards. Caller owns the transaction."""

from fastapi import HTTPException
from sqlalchemy import case, func, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .economy_models import GameReward, HintUse, Inventory, Wallet, WalletTransaction
from .economy_rules import CATALOG, START_COINS, START_HINT, reward
from .game_models import Game, Guess
from .models import User
from .campaign_service import complete_campaign


def initialize_account(connection, user_id: int) -> None:
    connection.execute(sqlite_insert(Wallet).values(user_id=user_id, coins=0).on_conflict_do_nothing())
    for kind in CATALOG:
        connection.execute(sqlite_insert(Inventory).values(user_id=user_id, kind=kind, quantity=0).on_conflict_do_nothing())
    granted = connection.execute(select(WalletTransaction.id).where(
        WalletTransaction.user_id == user_id, WalletTransaction.operation_key == "starter",
    )).first()
    if granted:
        return
    connection.execute(update(Wallet).where(Wallet.user_id == user_id).values(coins=Wallet.coins + START_COINS))
    connection.execute(update(Inventory).where(Inventory.user_id == user_id, Inventory.kind == START_HINT).values(quantity=Inventory.quantity + 1))
    connection.execute(insert(WalletTransaction).values(
        user_id=user_id, operation_key="starter", amount=START_COINS, reason="starter", item=None, game_id=None,
    ))


def wallet_state(connection, user_id: int) -> dict:
    coins = connection.execute(select(Wallet.coins).where(Wallet.user_id == user_id)).scalar_one_or_none()
    if coins is None:
        raise HTTPException(503, "Баланс ещё не подготовлен. Требуется запуск bootstrap.")
    inventory = dict(connection.execute(select(Inventory.kind, Inventory.quantity).where(Inventory.user_id == user_id)).all())
    points = {mode: 0 for mode in ("4", "5", "6", "campaign")}
    mode = case((Game.campaign_level.is_not(None), "campaign"), else_=Game.mode)
    points.update(dict(connection.execute(select(mode, func.sum(GameReward.points)).join(
        GameReward, GameReward.game_id == Game.id,
    ).where(Game.user_id == user_id).group_by(mode)).all()))
    return {"coins": coins, "inventory": inventory, "points": points}


def buy_item(connection, user_id: int, item: str, operation_key: str) -> dict:
    key = "purchase:" + operation_key
    previous = connection.execute(select(WalletTransaction).where(
        WalletTransaction.user_id == user_id, WalletTransaction.operation_key == key,
    )).mappings().first()
    if previous:
        if previous["item"] != item:
            raise HTTPException(409, "Этот ключ уже использован для другой покупки.")
        cost = -previous["amount"]
    else:
        cost = CATALOG[item]["price"]
        changed = connection.execute(update(Wallet).where(Wallet.user_id == user_id, Wallet.coins >= cost).values(coins=Wallet.coins - cost))
        if changed.rowcount != 1:
            raise HTTPException(409, "Недостаточно монет для покупки.")
        connection.execute(update(Inventory).where(Inventory.user_id == user_id, Inventory.kind == item).values(quantity=Inventory.quantity + 1))
        connection.execute(insert(WalletTransaction).values(
            user_id=user_id, operation_key=key, amount=-cost, reason="purchase", item=item, game_id=None,
        ))
    return {"economy": wallet_state(connection, user_id), "purchase": {"item": item, "price": cost, "operation_id": operation_key}}


def record_result(connection, game) -> None:
    if game["status"] == "active":
        return
    if connection.execute(select(GameReward.game_id).where(GameReward.game_id == game["id"])).first():
        return
    hints = connection.execute(select(func.count()).select_from(HintUse).where(HintUse.game_id == game["id"])).scalar_one()
    attempts = connection.execute(select(func.count()).select_from(Guess).where(Guess.game_id == game["id"])).scalar_one()
    result = reward(int(game["mode"]), attempts, hints) if game["status"] == "won" else {"points": 0, "coins": 0}
    connection.execute(insert(GameReward).values(game_id=game["id"], hints=hints, **result))
    complete_campaign(connection, game, attempts, hints)
    if result["coins"]:
        connection.execute(update(Wallet).where(Wallet.user_id == game["user_id"]).values(coins=Wallet.coins + result["coins"]))
        connection.execute(insert(WalletTransaction).values(
            user_id=game["user_id"], operation_key="reward:" + game["id"], amount=result["coins"],
            reason="win", item=None, game_id=game["id"],
        ))


def seed_economy(engine) -> None:
    # Each account/result uses a short transaction and can safely be resumed.
    with engine.connect() as connection:
        users = connection.execute(select(User.id)).scalars().all()
        games = connection.execute(select(Game.id).outerjoin(GameReward, GameReward.game_id == Game.id).where(
            Game.status != "active", GameReward.game_id.is_(None),
        )).scalars().all()
    for user_id in users:
        with engine.connect().execution_options(sqlite_immediate=True) as connection, connection.begin():
            initialize_account(connection, user_id)
    for game_id in games:
        with engine.connect().execution_options(sqlite_immediate=True) as connection, connection.begin():
            game = connection.execute(select(Game).where(Game.id == game_id)).mappings().one()
            record_result(connection, game)
