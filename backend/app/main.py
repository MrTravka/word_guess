"""API health and same-origin delivery of the compiled React application."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .bootstrap import migration_head
from .config import FRONTEND_DIST, Settings
from .database import create_database
from .version import VERSION


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
    engine = create_database(settings or Settings())
    revision_head = migration_head()

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="word_guess", version=VERSION, lifespan=lifespan)
    app.state.engine = engine

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
