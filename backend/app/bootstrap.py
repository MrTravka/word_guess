"""Validate content, migrate, then seed. Any failure stops startup."""

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

from .config import ROOT, Settings
from .database import create_database
from .seed import seed_words
from .economy_service import seed_economy

def migration_config() -> Config:
    return Config(str(ROOT / "backend" / "alembic.ini"))


def migration_head() -> str:
    return ScriptDirectory.from_config(migration_config()).get_current_head()


def migrate(engine: Engine) -> None:
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def bootstrap(settings: Settings | None = None) -> None:
    # Use the same offline content checker used by the research tools.
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from verify_content import verify

    verify(require_target=True)
    engine = create_database(settings or Settings())
    try:
        migrate(engine)
        imported = seed_words(engine)
        seed_economy(engine)
        print(f"Database ready; imported {imported} dictionary rows", flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    bootstrap()
