"""Audio remains opt-in when upgrading an existing account."""

from alembic import op
import sqlalchemy as sa

revision = "0008_audio"
down_revision = "0007_statistics"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("music_enabled", "sounds_enabled"):
        op.add_column("user_settings", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.text("0")))
    for name, value in (("music_volume", "25"), ("sounds_volume", "35")):
        op.add_column("user_settings", sa.Column(name, sa.Integer(),
                      sa.CheckConstraint(f"{name} BETWEEN 0 AND 100", name=f"settings_{name}"),
                      nullable=False, server_default=sa.text(value)))


def downgrade():
    for name in ("sounds_volume", "music_volume", "sounds_enabled", "music_enabled"):
        op.execute(f"ALTER TABLE user_settings DROP COLUMN {name}")
