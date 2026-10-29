"""Private chests, transparent odds and account-wide cosmetic selection."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from .accounts import Identity
from .chest_rules import public_odds
from .chest_service import chest_list, collection_state, open_chest, owned_chest, public_chest, select_skin
from .economy_service import wallet_state

router = APIRouter(prefix="/api")


class Opening(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_id: UUID


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skin_id: str | None = Field(max_length=16)


@router.get("/chests")
def list_chests(request: Request, user: Identity, page: Annotated[int, Query(ge=1, le=1000000000)] = 1,
                state: Literal["unopened", "opened"] = "unopened"):
    with request.app.state.engine.connect() as connection:
        return chest_list(connection, user["id"], page, state)


@router.get("/chests/{chest_id}")
def get_chest(chest_id: UUID, request: Request, user: Identity):
    with request.app.state.engine.connect() as connection:
        return {"chest": public_chest(connection, owned_chest(connection, user["id"], str(chest_id))),
                "economy": wallet_state(connection, user["id"]), "odds": public_odds()}


@router.post("/chests/{chest_id}/open")
def opening(chest_id: UUID, data: Opening, request: Request, user: Identity):
    with request.app.state.engine.connect().execution_options(sqlite_immediate=True) as connection, connection.begin():
        return {**open_chest(connection, user["id"], str(chest_id), str(data.operation_id)), "odds": public_odds()}


@router.get("/collection")
def collection(request: Request, user: Identity):
    with request.app.state.engine.connect() as connection:
        return collection_state(connection, user["id"])


@router.put("/collection/selection")
def selection(data: Selection, request: Request, user: Identity):
    with request.app.state.engine.connect().execution_options(sqlite_immediate=True) as connection, connection.begin():
        return select_skin(connection, user["id"], data.skin_id)
