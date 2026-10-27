"""Initial dictionary schema; account/game tables come in later stages."""

from alembic import op
import sqlalchemy as sa

revision = "0001_dictionary"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dictionary_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("checksum", sa.String(64), nullable=False, unique=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "words",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_word", sa.String(6), nullable=False, unique=True),
        sa.Column("display_word", sa.String(6), nullable=False),
        sa.Column("length", sa.Integer(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.Column("familiarity", sa.String(20), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("enabled_as_answer", sa.Boolean(), nullable=False),
        sa.Column("enabled_as_guess", sa.Boolean(), nullable=False),
        sa.Column("dictionary_version_id", sa.Integer(), sa.ForeignKey("dictionary_versions.id"), nullable=False),
        sa.CheckConstraint("length IN (4, 5, 6)", name="word_length_allowed"),
        sa.CheckConstraint("length(canonical_word) = length", name="word_length_matches"),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 3 OR difficulty IS NULL", name="word_difficulty"),
    )


def downgrade():
    op.drop_table("words")
    op.drop_table("dictionary_versions")
