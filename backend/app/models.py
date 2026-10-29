"""Dictionary and account tables; schema changes are managed by Alembic."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DictionaryVersion(Base):
    __tablename__ = "dictionary_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64), unique=True)
    source: Mapped[str] = mapped_column(String(100))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (
        CheckConstraint("length IN (4, 5, 6)", name="word_length_allowed"),
        CheckConstraint("length(canonical_word) = length", name="word_length_matches"),
        CheckConstraint("difficulty BETWEEN 1 AND 3 OR difficulty IS NULL", name="word_difficulty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_word: Mapped[str] = mapped_column(String(6), unique=True)
    display_word: Mapped[str] = mapped_column(String(6))
    length: Mapped[int]
    difficulty: Mapped[int | None]
    familiarity: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(100))
    enabled_as_answer: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled_as_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    dictionary_version_id: Mapped[int] = mapped_column(ForeignKey("dictionary_versions.id"))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(32), unique=True)
    display_name: Mapped[str] = mapped_column(String(40))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[int]


class AccountSession(Base):
    __tablename__ = "sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[int] = mapped_column(index=True)


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (CheckConstraint("theme IN ('system', 'light', 'dark')", name="settings_theme"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    theme: Mapped[str] = mapped_column(String(6), default="system")
