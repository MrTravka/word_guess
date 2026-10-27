"""Single container process; migrate/seed before accepting HTTP requests."""

import os
import sys

from .bootstrap import bootstrap


def main():
    bootstrap()
    os.execv(sys.executable, [
        sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0",
        "--port", "8000", "--workers", "1",
    ])


if __name__ == "__main__":
    main()
