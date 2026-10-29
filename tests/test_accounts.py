"""Account isolation, SQLite persistence and session/security boundaries."""

from concurrent.futures import ThreadPoolExecutor
import time

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text, update

from backend.app.bootstrap import migrate
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import AccountSession, User, UserSettings
from backend.app.security import COOKIE, PASSWORDS, token_hash

HEADERS = {"X-Requested-With": "word_guess", "Origin": "http://testserver"}
ALICE = {"login": "Alice_1", "display_name": "Алиса", "password": "password-123"}


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'accounts.db').as_posix()}")


@pytest.fixture
def app(settings):
    app = create_app(settings)
    migrate(app.state.engine)
    yield app
    app.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app, headers=HEADERS) as client:
        yield client


def test_registration_creates_session_and_hashes_secrets(client, app):
    response = client.post("/api/auth/register", json=ALICE)
    assert response.status_code == 201
    expected = {"user": {"id": 1, "login": "alice_1", "display_name": "Алиса"}, "settings": {"theme": "system"}}
    assert response.json() == expected
    assert client.get("/api/auth/me").json() == expected
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=2592000" in cookie
    token = client.cookies.get(COOKIE)
    with app.state.engine.connect() as connection:
        stored = connection.execute(select(User.password_hash)).scalar_one()
        assert stored.startswith("$argon2id$") and PASSWORDS.verify(stored, ALICE["password"])
        assert connection.execute(select(AccountSession.token_hash)).scalar_one() == token_hash(token)
    assert ALICE["password"] not in response.text and token not in response.text
    assert response.headers["cache-control"] == "no-store"


def test_normalized_login_collision_and_concurrent_registration_are_atomic(app):
    def signup(login):
        with TestClient(app, headers=HEADERS) as client:
            return client.post("/api/auth/register", json={**ALICE, "login": login}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(signup, ["ＡＬＩＣＥ_1", " alice_1 "])) == [201, 409]
    with app.state.engine.connect() as connection:
        for model in (User, UserSettings, AccountSession):
            assert connection.execute(select(func.count()).select_from(model)).scalar_one() == 1


def test_session_creation_failure_rolls_back_entire_registration(app):
    with app.state.engine.begin() as connection:
        connection.execute(text("""CREATE TRIGGER fail_session BEFORE INSERT ON sessions
            BEGIN SELECT RAISE(ABORT, 'session failure'); END"""))
    with TestClient(app, headers=HEADERS, raise_server_exceptions=False) as client:
        assert client.post("/api/auth/register", json=ALICE).status_code == 500
        assert COOKIE not in client.cookies
    with app.state.engine.begin() as connection:
        for model in (User, UserSettings, AccountSession):
            assert connection.execute(select(func.count()).select_from(model)).scalar_one() == 0
        connection.execute(text("DROP TRIGGER fail_session"))
    with TestClient(app, headers=HEADERS) as client:
        assert client.post("/api/auth/register", json=ALICE).status_code == 201


def test_two_accounts_have_separate_settings_and_survive_server_restart(client, app, settings):
    client.post("/api/auth/register", json=ALICE)
    token = client.cookies.get(COOKIE)
    assert client.patch("/api/settings", json={"theme": "dark"}).json() == {"theme": "dark"}
    with TestClient(app, headers=HEADERS) as bob:
        assert bob.post("/api/auth/register", json={**ALICE, "login": "bob", "display_name": "Боб"}).status_code == 201
        assert bob.get("/api/settings").json() == {"theme": "system"}
        assert bob.patch("/api/settings", json={"theme": "light", "user_id": 1}).status_code == 422
        assert bob.patch("/api/settings", json={"theme": "light"}).status_code == 200
        assert client.get("/api/settings").json() == {"theme": "dark"}
        assert bob.get("/api/auth/me").json()["user"]["login"] == "bob"
    restarted = create_app(settings)
    with TestClient(restarted, headers=HEADERS) as restored:
        restored.cookies.set(COOKIE, token)
        assert restored.get("/api/auth/me").json()["settings"] == {"theme": "dark"}
        migrate(restarted.state.engine)
        assert restored.get("/api/auth/me").json()["user"]["login"] == "alice_1"


def test_login_rotates_session_logout_revokes_it_and_is_repeatable(client, app):
    client.post("/api/auth/register", json=ALICE)
    first = client.cookies.get(COOKIE)
    assert client.post("/api/auth/login", json={"login": "ALICE_1", "password": ALICE["password"]}).status_code == 200
    second = client.cookies.get(COOKIE)
    assert first != second
    with TestClient(app, headers=HEADERS) as replay:
        replay.cookies.set(COOKIE, first)
        assert replay.get("/api/auth/me").status_code == 401
        assert client.post("/api/auth/logout").status_code == 204
        replay.cookies.set(COOKIE, second)
        assert replay.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_independent_device_sessions_remain_after_single_logout(client, app):
    client.post("/api/auth/register", json=ALICE)
    with TestClient(app, headers=HEADERS) as other:
        assert other.post("/api/auth/login", json={"login": "alice_1", "password": ALICE["password"]}).status_code == 200
        client.post("/api/auth/logout")
        assert other.get("/api/auth/me").status_code == 200


def test_expired_or_forged_session_cannot_read_or_modify_settings(client, app):
    client.post("/api/auth/register", json=ALICE)
    with app.state.engine.begin() as connection:
        connection.execute(update(AccountSession).values(expires_at=int(time.time()) - 1))
    assert client.get("/api/auth/me").status_code == 401
    assert client.patch("/api/settings", json={"theme": "dark"}).status_code == 401
    client.cookies.clear()
    client.cookies.set(COOKIE, "forged")
    assert client.get("/api/settings").status_code == 401
    assert client.get("/api/auth/me").headers["cache-control"] == "no-store"


def test_csrf_blocks_foreign_origin_and_missing_custom_header(client):
    for headers in (
        {**HEADERS, "Origin": "https://foreign.example"},
        {**HEADERS, "Origin": "null"},
        {"Origin": "http://testserver", "X-Requested-With": ""},
    ):
        assert client.post("/api/auth/register", json=ALICE, headers=headers).status_code == 403
        assert client.post("/api/auth/logout", headers=headers).status_code == 403
    assert client.post("/api/auth/register", json=ALICE).status_code == 201
    assert client.patch("/api/settings", json={"theme": "dark"}, headers={**HEADERS, "Origin": "https://foreign.example"}).status_code == 403
    assert client.get("/api/settings").json() == {"theme": "system"}


@pytest.mark.parametrize("change", [
    {"login": "ab"}, {"login": "has spaces"}, {"login": "bad<script>"},
    {"password": "tiny"}, {"password": "x" * 129},
    {"display_name": " "}, {"display_name": "name\ncontrol"}, {"display_name": "x" * 41},
])
def test_validation_does_not_echo_passwords_or_tokens(client, change):
    data = {**ALICE, **change}
    response = client.post("/api/auth/register", json=data)
    assert response.status_code == 422
    assert data["password"] not in response.text
    assert "input" not in response.text


def test_wrong_password_and_unknown_account_have_same_public_error(client):
    client.post("/api/auth/register", json=ALICE)
    existing = client.post("/api/auth/login", json={"login": "alice_1", "password": "wrong-password"})
    unknown = client.post("/api/auth/login", json={"login": "unknown", "password": "wrong-password"})
    assert existing.status_code == unknown.status_code == 401
    assert existing.json() == unknown.json()


def test_brute_force_is_limited_by_login_even_from_different_addresses(app):
    for number in range(11):
        with TestClient(app, headers=HEADERS, client=(f"192.0.2.{number}", 5000)) as client:
            response = client.post("/api/auth/login", json={"login": "unknown", "password": "wrong-password"})
        assert response.status_code == (401 if number < 10 else 429)
    assert response.headers["retry-after"] == "300"


def test_ip_limit_expires_and_does_not_leave_broken_limiter_entries(app, monkeypatch):
    import backend.app.security as security
    now = [1000]
    monkeypatch.setattr(security.time, "monotonic", lambda: now[0])
    with TestClient(app, headers=HEADERS) as client:
        for number in range(30):
            assert client.post("/api/auth/login", json={"login": f"unknown_{number}", "password": "wrong-password"}).status_code == 401
        for _ in range(2):
            assert client.post("/api/auth/login", json={"login": "newuser", "password": "wrong-password"}).status_code == 429
        now[0] += 301
        assert client.post("/api/auth/login", json={"login": "newuser", "password": "wrong-password"}).status_code == 401


def test_https_and_explicit_configuration_set_secure_cookie(settings):
    for secure, base_url in ((False, "https://testserver"), (True, "http://testserver")):
        app = create_app(settings.model_copy(update={"cookie_secure": secure}))
        migrate(app.state.engine)
        with TestClient(app, base_url=base_url, headers={**HEADERS, "Origin": base_url}) as client:
            response = client.post("/api/auth/register", json={**ALICE, "login": f"secure_{secure}"})
            assert response.status_code == 201
            assert "Secure" in response.headers["set-cookie"]


def test_explicit_trusted_origin_supports_reverse_proxy(settings):
    app = create_app(settings.model_copy(update={"auth_allowed_origins": ["https://words.example"]}))
    migrate(app.state.engine)
    with TestClient(app, headers={**HEADERS, "Origin": "https://words.example"}) as client:
        assert client.post("/api/auth/register", json=ALICE).status_code == 201
