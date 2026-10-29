"""Authenticated game API. Writes acquire SQLite's lock before reading state."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .accounts import Identity
from .game_models import Game
from .game_service import create_game, mode_condition, mutate_game, owned_game, public_game

router = APIRouter(prefix="/api/games")


class NewGame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["4", "5", "6", "campaign"]
    operation_id: UUID


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID
    version: int = Field(ge=0, strict=True)


class WordAttempt(Action):
    word: str = Field(min_length=1, max_length=32)


@router.get("")
def latest_game(request: Request, user: Identity, mode: Literal["4", "5", "6", "campaign"]):
    with request.app.state.engine.connect() as connection:
        game = connection.execute(select(Game).where(Game.user_id == user["id"], mode_condition(mode)).order_by(
            Game.created_at.desc(), Game.id.desc(),
        ).limit(1)).mappings().first()
        return public_game(connection, game) if game else None


@router.get("/{game_id}")
def get_game(game_id: UUID, request: Request, user: Identity):
    with request.app.state.engine.connect() as connection:
        return public_game(connection, owned_game(connection, str(game_id), user["id"]))


@router.post("")
def start_game(data: NewGame, request: Request, user: Identity):
    with request.app.state.engine.connect().execution_options(sqlite_immediate=True) as connection:
        with connection.begin():
            return create_game(connection, user["id"], data.mode, str(data.operation_id))


@router.post("/{game_id}/guesses")
def guess(game_id: UUID, data: WordAttempt, request: Request, user: Identity):
    with request.app.state.engine.connect().execution_options(sqlite_immediate=True) as connection:
        with connection.begin():
            return mutate_game(connection, user["id"], str(game_id), "guess", data)


@router.post("/{game_id}/surrender")
def surrender(game_id: UUID, data: Action, request: Request, user: Identity):
    with request.app.state.engine.connect().execution_options(sqlite_immediate=True) as connection:
        with connection.begin():
            return mutate_game(connection, user["id"], str(game_id), "surrender", data)
