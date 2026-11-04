"""Client side of the daily challenge. All judging happens on the server; this only plays and submits."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Sequence, Tuple

from game.maze.maze import Maze
from game.online.api import ApiClient
from game.online.errors import ServerError

REJECTIONS = {
    "too_fast": "Submitted too quickly to be a legitimate run.",
    "wall_crossed": "The submitted path crosses a wall.",
    "self_crossing": "The path crosses itself.",
    "exit_not_reached": "The path does not reach the exit.",
    "run_expired": "This run took too long and expired.",
}
ERRORS = {
    "no_challenge_today": "Today's challenge is not published yet. Try again later.",
    "profile_required": "Choose a username before playing the daily challenge.",
    "too_many_attempts": "Attempt limit reached for today. Come back tomorrow!",
    "not_authenticated": "Sign in to play the daily challenge.",
}


@dataclass(frozen=True)
class DailyRun:
    run_id: str
    day: date
    maze: Maze


@dataclass(frozen=True)
class DailyResult:
    accepted: bool
    elapsed_ms: int
    rank: Optional[int] = None
    best_ms: Optional[int] = None
    reason: Optional[str] = None

    @property
    def message(self) -> str:
        return "" if self.accepted else REJECTIONS.get(self.reason or "", "The run was rejected.")


@dataclass(frozen=True)
class BoardRow:
    rank: int
    username: str
    elapsed_ms: int
    is_me: bool


def friendly(exc: ServerError) -> str:
    return ERRORS.get(exc.code, f"Server error: {exc.code}")


class DailyClient:
    def __init__(self, api: ApiClient):
        self.api = api

    def start(self) -> DailyRun:
        body = self.api.rpc("start_daily_run")
        maze = Maze.from_dict(body)                       # ValueError on malformed data
        return DailyRun(body["run_id"], date.fromisoformat(body["day"]), maze)

    def submit(self, run: DailyRun, cells: Sequence[Tuple[int, int]]) -> DailyResult:
        body = self.api.rpc("submit_daily_run", {"p_run_id": run.run_id, "p_path": [list(c) for c in cells]})
        return DailyResult(bool(body["accepted"]), int(body["elapsed_ms"]), body.get("rank"),
                           body.get("best_ms"), body.get("reason"))

    def leaderboard(self, day: Optional[date] = None, limit: int = 50) -> List[BoardRow]:
        body = self.api.rpc("get_daily_leaderboard",
                            {"p_day": day.isoformat() if day else None, "p_limit": limit}, public=True)
        return [BoardRow(int(r["rank"]), str(r["username"]), int(r["elapsed_ms"]), bool(r["is_me"]))
                for r in (body or [])]
