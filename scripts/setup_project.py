"""Prepare local dependencies/builds without touching persistent SQLite data."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(command, *, cwd=ROOT, env=None):
    print(" > " + " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=cwd, env=env, check=True)


def fingerprint(paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def prepare(dev=False):
    if sys.version_info < (3, 12):
        raise RuntimeError("Python 3.12+ is required. Install it and retry run.bat.")
    node = shutil.which("node")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not node or not npm:
        raise RuntimeError("Node.js LTS (22.12+ or 24+) and npm are required; nothing was installed globally.")
    node_version = subprocess.check_output([node, "--version"], text=True).strip()
    parts = tuple(map(int, node_version.lstrip("v").split(".")))
    if parts < (22, 12, 0):
        raise RuntimeError(f"Node.js 22.12+ is required, found {node_version}")
    if not PYTHON.is_file():
        run([sys.executable, "-m", "venv", ROOT / ".venv"])
    CACHE.mkdir(exist_ok=True)
    state_file = CACHE / "setup.json"
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        state = {}

    def save():
        temporary = state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(state_file)

    requirement = ROOT / "backend" / ("requirements-dev.lock" if dev else "requirements.lock")
    python_version = subprocess.check_output([str(PYTHON), "--version"], text=True).strip()
    dependency_key = fingerprint([requirement]) + python_version
    probe = subprocess.run(
        [str(PYTHON), "-c", "import fastapi, sqlalchemy, alembic, pydantic_settings, uvicorn" + (", pytest, httpx" if dev else "")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if state.get(requirement.name) != dependency_key or probe.returncode:
        pip_env = {**os.environ, "PIP_CACHE_DIR": str(CACHE / "pip")}
        run([PYTHON, "-m", "pip", "install", "--require-hashes", "-r", requirement], env=pip_env)
        state[requirement.name] = dependency_key
        save()
    else:
        print("Python dependencies unchanged; skipping install", flush=True)

    frontend = ROOT / "frontend"
    dependencies = fingerprint([frontend / "package.json", frontend / "package-lock.json"]) + node_version
    npm_env = {**os.environ, "npm_config_cache": str(CACHE / "npm")}
    if state.get("npm") != dependencies or not (frontend / "node_modules" / ".package-lock.json").is_file():
        run([npm, "ci", "--no-audit", "--no-fund"], cwd=frontend, env=npm_env)
        state["npm"] = dependencies
        save()
    else:
        print("Node dependencies unchanged; skipping npm ci", flush=True)

    if not dev:
        files = [frontend / name for name in ("package.json", "package-lock.json", "index.html", "tsconfig.json", "vite.config.ts")]
        for directory in (frontend / "src", frontend / "public"):
            if directory.is_dir():
                files.extend(path for path in directory.rglob("*") if path.is_file())
        if (ROOT / ".env").is_file():
            files.append(ROOT / ".env")
        build_key = fingerprint(files) + node_version
        if state.get("build") != build_key or not (frontend / "dist" / "index.html").is_file():
            run([npm, "run", "build"], cwd=frontend, env=npm_env)
            state["build"] = build_key
            save()
        else:
            print("Frontend sources unchanged; skipping build", flush=True)
    run([PYTHON, "-m", "backend.app.bootstrap"])
    return npm
