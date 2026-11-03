"""ProgressService: the single entry point the UI uses for everything about progression.

It owns the PlayerProfile, applies the rules (rewards, lives, unlocks, stats) and saves.
It imports nothing from Kivy.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from game.core.balance import BalanceConfig
from game.core.errors import (DifficultyLockedError, InsufficientFundsError, LevelLockedError,
                              LivesFullError, NoLivesError, SaveError)
from game.maze.solver import solve
from game.persistence.repository import ProfileRepository
from game.progression import xp as xp_rules
from game.progression.difficulty import Difficulty, settings_for, time_limit
from game.progression.levels import build_level
from game.progression.profile import PlayerProfile
from game.progression.rewards import Rewards, calculate_rewards
from game.progression.session import DefeatReason, LevelSession, Outcome
from game.progression.stats import PlayerStats


@dataclass(frozen=True)
class LevelResult:
    outcome: Outcome
    difficulty: Difficulty
    level: int
    elapsed: float
    errors: int
    paths_completed: int
    lives_left: int
    rewards: Optional[Rewards] = None
    first_clear: bool = False
    new_best_time: bool = False
    level_ups: Tuple[int, ...] = ()          # player levels reached (e.g. (3, 4))
    level_up_coins: int = 0
    unlocked_level: Optional[int] = None
    unlocked_difficulty: Optional[Difficulty] = None
    defeat_reason: Optional[DefeatReason] = None

    @property
    def victory(self) -> bool:
        return self.outcome is Outcome.VICTORY

    @property
    def flawless(self) -> bool:
        return self.errors == 0


class ProgressService:
    def __init__(self, repository: ProfileRepository, config: BalanceConfig = BalanceConfig(),
                 clock: Callable[[], float] = time.time):
        self.repo = repository
        self.cfg = config
        self._clock = clock
        self.load_warning: Optional[str] = None
        self.save_error: Optional[str] = None
        now = self.now()
        data = repository.load()
        if data is None:
            self.profile = PlayerProfile.new(config, now)
        else:
            try:
                self.profile = PlayerProfile.from_dict(data, config)
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                repository.discard_corrupt()
                self.profile = PlayerProfile.new(config, now)
                self.load_warning = f"saved progress was unreadable and was reset ({exc})"
        self.profile.lives.refresh(now)

    # --- basics ---------------------------------------------------------------
    def now(self) -> float:
        return self._clock()

    def save(self) -> bool:
        try:
            self.repo.save(self.profile.to_dict())
            self.save_error = None
            return True
        except SaveError as exc:
            self.save_error = str(exc)       # the game keeps running; progress stays in memory
            return False

    @property
    def stats(self) -> PlayerStats:
        return self.profile.stats

    @property
    def coins(self) -> int:
        return self.profile.wallet.balance

    @property
    def xp(self) -> int:
        return self.profile.xp

    def player_level(self) -> int:
        return xp_rules.level_for_xp(self.profile.xp, self.cfg)

    def xp_progress(self) -> Tuple[int, int, int]:
        return xp_rules.progress(self.profile.xp, self.cfg)

    # --- lives -------------------------------------------------------------------
    def lives(self) -> int:
        self.profile.lives.refresh(self.now())
        return self.profile.lives.current

    def seconds_until_next_life(self) -> Optional[float]:
        return self.profile.lives.seconds_until_next(self.now())

    def buy_life(self) -> None:
        """Recover a life with coins (the first 'shop' item)."""
        lives = self.profile.lives
        lives.refresh(self.now())
        if lives.current >= lives.max_lives:
            raise LivesFullError("lives are already full")
        self.profile.wallet.spend(self.cfg.life_cost_coins, "buy_life")
        lives.gain(1, self.now())
        self.save()

    # --- unlocking ---------------------------------------------------------------------
    def difficulty_unlocked(self, difficulty: Difficulty) -> bool:
        difficulty = Difficulty(difficulty)
        if difficulty is not Difficulty.NIGHTMARE:
            return True
        return self.profile.unlocks.is_completed(Difficulty.HARD, self.cfg.nightmare_unlock_level)

    def highest_unlocked(self, difficulty: Difficulty) -> int:
        return self.profile.unlocks.highest_unlocked(difficulty)

    def is_level_unlocked(self, difficulty: Difficulty, level: int) -> bool:
        return self.difficulty_unlocked(difficulty) and self.profile.unlocks.is_unlocked(difficulty, level)

    def is_level_completed(self, difficulty: Difficulty, level: int) -> bool:
        return self.profile.unlocks.is_completed(difficulty, level)

    def has_next_level(self, difficulty: Difficulty, level: int) -> bool:
        return level < self.cfg.max_level and self.is_level_unlocked(difficulty, level + 1)

    # --- play flow ---------------------------------------------------------------------------
    def start_level(self, difficulty: Difficulty, level: int) -> LevelSession:
        difficulty = Difficulty(difficulty)
        if not self.difficulty_unlocked(difficulty):
            raise DifficultyLockedError(f"{difficulty.value} is locked")
        if not self.is_level_unlocked(difficulty, level):
            raise LevelLockedError(f"level {level} is locked")
        if self.lives() <= 0:
            raise NoLivesError("no lives left")
        maze = build_level(level, difficulty)
        s = settings_for(difficulty)
        limit = time_limit(difficulty, len(solve(maze)))
        self.profile.stats.record_start(PlayerStats.key(difficulty.value, level))
        session = LevelSession(maze, level, difficulty, limit, s.required_paths, self.now())
        self.save()
        return session

    def abandon(self, session: LevelSession) -> None:
        if session.active:
            session.abandon(self.now())
            self.profile.stats.record_abandon(session.elapsed)
            session.applied = True
            self.save()

    def conclude(self, session: LevelSession) -> LevelResult:
        """Apply a finished session (victory or defeat) to the profile. Idempotence-guarded."""
        if session.outcome not in (Outcome.VICTORY, Outcome.DEFEAT):
            raise ValueError("session has not ended in victory or defeat")
        if session.applied:
            raise ValueError("session was already applied")
        session.applied = True
        now, p = self.now(), self.profile
        key = PlayerStats.key(session.difficulty.value, session.level)
        if session.outcome is Outcome.DEFEAT:
            p.lives.lose(now)
            p.stats.record_defeat(key, session.elapsed)
            self.save()
            return LevelResult(Outcome.DEFEAT, session.difficulty, session.level, session.elapsed,
                               session.errors, session.paths_completed, p.lives.current,
                               defeat_reason=session.defeat_reason)

        first = not p.unlocks.is_completed(session.difficulty, session.level)
        rewards = calculate_rewards(session.level, session.difficulty, session.errors,
                                    session.paths_completed, first, self.cfg)
        old_level = self.player_level()
        nightmare_before = self.difficulty_unlocked(Difficulty.NIGHTMARE)
        p.xp += rewards.xp
        self._earn(rewards.coins, "level_clear")
        new_level = self.player_level()
        ups: List[int] = list(range(old_level + 1, new_level + 1))
        bonus_coins = 0
        for lvl in ups:                                   # level-up rewards: coins and a life
            coins = self.cfg.level_up_coins_per_level * lvl
            bonus_coins += coins
            self._earn(coins, "player_level_up")
            p.lives.gain(self.cfg.level_up_lives, now)
        unlocked = p.unlocks.record_completion(session.difficulty, session.level)
        new_best = p.stats.record_victory(key, session.level, session.elapsed)
        unlocked_diff = Difficulty.NIGHTMARE if (not nightmare_before
                                                 and self.difficulty_unlocked(Difficulty.NIGHTMARE)) else None
        self.save()
        return LevelResult(Outcome.VICTORY, session.difficulty, session.level, session.elapsed,
                           session.errors, session.paths_completed, p.lives.current, rewards, first,
                           new_best, tuple(ups), bonus_coins, unlocked, unlocked_diff)

    def _earn(self, amount: int, reason: str) -> None:
        self.profile.wallet.earn(amount, reason)
        self.profile.stats.total_coins_earned += amount
