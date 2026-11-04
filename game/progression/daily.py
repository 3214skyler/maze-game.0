"""Daily challenge definition: the same maze for every player on a given UTC day. Pure logic."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from game.maze.generators import generate
from game.maze.maze import Maze

ALGORITHMS = ("backtracker", "prim", "kruskal")
SIZES = (10, 12, 14, 16, 18, 20, 22)       # indexed by weekday: gentle on Monday, longest on Sunday


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def daily_seed(day: date) -> int:
    return day.year * 10000 + day.month * 100 + day.day        # e.g. 20261104


def build_daily_maze(day: date) -> Maze:
    size = SIZES[day.weekday()]
    return generate(size, size, seed=daily_seed(day), algorithm=ALGORITHMS[day.toordinal() % len(ALGORITHMS)])


def daily_row(day: date) -> dict:
    """The `daily_challenges` row for a day (what the publisher script uploads)."""
    m = build_daily_maze(day)
    return {"day": day.isoformat(), "seed": m.seed, "algorithm": m.algorithm, "width": m.width,
            "height": m.height, "start_cell": list(m.start), "exit_cell": list(m.exit), "walls": m.walls}
