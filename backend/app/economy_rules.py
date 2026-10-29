"""One server-side source for prices, inventory kinds and reward arithmetic."""

from fractions import Fraction

START_COINS = 150
START_HINT = "random_letter"
CATALOG = {
    "random_letter": {"title": "Случайная буква", "price": 60, "description": "Открыть букву в случайной неизвестной позиции."},
    "position_letter": {"title": "Буква на выбранном месте", "price": 100, "description": "Выбрать неизвестную позицию и открыть букву."},
    "eliminate": {"title": "Убрать лишние", "price": 25, "description": "Убрать три неизвестные буквы, которых нет в ответе."},
}
BASE_POINTS = (120, 100, 80, 60, 40, 20)
BASE_COINS = (30, 25, 20, 15, 10, 5)
LENGTH_MULTIPLIER = {4: Fraction(1), 5: Fraction(5, 4), 6: Fraction(3, 2)}
LETTER_HINT_LIMIT = 2
ELIMINATE_LIMIT = 1
ALPHABET = "абвгдежзийклмнопрстуфхцчшщъыьэюя"


def reward(length: int, attempt: int, hints: int) -> dict[str, int]:
    if length not in LENGTH_MULTIPLIER or not 1 <= attempt <= 6 or hints < 0:
        raise ValueError("Invalid reward inputs")
    multiplier = LENGTH_MULTIPLIER[length]
    penalty = max(Fraction(1, 4), Fraction(3, 4) ** hints)
    return {"points": int(BASE_POINTS[attempt - 1] * multiplier * penalty),
            "coins": int(BASE_COINS[attempt - 1] * multiplier)}
