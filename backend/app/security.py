"""Password hashing, opaque sessions and bounded authentication throttling."""

from collections import deque
from hashlib import sha256
import secrets
from threading import Lock
import time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException, Request, Response
from sqlalchemy import delete, insert, select

from .models import AccountSession, User

COOKIE = "word_guess_session"
PASSWORDS = PasswordHasher()
# Unknown accounts still perform the same password verification work.
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORDS.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def session_hash(request: Request) -> str:
    return token_hash(request.cookies.get(COOKIE, ""))


def create_session(connection, request: Request, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    connection.execute(delete(AccountSession).where(AccountSession.expires_at <= now))
    # Rotating the current browser session never leaves its previous token active.
    connection.execute(delete(AccountSession).where(AccountSession.token_hash == session_hash(request)))
    connection.execute(insert(AccountSession).values(
        token_hash=token_hash(token), user_id=user_id,
        expires_at=now + request.app.state.settings.session_days * 86400,
    ))
    return token


def set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE, token, max_age=request.app.state.settings.session_days * 86400,
        httponly=True, secure=request.app.state.settings.cookie_secure or request.url.scheme == "https",
        samesite="lax", path="/",
    )


def current_user(request: Request) -> dict:
    with request.app.state.engine.connect() as connection:
        user = connection.execute(select(User.id, User.login, User.display_name).join(
            AccountSession, AccountSession.user_id == User.id,
        ).where(
            AccountSession.token_hash == session_hash(request), AccountSession.expires_at > int(time.time()),
        )).mappings().first()
    if user is None:
        raise HTTPException(401, "Войдите в аккаунт.")
    return dict(user)


class AuthLimiter:
    """Single-process limit. Never trust X-Forwarded-For supplied by a client."""

    def __init__(self):
        self._attempts: dict[str, deque] = {}
        self._lock = Lock()

    def check(self, request: Request, login: str) -> None:
        now = time.monotonic()
        address = request.client.host if request.client else "unknown"
        keys = ((f"ip:{address}", 30), (f"login:{login}", 10))
        with self._lock:
            self._attempts = {
                key: values for key, values in self._attempts.items() if values and values[-1] > now - 300
            }
            if len(self._attempts) >= 10000:
                raise HTTPException(429, "Слишком много запросов. Попробуйте через пять минут.", headers={"Retry-After": "300"})
            for key, limit in keys:
                values = self._attempts.setdefault(key, deque())
                while values and values[0] <= now - 300:
                    values.popleft()
                if len(values) >= limit:
                    raise HTTPException(429, "Слишком много попыток. Попробуйте через пять минут.", headers={"Retry-After": "300"})
            for key, _ in keys:
                self._attempts[key].append(now)
