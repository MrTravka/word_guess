"""Repeated letters must consume only the unmatched answer's remaining counts."""

import pytest

from backend.app.game_rules import evaluate_guess, keyboard_status, normalize_word, valid_word


@pytest.mark.parametrize("answer,guess,expected", [
    ("касса", "маска", ["absent", "correct", "correct", "present", "correct"]),
    ("банка", "атака", ["present", "absent", "absent", "correct", "correct"]),
    ("касса", "сосна", ["present", "absent", "correct", "absent", "correct"]),
    ("топот", "потоп", ["present", "correct", "present", "correct", "absent"]),
    ("слово", "слово", ["correct"] * 5),
    ("слово", "парта", ["absent"] * 5),
    ("тест", "тетя", ["correct", "correct", "present", "absent"]),
])
def test_repeated_letter_feedback(answer, guess, expected):
    assert evaluate_guess(answer, guess) == expected


def test_normalization_and_validation():
    assert normalize_word("  ЁЛКА ") == "елка"
    assert valid_word("елка", 4)
    for word in ("ёлка", "кот", "вера!", "кoфе", "1234", "мама папа"):
        assert not valid_word(word, 4)
    with pytest.raises(ValueError):
        evaluate_guess("слово", "тест")


def test_keyboard_never_downgrades_previous_feedback():
    guesses = [
        {"word": "сосна", "marks": ["present", "absent", "correct", "absent", "correct"]},
        {"word": "соска", "marks": ["absent", "absent", "present", "absent", "present"]},
    ]
    assert keyboard_status(guesses) == {"с": "correct", "о": "absent", "н": "absent", "а": "correct", "к": "absent"}
