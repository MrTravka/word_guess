"""Offline checks of dictionary counts, review decisions and local assets."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

from fetch_content import fetch

ROOT = Path(__file__).resolve().parents[1]
WORDS = ROOT / "data" / "words"
LABELS = {1: "common", 2: "ordinary", 3: "challenging"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_rows(rows, reviews):
    seen = set()
    counts = {length: Counter() for length in (4, 5, 6)}
    for row in rows:
        word, display = row["canonical_word"], row["display_word"]
        require(re.fullmatch(r"[а-я]{4,6}", word), f"Invalid word: {word}")
        require(display.replace("ё", "е") == word, f"Invalid spelling: {word}")
        require(word not in seen, f"Duplicate normalized word: {word}")
        require(int(row["length"]) == len(word), f"Wrong length: {word}")
        require(row["source"] == "OpenCorpora:0.92:417150", f"Unknown source: {word}")
        require(row["paradigm_ids"] and all(
            part.isdigit() for part in row["paradigm_ids"].split()
        ), f"Missing dictionary evidence: {word}")
        for analysis in row["tags"].split(" | "):
            tags = set(re.split(r"[, ]", analysis))
            require({"NOUN", "sing", "nomn"} <= tags, f"Wrong grammar: {word}")
        review = reviews.get(word, {})
        decision = review.get("decision", "pending")
        require(row["review_status"] == decision, f"Review mismatch: {word}")
        enabled = "1" if decision == "answer" else "0"
        require(row["enabled_as_answer"] == enabled, f"Unreviewed answer: {word}")
        require(row["enabled_as_guess"] == enabled, f"Unreviewed guess: {word}")
        if decision == "answer":
            require(review.get("reason"), f"Missing review reason: {word}")
            difficulty = int(row["difficulty"])
            require(LABELS.get(difficulty) == row["familiarity"], f"Wrong label: {word}")
            require(difficulty == review["difficulty"], f"Difficulty mismatch: {word}")
            require(row["familiarity"] == review["familiarity"], f"Familiarity mismatch: {word}")
            counts[len(word)]["answers"] += 1
            counts[len(word)][f"difficulty_{difficulty}"] += 1
        else:
            require(not row["difficulty"] and row["familiarity"] == "unreviewed",
                    f"Unexpected unapproved difficulty: {word}")
        counts[len(word)]["candidates"] += 1
        counts[len(word)][decision] += 1
        seen.add(word)
    require(set(reviews) <= seen, "Reviews refer to absent source words")
    require([row["canonical_word"] for row in rows] == sorted(seen), "Rows not sorted")
    return counts


def verify(require_target=False):
    report = read_json(WORDS / "report.json")
    reviews = read_json(WORDS / "reviews.json")
    for name, expected in report["sha256"].items():
        require(Path(name).name == name, "Unexpected report path")
        actual = hashlib.sha256((WORDS / name).read_bytes()).hexdigest()
        require(actual == expected, f"Checksum mismatch: {name}")
    with (WORDS / "candidates.csv").open(encoding="utf-8", newline="") as stream:
        counts = validate_rows(list(csv.DictReader(stream)), reviews)
    all_met = True
    for length, actual in counts.items():
        recorded = report["by_length"][str(length)]
        for field, key in (("morphological_candidates", "candidates"),
                           ("reviewed_answers", "answers"), ("pending_review", "pending"),
                           ("manually_rejected", "reject")):
            require(recorded[field] == actual[key], f"Count mismatch: {length}/{field}")
        require(recorded["approved_shortfall"] == max(0, 1000 - actual["answers"]),
                f"Wrong shortfall: {length}")
        require(recorded["target"] == 1000, "Unexpected quantity requirement")
        for difficulty in (1, 2, 3):
            require(recorded["difficulty"].get(str(difficulty), 0) == actual[f"difficulty_{difficulty}"],
                    f"Difficulty count mismatch: {length}")
        all_met &= actual["answers"] >= 1000
        print(f"{length} letters: {actual['answers']} reviewed answers / {actual['candidates']} candidates")
    require(report["all_targets_met"] == all_met, "Wrong target result")
    if require_target:
        require(all_met, "1000 approved answers per length is not met")
    for asset in read_json(WORDS / "sources.json")["assets"]:
        # The raw research wheel is optional for the offline prepared-data check.
        if not asset["path"].startswith("data/sources/"):
            fetch(asset, check_only=True)
    audio = read_json(ROOT / "data/audio/source.json")
    require(audio["loop"] is True and audio["autoplay"] is False, "Wrong audio policy")
    require(audio["permission"], "Missing music permission record")
    fetch({"path": audio["path"], "sha256": audio["sha256"]}, check_only=True)
    require((ROOT / "THIRD_PARTY_NOTICES.md").is_file(), "Missing attribution")
    print("Content, licenses and audio: OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-target", action="store_true", help="Fail below 1000 answers per length")
    args = parser.parse_args()
    verify(args.require_target)


if __name__ == "__main__":
    main()
