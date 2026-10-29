"""Saved chest results and owned cosmetics; selection requires ownership in SQLite."""

from sqlalchemy import ForeignKey, ForeignKeyConstraint, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base


class Skin(Base):
    __tablename__ = "skins"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    title: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(160))


class ChestOpening(Base):
    __tablename__ = "chest_openings"
    __table_args__ = (UniqueConstraint("user_id", "operation_key", name="chest_opening_key"),)

    chest_id: Mapped[str] = mapped_column(ForeignKey("chests.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    operation_key: Mapped[str] = mapped_column(String(36))
    result: Mapped[dict] = mapped_column(JSON)
    opened_at: Mapped[int]


class UserSkin(Base):
    __tablename__ = "user_skins"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    skin_id: Mapped[str] = mapped_column(ForeignKey("skins.id"), primary_key=True)
    chest_id: Mapped[str] = mapped_column(ForeignKey("chests.id"), unique=True)


class SkinSelection(Base):
    __tablename__ = "skin_selection"
    __table_args__ = (ForeignKeyConstraint(["user_id", "skin_id"], ["user_skins.user_id", "user_skins.skin_id"]),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    skin_id: Mapped[str] = mapped_column(String(16))
