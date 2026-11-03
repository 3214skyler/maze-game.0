"""Which levels are unlocked / cleared, per difficulty."""
from __future__ import annotations

from typing import Any, Dict, Optional, Set

from game.progression.difficulty import Difficulty


class Unlocks:
    def __init__(self, max_level: int):
        self.max_level = max_level
        self._highest: Dict[str, int] = {}
        self._completed: Dict[str, Set[int]] = {}

    def highest_unlocked(self, difficulty: Difficulty) -> int:
        return self._highest.get(Difficulty(difficulty).value, 1)

    def is_unlocked(self, difficulty: Difficulty, level: int) -> bool:
        return 1 <= level <= self.highest_unlocked(difficulty)

    def is_completed(self, difficulty: Difficulty, level: int) -> bool:
        return level in self._completed.get(Difficulty(difficulty).value, set())

    def completed_count(self, difficulty: Difficulty) -> int:
        return len(self._completed.get(Difficulty(difficulty).value, set()))

    def record_completion(self, difficulty: Difficulty, level: int) -> Optional[int]:
        """Mark a level cleared. Returns the newly unlocked level number, if any."""
        if not self.is_unlocked(difficulty, level):
            raise ValueError(f"level {level} is not unlocked")
        key = Difficulty(difficulty).value
        self._completed.setdefault(key, set()).add(level)
        if level == self._highest.get(key, 1) and level < self.max_level:
            self._highest[key] = level + 1
            return level + 1
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {"highest": dict(self._highest),
                "completed": {k: sorted(v) for k, v in self._completed.items()}}

    @classmethod
    def from_dict(cls, data: Dict[str, Any], max_level: int) -> "Unlocks":
        u = cls(max_level)
        for key, levels in data.get("completed", {}).items():
            Difficulty(key)  # raises ValueError for unknown difficulties
            u._completed[key] = {int(n) for n in levels if 1 <= int(n) <= max_level}
        for key, value in data.get("highest", {}).items():
            Difficulty(key)
            u._highest[key] = max(1, min(int(value), max_level))
        for key, done in u._completed.items():       # never lock a level below a cleared one
            if done:
                u._highest[key] = max(u._highest.get(key, 1), min(max(done) + 1, max_level))
        return u
