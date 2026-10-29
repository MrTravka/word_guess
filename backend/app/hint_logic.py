"""Derive allowed hint targets from accepted feedback and saved hint outcomes."""

from sqlalchemy import select

from .economy_models import HintUse
from .economy_rules import ALPHABET, CATALOG, ELIMINATE_LIMIT, LETTER_HINT_LIMIT, reward


def unknown_absent_letters(answer, known):
    return [letter for letter in ALPHABET if letter not in answer and letter not in known]


def hint_state(connection, game, guesses, inventory) -> dict:
    uses = [dict(row) for row in connection.execute(select(
        HintUse.kind, HintUse.position, HintUse.letter, HintUse.removed,
    ).where(HintUse.game_id == game["id"]).order_by(HintUse.id)).mappings()]
    revealed = {str(use["position"]): use["letter"] for use in uses if use["position"] is not None}
    correct = {index for guess in guesses for index, mark in enumerate(guess["marks"]) if mark == "correct"}
    unknown = [index for index in range(len(game["answer"])) if index not in correct and str(index) not in revealed]
    known_keys = {letter for guess in guesses for letter in guess["word"]} | set(revealed.values())
    removed = {letter for use in uses for letter in use["removed"]}
    candidates = unknown_absent_letters(game["answer"], known_keys | removed)
    letter_uses = sum(use["kind"] != "eliminate" for use in uses)
    eliminate_uses = sum(use["kind"] == "eliminate" for use in uses)
    options = []
    for kind, item in CATALOG.items():
        reason = ""
        if game["status"] != "active":
            reason = "Партия завершена."
        elif kind != "eliminate" and letter_uses >= LETTER_HINT_LIMIT:
            reason = "Две буквы уже открыты подсказками."
        elif kind != "eliminate" and len(unknown) <= 1:
            reason = "Последнюю неизвестную букву нужно найти самостоятельно."
        elif kind == "eliminate" and eliminate_uses >= ELIMINATE_LIMIT:
            reason = "Лишние буквы уже убраны в этой партии."
        elif kind == "eliminate" and len(candidates) < 3:
            reason = "Нет трёх неизвестных лишних букв."
        elif inventory.get(kind, 0) < 1:
            reason = "В инвентаре нет этой подсказки."
        options.append({"kind": kind, **item, "quantity": inventory.get(kind, 0), "available": not reason, "reason": reason})
    attempt = min(len(guesses) + 1, 6)
    return {
        "uses": uses, "revealed": revealed, "unknown_positions": unknown, "options": options,
        "next_win": reward(len(game["answer"]), attempt, len(uses)),
        "next_win_with_hint": reward(len(game["answer"]), attempt, len(uses) + 1),
    }
