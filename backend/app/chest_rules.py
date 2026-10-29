"""Versioned public odds; cryptographic rolls happen only before saving an opening."""

import secrets

TABLE_VERSION = 1
DUPLICATE_COINS = 350
PRIZES = (
    {"kind": "coins", "coins": 40, "weight": 5000, "rarity": "common", "title": "40 монет"},
    {"kind": "coins", "coins": 70, "weight": 3000, "rarity": "common", "title": "70 монет"},
    {"kind": "coins", "coins": 150, "weight": 1200, "rarity": "rare", "title": "150 монет"},
    {"kind": "coins", "coins": 250, "weight": 600, "rarity": "rare", "title": "250 монет"},
    {"kind": "skin", "coins": 0, "weight": 100, "rarity": "very_rare", "title": "Косметический скин"},
    {"kind": "coins", "coins": 1000, "weight": 100, "rarity": "very_rare", "title": "1000 монет"},
)


def roll_prize() -> dict:
    roll = secrets.randbelow(10000)
    for prize in PRIZES:
        if roll < prize["weight"]:
            return {key: value for key, value in prize.items() if key != "weight"}
        roll -= prize["weight"]
    raise RuntimeError("Invalid chest probability table")


def public_odds() -> dict:
    return {"version": TABLE_VERSION, "prizes": [{**prize, "percent": prize["weight"] / 100} for prize in PRIZES],
            "duplicate_coins": DUPLICATE_COINS, "skin_count": 6}


def presentation(prize: dict) -> dict:
    # Decorative cards deliberately do not imitate the probability distribution.
    cards = [{key: value for key, value in PRIZES[index % len(PRIZES)].items() if key != "weight"}
             for index in range(32)]
    cards[26] = prize
    return {"table_version": TABLE_VERSION, "prize": prize, "reel": cards, "winner_index": 26}
