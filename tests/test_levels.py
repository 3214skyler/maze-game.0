import pytest

from game.maze.solver import is_solvable
from game.progression.levels import build_level, level_config


def test_levels_grow_then_cap():
    sizes = [level_config(n).width for n in (1, 5, 10, 50)]
    assert sizes == sorted(sizes) and sizes[-1] == 24


def test_levels_are_deterministic_and_solvable():
    for n in range(1, 31):
        a, b = build_level(n), build_level(n)
        assert a.walls == b.walls and is_solvable(a)


def test_algorithms_rotate():
    assert [level_config(n).algorithm for n in (1, 2, 3, 4)] == ["backtracker", "prim", "kruskal", "backtracker"]


def test_invalid_level():
    with pytest.raises(ValueError):
        level_config(0)
