"""SQLite connections and real transactions, including transactional DDL."""

from pathlib import Path
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url

from .config import Settings


def create_database(settings: Settings) -> Engine:
    database = make_url(settings.database_url).database
    Path(database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False, "timeout": settings.sqlite_busy_timeout / 1000},
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection: sqlite3.Connection, _record) -> None:
        # SQLAlchemy controls BEGIN; avoids sqlite3 legacy autocommit for DDL.
        connection.isolation_level = None
        cursor = connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout}")
            cursor.execute("PRAGMA foreign_keys=ON")
            mode = cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode.lower() != "wal":
                raise RuntimeError("SQLite WAL could not be enabled")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def begin_transaction(connection) -> None:
        immediate = connection.get_execution_options().get("sqlite_immediate", False)
        connection.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")

    return engine
