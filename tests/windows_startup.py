"""Clean/repeated Windows entrypoints in an isolated project path containing spaces."""

import http.cookiejar
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def port():
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


def stop(process):
    if process.poll() is not None:
        return
    try:
        process.send_signal(signal.CTRL_BREAK_EVENT)
        process.wait(timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        process.wait(timeout=5)


def main():
    if os.name != "nt":
        raise SystemExit("This check exercises Windows bat entrypoints")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse", type=Path, help="Reuse only a previous isolated .cache project")
    args = parser.parse_args()
    if args.reuse:
        project = args.reuse.resolve()
        if ROOT / ".cache" not in project.parents or project.name != "project" or not project.parent.name.startswith("windows-startup-"):
            raise RuntimeError("Reuse is limited to this test's isolated project")
        directory = project.parent
    else:
        directory = ROOT / ".cache" / f"windows-startup-{time.time_ns()} with spaces"
        project = directory / "project"
        project.mkdir(parents=True)
    for name in ("backend", "frontend", "scripts", "data"):
        shutil.copytree(ROOT / name, project / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("node_modules", ".venv", ".cache", "dist", "runtime", "sources", "__pycache__"))
    for name in ("run.bat", "run-dev.bat", "ost.mp3", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, project / name)
    database = project / "data/runtime/windows-test.db"
    api_port, vite_port = port(), port()
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database.as_posix()}", "APP_PORT": str(api_port),
           "VITE_PORT": str(vite_port), "COOKIE_SECURE": "false", "AUTH_ALLOWED_ORIGINS": "[]"}
    print(f"Isolated Windows project: {project}", flush=True)

    def launch(bat, log_name, *arguments):
        log = (directory / log_name).open("wb")
        process = subprocess.Popen(["cmd.exe", "/c", bat, *arguments], cwd=project, env=env,
                                   stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        log.close()
        return process

    prepared = launch("run.bat", "prepare.log", "--prepare-only")
    try:
        deadline = time.monotonic() + 600
        while prepared.poll() is None:
            if time.monotonic() > deadline:
                raise RuntimeError("Clean preparation timed out; inspect prepare.log")
            time.sleep(1)
        if prepared.returncode:
            raise RuntimeError((directory / "prepare.log").read_text(encoding="utf-8", errors="replace"))
    finally:
        stop(prepared)
    print("Repeated preparation PASS" if args.reuse else "Clean run.bat preparation PASS", flush=True)
    helper = project / "frontend/build/pwa.ts"
    with helper.open("a", encoding="utf-8") as probe:
        probe.write("\n// Acceptance rebuild probe\n")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    base = f"http://127.0.0.1:{api_port}"

    def request(path, body=None, method=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-Requested-With": "word_guess"})
        with opener.open(req, timeout=5) as response:
            return json.load(response)

    def ready(process, endpoint):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Entrypoint stopped unexpectedly; inspect its log")
            try:
                with opener.open(endpoint, timeout=2) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                time.sleep(0.2)
        raise RuntimeError("Entrypoint did not become ready")

    process = launch("run.bat", "production-first.log")
    try:
        ready(process, base + "/api/health")
        request("/api/auth/register", {"login": "windows_" + uuid4().hex[:12], "display_name": "Windows", "password": "local-test-password"})
        request("/api/settings", {"theme": "dark"}, "PATCH")
        game = request("/api/games", {"mode": "6", "operation_id": str(uuid4())})
        with sqlite3.connect(database) as connection:
            answer = connection.execute("SELECT answer FROM games WHERE id=?", (game["id"],)).fetchone()[0]
        word = "машина" if answer == "ворона" else "ворона"
        game = request(f"/api/games/{game['id']}/guesses", {"word": word, "version": game["version"], "operation_id": str(uuid4())})
        game = request(f"/api/games/{game['id']}/hints", {"kind": "random_letter", "version": game["version"], "operation_id": str(uuid4())})
        expected_account = request("/api/auth/me")
        expected_inventory = request("/api/inventory")
        assert "run build" in (directory / "production-first.log").read_text(encoding="utf-8", errors="replace")
        print("PWA build helper invalidates the production build cache PASS", flush=True)
        print("Production account, active game and hint saved PASS", flush=True)
    finally:
        stop(process)
    process = launch("run.bat", "production-second.log")
    try:
        ready(process, base + "/api/health")
        assert request("/api/auth/me") == expected_account
        assert request("/api/inventory") == expected_inventory
        assert request(f"/api/games/{game['id']}") == game
        print("Repeated production preserves cookie, theme, wallet, game and hint PASS", flush=True)
    finally:
        stop(process)
    process = launch("run-dev.bat", "development.log")
    try:
        base = f"http://127.0.0.1:{vite_port}"
        ready(process, base + "/api/health")
        assert request("/api/auth/me") == expected_account
        assert request("/api/inventory") == expected_inventory
        assert request(f"/api/games/{game['id']}") == game
        print("run-dev.bat Vite proxy preserves saved state PASS", flush=True)
    finally:
        stop(process)
    print(f"Windows entrypoints PASS; logs: {directory}", flush=True)


if __name__ == "__main__":
    main()
