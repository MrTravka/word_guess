"""Run production locally or supervise Vite + Uvicorn in one console."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

from setup_project import PYTHON, ROOT, prepare


def configuration():
    code = "from backend.app.config import Settings; print(Settings().model_dump_json())"
    return json.loads(subprocess.check_output([str(PYTHON), "-c", code], cwd=ROOT, text=True))


def start_process(command, *, cwd=ROOT):
    options = {}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    return subprocess.Popen(list(map(str, command)), cwd=cwd, **options)


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def wait_ready(process, port):
    deadline = time.monotonic() + 30
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"API exited with code {process.returncode}")
        try:
            with opener.open(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    raise RuntimeError("API did not become ready in 30 seconds")


def main():
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt

    if os.name == "nt":
        signal.signal(signal.SIGBREAK, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Prepare/migrate/seed then exit")
    args = parser.parse_args()
    children = []
    try:
        npm = prepare(args.dev)
        if args.prepare_only:
            return 0
        settings = configuration()
        command = [PYTHON, "-m", "uvicorn", "backend.app.main:app", "--host",
                   settings["app_host"], "--port", settings["app_port"], "--workers", "1"]
        if args.dev:
            command.extend(["--reload", "--reload-dir", "backend"])
        api = start_process(command)
        children.append(api)
        wait_ready(api, settings["app_port"])
        if args.dev:
            children.append(start_process([npm, "run", "dev", "--", "--port", settings["vite_port"]], cwd=ROOT / "frontend"))
            print(f"Open http://127.0.0.1:{settings['vite_port']} (development)", flush=True)
        else:
            print(f"Open http://127.0.0.1:{settings['app_port']}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
        for child in children:
            if child.poll() is not None:
                raise RuntimeError(f"A server stopped unexpectedly (code {child.returncode})")
    except KeyboardInterrupt:
        print("\nStopping servers...", flush=True)
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"\nStartup failed: {error}", file=sys.stderr, flush=True)
        return 1
    finally:
        for child in reversed(children):
            stop_process(child)


if __name__ == "__main__":
    raise SystemExit(main())
