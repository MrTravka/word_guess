"""Campaign selection and atomic progress. Caller holds the SQLite write lock."""

import secrets
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .campaign_models import CampaignCompletion, CampaignHistory, CampaignProgress, Chest
from .campaign_rules import level_length, preferred_difficulty, victory_stars
from .game_models import Game
from .models import Word


def current_level(connection, user_id: int) -> int:
    return connection.execute(select(CampaignProgress.current_level).where(
        CampaignProgress.user_id == user_id,
    )).scalar_one_or_none() or 1


def select_campaign_word(connection, user_id: int, level: int):
    length = level_length(level)
    words = connection.execute(select(Word.id, Word.canonical_word, Word.display_word, Word.difficulty).where(
        Word.length == length, Word.enabled_as_answer.is_(True),
    )).mappings().all()
    latest = connection.execute(select(CampaignHistory.word_id, CampaignHistory.cycle).where(
        CampaignHistory.user_id == user_id, CampaignHistory.level == level,
    ).order_by(CampaignHistory.id.desc()).limit(1)).mappings().first()
    previous = latest["word_id"] if latest else None
    cycle = latest["cycle"] if latest else 1
    seen = set(connection.execute(select(CampaignHistory.word_id).where(
        CampaignHistory.user_id == user_id, CampaignHistory.level == level, CampaignHistory.cycle == cycle,
    )).scalars())
    candidates = [word for word in words if word["id"] != previous and word["id"] not in seen]
    if not candidates:
        cycle += bool(latest)
        candidates = [word for word in words if word["id"] != previous]
    if not candidates:
        raise HTTPException(503, "Недостаточно новых слов для уровня. Попробуйте позднее.")
    recent = set(connection.execute(select(Game.answer).where(
        Game.user_id == user_id, Game.mode == str(length),
    ).order_by(Game.created_at.desc(), Game.id.desc()).limit(100)).scalars())
    difficulty = preferred_difficulty(level)
    preferred = [word for word in candidates if word["difficulty"] == difficulty]
    if level <= 10 and secrets.randbelow(100) < 80:
        simple = [word for word in preferred if len(set(word["canonical_word"])) == length]
        preferred = simple or preferred
    # Relax recency first, then difficulty, then restart the full length pool.
    pool = ([word for word in preferred if word["canonical_word"] not in recent] or preferred
            or [word for word in candidates if word["canonical_word"] not in recent] or candidates)
    return secrets.choice(pool), cycle


def prepare_campaign(connection, user_id: int):
    connection.execute(sqlite_insert(CampaignProgress).values(user_id=user_id, current_level=1).on_conflict_do_nothing())
    level = current_level(connection, user_id)
    word, cycle = select_campaign_word(connection, user_id, level)
    return level, word, cycle


def complete_campaign(connection, game, attempts: int, hints: int) -> None:
    level = game["campaign_level"]
    if level is None or game["status"] != "won":
        return
    changed = connection.execute(update(CampaignProgress).where(
        CampaignProgress.user_id == game["user_id"], CampaignProgress.current_level == level,
    ).values(current_level=level + 1))
    if changed.rowcount != 1:
        raise HTTPException(409, "Уровень уже пройден. Обновите кампанию.")
    connection.execute(insert(CampaignCompletion).values(
        user_id=game["user_id"], level=level, game_id=game["id"], stars=victory_stars(attempts, hints),
    ))
    if level % 10 == 0:
        connection.execute(insert(Chest).values(
            id=str(uuid4()), user_id=game["user_id"], level=level, game_id=game["id"], created_at=int(time.time()),
        ))


def game_campaign_result(connection, game):
    if game["campaign_level"] is None:
        return None
    stars = connection.execute(select(CampaignCompletion.stars).where(
        CampaignCompletion.game_id == game["id"],
    )).scalar_one_or_none()
    chest = connection.execute(select(Chest.id).where(Chest.game_id == game["id"])).scalar_one_or_none()
    return {"level": game["campaign_level"], "stars": stars, "chest_id": chest,
            "current_level": current_level(connection, game["user_id"])}


def campaign_page(connection, user_id: int, chapter: int | None) -> dict:
    level = current_level(connection, user_id)
    current_chapter = (level - 1) // 20 + 1
    chapter = chapter or current_chapter
    if chapter > current_chapter + 1:
        raise HTTPException(404, "Эта глава пока недоступна.")
    first = (chapter - 1) * 20 + 1
    stars = dict(connection.execute(select(CampaignCompletion.level, CampaignCompletion.stars).where(
        CampaignCompletion.user_id == user_id, CampaignCompletion.level.between(first, first + 19),
    )).all())
    chests = dict(connection.execute(select(Chest.level, Chest.id).where(
        Chest.user_id == user_id, Chest.level.between(first, first + 19),
    )).all())
    total = connection.execute(select(func.count()).select_from(Chest).where(Chest.user_id == user_id)).scalar_one()
    return {
        "current_level": level, "current_chapter": current_chapter, "chapter": chapter,
        "previous_chapter": chapter - 1 if chapter > 1 else None,
        "next_chapter": chapter + 1 if chapter <= current_chapter else None,
        "chests": total,
        "levels": [{"level": number, "length": level_length(number), "stars": stars.get(number, 0),
                    "status": "completed" if number < level else "current" if number == level else "locked",
                    "milestone": number % 10 == 0, "chest_id": chests.get(number)}
                   for number in range(first, first + 20)],
    }
