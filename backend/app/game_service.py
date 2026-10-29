"""Transactional game transitions; never return internal answer snapshots early."""

import secrets
import time
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import insert, select, update

from .definitions import definition_for
from .game_models import Game, GameOperation, GameStart, Guess
from .game_rules import MAX_ATTEMPTS, MODES, RULES_VERSION, evaluate_guess, keyboard_status, normalize_word, valid_word
from .models import Word
from .economy_models import GameReward
from .economy_service import record_result, wallet_state
from .hint_logic import hint_state
from .campaign_models import CampaignHistory
from .campaign_service import game_campaign_result, prepare_campaign


def mode_condition(mode: str):
    return Game.campaign_level.is_not(None) if mode == "campaign" else (
        (Game.mode == mode) & Game.campaign_level.is_(None)
    )


def game_mode(game) -> str:
    return "campaign" if game["campaign_level"] is not None else game["mode"]


def owned_game(connection, game_id: str, user_id: int):
    game = connection.execute(select(Game).where(Game.id == game_id, Game.user_id == user_id)).mappings().first()
    if game is None:
        raise HTTPException(404, "Партия не найдена.")
    return game


def public_game(connection, game) -> dict:
    guesses = [dict(row) for row in connection.execute(select(Guess.number, Guess.word, Guess.marks).where(
        Guess.game_id == game["id"],
    ).order_by(Guess.number)).mappings()]
    result = {
        "id": game["id"], "mode": game_mode(game), "length": len(game["answer"]),
        "status": game["status"], "version": game["version"], "rules_version": game["rules_version"],
        "max_attempts": MAX_ATTEMPTS, "guesses": guesses, "keyboard": keyboard_status(guesses),
    }
    result["economy"] = wallet_state(connection, game["user_id"])
    hints = hint_state(connection, game, guesses, result["economy"]["inventory"])
    result["hints"] = hints
    for use in hints["uses"]:
        for letter in use["removed"]:
            result["keyboard"].setdefault(letter, "absent")
        if use["letter"] is not None:
            result["keyboard"][use["letter"]] = "correct"
    saved = connection.execute(select(GameReward.points, GameReward.coins, GameReward.hints).where(GameReward.game_id == game["id"])).mappings().first()
    result["reward"] = dict(saved) if saved else None
    result["campaign"] = game_campaign_result(connection, game)
    if game["status"] != "active":
        result["answer"] = {"word": game["display_answer"], "definition": definition_for(game["answer"])}
    return result


def create_game(connection, user_id: int, mode: str, operation_key: str) -> dict:
    previous_request = connection.execute(select(Game).join(GameStart, GameStart.game_id == Game.id).where(
        GameStart.user_id == user_id, GameStart.operation_key == operation_key,
    )).mappings().first()
    if previous_request:
        if game_mode(previous_request) != mode:
            raise HTTPException(409, "Этот ключ уже использован для другого режима.")
        return public_game(connection, previous_request)
    active = connection.execute(select(Game).where(
        Game.user_id == user_id, mode_condition(mode), Game.status == "active",
    )).mappings().first()
    if active:
        connection.execute(insert(GameStart).values(user_id=user_id, operation_key=operation_key, game_id=active["id"]))
        return public_game(connection, active)
    level, cycle = None, None
    if mode == "campaign":
        level, word, cycle = prepare_campaign(connection, user_id)
    else:
        words = connection.execute(select(Word.id, Word.canonical_word, Word.display_word).where(
            Word.length == MODES[mode], Word.enabled_as_answer.is_(True),
        )).mappings().all()
        if not words:
            raise HTTPException(503, "Словарь временно недоступен. Попробуйте позднее.")
        word = secrets.choice(words)
    game_id = str(uuid4())
    connection.execute(insert(Game).values(
        id=game_id, user_id=user_id, mode=str(len(word["canonical_word"])),
        campaign_level=level, word_id=word["id"],
        answer=word["canonical_word"], display_answer=word["display_word"],
        rules_version=RULES_VERSION, status="active", version=0,
        created_at=time.time_ns(), finished_at=None,
    ))
    if level is not None:
        connection.execute(insert(CampaignHistory).values(
            user_id=user_id, level=level, cycle=cycle, word_id=word["id"], game_id=game_id,
        ))
    connection.execute(insert(GameStart).values(user_id=user_id, operation_key=operation_key, game_id=game_id))
    return public_game(connection, owned_game(connection, game_id, user_id))


def mutate_game(connection, user_id: int, game_id: str, kind: str, data) -> dict:
    game = owned_game(connection, game_id, user_id)
    word = normalize_word(data.word) if kind == "guess" else None
    key = str(data.operation_id)
    replay = connection.execute(select(GameOperation).where(
        GameOperation.game_id == game_id, GameOperation.operation_key == key,
    )).mappings().first()
    if replay:
        if (replay["kind"], replay["word"], replay["expected_version"]) != (kind, word, data.version):
            raise HTTPException(409, "Этот ключ уже использован для другого действия.")
        return public_game(connection, game)
    if game["status"] != "active":
        raise HTTPException(409, "Партия уже завершена. Обновите её состояние.")
    if data.version != game["version"]:
        raise HTTPException(409, "Партия изменилась в другой вкладке. Состояние будет обновлено.")
    if game["rules_version"] != RULES_VERSION:
        raise HTTPException(409, "Для этой партии требуется другая версия правил.")
    status = "surrendered" if kind == "surrender" else "active"
    if kind == "guess":
        length = MODES[game["mode"]]
        if not valid_word(word, length):
            raise HTTPException(422, f"Введите слово из {length} русских букв.")
        guesses = connection.execute(select(Guess.word).where(Guess.game_id == game_id)).scalars().all()
        if word in guesses:
            raise HTTPException(422, "Это слово уже проверено. Попытка не потрачена.")
        allowed = connection.execute(select(Word.id).where(
            Word.canonical_word == word, Word.enabled_as_guess.is_(True),
        )).first()
        # A seed update must never make the current game's own answer invalid.
        if allowed is None and word != game["answer"]:
            raise HTTPException(422, "Такого существительного нет в словаре. Попытка не потрачена.")
        number = len(guesses) + 1
        if number > MAX_ATTEMPTS:
            raise HTTPException(409, "Все попытки использованы.")
        marks = evaluate_guess(game["answer"], word)
        connection.execute(insert(Guess).values(game_id=game_id, number=number, word=word, marks=marks))
        status = "won" if word == game["answer"] else "lost" if number == MAX_ATTEMPTS else "active"
    connection.execute(insert(GameOperation).values(
        game_id=game_id, operation_key=key, kind=kind, word=word, expected_version=data.version,
    ))
    finished_at_ns = time.time_ns() if status != "active" else None
    connection.execute(update(Game).where(Game.id == game_id).values(
        version=game["version"] + 1, status=status,
        finished_at=finished_at_ns // 1000000000 if finished_at_ns is not None else None,
        finished_at_ns=finished_at_ns,
    ))
    finished = owned_game(connection, game_id, user_id)
    record_result(connection, finished)
    return public_game(connection, finished)
