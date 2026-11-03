"""Lives with time-based regeneration. Time is always passed in, so it is fully testable."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from game.core.errors import NoLivesError


@dataclass
class Lives:
    max_lives: int
    regen_seconds: float
    current: int
    last_update: float     # epoch seconds when regeneration last advanced

    @classmethod
    def full(cls, max_lives: int, regen_seconds: float, now: float) -> "Lives":
        return cls(max_lives, regen_seconds, max_lives, now)

    def refresh(self, now: float) -> int:
        """Apply regeneration up to `now`. Returns how many lives were gained."""
        if now < self.last_update:          # device clock moved backwards: never go negative
            self.last_update = now
        if self.current >= self.max_lives:
            self.current, self.last_update = self.max_lives, now
            return 0
        gained = int((now - self.last_update) // self.regen_seconds)
        if gained <= 0:
            return 0
        new = min(self.max_lives, self.current + gained)
        actual = new - self.current
        self.current = new
        self.last_update = now if new >= self.max_lives else self.last_update + gained * self.regen_seconds
        return actual

    @property
    def has_lives(self) -> bool:
        return self.current > 0

    def lose(self, now: float) -> None:
        self.refresh(now)
        if self.current <= 0:
            raise NoLivesError("no lives left")
        if self.current >= self.max_lives:
            self.last_update = now           # regeneration starts when the first life is lost
        self.current -= 1

    def gain(self, amount: int, now: float) -> None:
        self.refresh(now)
        self.current = min(self.max_lives, self.current + amount)
        if self.current >= self.max_lives:
            self.last_update = now

    def seconds_until_next(self, now: float) -> Optional[float]:
        self.refresh(now)
        if self.current >= self.max_lives:
            return None
        return max(0.0, self.regen_seconds - (now - self.last_update))

    def to_dict(self) -> Dict[str, Any]:
        return {"current": self.current, "last_update": self.last_update}

    @classmethod
    def from_dict(cls, data: Dict[str, Any], max_lives: int, regen_seconds: float) -> "Lives":
        current = int(data["current"])
        if current < 0:
            raise ValueError("negative lives")
        return cls(max_lives, regen_seconds, min(current, max_lives), float(data["last_update"]))
