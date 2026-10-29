"""Independent audio preferences; theme API stays compatible with older clients."""

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import select, update

from .accounts import Identity
from .models import UserSettings

router = APIRouter(prefix="/api/settings/audio")


class AudioPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    music_enabled: StrictBool
    sounds_enabled: StrictBool
    music_volume: int = Field(ge=0, le=100, strict=True)
    sounds_volume: int = Field(ge=0, le=100, strict=True)


@router.get("")
def audio_preferences(request: Request, user: Identity):
    with request.app.state.engine.connect() as connection:
        return dict(connection.execute(select(
            UserSettings.music_enabled, UserSettings.sounds_enabled,
            UserSettings.music_volume, UserSettings.sounds_volume,
        ).where(UserSettings.user_id == user["id"])).mappings().one())


@router.put("")
def save_audio(data: AudioPreferences, request: Request, user: Identity):
    with request.app.state.engine.begin() as connection:
        connection.execute(update(UserSettings).where(UserSettings.user_id == user["id"]).values(**data.model_dump()))
    return data
