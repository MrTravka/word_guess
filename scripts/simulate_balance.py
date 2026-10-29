"""Reproducible scenario report using production reward and chest rules."""

import argparse
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path
import random
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.campaign_rules import level_length
from backend.app.chest_rules import DUPLICATE_COINS, PRIZES, roll_prize
from backend.app.economy_rules import CATALOG, reward
from backend.app.version import VERSION

ATTEMPTS = (2, 13, 30, 30, 18, 7)


def report(samples=100000, seed=20261029):
    rng = random.Random(seed)
    categories, rarity = Counter(), Counter()
    cash = compensation = 0
    skins = set()
    duplicates = 0
    with patch("backend.app.chest_rules.secrets.randbelow", side_effect=rng.randrange):
        for _ in range(samples):
            prize = roll_prize()
            categories[prize["title"]] += 1
            rarity[prize["rarity"]] += 1
            cash += prize["coins"]
            if prize["kind"] == "skin":
                skin = rng.randrange(6)
                if skin in skins:
                    compensation += DUPLICATE_COINS
                    duplicates += 1
                skins.add(skin)
    base_chest = sum(Fraction(item["coins"] * item["weight"], 10000) for item in PRIZES)
    means = {length: sum(Fraction(weight, 100) * reward(length, attempt, 0)["coins"]
                         for attempt, weight in enumerate(ATTEMPTS, 1)) for length in (4, 5, 6)}
    lengths = Counter(level_length(level) for level in range(101, 10101))
    campaign_base = sum(Fraction(count, 10000) * means[length] for length, count in lengths.items())
    campaign_with_chests = campaign_base + base_chest / 10
    collection_chests = sum(Fraction(6, count) for count in range(1, 7)) * 100
    return {
        "version": VERSION, "seed": seed, "chest_samples": samples,
        "assumptions": {
            "attempt_distribution_on_wins_percent": list(ATTEMPTS),
            "campaign_length_window": "101..10100", "chests_opened_per_wins": "1/10",
            "note": "Scenario assumptions, not observed human performance. Losses pay zero; hints do not reduce coins.",
        },
        "chests": {
            "expected_base_coins": float(base_chest), "observed_base_coins": round(cash / samples, 4),
            "observed_coins_with_duplicate_compensation": round((cash + compensation) / samples, 4),
            "expected_coins_when_all_skins_owned": float(base_chest + Fraction(DUPLICATE_COINS, 100)),
            "counts": dict(categories), "rarity_counts": dict(rarity), "unique_skins": len(skins), "duplicates": duplicates,
            "expected_chests_for_all_six_skins": float(collection_chests),
            "expected_campaign_wins_for_all_six_skins": float(collection_chests * 10),
        },
        "coins_per_win": {str(length): round(float(mean), 4) for length, mean in means.items()},
        "campaign": {
            "length_counts": {str(length): count for length, count in sorted(lengths.items())},
            "coins_per_win_without_chests": round(float(campaign_base), 4),
            "coins_per_win_with_chests": round(float(campaign_with_chests), 4),
        },
        "wins_to_buy_hint": {kind: {
            "price": item["price"],
            "free_play_equal_lengths": round(item["price"] / float(sum(means.values()) / 3), 2),
            "campaign_with_chests": round(item["price"] / float(campaign_with_chests), 2),
        } for kind, item in CATALOG.items()},
        "conclusion": "Keep planned prices/rewards. Letter hints fit roughly 2–5 campaign wins; eliminate is intentionally cheaper. Human calibration remains pending.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=20261029)
    parser.add_argument("--output", type=Path, default=ROOT / "data/balance/report.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.samples < 1000:
        parser.error("Use at least 1000 chest samples")
    result = report(args.samples, args.seed)
    encoded = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != encoded:
            parser.exit(1, "Balance report is outdated\n")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    print(f"Chest samples: {args.samples}; base coins expected={result['chests']['expected_base_coins']}, observed={result['chests']['observed_base_coins']}")
    print("Rarity counts: " + json.dumps(result["chests"]["rarity_counts"]))
    print("Coins per win: " + json.dumps(result["coins_per_win"]))
    print("Campaign with chests: " + str(result["campaign"]["coins_per_win_with_chests"]))
    print("Balance report reproduction OK" if args.check else f"Report written: {args.output}")


if __name__ == "__main__":
    main()
