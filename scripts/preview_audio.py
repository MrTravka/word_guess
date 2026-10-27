"""Local, user-started looping preview of the supplied ost.mp3 (no app yet)."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PAGE = """<!doctype html>
<html lang="ru"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>word_guess — проверка музыки</title>
<style>
body { font: 1rem system-ui; max-width: 40rem; margin: 3rem auto; padding: 1rem;
       background: #f5f7f6; color: #14231b; }
audio { width: 100%; } a { color: #15803d; }
@media (prefers-color-scheme: dark) {
  body { background: #101713; color: #f1f7f3; }
}
</style>
<h1>Проверка музыки</h1>
<p>Нажмите «Воспроизвести». После окончания трек повторяется автоматически.
Громкость и пауза доступны в проигрывателе.</p>
<audio aria-label="Музыка игры, циклическое воспроизведение"
       controls loop preload="none" src="/ost.mp3"></audio>
<p>Это локальная проверка исходного MP3. Бесшовность музыкального стыка
нужно оценить на слух; браузерный повтор сам по себе её не гарантирует.</p>
</html>""".encode("utf-8")


class PreviewHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.respond(head=True)

    def do_GET(self):
        self.respond(head=False)

    def respond(self, *, head):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE)))
            self.end_headers()
            if not head:
                self.wfile.write(PAGE)
        elif self.path == "/ost.mp3":
            # Serve this file only; do not expose the project directory.
            with (ROOT / "ost.mp3").open("rb") as audio:
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str((ROOT / "ost.mp3").stat().st_size))
                self.end_headers()
                if not head:
                    shutil.copyfileobj(audio, self.wfile)
        else:
            self.send_error(404)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    if not (ROOT / "ost.mp3").is_file():
        raise SystemExit("Place ost.mp3 in the project root first")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), PreviewHandler)
    print(f"Open http://127.0.0.1:{args.port} — Ctrl+C to stop", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
