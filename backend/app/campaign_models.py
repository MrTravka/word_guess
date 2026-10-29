"""Campaign progression, selection cycles, first wins and unopened chests."""

from sqlalchemy import CheckConstraint, ForeignKey, Index, UniqueConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class CampaignProgress(Base):
    __tablename__ = "campaign_progress"
    __table_args__ = (CheckConstraint("current_level > 0", name="campaign_level_positive"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    current_level: Mapped[int]


class CampaignHistory(Base):
    __tablename__ = "campaign_level_history"
    __table_args__ = (
        UniqueConstraint("user_id", "level", "cycle", "word_id", name="campaign_word_once_per_cycle"),
        CheckConstraint("level > 0 AND cycle > 0", name="campaign_history_positive"),
        Index("campaign_history_level", "user_id", "level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    level: Mapped[int]
    cycle: Mapped[int]
    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"))
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), unique=True)


class CampaignCompletion(Base):
    __tablename__ = "campaign_completions"
    __table_args__ = (CheckConstraint("level > 0 AND stars BETWEEN 1 AND 3", name="campaign_completion_valid"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    level: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), unique=True)
    stars: Mapped[int]


class Chest(Base):
    __tablename__ = "chests"
    __table_args__ = (
        UniqueConstraint("user_id", "level", name="chest_per_milestone"),
        CheckConstraint("level > 0 AND level % 10 = 0", name="chest_milestone"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    level: Mapped[int]
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), unique=True)
    created_at: Mapped[int]
