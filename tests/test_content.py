"""Content boundaries that cannot be established by counting words alone."""

import copy
import csv
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from prepare_words import normalize, rejection_reason, make_rows
from verify_content import validate_rows


def tag(*extra, pos="NOUN", case="nomn", number="sing"):
    return SimpleNamespace(POS=pos, case=case, number=number, grammemes=set(extra))


class MorphologyTests(unittest.TestCase):
    def test_normalization_merges_yo_case_and_whitespace(self):
        self.assertEqual(normalize(" ЁЛКА "), "елка")

    def test_nouns_must_be_initial_singular_nominative(self):
        for grammar in (tag(pos="ADJF"), tag(number="plur"), tag(case="gent")):
            with self.subTest(grammar=grammar):
                self.assertIsNotNone(rejection_reason("слово", "слово", grammar))
        self.assertEqual(rejection_reason("берегу", "берег", tag()), "not_lemma")

    def test_proper_names_abbreviations_errors_and_plural_only_are_excluded(self):
        for grammeme in ("Name", "Surn", "Patr", "Geox", "Orgn", "Abbr", "Pltm", "Erro", "Vulg"):
            with self.subTest(grammeme=grammeme):
                self.assertEqual(rejection_reason("тест", "тест", tag(grammeme)), "excluded_tags")

    def test_indeclinable_nouns_are_not_mistaken_for_abbreviations(self):
        self.assertIsNone(rejection_reason("кофе", "кофе", tag("Fixd")))

    def test_punctuation_and_latin_letters_are_not_accepted(self):
        for word in ("abcde", "север-юг", "сл0во"):
            self.assertEqual(rejection_reason(word, word, tag()), "not_russian_letters")

    def test_unreviewed_words_are_never_enabled(self):
        candidates = {"елка": {"spellings": {"елка", "ёлка"}, "tags": {"NOUN,inan femn,sing,nomn"}, "ids": {1}}}
        row = make_rows(candidates, {})[0]
        self.assertEqual(row["display_word"], "ёлка")
        self.assertEqual(row["enabled_as_answer"], 0)
        self.assertEqual(row["enabled_as_guess"], 0)
        self.assertEqual(row["difficulty"], "")


class PreparedContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (ROOT / "data/words/candidates.csv").open(encoding="utf-8", newline="") as stream:
            cls.rows = list(csv.DictReader(stream))
        cls.reviews = json.loads((ROOT / "data/words/reviews.json").read_text(encoding="utf-8"))

    def test_each_mode_has_a_thousand_approved_unique_nouns(self):
        counts = validate_rows(self.rows, self.reviews)
        for length in (4, 5, 6):
            self.assertGreaterEqual(counts[length]["answers"], 1000)

    def test_campaign_has_reviewed_hard_words_for_each_length(self):
        for length in (4, 5, 6):
            hard = [row for row in self.rows if row["length"] == str(length)
                    and row["enabled_as_answer"] == "1" and row["difficulty"] == "3"]
            self.assertGreater(len(hard), 0)
            self.assertTrue(all(self.reviews[row["canonical_word"]]["familiarity"] == "challenging" for row in hard))

    def test_normalized_duplicate_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_rows([self.rows[0], self.rows[0]], self.reviews)

    def test_unreviewed_word_cannot_be_silently_promoted(self):
        row = copy.copy(next(r for r in self.rows if r["review_status"] == "pending"))
        row["enabled_as_answer"] = "1"
        with self.assertRaisesRegex(ValueError, "Unreviewed answer"):
            validate_rows([row], {})

    def test_brand_abbreviation_and_unmarked_archaism_are_disabled(self):
        indexed = {r["canonical_word"]: r for r in self.rows}
        for word in ("ауди", "кбит", "нощь", "жопа"):
            with self.subTest(word=word):
                self.assertEqual(indexed[word]["review_status"], "reject")
                self.assertEqual(indexed[word]["enabled_as_answer"], "0")


if __name__ == "__main__":
    unittest.main()
