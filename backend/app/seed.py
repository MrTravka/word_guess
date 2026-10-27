"""Atomic, repeatable import of prepared server-side dictionary data."""

import csv
from datetime import datetime, timezone
import hashlib

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Engine

from .config import WORDS_FILE
from .models import DictionaryVersion, Word


def seed_words(engine: Engine) -> int:
    checksum = hashlib.sha256(WORDS_FILE.read_bytes()).hexdigest()
    with WORDS_FILE.open(encoding="utf-8", newline="") as source:
        rows = [
            {
                "canonical_word": row["canonical_word"], "display_word": row["display_word"],
                "length": int(row["length"]),
                "difficulty": int(row["difficulty"]) if row["difficulty"] else None,
                "familiarity": row["familiarity"], "source": row["source"],
                "enabled_as_answer": row["enabled_as_answer"] == "1",
                "enabled_as_guess": row["enabled_as_guess"] == "1",
            }
            for row in csv.DictReader(source)
        ]
    # Serialize simultaneous initializers before any read-modify-write.
    with engine.connect().execution_options(sqlite_immediate=True) as connection:
        with connection.begin():
            current = connection.execute(select(DictionaryVersion.id).where(
                DictionaryVersion.checksum == checksum,
            )).scalar_one_or_none()
            last_applied = connection.execute(select(DictionaryVersion.id).order_by(
                DictionaryVersion.imported_at.desc(), DictionaryVersion.id.desc(),
            ).limit(1)).scalar_one_or_none()
            if current is not None and current == last_applied:
                return 0
            if current is None:
                version_id = connection.execute(insert(DictionaryVersion).values(
                    checksum=checksum, source="OpenCorpora:0.92:417150",
                    imported_at=datetime.now(timezone.utc),
                ).returning(DictionaryVersion.id)).scalar_one()
            else:
                version_id = current
                connection.execute(update(DictionaryVersion).where(DictionaryVersion.id == current).values(
                    imported_at=datetime.now(timezone.utc),
                ))
            connection.execute(update(Word).values(enabled_as_answer=False, enabled_as_guess=False))
            for row in rows:
                row["dictionary_version_id"] = version_id
            statement = insert(Word)
            connection.execute(statement.on_conflict_do_update(
                index_elements=[Word.canonical_word],
                set_={key: getattr(statement.excluded, key) for key in rows[0] if key != "canonical_word"},
            ), rows)
    return len(rows)
