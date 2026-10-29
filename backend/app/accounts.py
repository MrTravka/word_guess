"""Account API: atomic signup, session rotation and private theme settings."""

import re
import time
from typing import Annotated, Literal
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from .models import AccountSession, User, UserSettings
from .economy_service import initialize_account
from .security import (
    COOKIE, DUMMY_HASH, PASSWORDS, create_session, current_user, session_hash,
    set_session_cookie, verify_password,
)

router = APIRouter(prefix="/api")
Identity = Annotated[dict, Depends(current_user)]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128, repr=False)

    @field_validator("login", mode="before")
    @classmethod
    def normalize_login(cls, value):
        if not isinstance(value, str):
            raise ValueError("Логин должен быть строкой.")
        value = unicodedata.normalize("NFKC", value).strip().casefold()
        if not re.fullmatch(r"[a-zа-яё0-9_]{3,32}", value):
            raise ValueError("Логин: 3–32 буквы, цифры или знак подчёркивания.")
        return value


class Registration(Credentials):
    display_name: str = Field(min_length=1, max_length=40)

    @field_validator("display_name", mode="before")
    @classmethod
    def clean_name(cls, value):
        if not isinstance(value, str):
            raise ValueError("Имя должно быть строкой.")
        value = value.strip()
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("Имя содержит недопустимые символы.")
        return value


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: Literal["system", "light", "dark"]


def account_result(connection, user_id: int) -> dict:
    user = connection.execute(select(User.id, User.login, User.display_name).where(User.id == user_id)).mappings().one()
    theme = connection.execute(select(UserSettings.theme).where(UserSettings.user_id == user_id)).scalar_one()
    return {"user": dict(user), "settings": {"theme": theme}}


@router.post("/auth/register", status_code=201)
def register(data: Registration, request: Request, response: Response):
    request.app.state.auth_limiter.check(request, data.login)
    password_hash = PASSWORDS.hash(data.password)
    try:
        with request.app.state.engine.begin() as connection:
            user_id = connection.execute(insert(User).values(
                login=data.login, display_name=data.display_name,
                password_hash=password_hash, created_at=int(time.time()),
            )).inserted_primary_key[0]
            connection.execute(insert(UserSettings).values(user_id=user_id, theme="system"))
            initialize_account(connection, user_id)
            token = create_session(connection, request, user_id)
            result = account_result(connection, user_id)
    except IntegrityError:
        with request.app.state.engine.connect() as connection:
            existing = connection.execute(select(User.id).where(User.login == data.login)).first()
        if existing is None:
            raise
        raise HTTPException(409, "Этот логин уже занят.") from None
    set_session_cookie(response, request, token)
    return result


@router.post("/auth/login")
def login(data: Credentials, request: Request, response: Response):
    request.app.state.auth_limiter.check(request, data.login)
    with request.app.state.engine.connect() as connection:
        user = connection.execute(select(User.id, User.password_hash).where(User.login == data.login)).mappings().first()
    if not verify_password(user["password_hash"] if user else DUMMY_HASH, data.password) or user is None:
        raise HTTPException(401, "Неверный логин или пароль.")
    replacement = PASSWORDS.hash(data.password) if PASSWORDS.check_needs_rehash(user["password_hash"]) else None
    with request.app.state.engine.begin() as connection:
        if replacement:
            connection.execute(update(User).where(User.id == user["id"]).values(password_hash=replacement))
        token = create_session(connection, request, user["id"])
        result = account_result(connection, user["id"])
    set_session_cookie(response, request, token)
    return result


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response):
    with request.app.state.engine.begin() as connection:
        connection.execute(delete(AccountSession).where(AccountSession.token_hash == session_hash(request)))
    response.delete_cookie(
        COOKIE, path="/", httponly=True, samesite="lax",
        secure=request.app.state.settings.cookie_secure or request.url.scheme == "https",
    )


@router.get("/auth/me")
def me(request: Request, user: Identity):
    with request.app.state.engine.connect() as connection:
        return account_result(connection, user["id"])


@router.get("/settings")
def get_settings(request: Request, user: Identity):
    with request.app.state.engine.connect() as connection:
        return {"theme": connection.execute(select(UserSettings.theme).where(UserSettings.user_id == user["id"])).scalar_one()}


@router.patch("/settings")
def save_settings(data: Preferences, request: Request, user: Identity):
    with request.app.state.engine.begin() as connection:
        connection.execute(update(UserSettings).where(UserSettings.user_id == user["id"]).values(theme=data.theme))
    return data
