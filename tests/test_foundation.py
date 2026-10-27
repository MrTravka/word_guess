"""Migration/seed integrity, SQLite transactions and public HTTP boundaries."""

from concurrent.futures import ThreadPoolExecutor
import csv

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from backend.app.bootstrap import migrate, migration_config, migration_head
from backend.app.config import Settings
from backend.app.database import create_database
from backend.app.main import create_app
from backend.app.models import DictionaryVersion, Word
from backend.app.seed import seed_words
from backend.app.version import VERSION


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'data with spaces' / 'test.db').as_posix()}")


@pytest.fixture
def engine(settings):
    engine = create_database(settings)
    yield engine
    engine.dispose()


def word_counts(engine):
    with engine.connect() as connection:
        return dict(connection.execute(select(Word.length, func.count()).where(
            Word.enabled_as_answer.is_(True),
        ).group_by(Word.length)).all())


def test_only_file_based_sqlite_is_allowed():
    for url in ("postgresql://localhost/game", "sqlite:///:memory:", "sqlite:///data.db?uri=true"):
        with pytest.raises(ValueError):
            Settings(_env_file=None, database_url=url)


def test_pragmas_on_every_connection(engine):
    # Hold two connections concurrently so the test covers two DBAPI handles.
    with engine.connect() as first, engine.connect() as second:
        for connection in (first, second):
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000


def test_migrations_and_seed_are_repeatable_and_preserve_other_data(engine):
    migrate(engine)
    assert seed_words(engine) == 11594
    expected = {4: 1119, 5: 1102, 6: 1502}
    assert word_counts(engine) == expected
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE preservation_probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO preservation_probe VALUES (1, 'keep me')"))
    migrate(engine)
    assert seed_words(engine) == 0
    assert word_counts(engine) == expected
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(DictionaryVersion)).scalar() == 1
        assert connection.execute(text("SELECT value FROM preservation_probe")).scalar() == "keep me"
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar() == migration_head()


def test_concurrent_seeds_do_not_duplicate_words_or_versions(engine):
    migrate(engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: seed_words(engine), range(2)))
    assert sorted(results) == [0, 11594]
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(Word)).scalar() == 11594
        assert connection.execute(select(func.count()).select_from(DictionaryVersion)).scalar() == 1


def test_reverting_a_dictionary_snapshot_reapplies_its_rows(engine, tmp_path, monkeypatch):
    import backend.app.seed as seed_module

    original = seed_module.WORDS_FILE
    migrate(engine)
    seed_words(engine)
    with original.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fields = reader.fieldnames
    row = next(row for row in rows if row["canonical_word"] == "аист")
    row["enabled_as_answer"] = "0"
    row["enabled_as_guess"] = "0"
    changed = tmp_path / "changed.csv"
    with changed.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(seed_module, "WORDS_FILE", changed)
    assert seed_words(engine) == 11594
    assert word_counts(engine)[4] == 1118
    monkeypatch.setattr(seed_module, "WORDS_FILE", original)
    assert seed_words(engine) == 11594
    assert word_counts(engine)[4] == 1119
    assert seed_words(engine) == 0
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(DictionaryVersion)).scalar() == 2


def test_transaction_rolls_back_schema_and_rows(engine):
    with pytest.raises(RuntimeError, match="rollback"):
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE rollback_probe (id INTEGER)"))
            connection.execute(text("INSERT INTO rollback_probe VALUES (1)"))
            raise RuntimeError("rollback")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM sqlite_master WHERE name = 'rollback_probe'")).scalar() == 0


def test_seed_failure_rolls_back_version_and_all_words(engine):
    migrate(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TRIGGER fail_seed BEFORE INSERT ON words
            WHEN NEW.canonical_word = 'аист' BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
    with pytest.raises(IntegrityError):
        seed_words(engine)
    with engine.connect() as connection:
        assert connection.execute(select(func.count()).select_from(Word)).scalar() == 0
        assert connection.execute(select(func.count()).select_from(DictionaryVersion)).scalar() == 0


def test_foreign_keys_reject_unknown_dictionary_versions(engine):
    migrate(engine)
    seed_words(engine)
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text("UPDATE words SET dictionary_version_id = -1"))


def test_migration_matches_models(engine):
    migrate(engine)
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.check(config)


def test_health_is_not_ready_until_migration_and_seed(settings, tmp_path):
    app = create_app(settings, frontend_dist=tmp_path / "missing")
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable", "database": "unavailable", "version": VERSION}
        migrate(app.state.engine)
        assert client.get("/api/health").status_code == 503
        seed_words(app.state.engine)
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["version"] == VERSION
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/").status_code == 503


def test_static_assets_spa_and_private_files(settings, tmp_path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>fixture</title>", encoding="utf-8")
    (assets / "main.js").write_text("console.log('fixture')", encoding="utf-8")
    with TestClient(create_app(settings, frontend_dist=dist)) as client:
        for route in ("/", "/campaign"):
            assert client.get(route).status_code == 200
            assert "fixture" in client.get(route).text
        assert client.get("/assets/main.js").status_code == 200
        for route in ("/api/unknown", "/data/words/candidates.csv", "/.env", "/backend/app/version.py", "/assets/missing.js"):
            assert client.get(route).status_code == 404
