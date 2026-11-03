"""The whole persistent player state as one serialisable object (UI never stores progress)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from game.core.balance import BalanceConfig
from game.economy.wallet import Wallet
from game.lives.lives import Lives
from game.progression.stats import PlayerStats
from game.progression.unlocks import Unlocks


@dataclass
class PlayerProfile:
    xp: int
    wallet: Wallet
    lives: Lives
    stats: PlayerStats
    unlocks: Unlocks

    @classmethod
    def new(cls, cfg: BalanceConfig, now: float) -> "PlayerProfile":
        return cls(0, Wallet(history_limit=cfg.history_limit),
                   Lives.full(cfg.max_lives, cfg.life_regen_seconds, now),
                   PlayerStats(), Unlocks(cfg.max_level))

    def to_dict(self) -> Dict[str, Any]:
        return {"xp": self.xp, "wallet": self.wallet.to_dict(), "lives": self.lives.to_dict(),
                "stats": self.stats.to_dict(), "unlocks": self.unlocks.to_dict()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any], cfg: BalanceConfig) -> "PlayerProfile":
        """Raises KeyError/TypeError/ValueError on malformed data (the service falls back safely)."""
        xp = int(data["xp"])
        if xp < 0:
            raise ValueError("negative xp")
        return cls(xp, Wallet.from_dict(data["wallet"], cfg.history_limit),
                   Lives.from_dict(data["lives"], cfg.max_lives, cfg.life_regen_seconds),
                   PlayerStats.from_dict(data["stats"]), Unlocks.from_dict(data["unlocks"], cfg.max_level))
