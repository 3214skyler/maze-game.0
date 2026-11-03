"""XP, rewards, wallet, lives, unlocks, stats, difficulty."""
import pytest

from game.core.balance import BalanceConfig
from game.core.errors import InsufficientFundsError, NoLivesError
from game.economy.wallet import Wallet
from game.lives.lives import Lives
from game.maze.solver import is_solvable, solve
from game.progression import xp
from game.progression.difficulty import Difficulty, settings_for, time_limit
from game.progression.levels import build_level, level_config
from game.progression.rewards import calculate_rewards
from game.progression.stats import PlayerStats
from game.progression.unlocks import Unlocks

CFG = BalanceConfig()


# ---- XP ----------------------------------------------------------------------
def test_xp_curve_is_increasing_and_levels_are_consistent():
    needs = [xp.xp_needed(l) for l in range(1, 30)]
    assert needs == sorted(needs) and needs[0] == 100
    total = 0
    for level in range(1, 20):
        assert xp.level_for_xp(total) == level
        assert xp.level_for_xp(total + xp.xp_needed(level) - 1) == level
        total += xp.xp_needed(level)
    assert xp.level_for_xp(total) == 20


def test_xp_progress_inside_level():
    assert xp.progress(0) == (1, 0, 100)
    assert xp.progress(150) == (2, 50, 135)
    assert xp.progress(-5) == (1, 0, 100)


def test_player_level_cap():
    cfg = BalanceConfig(max_player_level=5)
    assert xp.level_for_xp(10 ** 9, cfg) == 5
    assert xp.progress(10 ** 9, cfg) == (5, 0, 0)


# ---- rewards ---------------------------------------------------------------------
def test_reward_breakdown_components():
    r = calculate_rewards(1, Difficulty.NORMAL, errors=0, paths_completed=1, first_clear=True)
    assert r.xp_breakdown["base"] == 24 and r.xp_breakdown["flawless"] == 6
    assert "all_paths" not in r.xp_breakdown and "replay" not in r.xp_breakdown
    assert r.xp == sum(r.xp_breakdown.values()) and r.coins == sum(r.coin_breakdown.values())


def test_flawless_and_all_paths_bonuses_increase_rewards():
    base = calculate_rewards(5, Difficulty.NORMAL, 3, 1, True)
    flawless = calculate_rewards(5, Difficulty.NORMAL, 0, 1, True)
    all_paths = calculate_rewards(5, Difficulty.NORMAL, 3, 3, True)
    assert flawless.xp > base.xp and all_paths.xp > base.xp
    assert flawless.coins > base.coins and all_paths.coins > base.coins


def test_harder_difficulty_pays_more():
    xps = [calculate_rewards(10, d, 0, 3, True).xp for d in
           (Difficulty.EASY, Difficulty.NORMAL, Difficulty.HARD, Difficulty.NIGHTMARE)]
    assert xps == sorted(xps) and len(set(xps)) == 4


def test_rewards_grow_with_level_and_replays_pay_half():
    assert calculate_rewards(20, Difficulty.NORMAL, 0, 1, True).xp > calculate_rewards(2, Difficulty.NORMAL, 0, 1, True).xp
    first = calculate_rewards(10, Difficulty.HARD, 0, 3, True)
    replay = calculate_rewards(10, Difficulty.HARD, 0, 3, False)
    assert abs(replay.xp - first.xp * 0.5) <= 1 and replay.coins < first.coins
    assert isinstance(replay.xp, int) and replay.xp > 0


# ---- wallet -------------------------------------------------------------------------
def test_wallet_earn_spend_and_history():
    w = Wallet()
    w.earn(30, "a"); w.spend(10, "b")
    assert w.balance == 20 and [h["amount"] for h in w.history] == [30, -10]
    with pytest.raises(InsufficientFundsError):
        w.spend(21, "c")
    assert w.balance == 20
    with pytest.raises(ValueError):
        w.earn(-1, "x")


def test_wallet_history_is_capped_and_roundtrips():
    w = Wallet(history_limit=5)
    for i in range(20):
        w.earn(1, str(i))
    assert len(w.history) == 5 and w.balance == 20
    assert Wallet.from_dict(w.to_dict(), 5).balance == 20
    with pytest.raises(ValueError):
        Wallet.from_dict({"balance": -3}, 5)


# ---- lives ----------------------------------------------------------------------------
def make_lives(now=1000.0):
    return Lives.full(3, 100.0, now)


def test_lose_and_regenerate():
    l = make_lives()
    l.lose(1000.0)
    assert l.current == 2
    assert l.refresh(1099.0) == 0
    assert l.seconds_until_next(1050.0) == pytest.approx(50.0)
    assert l.refresh(1100.0) == 1 and l.current == 3
    assert l.seconds_until_next(1100.0) is None


def test_regeneration_is_capped_and_partial_progress_kept():
    l = make_lives()
    l.lose(1000.0); l.lose(1000.0); l.lose(1000.0)
    assert l.current == 0 and not l.has_lives
    l.refresh(1250.0)                          # 2.5 periods elapsed
    assert l.current == 2
    assert l.seconds_until_next(1250.0) == pytest.approx(50.0)
    l.refresh(10 ** 6)
    assert l.current == 3


def test_cannot_lose_below_zero():
    l = make_lives()
    for _ in range(3):
        l.lose(1000.0)
    with pytest.raises(NoLivesError):
        l.lose(1000.0)
    assert l.current == 0


def test_gain_never_exceeds_max_and_clock_going_backwards_is_safe():
    l = make_lives()
    l.lose(1000.0)
    l.gain(5, 1000.0)
    assert l.current == 3
    l.lose(2000.0)
    assert l.refresh(1500.0) == 0 and l.current == 2     # clock moved back: no free lives, no crash


def test_lives_roundtrip_is_clamped_to_config():
    l = Lives.from_dict({"current": 99, "last_update": 5}, 4, 60.0)
    assert l.current == 4 and l.max_lives == 4
    with pytest.raises(ValueError):
        Lives.from_dict({"current": -1, "last_update": 5}, 4, 60.0)


# ---- unlocks ---------------------------------------------------------------------------------
def test_unlocks_start_at_level_one_and_advance_on_completion():
    u = Unlocks(10)
    d = Difficulty.NORMAL
    assert u.is_unlocked(d, 1) and not u.is_unlocked(d, 2) and u.highest_unlocked(d) == 1
    assert u.record_completion(d, 1) == 2
    assert u.is_unlocked(d, 2) and u.is_completed(d, 1) and not u.is_completed(d, 2)
    assert u.record_completion(d, 1) is None            # replay unlocks nothing new
    assert u.highest_unlocked(d) == 2


def test_cannot_complete_locked_level_and_difficulties_are_independent():
    u = Unlocks(10)
    with pytest.raises(ValueError):
        u.record_completion(Difficulty.NORMAL, 3)
    u.record_completion(Difficulty.EASY, 1)
    assert u.highest_unlocked(Difficulty.HARD) == 1


def test_last_level_does_not_unlock_beyond_max():
    u = Unlocks(2)
    u.record_completion(Difficulty.EASY, 1)
    assert u.record_completion(Difficulty.EASY, 2) is None
    assert u.highest_unlocked(Difficulty.EASY) == 2


def test_unlocks_roundtrip_and_repair():
    u = Unlocks(10)
    for n in (1, 2, 3):
        u.record_completion(Difficulty.NORMAL, n)
    again = Unlocks.from_dict(u.to_dict(), 10)
    assert again.highest_unlocked(Difficulty.NORMAL) == 4 and again.is_completed(Difficulty.NORMAL, 3)
    repaired = Unlocks.from_dict({"completed": {"normal": [5]}, "highest": {"normal": 1}}, 10)
    assert repaired.highest_unlocked(Difficulty.NORMAL) == 6   # cannot be below a cleared level
    with pytest.raises(ValueError):
        Unlocks.from_dict({"completed": {"bogus": [1]}}, 10)


# ---- stats -------------------------------------------------------------------------------------
def test_stats_definitions():
    s = PlayerStats()
    k = s.key("normal", 3)
    s.record_start(k); s.record_start(k)
    assert s.record_victory(k, 3, 12.5) is True
    assert s.record_victory(k, 3, 14.0) is False          # slower: not a new best
    assert s.record_victory(k, 3, 9.0) is True
    s.record_defeat(k, 30.0)
    s.record_abandon(4.0)
    assert (s.attempts, s.levels_played, s.levels_completed, s.defeats) == (2, 4, 3, 1)
    assert s.best_level == 3 and s.best_time(k) == 9.0
    assert s.total_play_seconds == pytest.approx(12.5 + 14 + 9 + 30 + 4)


def test_stats_roundtrip_and_validation():
    s = PlayerStats()
    s.record_start("easy:1"); s.record_victory("easy:1", 1, 7.0)
    s2 = PlayerStats.from_dict(s.to_dict())
    assert s2.to_dict() == s.to_dict()
    with pytest.raises(ValueError):
        PlayerStats.from_dict({"attempts": -1})


# ---- difficulty & levels -----------------------------------------------------------------------
@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_levels_deterministic_and_solvable_for_every_difficulty(difficulty):
    for n in (1, 2, 3, 7, 15, 30, 60):
        a, b = build_level(n, difficulty), build_level(n, difficulty)
        assert a.walls == b.walls and is_solvable(a)


def test_normal_difficulty_keeps_original_curve():
    assert [level_config(n).width for n in (1, 5, 10, 50)] == [6, 10, 15, 24]


def test_first_levels_are_gentle_and_difficulties_scale():
    for d in Difficulty:
        c = level_config(1, d)
        assert c.width * c.height <= 120                  # level 1 is never huge
    for n in (1, 5, 12):
        sizes = [level_config(n, d).width for d in
                 (Difficulty.EASY, Difficulty.NORMAL, Difficulty.HARD, Difficulty.NIGHTMARE)]
        assert sizes == sorted(sizes)


def test_difficulties_generate_different_mazes():
    walls = {d: build_level(5, d).walls for d in Difficulty}
    assert len({repr(w) for w in walls.values()}) == 4


def test_time_limits_and_required_paths_scale():
    per_path = [time_limit(d, 20) / settings_for(d).required_paths for d in Difficulty]
    assert per_path == sorted(per_path, reverse=True)     # less time per required path as it gets harder
    assert time_limit(Difficulty.HARD, 20) > time_limit(Difficulty.HARD, 10)   # longer maze, more time
    req = [settings_for(d).required_paths for d in Difficulty]
    assert req == [1, 1, 2, 3]
    m = build_level(1, Difficulty.NORMAL)
    assert time_limit(Difficulty.NORMAL, len(solve(m))) > len(solve(m))   # always more than 1s per cell
