"""Serve only explicit public PWA assets; never expose repository or dictionary paths."""

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse


def register_public_assets(app, frontend_dist: Path):
    files = {
        "/manifest.webmanifest": "application/manifest+json",
        "/sw.js": "text/javascript",
        "/index.html": "text/html",
        "/audio/ost.mp3": "audio/mpeg",
        **{f"/icons/{name}.png": "image/png" for name in ("brand-c", "icon-180", "icon-192", "icon-512", "maskable-512")},
    }
    def register(url, media_type):
        path = frontend_dist / url.lstrip("/")
        def serve():
            if not path.is_file():
                raise HTTPException(404, "File not found")
            headers = {"Cache-Control": "no-cache"}
            if url == "/sw.js":
                headers["Service-Worker-Allowed"] = "/"
            return FileResponse(path, media_type=media_type, headers=headers)
        app.add_api_route(url, serve, methods=["GET"], include_in_schema=False)
    for url, media_type in files.items():
        register(url, media_type)
