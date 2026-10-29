"""Checked balances, a monetary ledger, saved results and consumed hints."""

from sqlalchemy import CheckConstraint, ForeignKey, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .models import Base

KINDS_CHECK = "kind IN ('random_letter', 'position_letter', 'eliminate')"


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (CheckConstraint("coins >= 0", name="wallet_nonnegative"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    coins: Mapped[int]


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (CheckConstraint(KINDS_CHECK, name="inventory_kind"),
                      CheckConstraint("quantity >= 0", name="inventory_nonnegative"))

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(15), primary_key=True)
    quantity: Mapped[int]


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    __table_args__ = (
        UniqueConstraint("user_id", "operation_key", name="wallet_operation_key"),
        CheckConstraint("amount != 0", name="wallet_transaction_nonzero"),
        CheckConstraint("reason IN ('starter', 'purchase', 'win', 'chest')", name="wallet_transaction_reason"),
        UniqueConstraint("chest_id", name="wallet_chest_once"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    operation_key: Mapped[str] = mapped_column(String(80))
    amount: Mapped[int]
    reason: Mapped[str] = mapped_column(String(8))
    item: Mapped[str | None] = mapped_column(String(15))
    game_id: Mapped[str | None] = mapped_column(ForeignKey("games.id"), unique=True)
    chest_id: Mapped[str | None] = mapped_column(ForeignKey("chests.id", name="wallet_chest"))


class GameReward(Base):
    __tablename__ = "game_rewards"
    __table_args__ = (CheckConstraint("points >= 0 AND coins >= 0 AND hints >= 0", name="reward_nonnegative"),)

    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), primary_key=True)
    points: Mapped[int]
    coins: Mapped[int]
    hints: Mapped[int]


class HintUse(Base):
    __tablename__ = "hint_uses"
    __table_args__ = (CheckConstraint(KINDS_CHECK, name="hint_kind"),
                      UniqueConstraint("game_id", "position", name="hint_position_once"))

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("game_operations.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(15))
    position: Mapped[int | None]
    letter: Mapped[str | None] = mapped_column(String(1))
    removed: Mapped[list[str]] = mapped_column(JSON)
