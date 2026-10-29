"""Prepare short Russian noun definitions from a pinned local Kaikki snapshot."""

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote

from fetch_content import digest, fetch

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "data/definitions"
BLOCKED = {"form-of", "abbreviation", "proper-noun", "obsolete", "archaic", "vulgar", "offensive", "derogatory"}
BAD_TEXT = re.compile(r"(?:^|\s)(?:устар\.|обсц\.|неценз\.|вульг\.|бран\.|груб\.|эвф\.)|значение (?:отсутствует|не указано)")


def normalized(word):
    return word.lower().replace("ё", "е")


def noun_definitions(entry):
    word = entry.get("word", "")
    if entry.get("lang_code") != "ru" or entry.get("pos") != "noun":
        return
    if not re.fullmatch(r"[а-яё]{4,6}", word) or BLOCKED.intersection(entry.get("tags", [])):
        return
    for sense in entry.get("senses", []):
        if sense.get("form_of") or sense.get("alt_of") or BLOCKED.intersection(sense.get("tags", [])):
            continue
        for gloss in sense.get("glosses", []):
            text = " ".join(gloss.split())
            if BAD_TEXT.search(text) or not re.search(r"[а-яё]", text) or len(text) < 10:
                continue
            if len(text) > 360:
                text = text[:357].rsplit(" ", 1)[0] + "…"
            yield word, text


def prepare(snapshot):
    with (ROOT / "data/words/candidates.csv").open(encoding="utf-8", newline="") as stream:
        rows = {row["canonical_word"]: row for row in csv.DictReader(stream)}
    entries, ranks = {}, {}
    with gzip.open(snapshot, "rt", encoding="utf-8") as stream:
        for line in stream:
            for word, text in noun_definitions(json.loads(line)):
                canonical = normalized(word)
                if canonical not in rows:
                    continue
                rank = (word != rows[canonical]["display_word"],)
                if canonical not in ranks or rank < ranks[canonical]:
                    entries[canonical] = {"text": text, "url": "https://ru.wiktionary.org/wiki/" + quote(word), "source_word": word}
                    ranks[canonical] = rank
    return dict(sorted(entries.items())), rows


def serialize(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def verify_definitions():
    manifest = json.loads((DIRECTORY / "source.json").read_text(encoding="utf-8"))
    report = json.loads((DIRECTORY / "report.json").read_text(encoding="utf-8"))
    entries = json.loads((DIRECTORY / "entries.json").read_text(encoding="utf-8"))
    if digest(DIRECTORY / "entries.json") != report["entries_sha256"]:
        raise ValueError("Definitions checksum mismatch")
    for word, entry in entries.items():
        if not re.fullmatch(r"[а-я]{4,6}", word) or not 10 <= len(entry["text"]) <= 360:
            raise ValueError("Invalid definition")
        if normalized(entry["source_word"]) != word or entry["url"] != "https://ru.wiktionary.org/wiki/" + quote(entry["source_word"]):
            raise ValueError("Invalid definition attribution")
    if len(entries) != report["total"]:
        raise ValueError("Definition count mismatch")
    if report["source_sha256"] != manifest["snapshot"]["sha256"]:
        raise ValueError("Definition source mismatch")
    if dict(Counter(str(len(word)) for word in entries)) != report["by_length"]:
        raise ValueError("Definition length counts mismatch")
    with (ROOT / "data/words/candidates.csv").open(encoding="utf-8", newline="") as stream:
        rows = {row["canonical_word"]: row for row in csv.DictReader(stream)}
    if not entries.keys() <= rows.keys():
        raise ValueError("Definitions refer to unknown candidates")
    coverage = {str(length): sum(word in entries and row["enabled_as_answer"] == "1"
        for word, row in rows.items() if len(word) == length) for length in (4, 5, 6)}
    if coverage != report["answer_coverage"]:
        raise ValueError("Definition answer coverage mismatch")
    fetch(manifest["license_asset"], check_only=True)
    print(f"Local noun definitions: {len(entries)}; CC BY-SA 4.0 verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="Download the pinned snapshot when absent")
    parser.add_argument("--check", action="store_true", help="Reproduce without writing")
    args = parser.parse_args()
    manifest = json.loads((DIRECTORY / "source.json").read_text(encoding="utf-8"))
    asset = manifest["snapshot"]
    fetch(asset, check_only=not args.fetch)
    entries, rows = prepare(ROOT / asset["path"])
    content = serialize(entries)
    report = {
        "source_sha256": asset["sha256"], "entries_sha256": hashlib.sha256(content).hexdigest(),
        "total": len(entries), "by_length": dict(sorted(Counter(str(len(word)) for word in entries).items())),
        "answer_coverage": {str(length): sum(word in entries and row["enabled_as_answer"] == "1"
            for word, row in rows.items() if len(word) == length) for length in (4, 5, 6)},
    }
    for name, data in {"entries.json": content, "report.json": serialize(report)}.items():
        path = DIRECTORY / name
        if args.check:
            if path.read_bytes() != data:
                raise SystemExit(f"Outdated definitions: {name}")
        else:
            path.write_bytes(data)
    verify_definitions()


if __name__ == "__main__":
    main()
