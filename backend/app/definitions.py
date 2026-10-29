"""Local licensed definitions; callers must only use this after game completion."""

from functools import lru_cache
import json

from .config import ROOT


@lru_cache(maxsize=1)
def definitions() -> dict:
    return json.loads((ROOT / "data/definitions/entries.json").read_text(encoding="utf-8"))


def definition_for(word: str) -> dict | None:
    entry = definitions().get(word)
    if entry is None:
        return None
    return {
        "text": entry["text"], "url": entry["url"], "source": "Русский Викисловарь / Kaikki",
        "license": "CC BY-SA 4.0", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
    }
