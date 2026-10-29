"""SQLite backup copies committed WAL state without replacing any user file."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from backend.app.backup import copy_database
from backend.app.bootstrap import migrate
from backend.app.config import ROOT, Settings
from backend.app.database import create_database
from backend.app.main import create_app
from backend.app.security import COOKIE
from test_games import HEADERS, app, attempt, client, settings, start
from test_hints import hint


def database(settings):
    from sqlalchemy.engine import make_url
    return Path(make_url(settings.database_url).database)


def test_backup_restore_preserves_session_progress_hints_wallet_and_settings(client, app, settings, tmp_path):
    won = attempt(client, start(client, "4"), "елка").json()
    active = hint(client, start(client)).json()
    client.patch("/api/settings", json={"theme": "dark"})
    audio = {"music_enabled": True, "sounds_enabled": False, "music_volume": 25, "sounds_volume": 50}
    client.put("/api/settings/audio", json=audio)
    saved_wallet = client.get("/api/inventory").json()
    backup = tmp_path / "copies with spaces" / "saved.db"
    report = copy_database(database(settings), backup)
    assert report["sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()
    restored = tmp_path / "new database.db"
    copy_database(backup, restored)
    restored_settings = Settings(_env_file=None, database_url=f"sqlite:///{restored.as_posix()}")
    restored_app = create_app(restored_settings)
    migrate(restored_app.state.engine)
    with TestClient(restored_app, headers=HEADERS) as recovered:
        recovered.cookies.set(COOKIE, client.cookies.get(COOKIE))
        assert recovered.get("/api/auth/me").json()["user"]["login"] == "player"
        assert recovered.get("/api/settings").json() == {"theme": "dark"}
        assert recovered.get("/api/settings/audio").json() == audio
        assert recovered.get("/api/inventory").json() == saved_wallet
        assert recovered.get(f"/api/games/{won['id']}").json()["reward"] == won["reward"]
        assert recovered.get(f"/api/games/{active['id']}").json() == active
        assert attempt(recovered, active, "касса").json()["status"] == "won"
    # Completing a restored game cannot change its independent source DB.
    assert client.get(f"/api/games/{active['id']}").json()["status"] == "active"


def test_committed_wal_pages_are_copied_even_while_source_connection_is_open(client, app, settings, tmp_path):
    with app.state.engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA wal_autocheckpoint=0")
        connection.commit()
        connection.execute(text("UPDATE user_settings SET theme='dark' WHERE user_id=1"))
        connection.commit()
        assert Path(str(database(settings)) + "-wal").is_file()
        target = tmp_path / "wal-copy.db"
        copy_database(database(settings), target)
        with sqlite3.connect(target) as copied:
            assert copied.execute("SELECT theme FROM user_settings WHERE user_id=1").fetchone() == ("dark",)
            assert copied.execute("PRAGMA quick_check").fetchone() == ("ok",)


def test_two_backups_to_same_path_publish_once(client, settings, tmp_path):
    output = tmp_path / "one.db"
    def save(_):
        try:
            copy_database(database(settings), output)
            return "saved"
        except FileExistsError:
            return "exists"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, range(2))) == ["exists", "saved"]
    with sqlite3.connect(output) as connection:
        assert connection.execute("SELECT count(*) FROM users").fetchone() == (1,)


@pytest.mark.parametrize("suffix", ["", "-wal", "-shm", "-journal"])
def test_restore_refuses_existing_output_and_sidecars_without_modifying_them(client, settings, tmp_path, suffix):
    output = tmp_path / "existing.db"
    protected = Path(str(output) + suffix)
    protected.write_bytes(b"must remain intact")
    with pytest.raises(FileExistsError):
        copy_database(database(settings), output)
    assert protected.read_bytes() == b"must remain intact"
    assert not list(tmp_path.glob(".word-guess-backup-*"))


@pytest.mark.parametrize("kind", ["missing", "invalid", "foreign", "future"])
def test_invalid_sources_do_not_publish_an_output(settings, tmp_path, kind):
    source = tmp_path / "source.db"
    if kind == "invalid":
        source.write_bytes(b"not sqlite")
    elif kind == "foreign":
        with sqlite3.connect(source) as connection:
            connection.execute("CREATE TABLE unrelated(id integer)")
    elif kind == "future":
        engine = create_database(settings)
        migrate(engine)
        engine.dispose()
        source = database(settings)
        with sqlite3.connect(source) as connection:
            connection.execute("UPDATE alembic_version SET version_num='unknown_future'")
    output = tmp_path / "not-created.db"
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        copy_database(source, output)
    assert not output.exists()
    assert not list(tmp_path.glob(".word-guess-backup-*"))


def test_source_and_output_cannot_match(client, settings):
    source = database(settings)
    before = source.read_bytes()
    with pytest.raises(ValueError):
        copy_database(source, source)
    assert source.read_bytes() == before


def test_cli_backup_and_restore_use_explicit_paths_and_fail_safely(client, settings, tmp_path):
    backup, restored = tmp_path / "copy with spaces.db", tmp_path / "restore with spaces.db"
    def run(*arguments, env=None):
        return subprocess.run([sys.executable, "-m", "backend.app.backup", *map(str, arguments)], cwd=ROOT, capture_output=True, text=True, env=env)
    assert run("backup", "--database", database(settings), "--output", backup).returncode == 0
    assert run("restore", "--source", backup, "--output", restored).returncode == 0
    failed = run("restore", "--source", backup, "--output", restored)
    assert failed.returncode == 1 and "already exist" in failed.stderr
    assert run("backup", "--output", tmp_path / "from-config.db", env={
        **os.environ, "DATABASE_URL": f"sqlite:///{database(settings).as_posix()}",
    }).returncode == 0
