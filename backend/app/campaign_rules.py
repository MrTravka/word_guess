"""Bounded campaign parameters; lengths are reproducible without fixing answers."""

import secrets


def level_length(level: int) -> int:
    if level <= 20:
        return 4
    if level <= 40:
        return 4 if level % 2 else 5
    if level <= 60:
        return 5
    if level <= 100:
        return 5 if level % 2 else 6
    # Each hundred late levels has exactly 20/35/45 lengths, interleaved.
    slot = ((level - 101) * 37) % 100
    return 4 if slot < 20 else 5 if slot < 55 else 6


def hard_percent(level: int) -> int:
    return 0 if level <= 100 else min(35, 10 + (level - 100) // 8)


def preferred_difficulty(level: int) -> int:
    roll = secrets.randbelow(100)
    if level <= 40:
        return 1
    if level <= 60:
        return 1 if roll < 50 else 2
    if level <= 100:
        return 1 if roll < 25 else 2
    hard = hard_percent(level)
    return 3 if roll < hard else 1 if roll < hard + 25 else 2


def victory_stars(attempts: int, hints: int) -> int:
    return 1 if hints or attempts >= 5 else 2 if attempts >= 3 else 3
