"""Consistent SQLite backups and non-destructive restore into a new file."""

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from .bootstrap import migration_config
from .config import Settings


def validate(connection: sqlite3.Connection) -> str:
    if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
        raise ValueError("SQLite integrity check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise ValueError("SQLite foreign key check failed")
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"alembic_version", "words", "dictionary_versions"} <= tables:
        raise ValueError("This is not a word_guess database")
    revisions = connection.execute("SELECT version_num FROM alembic_version").fetchall()
    known = {item.revision for item in ScriptDirectory.from_config(migration_config()).walk_revisions()}
    if len(revisions) != 1 or revisions[0][0] not in known:
        raise ValueError("Unknown database schema; use a compatible application version")
    return revisions[0][0]


def copy_database(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if not source.is_file():
        raise ValueError("Source database does not exist")
    if source == output:
        raise ValueError("Source and output must be different files")
    if any(Path(str(output) + suffix).exists() for suffix in ("", "-wal", "-shm", "-journal")):
        raise FileExistsError("Output or its SQLite sidecars already exist; choose a new path")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".word-guess-backup-", suffix=".db", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary)
    deadline = time.monotonic() + 60

    def progress(_status, _remaining, _total):
        if time.monotonic() > deadline:
            raise TimeoutError("Backup timed out; retry when database activity is lower")

    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=5)) as original:
            # Validate only the completed copy: concurrent commits may change the source.
            with closing(sqlite3.connect(temporary, timeout=5)) as copied:
                original.backup(copied, pages=256, progress=progress, sleep=0.05)
                copied.execute("PRAGMA journal_mode=DELETE")
                revision = validate(copied)
        with temporary.open("rb+") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            os.fsync(stream.fileno())
        # An atomic hard link refuses an existing destination on Windows and Linux.
        # Temporary file and output are on the same local filesystem.
        os.link(temporary, output)
        return {"path": str(output), "bytes": output.stat().st_size, "sha256": digest, "revision": revision}
    finally:
        # Only this function's uniquely created temporary file is removed.
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(str(temporary) + suffix).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    backup = commands.add_parser("backup", help="Backup a running database, including committed WAL pages")
    backup.add_argument("--database", type=Path, help="Override DATABASE_URL with a file path")
    backup.add_argument("--output", type=Path, required=True)
    restore = commands.add_parser("restore", help="Restore into a new database; existing files are never replaced")
    restore.add_argument("--source", type=Path, required=True)
    restore.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "backup":
            source = args.database or Path(make_url(Settings().database_url).database)
        else:
            source = args.source
        print(json.dumps(copy_database(source, args.output), ensure_ascii=False))
        return 0
    except (OSError, ValueError, sqlite3.Error, TimeoutError) as error:
        parser.exit(1, f"Database copy failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
