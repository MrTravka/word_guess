"""Add campaign without rebuilding the games table referenced by saved rewards."""

from alembic import op
import sqlalchemy as sa

revision = "0005_campaign"
down_revision = "0004_economy"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite supports a nullable column with an inline CHECK via ALTER ADD COLUMN.
    op.add_column("games", sa.Column("campaign_level", sa.Integer(),
                  sa.CheckConstraint("campaign_level IS NULL OR campaign_level > 0", name="game_campaign_level")))
    op.drop_index("one_active_game", table_name="games")
    op.create_index("one_active_game", "games", ["user_id", "mode"], unique=True,
                    sqlite_where=sa.text("status = 'active' AND campaign_level IS NULL"))
    op.create_index("one_active_campaign", "games", ["user_id"], unique=True,
                    sqlite_where=sa.text("status = 'active' AND campaign_level IS NOT NULL"))
    op.create_table("campaign_progress",
                    sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
                    sa.Column("current_level", sa.Integer(), nullable=False),
                    sa.CheckConstraint("current_level > 0", name="campaign_level_positive"))
    op.create_table("campaign_level_history",
                    sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
                    sa.Column("level", sa.Integer(), nullable=False),
                    sa.Column("cycle", sa.Integer(), nullable=False),
                    sa.Column("word_id", sa.Integer(), sa.ForeignKey("words.id"), nullable=False),
                    sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False, unique=True),
                    sa.UniqueConstraint("user_id", "level", "cycle", "word_id", name="campaign_word_once_per_cycle"),
                    sa.CheckConstraint("level > 0 AND cycle > 0", name="campaign_history_positive"))
    op.create_index("campaign_history_level", "campaign_level_history", ["user_id", "level"])
    op.create_table("campaign_completions",
                    sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
                    sa.Column("level", sa.Integer(), primary_key=True),
                    sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False, unique=True),
                    sa.Column("stars", sa.Integer(), nullable=False),
                    sa.CheckConstraint("level > 0 AND stars BETWEEN 1 AND 3", name="campaign_completion_valid"))
    op.create_table("chests",
                    sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
                    sa.Column("level", sa.Integer(), nullable=False),
                    sa.Column("game_id", sa.String(36), sa.ForeignKey("games.id"), nullable=False, unique=True),
                    sa.Column("created_at", sa.Integer(), nullable=False),
                    sa.UniqueConstraint("user_id", "level", name="chest_per_milestone"),
                    sa.CheckConstraint("level > 0 AND level % 10 = 0", name="chest_milestone"))
    op.create_index("ix_chests_user_id", "chests", ["user_id"])


def downgrade():
    # A downgrade must not silently turn campaign progress into free games.
    if op.get_bind().execute(sa.text("SELECT 1 FROM games WHERE campaign_level IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Campaign games exist; restore a backup to downgrade safely")
    op.drop_table("chests")
    op.drop_table("campaign_completions")
    op.drop_table("campaign_level_history")
    op.drop_table("campaign_progress")
    op.drop_index("one_active_campaign", table_name="games")
    op.drop_index("one_active_game", table_name="games")
    op.create_index("one_active_game", "games", ["user_id", "mode"], unique=True,
                    sqlite_where=sa.text("status = 'active'"))
    # Native DROP COLUMN avoids rebuilding a parent table with foreign keys.
    op.execute("ALTER TABLE games DROP COLUMN campaign_level")
