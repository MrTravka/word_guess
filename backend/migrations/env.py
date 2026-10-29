"""Migrations reuse the configured engine, including SQLite connection rules."""

from alembic import context

from backend.app.config import Settings
from backend.app.database import create_database
from backend.app.models import Base
from backend.app import game_models  # Register game tables in Alembic metadata.
from backend.app import economy_models  # Register balances and hint tables.
from backend.app import campaign_models  # Register campaign history and chests.
from backend.app import chest_models  # Register saved openings and cosmetics.


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    engine = create_database(Settings())
    try:
        with engine.begin() as connection:
            run(connection)
    finally:
        engine.dispose()
