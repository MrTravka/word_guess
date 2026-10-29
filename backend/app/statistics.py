"""Authenticated all-time leaderboards and the current player's private statistics."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from .accounts import Identity
from .statistics_service import leaderboard, personal_statistics

router = APIRouter(prefix="/api")
Mode = Literal["4", "5", "6", "campaign"]


@router.get("/leaderboards")
def rankings(request: Request, user: Identity, mode: Mode = "5", page: Annotated[int, Query(ge=1, le=1000000000)] = 1):
    with request.app.state.engine.connect() as connection:
        return leaderboard(connection, user, mode, page)


@router.get("/profile/stats")
def statistics(request: Request, user: Identity, mode: Mode = "5"):
    with request.app.state.engine.connect() as connection:
        return personal_statistics(connection, user["id"], mode)
