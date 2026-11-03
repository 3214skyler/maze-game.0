"""Player experience levels (independent from maze levels)."""
from __future__ import annotations

from typing import Tuple

from game.core.balance import BalanceConfig


def xp_needed(level: int, cfg: BalanceConfig = BalanceConfig()) -> int:
    """XP required to go from `level` to `level + 1`."""
    return int(round(cfg.xp_first_level * cfg.xp_growth ** (level - 1)))


def level_for_xp(total_xp: int, cfg: BalanceConfig = BalanceConfig()) -> int:
    level, remaining = 1, max(0, total_xp)
    while level < cfg.max_player_level and remaining >= xp_needed(level, cfg):
        remaining -= xp_needed(level, cfg)
        level += 1
    return level


def progress(total_xp: int, cfg: BalanceConfig = BalanceConfig()) -> Tuple[int, int, int]:
    """(player level, XP gained inside this level, XP needed for the next); needed=0 at max level."""
    level, remaining = 1, max(0, total_xp)
    while level < cfg.max_player_level and remaining >= xp_needed(level, cfg):
        remaining -= xp_needed(level, cfg)
        level += 1
    if level >= cfg.max_player_level:
        return level, 0, 0
    return level, remaining, xp_needed(level, cfg)
