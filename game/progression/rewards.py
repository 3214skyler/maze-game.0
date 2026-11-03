"""Reward calculation. Pure function of what happened in the level."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from game.core.balance import BalanceConfig
from game.progression.difficulty import Difficulty, settings_for


@dataclass(frozen=True)
class Rewards:
    xp: int
    coins: int
    xp_breakdown: Dict[str, int] = field(default_factory=dict)
    coin_breakdown: Dict[str, int] = field(default_factory=dict)


def _compose(base: int, multiplier: float, flawless_bonus: float, all_bonus: float,
             flawless: bool, all_paths: bool, first_clear: bool, replay_multiplier: float) -> Dict[str, int]:
    parts = {"base": base, "difficulty": round(base * (multiplier - 1.0))}
    if flawless:
        parts["flawless"] = round(base * flawless_bonus)
    if all_paths:
        parts["all_paths"] = round(base * all_bonus)
    if not first_clear:
        subtotal = sum(parts.values())
        parts["replay"] = round(subtotal * replay_multiplier) - subtotal   # negative adjustment
    return parts


def calculate_rewards(level: int, difficulty: Difficulty, errors: int, paths_completed: int,
                      first_clear: bool, cfg: BalanceConfig = BalanceConfig()) -> Rewards:
    s = settings_for(difficulty)
    flawless = errors == 0
    all_paths = paths_completed >= 3
    xp = _compose(cfg.base_xp + cfg.xp_per_level * level, s.xp_multiplier, cfg.flawless_bonus,
                  cfg.all_paths_bonus, flawless, all_paths, first_clear, cfg.replay_multiplier)
    coins = _compose(cfg.base_coins + cfg.coins_per_two_levels * (level // 2), s.coin_multiplier,
                     cfg.coin_flawless_bonus, cfg.coin_all_paths_bonus, flawless, all_paths,
                     first_clear, cfg.replay_multiplier)
    return Rewards(max(0, sum(xp.values())), max(0, sum(coins.values())), xp, coins)
