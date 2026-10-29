"""Read-only aggregates of saved results, in the caller's SQLite snapshot."""

from fastapi import HTTPException
from sqlalchemy import case, func, literal, select

from .campaign_models import CampaignProgress
from .economy_models import GameReward
from .game_models import Game, Guess
from .game_service import mode_condition
from .models import User

PAGE_SIZE = 20


def personal_statistics(connection, user_id: int, mode: str) -> dict:
    finished = select(
        Game.id, Game.status, Game.created_at,
        func.coalesce(Game.finished_at_ns, Game.finished_at * 1000000000).label("finished_at_ns"), GameReward.points,
        func.count(Guess.id).label("attempts"),
    ).join(GameReward, GameReward.game_id == Game.id).outerjoin(Guess, Guess.game_id == Game.id).where(
        Game.user_id == user_id, mode_condition(mode), Game.status != "active",
    ).group_by(Game.id).subquery()
    won = finished.c.status == "won"
    summary = connection.execute(select(
        func.count().label("games"), func.coalesce(func.sum(case((won, 1), else_=0)), 0).label("wins"),
        func.coalesce(func.sum(finished.c.points), 0).label("points"),
        func.coalesce(func.sum(case((won, finished.c.attempts), else_=0)), 0).label("winning_attempts"),
        func.coalesce(func.sum(case((finished.c.status == "surrendered", 1), else_=0)), 0).label("surrendered"),
    ).select_from(finished)).mappings().one()
    distribution = dict(connection.execute(select(finished.c.attempts, func.count()).where(won).group_by(
        finished.c.attempts,
    )).all())
    # Each loss starts a new group; count wins within groups without loading history.
    sequence = select(finished.c.status, func.sum(case((won, 0), else_=1)).over(
        order_by=[finished.c.finished_at_ns, finished.c.created_at, finished.c.id],
        rows=(None, 0),
    ).label("loss_group")).subquery()
    streaks = select(func.count().label("length")).where(sequence.c.status == "won").group_by(sequence.c.loss_group).subquery()
    best = connection.execute(select(func.coalesce(func.max(streaks.c.length), 0))).scalar_one()
    games, wins = summary["games"], summary["wins"]
    level = connection.execute(select(CampaignProgress.current_level).where(
        CampaignProgress.user_id == user_id,
    )).scalar_one_or_none() if mode == "campaign" else None
    return {
        "mode": mode, "games": games, "wins": wins, "losses": games - wins,
        "surrendered": summary["surrendered"], "points": summary["points"],
        "win_rate": round(wins / games * 100, 2) if games else 0,
        "average_attempts": round(summary["winning_attempts"] / wins, 2) if wins else None,
        "best_streak": best, "current_level": (level or 1) if mode == "campaign" else None,
        "attempt_distribution": [{"attempt": attempt, "wins": distribution.get(attempt, 0)} for attempt in range(1, 7)],
    }


def leaderboard(connection, user: dict, mode: str, page: int) -> dict:
    wins = func.sum(case((Game.status == "won", 1), else_=0))
    totals = select(
        Game.user_id, func.sum(GameReward.points).label("points"), wins.label("wins"),
        func.max(case((Game.status == "won", func.coalesce(Game.finished_at_ns, Game.finished_at * 1000000000)))).label("achieved_at"),
    ).join(GameReward, GameReward.game_id == Game.id).where(
        mode_condition(mode), Game.status != "active",
    ).group_by(Game.user_id).having(wins > 0).subquery()
    order = [totals.c.points.desc(), totals.c.wins.desc(), totals.c.achieved_at, totals.c.user_id]
    ranked = select(
        totals.c.user_id, User.display_name, totals.c.points, totals.c.wins,
        func.row_number().over(order_by=order).label("rank"),
        (func.coalesce(CampaignProgress.current_level, 1) if mode == "campaign" else literal(None)).label("current_level"),
    ).join(User, User.id == totals.c.user_id).outerjoin(
        CampaignProgress, CampaignProgress.user_id == totals.c.user_id,
    ).subquery()
    total = connection.execute(select(func.count()).select_from(totals)).scalar_one()
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    if page > pages:
        raise HTTPException(404, "Такой страницы рейтинга пока нет.")

    def public_entry(row):
        return {key: row[key] for key in ("rank", "display_name", "points", "wins", "current_level")} | {
            "is_self": row["user_id"] == user["id"],
        }

    rows = connection.execute(select(ranked).order_by(ranked.c.rank).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)).mappings()
    entries = [public_entry(row) for row in rows]
    own = connection.execute(select(ranked).where(ranked.c.user_id == user["id"])).mappings().first()
    statistics = personal_statistics(connection, user["id"], mode)
    self_entry = public_entry(own) if own else {
        "rank": None, "display_name": user["display_name"], "points": statistics["points"], "wins": statistics["wins"],
        "current_level": statistics["current_level"], "is_self": True,
    }
    return {"mode": mode, "page": page, "pages": pages, "total": total, "entries": entries,
            "self": self_entry, "self_page": (own["rank"] - 1) // PAGE_SIZE + 1 if own else None,
            "statistics": statistics}
