"""Private wallet/inventory reads and idempotent single-item purchases."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from .accounts import Identity
from .economy_rules import CATALOG
from .economy_service import buy_item, wallet_state

router = APIRouter(prefix="/api")


class Purchase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item: Literal["random_letter", "position_letter", "eliminate"]
    operation_id: UUID


@router.get("/inventory")
def inventory(request: Request, user: Identity):
    with request.app.state.engine.connect() as connection:
        return wallet_state(connection, user["id"])


@router.get("/shop")
def shop(request: Request, user: Identity):
    with request.app.state.engine.connect() as connection:
        return {"catalog": [{"id": kind, **item} for kind, item in CATALOG.items()], "economy": wallet_state(connection, user["id"])}


@router.post("/shop/purchases")
def purchase(data: Purchase, request: Request, user: Identity):
    with request.app.state.engine.connect().execution_options(sqlite_immediate=True) as connection, connection.begin():
        return buy_item(connection, user["id"], data.item, str(data.operation_id))
