"""One attempt at one level: timer, errors, and the exact rules for victory and defeat.

RULES
  * VICTORY  – at least `required_paths` of the three paths reached the exit before time ran out.
  * DEFEAT   – the time limit expired first. This is the ONLY way to lose a life.
  * ERRORS   – hitting a wall or crossing your own path is counted (it only affects the flawless
               bonus). Exploring wrong routes never costs a life; you can always backtrack or reset.
  * ABANDONED – leaving the level early: no victory, no defeat, no life lost.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from game.maze.maze import Maze
from game.progression.difficulty import Difficulty


class Outcome(str, Enum):
    IN_PROGRESS = "in_progress"
    VICTORY = "victory"
    DEFEAT = "defeat"
    ABANDONED = "abandoned"


class DefeatReason(str, Enum):
    TIME_UP = "time_up"


class LevelSession:
    def __init__(self, maze: Maze, level: int, difficulty: Difficulty, time_limit: float,
                 required_paths: int, now: float):
        self.maze = maze
        self.level = level
        self.difficulty = Difficulty(difficulty)
        self.time_limit = time_limit
        self.required_paths = required_paths
        self.started_at = now
        self.errors = 0
        self.paths_completed = 0
        self.outcome = Outcome.IN_PROGRESS
        self.defeat_reason: Optional[DefeatReason] = None
        self.elapsed = 0.0
        self.applied = False          # set by ProgressService once rewards/penalties were applied

    @property
    def active(self) -> bool:
        return self.outcome is Outcome.IN_PROGRESS

    def elapsed_at(self, now: float) -> float:
        return self.elapsed if not self.active else max(0.0, now - self.started_at)

    def time_left(self, now: float) -> float:
        return max(0.0, self.time_limit - self.elapsed_at(now))

    def record_error(self) -> None:
        if self.active:
            self.errors += 1

    def update(self, paths_completed: int, now: float) -> Outcome:
        """Re-evaluate the session. Call after path changes and on every timer tick."""
        if not self.active:
            return self.outcome
        self.paths_completed = paths_completed
        elapsed = max(0.0, now - self.started_at)
        if paths_completed >= self.required_paths and elapsed <= self.time_limit:
            self.outcome, self.elapsed = Outcome.VICTORY, elapsed
        elif elapsed >= self.time_limit:
            self.outcome, self.elapsed = Outcome.DEFEAT, self.time_limit
            self.defeat_reason = DefeatReason.TIME_UP
        return self.outcome

    def abandon(self, now: float) -> None:
        if self.active:
            self.outcome, self.elapsed = Outcome.ABANDONED, max(0.0, now - self.started_at)
