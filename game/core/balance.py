"""All tunable numbers of the progression system in one place (no magic numbers elsewhere)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BalanceConfig:
    # lives
    max_lives: int = 5
    life_regen_seconds: float = 300.0     # one life every 5 minutes
    life_cost_coins: int = 50             # buying a life with coins
    # levels
    max_level: int = 100
    nightmare_unlock_level: int = 10      # complete this level on HARD to unlock NIGHTMARE
    # XP rewards
    base_xp: int = 20
    xp_per_level: int = 4
    flawless_bonus: float = 0.25          # fraction of base, no wall/self-crossing errors
    all_paths_bonus: float = 0.20         # fraction of base, all three paths completed
    # coin rewards
    base_coins: int = 5
    coins_per_two_levels: int = 1
    coin_flawless_bonus: float = 0.25
    coin_all_paths_bonus: float = 0.20
    replay_multiplier: float = 0.5        # replaying an already cleared level pays half
    # player level curve
    xp_first_level: int = 100             # XP to go from player level 1 to 2
    xp_growth: float = 1.35               # each further level needs 35% more
    max_player_level: int = 100
    level_up_coins_per_level: int = 10    # coins granted on reaching level L: 10 * L
    level_up_lives: int = 1
    # persistence
    history_limit: int = 50               # wallet transactions kept in the save file
