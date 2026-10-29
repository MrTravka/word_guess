"""Game snapshots, six guesses and persistent idempotency keys."""

from alembic import op
import sqlalchemy as sa

revision = "0003_games"
down_revision = "0002_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "games",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("mode", sa.String(1), nullable=False),
        sa.Column("word_id", sa.Integer(), sa.ForeignKey("words.id"), nullable=False),
        sa.Column("answer", sa.String(6), nullable=False),
        sa.Column("display_answer", sa.String(6), nullable=False),
        sa.Column("rules_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(11), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("finished_at", sa.Integer(), nullable=True),
        sa.CheckConstraint("mode IN ('4', '5', '6')", name="game_mode"),
        sa.CheckConstraint("status IN ('active', 'won', 'lost', 'surrendered')", name="game_status"),
        sa.CheckConstraint("version >= 0", name="game_version"),
    )
    op.create_index("one_active_game", "games", ["user_id", "mode"], unique=True, sqlite_where=sa.text("status = 'active'"))
    op.create_index("games_user_mode_created", "games", ["user_id", "mode", "created_at"])
    op.create_table(
        "game_starts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("operation_key", sa.String(36), nullable=False),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.UniqueConstraint("user_id", "operation_key", name="game_start_key"),
    )
    op.create_table(
        "guesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("word", sa.String(6), nullable=False),
        sa.Column("marks", sa.JSON(), nullable=False),
        sa.UniqueConstraint("game_id", "number", name="guess_number"),
        sa.UniqueConstraint("game_id", "word", name="guess_word"),
        sa.CheckConstraint("number BETWEEN 1 AND 6", name="guess_attempt_range"),
    )
    op.create_table(
        "game_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("operation_key", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(9), nullable=False),
        sa.Column("word", sa.String(6), nullable=True),
        sa.Column("expected_version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("game_id", "operation_key", name="game_operation_key"),
        sa.CheckConstraint("kind IN ('guess', 'surrender')", name="game_operation_kind"),
    )


def downgrade():
    op.drop_table("game_operations")
    op.drop_table("guesses")
    op.drop_table("game_starts")
    op.drop_index("games_user_mode_created", table_name="games")
    op.drop_index("one_active_game", table_name="games")
    op.drop_table("games")
