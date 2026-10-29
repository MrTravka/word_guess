"""Audio opt-in, saved preferences, migrations and explicit public asset boundaries."""

import hashlib
import struct

from alembic import command
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.bootstrap import migrate, migration_config
from backend.app.config import ROOT
from backend.app.main import create_app
from backend.app.security import COOKIE
from test_games import HEADERS, app, client, settings, start

DEFAULT = {"music_enabled": False, "sounds_enabled": False, "music_volume": 25, "sounds_volume": 35}
CUSTOM = {"music_enabled": True, "sounds_enabled": True, "music_volume": 40, "sounds_volume": 55}


def test_audio_is_opt_in_separate_from_theme_and_survives_restart(client, app, settings):
    assert client.get("/api/settings/audio").json() == DEFAULT
    assert client.put("/api/settings/audio", json=CUSTOM).json() == CUSTOM
    client.patch("/api/settings", json={"theme": "dark"})
    assert client.get("/api/settings/audio").json() == CUSTOM
    assert client.get("/api/settings").json() == {"theme": "dark"}
    with TestClient(create_app(settings), headers=HEADERS) as restored:
        restored.cookies.set(COOKIE, client.cookies.get(COOKIE))
        assert restored.get("/api/settings/audio").json() == CUSTOM
        assert restored.get("/api/settings/audio").headers["cache-control"] == "no-store"


@pytest.mark.parametrize("change", [
    {"music_volume": -1}, {"music_volume": 101}, {"sounds_volume": 25.5}, {"sounds_volume": True},
    {"music_enabled": "true"}, {"sounds_enabled": 1}, {"user_id": 5},
])
def test_audio_rejects_invalid_or_foreign_fields_without_changing_preferences(client, change):
    assert client.put("/api/settings/audio", json={**DEFAULT, **change}).status_code == 422
    assert client.get("/api/settings/audio").json() == DEFAULT


def test_audio_is_private_and_database_checks_volume(client, app):
    client.put("/api/settings/audio", json=CUSTOM)
    with TestClient(app, headers=HEADERS) as other:
        assert other.get("/api/settings/audio").status_code == 401
        assert other.put("/api/settings/audio", json=CUSTOM).status_code == 401
        assert other.post("/api/auth/register", json={"login": "other", "display_name": "Другой", "password": "password-123"}).status_code == 201
        assert other.get("/api/settings/audio").json() == DEFAULT
    with app.state.engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(text("UPDATE user_settings SET music_volume=200 WHERE user_id=1"))
    assert client.get("/api/settings/audio").json() == CUSTOM
    assert client.put("/api/settings/audio", json=DEFAULT, headers={**HEADERS, "Origin": "https://foreign.example"}).status_code == 403


def test_audio_migration_preserves_theme_active_game_and_accounts(client, app):
    client.patch("/api/settings", json={"theme": "dark"})
    game = start(client)
    config = migration_config()
    with app.state.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0007_statistics")
    migrate(app.state.engine)
    migrate(app.state.engine)
    assert client.get("/api/settings/audio").json() == DEFAULT
    assert client.get("/api/settings").json() == {"theme": "dark"}
    assert client.get(f"/api/games/{game['id']}").json() == game
    with app.state.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_public_pwa_assets_are_explicit_and_audio_supports_ranges(settings, tmp_path):
    frontend = tmp_path / "frontend"
    (frontend / "audio").mkdir(parents=True)
    (frontend / "icons").mkdir()
    (frontend / "index.html").write_text("<main>public shell</main>", encoding="utf-8")
    (frontend / "sw.js").write_text("/* worker */", encoding="utf-8")
    (frontend / "manifest.webmanifest").write_text('{"name":"word_guess"}', encoding="utf-8")
    (frontend / "audio/ost.mp3").write_bytes(b"test audio range")
    (frontend / "icons/icon-192.png").write_bytes(b"icon")
    # Even a mistakenly placed extra file cannot become a public route.
    (frontend / "audio/private.db").write_bytes(b"not public")
    with TestClient(create_app(settings, frontend_dist=frontend)) as public:
        worker = public.get("/sw.js")
        assert worker.status_code == 200
        assert worker.headers["service-worker-allowed"] == "/"
        assert worker.headers["cache-control"] == "no-cache"
        assert public.get("/manifest.webmanifest").headers["content-type"].startswith("application/manifest+json")
        assert public.get("/index.html").text == "<main>public shell</main>"
        audio = public.get("/audio/ost.mp3", headers={"Range": "bytes=0-3"})
        assert audio.status_code == 206 and audio.content == b"test"
        assert audio.headers["content-type"] == "audio/mpeg"
        for path in ("/audio/private.db", "/data/words/candidates.csv", "/backend/app/models.py", "/.env", "/icons/other.png"):
            assert public.get(path).status_code == 404


def test_distributed_audio_is_unchanged_and_icons_have_installable_sizes():
    assert hashlib.sha256((ROOT / "ost.mp3").read_bytes()).digest() == hashlib.sha256((ROOT / "frontend/public/audio/ost.mp3").read_bytes()).digest()
    for name, size in (("icon-180", 180), ("icon-192", 192), ("icon-512", 512), ("maskable-512", 512)):
        data = (ROOT / f"frontend/public/icons/{name}.png").read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert struct.unpack("!II", data[16:24]) == (size, size)
