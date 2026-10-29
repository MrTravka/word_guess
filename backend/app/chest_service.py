"""SQLite-safe chest openings. Award and immutable presentation commit together."""

import secrets
import time

from fastapi import HTTPException
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .campaign_models import Chest
from .chest_models import ChestOpening, Skin, SkinSelection, UserSkin
from .chest_rules import DUPLICATE_COINS, presentation, public_odds, roll_prize
from .economy_models import Wallet, WalletTransaction
from .economy_service import wallet_state


def owned_chest(connection, user_id: int, chest_id: str):
    chest = connection.execute(select(Chest).where(Chest.id == chest_id, Chest.user_id == user_id)).mappings().first()
    if chest is None:
        raise HTTPException(404, "Сундук не найден.")
    return chest


def public_chest(connection, chest) -> dict:
    opening = connection.execute(select(ChestOpening.operation_key, ChestOpening.result, ChestOpening.opened_at).where(
        ChestOpening.chest_id == chest["id"],
    )).mappings().first()
    return {"id": chest["id"], "level": chest["level"], "created_at": chest["created_at"],
            "opening": dict(opening) if opening else None}


def chest_list(connection, user_id: int, page: int, state: str) -> dict:
    opened = select(ChestOpening.chest_id).where(ChestOpening.user_id == user_id)
    opened_count = connection.execute(select(func.count()).select_from(ChestOpening).where(
        ChestOpening.user_id == user_id,
    )).scalar_one()
    total = connection.execute(select(func.count()).select_from(Chest).where(Chest.user_id == user_id)).scalar_one()
    condition = Chest.id.in_(opened) if state == "opened" else Chest.id.not_in(opened)
    count = opened_count if state == "opened" else total - opened_count
    rows = connection.execute(select(Chest).where(Chest.user_id == user_id, condition).order_by(
        Chest.level.desc(),
    ).offset((page - 1) * 20).limit(20)).mappings()
    return {"items": [public_chest(connection, row) for row in rows], "page": page,
            "pages": max(1, (count + 19) // 20), "unopened": total - opened_count, "opened": opened_count,
            "odds": public_odds()}


def open_chest(connection, user_id: int, chest_id: str, operation_key: str) -> dict:
    chest = owned_chest(connection, user_id, chest_id)
    used = connection.execute(select(ChestOpening.chest_id).where(
        ChestOpening.user_id == user_id, ChestOpening.operation_key == operation_key,
    )).scalar_one_or_none()
    if used is not None and used != chest_id:
        raise HTTPException(409, "Этот ключ уже использован для другого сундука.")
    if connection.execute(select(ChestOpening.chest_id).where(ChestOpening.chest_id == chest_id)).first():
        return {"chest": public_chest(connection, chest), "economy": wallet_state(connection, user_id)}
    prize = roll_prize()
    if prize["kind"] == "skin":
        skins = connection.execute(select(Skin).order_by(Skin.id)).mappings().all()
        if len(skins) != 6:
            raise HTTPException(503, "Коллекция временно недоступна.")
        skin = dict(secrets.choice(skins))
        prize["skin"] = skin
        duplicate = connection.execute(select(UserSkin.skin_id).where(
            UserSkin.user_id == user_id, UserSkin.skin_id == skin["id"],
        )).first()
        if duplicate:
            prize.update(kind="duplicate", coins=DUPLICATE_COINS, title=f"Повтор: {skin['title']} · {DUPLICATE_COINS} монет")
        else:
            prize["title"] = skin["title"]
            connection.execute(insert(UserSkin).values(user_id=user_id, skin_id=skin["id"], chest_id=chest_id))
    if prize["coins"]:
        connection.execute(update(Wallet).where(Wallet.user_id == user_id).values(coins=Wallet.coins + prize["coins"]))
        connection.execute(insert(WalletTransaction).values(
            user_id=user_id, operation_key="chest:" + operation_key, reason="chest", amount=prize["coins"],
            item=None, game_id=None, chest_id=chest_id,
        ))
    connection.execute(insert(ChestOpening).values(
        chest_id=chest_id, user_id=user_id, operation_key=operation_key,
        result=presentation(prize), opened_at=int(time.time()),
    ))
    return {"chest": public_chest(connection, chest), "economy": wallet_state(connection, user_id)}


def collection_state(connection, user_id: int) -> dict:
    owned = set(connection.execute(select(UserSkin.skin_id).where(UserSkin.user_id == user_id)).scalars())
    selected = connection.execute(select(SkinSelection.skin_id).where(SkinSelection.user_id == user_id)).scalar_one_or_none()
    skins = connection.execute(select(Skin).order_by(Skin.id)).mappings()
    return {"selected_skin": selected, "skins": [{**skin, "owned": skin["id"] in owned} for skin in skins]}


def select_skin(connection, user_id: int, skin_id: str | None) -> dict:
    if skin_id is None:
        connection.execute(delete(SkinSelection).where(SkinSelection.user_id == user_id))
    else:
        owned = connection.execute(select(UserSkin.skin_id).where(
            UserSkin.user_id == user_id, UserSkin.skin_id == skin_id,
        )).first()
        if not owned:
            raise HTTPException(409, "Этот скин ещё не получен.")
        connection.execute(sqlite_insert(SkinSelection).values(user_id=user_id, skin_id=skin_id).on_conflict_do_update(
            index_elements=[SkinSelection.user_id], set_={"skin_id": skin_id},
        ))
    return collection_state(connection, user_id)
