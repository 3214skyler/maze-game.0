import pytest

from game.core.balance import BalanceConfig
from game.core.errors import (DifficultyLockedError, InsufficientFundsError, LevelLockedError,
                              LivesFullError, NoLivesError)
from game.persistence.repository import MemoryRepository
from game.progression.difficulty import Difficulty
from game.progression.service import ProgressService
from game.progression.session import DefeatReason, Outcome

N, E, H, NM = Difficulty.NORMAL, Difficulty.EASY, Difficulty.HARD, Difficulty.NIGHTMARE


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def svc(clock):
    return ProgressService(MemoryRepository(), clock=clock)


def win(svc, clock, difficulty=N, level=1, errors=0, paths=None, seconds=5.0):
    s = svc.start_level(difficulty, level)
    for _ in range(errors):
        s.record_error()
    clock.t += seconds
    s.update(paths if paths is not None else s.required_paths, svc.now())
    assert s.outcome is Outcome.VICTORY
    return svc.conclude(s)


def lose(svc, clock, difficulty=N, level=1):
    s = svc.start_level(difficulty, level)
    clock.t += s.time_limit + 1
    s.update(0, svc.now())
    assert s.outcome is Outcome.DEFEAT
    return svc.conclude(s)


# ---- start rules -----------------------------------------------------------------
def test_only_level_one_is_unlocked_at_first(svc):
    assert svc.is_level_unlocked(N, 1) and not svc.is_level_unlocked(N, 2)
    with pytest.raises(LevelLockedError):
        svc.start_level(N, 2)
    with pytest.raises(LevelLockedError):
        svc.start_level(N, 0)


def test_nightmare_is_locked_until_hard_milestone(svc):
    assert not svc.difficulty_unlocked(NM)
    with pytest.raises(DifficultyLockedError):
        svc.start_level(NM, 1)
    svc.profile.unlocks.record_completion(H, 1)
    for n in range(2, svc.cfg.nightmare_unlock_level + 1):
        svc.profile.unlocks.record_completion(H, n)
    assert svc.difficulty_unlocked(NM)


def test_next_level_unlocks_only_after_victory(svc, clock):
    assert not svc.has_next_level(N, 1)
    r = win(svc, clock)
    assert r.unlocked_level == 2 and svc.has_next_level(N, 1) and svc.highest_unlocked(N) == 2
    svc.start_level(N, 2)                          # now allowed


def test_defeat_does_not_unlock(svc, clock):
    lose(svc, clock)
    assert not svc.is_level_unlocked(N, 2)


def test_replay_of_cleared_level_is_allowed_and_unlocks_nothing(svc, clock):
    win(svc, clock)
    r = win(svc, clock)
    assert not r.first_clear and r.unlocked_level is None and svc.highest_unlocked(N) == 2


# ---- victory ----------------------------------------------------------------------------
def test_victory_awards_xp_coins_and_stats(svc, clock):
    r = win(svc, clock, errors=0, seconds=7.0)
    assert r.victory and r.first_clear and r.new_best_time and r.flawless
    assert svc.xp == r.rewards.xp > 0
    assert svc.coins == r.rewards.coins + r.level_up_coins
    st = svc.stats
    assert (st.attempts, st.levels_played, st.levels_completed, st.defeats, st.best_level) == (1, 1, 1, 0, 1)
    assert st.best_time("normal:1") == 7.0 and st.total_play_seconds == pytest.approx(7.0)
    assert st.total_coins_earned == svc.coins


def test_errors_remove_flawless_bonus_but_cost_no_life(svc, clock):
    flawless = win(svc, clock, level=1, errors=0)
    svc2 = ProgressService(MemoryRepository(), clock=clock)
    sloppy = win(svc2, clock, errors=5)
    assert sloppy.rewards.xp < flawless.rewards.xp and not sloppy.flawless
    assert svc2.lives() == svc2.cfg.max_lives


def test_all_paths_bonus_only_when_all_three(svc, clock):
    two = win(svc, clock, H, 1, paths=2)
    svc2 = ProgressService(MemoryRepository(), clock=clock)
    three = win(svc2, clock, H, 1, paths=3)
    assert "all_paths" not in two.rewards.xp_breakdown and "all_paths" in three.rewards.xp_breakdown


def test_replay_pays_less_and_best_time_only_improves(svc, clock):
    first = win(svc, clock, seconds=10.0)
    again = win(svc, clock, seconds=20.0)
    assert again.rewards.xp < first.rewards.xp and not again.new_best_time
    faster = win(svc, clock, seconds=4.0)
    assert faster.new_best_time and svc.stats.best_time("normal:1") == 4.0


def test_player_level_up_grants_coins_and_a_life(clock):
    cfg = BalanceConfig(max_lives=5)
    svc = ProgressService(MemoryRepository(), cfg, clock)
    svc.start_level(N, 1)                                   # attempt
    svc.profile.lives.current = 2
    svc.profile.xp = 95                                     # 5 XP short of player level 2
    r = win(svc, clock)
    assert r.level_ups == (2,) and svc.player_level() == 2
    assert r.level_up_coins == cfg.level_up_coins_per_level * 2
    assert svc.lives() == 3 and r.lives_left == 3           # +1 life from the level-up


def test_multiple_level_ups_at_once(clock):
    svc = ProgressService(MemoryRepository(), clock=clock)
    svc.profile.xp = 99
    r = win(svc, clock, H, 1, paths=3)
    assert svc.player_level() >= 2 and list(r.level_ups) == list(range(2, svc.player_level() + 1))


# ---- defeat & lives -------------------------------------------------------------------------
def test_defeat_costs_exactly_one_life_and_reports_reason(svc, clock):
    r = lose(svc, clock)
    assert r.outcome is Outcome.DEFEAT and r.defeat_reason is DefeatReason.TIME_UP
    assert r.lives_left == svc.cfg.max_lives - 1 == svc.lives()
    assert (svc.stats.defeats, svc.stats.levels_played, svc.stats.levels_completed) == (1, 1, 0)
    assert svc.xp == 0 and svc.coins == 0


def test_cannot_start_without_lives_until_regeneration(svc, clock):
    for _ in range(svc.cfg.max_lives):
        lose(svc, clock)
    assert svc.lives() == 0
    with pytest.raises(NoLivesError):
        svc.start_level(N, 1)
    clock.t += svc.cfg.life_regen_seconds
    assert svc.lives() == 1
    svc.start_level(N, 1)


def test_seconds_until_next_life(svc, clock):
    assert svc.seconds_until_next_life() is None
    lose(svc, clock)
    wait = svc.seconds_until_next_life()
    assert 0 < wait <= svc.cfg.life_regen_seconds


def test_buy_life_with_coins(svc, clock):
    with pytest.raises(LivesFullError):
        svc.buy_life()
    lose(svc, clock)
    with pytest.raises(InsufficientFundsError):
        svc.buy_life()
    assert svc.lives() == svc.cfg.max_lives - 1
    svc.profile.wallet.earn(svc.cfg.life_cost_coins, "test")
    svc.buy_life()
    assert svc.lives() == svc.cfg.max_lives and svc.coins == 0


def test_abandon_costs_nothing(svc, clock):
    s = svc.start_level(N, 1)
    clock.t += 3
    svc.abandon(s)
    assert svc.lives() == svc.cfg.max_lives and svc.stats.attempts == 1
    assert svc.stats.levels_played == 0 and svc.stats.total_play_seconds == pytest.approx(3.0)


def test_session_cannot_be_concluded_twice_or_early(svc, clock):
    s = svc.start_level(N, 1)
    with pytest.raises(ValueError):
        svc.conclude(s)
    clock.t += 5
    s.update(1, svc.now())
    svc.conclude(s)
    with pytest.raises(ValueError):
        svc.conclude(s)


def test_three_difficulties_progress_separately(svc, clock):
    win(svc, clock, E, 1)
    assert svc.highest_unlocked(E) == 2 and svc.highest_unlocked(N) == 1 and svc.highest_unlocked(H) == 1
    assert svc.stats.best_level == 1
