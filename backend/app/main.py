"""API health and same-origin delivery of the compiled React application."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .bootstrap import migration_head
from .config import FRONTEND_DIST, Settings
from .database import create_database
from .version import VERSION
from .accounts import router as accounts_router
from .security import AuthLimiter
from .games import router as games_router
from .economy import router as economy_router
from .hints import router as hints_router
from .campaign import router as campaign_router


def readiness(engine: Engine, revision_head: str) -> bool:
    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            counts = dict(connection.execute(text(
                "SELECT length, count(*) FROM words WHERE enabled_as_answer = 1 GROUP BY length",
            )).all())
            return revision == revision_head and all(counts.get(length, 0) >= 1000 for length in (4, 5, 6))
    except SQLAlchemyError:
        return False


def create_app(settings: Settings | None = None, frontend_dist: Path = FRONTEND_DIST) -> FastAPI:
    settings = settings or Settings()
    engine = create_database(settings)
    revision_head = migration_head()

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="word_guess", version=VERSION, lifespan=lifespan)
    app.state.engine = engine
    app.state.settings = settings
    app.state.auth_limiter = AuthLimiter()

    @app.middleware("http")
    async def protect_api(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                origin = request.headers.get("origin")
                allowed = {str(request.base_url).rstrip("/"), *settings.auth_allowed_origins}
                if request.headers.get("x-requested-with") != "word_guess" or (origin is not None and origin not in allowed):
                    return JSONResponse({"detail": "Запрос с этого источника запрещён."}, status_code=403, headers={"Cache-Control": "no-store"})
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _error: RequestValidationError):
        # Pydantic errors may include the submitted password; never echo inputs.
        if request.url.path.startswith("/api/games"):
            return JSONResponse({"detail": "Некорректный запрос партии: проверьте режим, слово, версию и ключ действия."}, status_code=422)
        if request.url.path.startswith("/api/shop"):
            return JSONResponse({"detail": "Некорректная покупка: выберите предмет и новый ключ операции."}, status_code=422)
        if request.url.path.startswith("/api/campaign"):
            return JSONResponse({"detail": "Некорректный номер главы кампании."}, status_code=422)
        return JSONResponse({"detail": "Проверьте данные: логин 3–32 буквы/цифры/_, пароль 8–128 символов, имя 1–40 символов; тема — системная, светлая или тёмная."}, status_code=422)

    app.include_router(accounts_router)
    app.include_router(games_router)
    app.include_router(economy_router)
    app.include_router(hints_router)
    app.include_router(campaign_router)

    @app.get("/api/health")
    def health():
        ready = readiness(engine, revision_head)
        return JSONResponse(
            {"status": "ok" if ready else "unavailable", "database": "ready" if ready else "unavailable", "version": VERSION},
            status_code=200 if ready else 503,
            headers={"Cache-Control": "no-store"},
        )

    assets = frontend_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        # Never turn API errors or source/hidden-file requests into SPA pages.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        if path and ("." in path or path.startswith("assets/")):
            raise HTTPException(404, "File not found")
        index = frontend_dist / "index.html"
        if not index.is_file():
            return JSONResponse({"detail": "Frontend is not built; use run.bat"}, status_code=503)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
