"""Definition provenance and guess-only promotion boundaries."""

import json
from pathlib import Path

from prepare_definitions import noun_definitions, verify_definitions
from prepare_guesses import EVIDENCE, prepare_reviews
from prepare_words import make_rows


def entry(**changes):
    return {"word": "слово", "lang_code": "ru", "pos": "noun", "senses": [{"glosses": ["Единица человеческой речи."]}], **changes}


def test_noun_definitions_exclude_other_languages_forms_and_unsafe_labels():
    for changes in ({"lang_code": "uk"}, {"pos": "name"}, {"word": "Слава"},
                    {"tags": ["archaic"]}, {"senses": [{"form_of": [{"word": "слово"}], "glosses": ["форма другого слова"]}]},
                    {"senses": [{"glosses": ["обсц. недопустимое толкование"]}]}):
        assert list(noun_definitions(entry(**changes))) == []
    assert list(noun_definitions(entry())) == [("слово", "Единица человеческой речи.")]


def test_only_short_plain_gloss_is_kept_without_examples():
    result = list(noun_definitions(entry(senses=[{"glosses": ["Слово " * 100], "examples": [{"text": "Не копировать пример"}]}])))
    assert len(result[0][1]) <= 360 and result[0][1].endswith("…")
    assert "пример" not in result[0][1]


def test_guess_promotion_never_overrides_editorial_answers_or_rejections():
    definitions = {word: {"url": f"https://ru.wiktionary.org/wiki/{word}"} for word in ("слово", "форма", "марка", "гений")}
    reviews = {"слово": {"decision": "answer"}, "марка": {"decision": "reject"}}
    rows = [{"canonical_word": word} for word in definitions]
    result = prepare_reviews(rows, reviews, definitions)
    assert result["слово"] == reviews["слово"] and result["марка"] == reviews["марка"]
    assert result["форма"]["decision"] == "guess" and result["форма"]["evidence"] == EVIDENCE
    assert prepare_reviews(rows, result, definitions) == result


def test_cross_checked_guess_is_not_an_answer():
    candidate = {"форма": {"spellings": {"форма"}, "tags": {"NOUN,inan femn,sing,nomn"}, "ids": {1}}}
    row = make_rows(candidate, {"форма": {"decision": "guess"}})[0]
    assert row["enabled_as_guess"] == 1 and row["enabled_as_answer"] == 0
    assert row["difficulty"] == "" and row["familiarity"] == "unreviewed"


def test_local_definitions_have_verified_attribution_and_coverage():
    verify_definitions()
    root = Path(__file__).resolve().parents[1]
    report = json.loads((root / "data/definitions/report.json").read_text(encoding="utf-8"))
    assert report["total"] > 3000
    assert all(report["answer_coverage"][str(length)] > 900 for length in (4, 5, 6))
