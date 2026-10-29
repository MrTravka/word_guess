"""Preserve completion timestamps with finer precision for ranking ties."""

from alembic import op
import sqlalchemy as sa

revision = "0007_statistics"
down_revision = "0006_chests"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("games", sa.Column("finished_at_ns", sa.Integer(), nullable=True))
    # Old results retain their original second-level precision and ordering.
    op.execute("UPDATE games SET finished_at_ns = finished_at * 1000000000 WHERE finished_at IS NOT NULL")


def downgrade():
    op.execute("ALTER TABLE games DROP COLUMN finished_at_ns")
