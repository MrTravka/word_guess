"""Environment configuration shared by API, migrations and bootstrap."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "sqlite:///data/runtime/word_guess.db"
    sqlite_busy_timeout: int = Field(default=5000, ge=1, le=60000)
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    vite_port: int = Field(default=5173, ge=1, le=65535)

    @field_validator("database_url")
    @classmethod
    def sqlite_only(cls, value: str) -> str:
        url = make_url(value)
        if url.drivername != "sqlite" or url.host or url.query:
            raise ValueError("DATABASE_URL must be a file-based sqlite:/// URL")
        if not url.database or url.database == ":memory:":
            raise ValueError("DATABASE_URL must point to a persistent SQLite file")
        database = Path(url.database)
        if not database.is_absolute():
            database = ROOT / database
        return url.set(database=str(database.resolve())).render_as_string(hide_password=False)


FRONTEND_DIST = ROOT / "frontend" / "dist"
WORDS_FILE = ROOT / "data" / "words" / "candidates.csv"
