"""Prepare isolated browser fixtures through production game/reward services."""

from pathlib import Path
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import insert, select

from backend.app.config import Settings
from backend.app.database import create_database
from backend.app.economy_service import initialize_account
from backend.app.game_service import create_game, mutate_game, owned_game
from backend.app.models import User, UserSettings, Word


def play(connection, user_id, mode, attempts=1, surrender=False):
    game = create_game(connection, user_id, mode, str(uuid4()))
    if surrender:
        mutate_game(connection, user_id, game["id"], "surrender", SimpleNamespace(version=0, operation_id=uuid4()))
        return
    answer = owned_game(connection, game["id"], user_id)["answer"]
    guesses = connection.execute(select(Word.canonical_word).where(
        Word.length == len(answer), Word.enabled_as_guess.is_(True), Word.canonical_word != answer,
    ).order_by(Word.id).limit(attempts - 1)).scalars().all()
    for word in [*guesses, answer]:
        game = mutate_game(connection, user_id, game["id"], "guess", SimpleNamespace(
            word=word, version=game["version"], operation_id=uuid4(),
        ))


def main():
    database = Path(sys.argv[1]).resolve()
    # This helper must never write to a user's runtime DB.
    cache = Path(__file__).resolve().parents[1] / ".cache"
    if cache not in database.parents or not database.parent.name.startswith("accounts-browser-"):
        raise RuntimeError("Browser fixtures require their isolated .cache directory")
    engine = create_database(Settings(_env_file=None, database_url=f"sqlite:///{database.as_posix()}"))
    try:
        with engine.connect() as connection:
            owner = connection.execute(select(User).where(User.login == "leaderboards_browser")).mappings().one()
        for index in range(25):
            with engine.connect().execution_options(sqlite_immediate=True) as connection, connection.begin():
                name = "Я" * 40 if index == 0 else "<img src=x onerror=alert(1)>" if index == 1 else f"Игрок {index + 1:02}"
                user_id = connection.execute(insert(User).values(
                    login=f"rank_fixture_{index:02}", display_name=name,
                    password_hash=owner["password_hash"], created_at=int(time.time()),
                )).inserted_primary_key[0]
                connection.execute(insert(UserSettings).values(user_id=user_id, theme="system"))
                initialize_account(connection, user_id)
                for mode in ("4", "5", "6", "campaign"):
                    play(connection, user_id, mode)
        with engine.connect().execution_options(sqlite_immediate=True) as connection, connection.begin():
            play(connection, owner["id"], "4", attempts=4)
            play(connection, owner["id"], "5", attempts=3)
            play(connection, owner["id"], "5", surrender=True)
            play(connection, owner["id"], "campaign", attempts=6)
        print("25 opponents, four modes and saved personal results ready")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
