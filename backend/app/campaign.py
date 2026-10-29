"""Authenticated, bounded campaign map pages."""

from typing import Annotated

from fastapi import APIRouter, Query, Request

from .accounts import Identity
from .campaign_service import campaign_page

router = APIRouter(prefix="/api/campaign")


@router.get("")
def progress(request: Request, user: Identity, chapter: Annotated[int | None, Query(ge=1)] = None):
    with request.app.state.engine.connect() as connection:
        return campaign_page(connection, user["id"], chapter)
