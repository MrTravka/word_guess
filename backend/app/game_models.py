"""Persisted game snapshots and operation keys for SQLite-safe retries."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        CheckConstraint("mode IN ('4', '5', '6')", name="game_mode"),
        CheckConstraint("status IN ('active', 'won', 'lost', 'surrendered')", name="game_status"),
        CheckConstraint("version >= 0", name="game_version"),
        Index("one_active_game", "user_id", "mode", unique=True,
              sqlite_where=text("status = 'active' AND campaign_level IS NULL")),
        Index("one_active_campaign", "user_id", unique=True,
              sqlite_where=text("status = 'active' AND campaign_level IS NOT NULL")),
        CheckConstraint("campaign_level IS NULL OR campaign_level > 0", name="game_campaign_level"),
        Index("games_user_mode_created", "user_id", "mode", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    mode: Mapped[str] = mapped_column(String(1))
    # mode retains the physical word length; this discriminator identifies campaign games.
    campaign_level: Mapped[int | None]
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"))
    answer: Mapped[str] = mapped_column(String(6))
    display_answer: Mapped[str] = mapped_column(String(6))
    rules_version: Mapped[int]
    status: Mapped[str] = mapped_column(String(11))
    version: Mapped[int]
    created_at: Mapped[int]
    finished_at: Mapped[int | None]


class GameStart(Base):
    __tablename__ = "game_starts"
    __table_args__ = (UniqueConstraint("user_id", "operation_key", name="game_start_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    operation_key: Mapped[str] = mapped_column(String(36))
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))


class Guess(Base):
    __tablename__ = "guesses"
    __table_args__ = (
        UniqueConstraint("game_id", "number", name="guess_number"),
        UniqueConstraint("game_id", "word", name="guess_word"),
        CheckConstraint("number BETWEEN 1 AND 6", name="guess_attempt_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    number: Mapped[int]
    word: Mapped[str] = mapped_column(String(6))
    marks: Mapped[list[str]] = mapped_column(JSON)


class GameOperation(Base):
    __tablename__ = "game_operations"
    __table_args__ = (
        UniqueConstraint("game_id", "operation_key", name="game_operation_key"),
        CheckConstraint("kind IN ('guess', 'surrender', 'hint')", name="game_operation_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"))
    operation_key: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(9))
    word: Mapped[str | None] = mapped_column(String(6))
    expected_version: Mapped[int]
    hint_kind: Mapped[str | None] = mapped_column(String(15))
    position: Mapped[int | None]
