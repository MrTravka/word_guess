"""Cross-check additional guess-only nouns without expanding the answer pool."""

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORDS = ROOT / "data/words"
EVIDENCE = "Wiktionary/Kaikki:2026-10-01"


def prepare_reviews(rows, reviews, definitions):
    # Regenerate only automatic decisions; retain editorial answers/rejections.
    result = {word: review for word, review in reviews.items()
              if not (review["decision"] == "guess" and review.get("evidence") == EVIDENCE)}
    for row in rows:
        word = row["canonical_word"]
        if word not in result and word in definitions:
            result[word] = {
                "decision": "guess", "evidence": EVIDENCE, "evidence_url": definitions[word]["url"],
                "reason": "Только допустимый ввод: начальная форма NOUN/sing/nomn из OpenCorpora подтверждена русской статьёй существительного в Викисловаре. Редкость не оценивалась; как ответ не используется.",
            }
    return dict(sorted(result.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check decisions without writing")
    args = parser.parse_args()
    definitions = json.loads((ROOT / "data/definitions/entries.json").read_text(encoding="utf-8"))
    reviews = json.loads((WORDS / "reviews.json").read_text(encoding="utf-8"))
    with (WORDS / "candidates.csv").open(encoding="utf-8", newline="") as stream:
        result = prepare_reviews(list(csv.DictReader(stream)), reviews, definitions)
    data = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path = WORDS / "reviews.json"
    if args.check:
        if path.read_bytes() != data:
            raise SystemExit("Guess-only decisions are outdated")
    else:
        path.write_bytes(data)
    print(f"Cross-checked guess-only nouns: {sum(review['decision'] == 'guess' for review in result.values())}")


if __name__ == "__main__":
    main()
