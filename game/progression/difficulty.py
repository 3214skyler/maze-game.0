"""Difficulty definitions. NIGHTMARE is the special, unlockable tier."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple


class Difficulty(str, Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    NIGHTMARE = "nightmare"


@dataclass(frozen=True)
class DifficultySettings:
    label: str
    size_offset: int          # added to the base maze size of a level
    size_cap: int
    algorithms: Tuple[str, ...]
    time_base: float          # seconds granted regardless of maze length
    time_per_cell: float      # seconds per solution cell, per required path
    required_paths: int       # paths that must reach the exit to win (1..3)
    xp_multiplier: float
    coin_multiplier: float
    seed_stride: int          # keeps mazes of different difficulties distinct


SETTINGS: Dict[Difficulty, DifficultySettings] = {
    Difficulty.EASY: DifficultySettings("EASY", -1, 20, ("backtracker", "prim"),
                                        20.0, 1.5, 1, 1.0, 1.0, 100_000),
    # NORMAL reproduces the original level curve exactly (size 5+n capped at 24).
    Difficulty.NORMAL: DifficultySettings("NORMAL", 0, 24, ("backtracker", "prim", "kruskal"),
                                          15.0, 1.0, 1, 1.5, 1.25, 0),
    Difficulty.HARD: DifficultySettings("HARD", 2, 28, ("prim", "kruskal"),
                                        10.0, 0.7, 2, 2.2, 1.6, 200_000),
    Difficulty.NIGHTMARE: DifficultySettings("NIGHTMARE", 4, 32, ("kruskal", "prim"),
                                             8.0, 0.5, 3, 3.5, 2.5, 300_000),
}


def settings_for(difficulty: Difficulty) -> DifficultySettings:
    return SETTINGS[Difficulty(difficulty)]


def time_limit(difficulty: Difficulty, solution_length: int) -> float:
    """Seconds allowed: scales with the route length and with the number of required paths."""
    s = settings_for(difficulty)
    return round(s.time_base + s.time_per_cell * solution_length * s.required_paths, 1)
