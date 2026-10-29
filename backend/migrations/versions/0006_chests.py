"""Persistent openings and six cosmetics; existing unopened chests are preserved."""

from alembic import op
import sqlalchemy as sa

revision = "0006_chests"
down_revision = "0005_campaign"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("skins",
                    sa.Column("id", sa.String(16), primary_key=True),
                    sa.Column("title", sa.String(40), nullable=False),
                    sa.Column("description", sa.String(160), nullable=False))
    skins = sa.table("skins", sa.column("id", sa.String), sa.column("title", sa.String), sa.column("description", sa.String))
    op.bulk_insert(skins, [
        {"id": "linen", "title": "Лён", "description": "Мягкая фактура и двойные рамки клеток."},
        {"id": "grove", "title": "Лесная тропа", "description": "Спокойный фон и округлые клетки."},
        {"id": "orbit", "title": "Орбиты", "description": "Лёгкая сетка и круглые клетки."},
        {"id": "mosaic", "title": "Мозаика", "description": "Геометрический фон и строгие углы."},
        {"id": "contour", "title": "Контур", "description": "Тонкая штриховка и выразительные рамки."},
        {"id": "nightfall", "title": "Звёздная ночь", "description": "Точки созвездий и мягкие тени."},
    ])
    op.create_table("chest_openings",
                    sa.Column("chest_id", sa.String(36), sa.ForeignKey("chests.id"), primary_key=True),
                    sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
                    sa.Column("operation_key", sa.String(36), nullable=False),
                    sa.Column("result", sa.JSON(), nullable=False),
                    sa.Column("opened_at", sa.Integer(), nullable=False),
                    sa.UniqueConstraint("user_id", "operation_key", name="chest_opening_key"))
    op.create_index("ix_chest_openings_user_id", "chest_openings", ["user_id"])
    op.create_table("user_skins",
                    sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
                    sa.Column("skin_id", sa.String(16), sa.ForeignKey("skins.id"), primary_key=True),
                    sa.Column("chest_id", sa.String(36), sa.ForeignKey("chests.id"), nullable=False, unique=True))
    op.create_table("skin_selection",
                    sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
                    sa.Column("skin_id", sa.String(16), nullable=False),
                    sa.ForeignKeyConstraint(["user_id", "skin_id"], ["user_skins.user_id", "user_skins.skin_id"]))
    with op.batch_alter_table("wallet_transactions") as batch:
        batch.drop_constraint("wallet_transaction_reason", type_="check")
        batch.create_check_constraint("wallet_transaction_reason", "reason IN ('starter', 'purchase', 'win', 'chest')")
        batch.add_column(sa.Column("chest_id", sa.String(36), nullable=True))
        batch.create_foreign_key("wallet_chest", "chests", ["chest_id"], ["id"])
        batch.create_unique_constraint("wallet_chest_once", ["chest_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM chest_openings LIMIT 1")).first():
        raise RuntimeError("Opened chests exist; restore a backup to downgrade safely")
    with op.batch_alter_table("wallet_transactions") as batch:
        batch.drop_constraint("wallet_chest", type_="foreignkey")
        batch.drop_constraint("wallet_chest_once", type_="unique")
        batch.drop_column("chest_id")
        batch.drop_constraint("wallet_transaction_reason", type_="check")
        batch.create_check_constraint("wallet_transaction_reason", "reason IN ('starter', 'purchase', 'win')")
    op.drop_table("skin_selection")
    op.drop_table("user_skins")
    op.drop_table("chest_openings")
    op.drop_table("skins")
