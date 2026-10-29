"""Server-owned rules for word normalization and repeated-letter feedback."""

from collections import Counter
import re

RULES_VERSION = 1
MAX_ATTEMPTS = 6
MODES = {"4": 4, "5": 5, "6": 6}
PRIORITY = {"absent": 0, "present": 1, "correct": 2}


def normalize_word(word: str) -> str:
    return word.strip().lower().replace("ё", "е")


def valid_word(word: str, length: int) -> bool:
    return len(word) == length and re.fullmatch(r"[а-я]+", word) is not None


def evaluate_guess(answer: str, guess: str) -> list[str]:
    if len(answer) != len(guess):
        raise ValueError("Answer and guess must have equal lengths")
    marks = ["absent"] * len(answer)
    remaining = Counter(answer)
    for index, letter in enumerate(guess):
        if letter == answer[index]:
            marks[index] = "correct"
            remaining[letter] -= 1
    for index, letter in enumerate(guess):
        if marks[index] != "correct" and remaining[letter] > 0:
            marks[index] = "present"
            remaining[letter] -= 1
    return marks


def keyboard_status(guesses: list[dict]) -> dict[str, str]:
    result = {}
    for guess in guesses:
        for letter, mark in zip(guess["word"], guess["marks"]):
            if letter not in result or PRIORITY[mark] > PRIORITY[result[letter]]:
                result[letter] = mark
    return result
