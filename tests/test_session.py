import pytest

from game.maze.generators import generate
from game.progression.difficulty import Difficulty
from game.progression.session import DefeatReason, LevelSession, Outcome


def make(limit=60.0, required=1, now=100.0):
    return LevelSession(generate(5, 5, seed=1), 1, Difficulty.NORMAL, limit, required, now)


def test_victory_when_required_paths_done_in_time():
    s = make(required=2)
    assert s.update(1, 110.0) is Outcome.IN_PROGRESS
    assert s.update(2, 120.0) is Outcome.VICTORY
    assert s.elapsed == pytest.approx(20.0) and s.defeat_reason is None


def test_defeat_only_by_time_up():
    s = make(limit=30.0)
    assert s.update(0, 129.9) is Outcome.IN_PROGRESS
    assert s.update(0, 130.0) is Outcome.DEFEAT
    assert s.defeat_reason is DefeatReason.TIME_UP and s.elapsed == 30.0


def test_errors_never_end_the_session():
    s = make()
    for _ in range(50):
        s.record_error()
    assert s.errors == 50 and s.update(0, 101.0) is Outcome.IN_PROGRESS


def test_completing_after_time_expired_is_a_defeat():
    s = make(limit=30.0)
    assert s.update(1, 135.0) is Outcome.DEFEAT


def test_completing_exactly_at_the_limit_is_a_victory():
    assert make(limit=30.0).update(1, 130.0) is Outcome.VICTORY


def test_outcome_is_final():
    s = make()
    s.update(1, 105.0)
    assert s.update(0, 1000.0) is Outcome.VICTORY
    s.record_error()
    assert s.errors == 0               # ignored after the end


def test_abandon_is_neither_win_nor_loss():
    s = make()
    s.abandon(110.0)
    assert s.outcome is Outcome.ABANDONED and s.elapsed == pytest.approx(10.0)
    assert s.update(1, 111.0) is Outcome.ABANDONED


def test_time_left_counts_down_and_freezes():
    s = make(limit=30.0)
    assert s.time_left(110.0) == pytest.approx(20.0)
    s.update(1, 110.0)
    assert s.time_left(500.0) == pytest.approx(20.0)
