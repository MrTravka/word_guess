"""Serve an isolated production bundle so update tests never mutate the real build."""

import os
from pathlib import Path

from backend.app.main import create_app


def create_test_app():
    path = Path(os.environ["TEST_FRONTEND_DIST"]).resolve()
    cache = Path(__file__).resolve().parents[1] / ".cache"
    if cache not in path.parents or not path.parent.name.startswith("accounts-browser-"):
        raise RuntimeError("PWA tests require an isolated .cache frontend")
    return create_app(frontend_dist=path)
