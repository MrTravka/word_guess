"""Validate, consume and persist hint outcomes exactly once."""

import secrets
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import insert, select, update

from .accounts import Identity
from .economy_models import HintUse, Inventory
from .game_models import Game, GameOperation
from .game_service import owned_game, public_game
from .hint_logic import unknown_absent_letters

router = APIRouter(prefix="/api/games")


class HintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    version: int = Field(ge=0, strict=True)
    kind: Literal["random_letter", "position_letter", "eliminate"]
    position: int | None = Field(default=None, ge=0, le=5, strict=True)

    @model_validator(mode="after")
    def target_only_for_position_hint(self):
        if (self.kind == "position_letter") != (self.position is not None):
            raise ValueError("Only a position hint requires a target")
        return self


def apply_hint(connection, user_id: int, game_id: str, data: HintRequest) -> dict:
    game = owned_game(connection, game_id, user_id)
    previous = connection.execute(select(GameOperation).where(
        GameOperation.game_id == game_id, GameOperation.operation_key == str(data.operation_id),
    )).mappings().first()
    if previous:
        payload = ("hint", data.kind, data.position, data.version)
        if (previous["kind"], previous["hint_kind"], previous["position"], previous["expected_version"]) != payload:
            raise HTTPException(409, "Этот ключ уже использован для другого действия.")
        return public_game(connection, game)
    if game["status"] != "active" or game["version"] != data.version:
        raise HTTPException(409, "Партия изменилась или завершена. Обновите состояние.")
    public = public_game(connection, game)
    state = public["hints"]
    option = next(option for option in state["options"] if option["kind"] == data.kind)
    if not option["available"]:
        raise HTTPException(422, option["reason"])
    position, letter, removed = None, None, []
    if data.kind == "eliminate":
        candidates = unknown_absent_letters(game["answer"], public["keyboard"])
        for _ in range(3):
            selected = secrets.choice(candidates)
            candidates.remove(selected)
            removed.append(selected)
        removed.sort()
    else:
        if data.kind == "position_letter":
            position = data.position
            if position not in state["unknown_positions"]:
                raise HTTPException(422, "Выберите ещё неизвестную позицию.")
        else:
            position = secrets.choice(state["unknown_positions"])
        letter = game["answer"][position]
    spent = connection.execute(update(Inventory).where(
        Inventory.user_id == user_id, Inventory.kind == data.kind, Inventory.quantity > 0,
    ).values(quantity=Inventory.quantity - 1))
    if spent.rowcount != 1:
        raise HTTPException(409, "Подсказка уже потрачена в другом запросе.")
    operation_id = connection.execute(insert(GameOperation).values(
        game_id=game_id, operation_key=str(data.operation_id), kind="hint", word=None,
        expected_version=data.version, hint_kind=data.kind, position=data.position,
    )).inserted_primary_key[0]
    connection.execute(insert(HintUse).values(
        game_id=game_id, operation_id=operation_id, kind=data.kind, position=position, letter=letter, removed=removed,
    ))
    connection.execute(update(Game).where(Game.id == game_id).values(version=game["version"] + 1))
    return public_game(connection, owned_game(connection, game_id, user_id))


@router.post("/{game_id}/hints")
def hint(game_id: UUID, data: HintRequest, request: Request, user: Identity):
    with request.app.state.engine.connect().execution_options(sqlite_immediate=True) as connection, connection.begin():
        return apply_hint(connection, user["id"], str(game_id), data)
