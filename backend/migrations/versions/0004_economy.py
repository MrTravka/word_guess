"""Economy ledger, one result per game and persistent hint outcomes."""

from alembic import op
import sqlalchemy as sa

revision = "0004_economy"
down_revision = "0003_games"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("game_operations") as batch:
        batch.drop_constraint("game_operation_kind", type_="check")
        batch.create_check_constraint("game_operation_kind", "kind IN ('guess', 'surrender', 'hint')")
        batch.add_column(sa.Column("hint_kind", sa.String(15), nullable=True))
        batch.add_column(sa.Column("position", sa.Integer(), nullable=True))
    op.create_table(
        "wallets", sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.CheckConstraint("coins >= 0", name="wallet_nonnegative"),
    )
    op.create_table(
        "inventory", sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("kind", sa.String(15), primary_key=True), sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("kind IN ('random_letter', 'position_letter', 'eliminate')", name="inventory_kind"),
        sa.CheckConstraint("quantity >= 0", name="inventory_nonnegative"),
    )
    op.create_table(
        "wallet_transactions", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operation_key", sa.String(80), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False), sa.Column("reason", sa.String(8), nullable=False),
        sa.Column("item", sa.String(15), nullable=True),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=True, unique=True),
        sa.UniqueConstraint("user_id", "operation_key", name="wallet_operation_key"),
        sa.CheckConstraint("amount != 0", name="wallet_transaction_nonzero"),
        sa.CheckConstraint("reason IN ('starter', 'purchase', 'win')", name="wallet_transaction_reason"),
    )
    op.create_index("ix_wallet_transactions_user_id", "wallet_transactions", ["user_id"])
    op.create_table(
        "game_rewards", sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), primary_key=True),
        sa.Column("points", sa.Integer(), nullable=False), sa.Column("coins", sa.Integer(), nullable=False),
        sa.Column("hints", sa.Integer(), nullable=False),
        sa.CheckConstraint("points >= 0 AND coins >= 0 AND hints >= 0", name="reward_nonnegative"),
    )
    op.create_table(
        "hint_uses", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("operation_id", sa.Integer(), sa.ForeignKey("game_operations.id"), nullable=False, unique=True),
        sa.Column("kind", sa.String(15), nullable=False), sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("letter", sa.String(1), nullable=True), sa.Column("removed", sa.JSON(), nullable=False),
        sa.CheckConstraint("kind IN ('random_letter', 'position_letter', 'eliminate')", name="hint_kind"),
        sa.UniqueConstraint("game_id", "position", name="hint_position_once"),
    )
    op.create_index("ix_hint_uses_game_id", "hint_uses", ["game_id"])


def downgrade():
    op.drop_index("ix_hint_uses_game_id", table_name="hint_uses")
    op.drop_table("hint_uses")
    op.drop_table("game_rewards")
    op.drop_index("ix_wallet_transactions_user_id", table_name="wallet_transactions")
    op.drop_table("wallet_transactions")
    op.drop_table("inventory")
    op.drop_table("wallets")
    with op.batch_alter_table("game_operations") as batch:
        batch.drop_constraint("game_operation_kind", type_="check")
        batch.create_check_constraint("game_operation_kind", "kind IN ('guess', 'surrender')")
        batch.drop_column("hint_kind")
        batch.drop_column("position")
