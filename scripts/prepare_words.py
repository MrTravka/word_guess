"""Audit a pinned OpenCorpora snapshot; never promote unreviewed answers."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
from importlib.metadata import version
import io
import json
from pathlib import Path
import re

import pymorphy3

ROOT = Path(__file__).resolve().parents[1]
WORDS = ROOT / "data" / "words"
CYRILLIC = re.compile(r"[а-яё]+")
SOURCE = "OpenCorpora:0.92:417150"
PACKAGES = {
    "pymorphy3": "2.0.6",
    "pymorphy3-dicts-ru": "2.4.417150.4580142",
    "dawg2-python": "0.9.0",
    "setuptools": "84.2.1",
}
EXCLUDED_TAGS = {
    "Name", "Surn", "Patr", "Geox", "Orgn", "Trad", "Abbr", "Init",
    "Pltm", "Erro", "Dist", "Arch", "Slng", "Infr", "Vulg", "Litr",
}
FIELDS = [
    "canonical_word", "display_word", "length", "difficulty", "familiarity",
    "source", "enabled_as_answer", "enabled_as_guess", "review_status",
    "tags", "paradigm_ids",
]


def normalize(word):
    return word.strip().lower().replace("ё", "е")


def rejection_reason(word, normal_form, tag):
    """First failing rule only; counters therefore partition short parses."""
    if tag.POS != "NOUN":
        return "not_noun"
    if tag.case != "nomn" or tag.number != "sing":
        return "not_singular_nominative"
    if word != normal_form:
        return "not_lemma"
    if not CYRILLIC.fullmatch(word):
        return "not_russian_letters"
    if tag.grammemes & EXCLUDED_TAGS:
        return "excluded_tags"
    return None


def extract(dictionary):
    candidates = defaultdict(lambda: {"spellings": set(), "tags": set(), "ids": set()})
    counts = Counter()
    excluded_tags = Counter()
    for word, (para_id, idx) in dictionary.words.iteritems():
        counts["all_word_parses"] += 1
        if len(word) not in (4, 5, 6):
            continue
        counts["short_word_parses"] += 1
        tag = dictionary.build_tag_info(para_id, idx)
        normal_form = dictionary.build_normal_form(para_id, idx, word)
        reason = rejection_reason(word, normal_form, tag)
        if reason:
            counts[reason] += 1
            if reason == "excluded_tags":
                excluded_tags.update(tag.grammemes & EXCLUDED_TAGS)
            continue
        counts["accepted_parses"] += 1
        item = candidates[normalize(word)]
        item["spellings"].add(word)
        item["tags"].add(str(tag))
        item["ids"].add(para_id)
    return candidates, dict(sorted(counts.items())), dict(sorted(excluded_tags.items()))


def load_reviews(candidates):
    reviews = json.loads((WORDS / "reviews.json").read_text(encoding="utf-8"))
    for word, review in reviews.items():
        if word != normalize(word) or word not in candidates:
            raise ValueError(f"Review is not a normalized source candidate: {word}")
        if review["decision"] not in {"answer", "reject"} or not review["reason"]:
            raise ValueError(f"Invalid review: {word}")
        if review["decision"] == "answer":
            if review["difficulty"] not in (1, 2, 3):
                raise ValueError(f"Invalid difficulty: {word}")
            if review["familiarity"] not in {"common", "ordinary", "challenging"}:
                raise ValueError(f"Invalid familiarity: {word}")
    return reviews


def make_rows(candidates, reviews):
    rows = []
    for word, item in sorted(candidates.items()):
        review = reviews.get(word, {})
        decision = review.get("decision", "pending")
        # Prefer original ё spelling; retain every source tag for later review.
        display = min(item["spellings"], key=lambda s: ("ё" not in s, s))
        rows.append({
            "canonical_word": word, "display_word": display, "length": len(word),
            "difficulty": review.get("difficulty", ""),
            "familiarity": review.get("familiarity", "unreviewed"),
            "source": SOURCE, "enabled_as_answer": int(decision == "answer"),
            "enabled_as_guess": int(decision == "answer"),
            "review_status": decision, "tags": " | ".join(sorted(item["tags"])),
            "paradigm_ids": " ".join(map(str, sorted(item["ids"]))),
        })
    return rows


def serialize_rows(rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def make_report(dictionary, candidates, counts, tags, rows, csv_bytes):
    by_length = {}
    for length in (4, 5, 6):
        group = [row for row in rows if row["length"] == length]
        approved = sum(row["enabled_as_answer"] for row in group)
        by_length[str(length)] = {
            "morphological_candidates": len(group), "reviewed_answers": approved,
            "pending_review": sum(row["review_status"] == "pending" for row in group),
            "manually_rejected": sum(row["review_status"] == "reject" for row in group),
            "target": 1000, "candidate_shortfall": max(0, 1000 - len(group)),
            "approved_shortfall": max(0, 1000 - approved),
            "difficulty": dict(sorted(Counter(
                str(row["difficulty"]) for row in group if row["enabled_as_answer"]
            ).items())),
        }
    spellings = sum(len(item["spellings"]) for item in candidates.values())
    return {
        "status": "research_not_release_dictionary",
        "source": SOURCE,
        "dictionary_metadata": dictionary.meta,
        "tool_versions": PACKAGES,
        "exclusion_policy": sorted(EXCLUDED_TAGS),
        "counts": counts,
        "excluded_tag_occurrences_nonexclusive": tags,
        "unique_source_spellings": spellings,
        "yo_e_collisions": spellings - len(candidates),
        "merged_homonym_parses": counts["accepted_parses"] - spellings,
        "by_length": by_length,
        "all_targets_met": all(v["reviewed_answers"] >= 1000 for v in by_length.values()),
        "sha256": {
            "candidates.csv": hashlib.sha256(csv_bytes).hexdigest(),
            "reviews.json": hashlib.sha256((WORDS / "reviews.json").read_bytes()).hexdigest(),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Compare without writing")
    args = parser.parse_args()
    for package, expected in PACKAGES.items():
        if version(package) != expected:
            raise SystemExit(f"Install scripts/content-requirements.txt: {package} != {expected}")
    dictionary = pymorphy3.MorphAnalyzer().dictionary
    if dictionary.meta["source_revision"] != "417150":
        raise SystemExit("Unexpected dictionary revision")
    candidates, counts, tags = extract(dictionary)
    rows = make_rows(candidates, load_reviews(candidates))
    csv_bytes = serialize_rows(rows)
    report = make_report(dictionary, candidates, counts, tags, rows, csv_bytes)
    files = {
        "candidates.csv": csv_bytes,
        "report.json": (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    }
    for name, content in files.items():
        path = WORDS / name
        if args.check:
            if not path.exists() or path.read_bytes() != content:
                raise SystemExit(f"Outdated content: {path.relative_to(ROOT)}")
        else:
            path.write_bytes(content)
    for length, stats in report["by_length"].items():
        print(f"{length}: candidates={stats['morphological_candidates']}, "
              f"answers={stats['reviewed_answers']}, pending={stats['pending_review']}")
    print("Reproduction OK" if args.check else "Content written")
    print("1000 answers per length: " + ("PASS" if report["all_targets_met"] else "NOT MET"))


if __name__ == "__main__":
    main()
