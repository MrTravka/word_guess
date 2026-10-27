"""Download the pinned research source and verify local attribution files."""

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "words" / "sources.json"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked_path(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Path outside project: {relative}")
    return path


def fetch(asset, check_only):
    path = checked_path(asset["path"])
    expected = asset["sha256"]
    if path.exists():
        if digest(path) != expected:
            raise ValueError(f"Checksum mismatch, existing file kept: {asset['path']}")
    elif check_only:
        raise ValueError(f"Missing asset: {asset['path']}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".part")
        try:
            request = urllib.request.Request(asset["url"], headers={"User-Agent": "word_guess-content/1"})
            with urllib.request.urlopen(request, timeout=60) as response:
                with temporary.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
            if digest(temporary) != expected:
                raise ValueError(f"Downloaded checksum mismatch: {asset['path']}")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    print(f"SHA256 OK: {asset['path']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify offline; never download")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for asset in manifest["assets"]:
        fetch(asset, args.check)


if __name__ == "__main__":
    main()
