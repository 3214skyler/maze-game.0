"""Lifetime player statistics.

Definitions: attempts = level sessions started; levels_played = sessions that ended in a
victory or defeat (abandoned ones are not counted); levels_completed = victories (replays count).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class LevelRecord:
    attempts: int = 0
    completions: int = 0
    best_time: Optional[float] = None


@dataclass
class PlayerStats:
    attempts: int = 0
    levels_played: int = 0
    levels_completed: int = 0
    defeats: int = 0
    best_level: int = 0                       # highest level cleared on any difficulty
    total_coins_earned: int = 0
    total_play_seconds: float = 0.0
    per_level: Dict[str, LevelRecord] = field(default_factory=dict)

    @staticmethod
    def key(difficulty: str, level: int) -> str:
        return f"{difficulty}:{level}"

    def _rec(self, key: str) -> LevelRecord:
        return self.per_level.setdefault(key, LevelRecord())

    def record_start(self, key: str) -> None:
        self.attempts += 1
        self._rec(key).attempts += 1

    def record_victory(self, key: str, level: int, elapsed: float) -> bool:
        """Returns True when this is a new best time for the level."""
        self.levels_played += 1
        self.levels_completed += 1
        self.total_play_seconds += elapsed
        self.best_level = max(self.best_level, level)
        rec = self._rec(key)
        rec.completions += 1
        new_best = rec.best_time is None or elapsed < rec.best_time
        if new_best:
            rec.best_time = round(elapsed, 2)
        return new_best

    def record_defeat(self, key: str, elapsed: float) -> None:
        self.levels_played += 1
        self.defeats += 1
        self.total_play_seconds += elapsed

    def record_abandon(self, elapsed: float) -> None:
        self.total_play_seconds += elapsed

    def best_time(self, key: str) -> Optional[float]:
        rec = self.per_level.get(key)
        return rec.best_time if rec else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempts": self.attempts, "levels_played": self.levels_played,
            "levels_completed": self.levels_completed, "defeats": self.defeats,
            "best_level": self.best_level, "total_coins_earned": self.total_coins_earned,
            "total_play_seconds": round(self.total_play_seconds, 2),
            "per_level": {k: {"attempts": r.attempts, "completions": r.completions,
                              "best_time": r.best_time} for k, r in self.per_level.items()},
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PlayerStats":
        s = cls()
        for name in ("attempts", "levels_played", "levels_completed", "defeats",
                     "best_level", "total_coins_earned"):
            value = int(d.get(name, 0))
            if value < 0:
                raise ValueError(f"negative stat {name}")
            setattr(s, name, value)
        s.total_play_seconds = max(0.0, float(d.get("total_play_seconds", 0.0)))
        for key, r in d.get("per_level", {}).items():
            bt = r.get("best_time")
            s.per_level[key] = LevelRecord(max(0, int(r.get("attempts", 0))),
                                           max(0, int(r.get("completions", 0))),
                                           None if bt is None else float(bt))
        return s
