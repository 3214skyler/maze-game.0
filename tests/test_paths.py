import pytest

from game.maze.generators import generate
from game.maze.maze import E, Maze, S
from game.maze.solver import solve
from game.paths.manager import PathManager
from game.paths.path import Path, StepResult


@pytest.fixture
def corridor():
    """3x2 maze: (0,0)-(1,0)-(2,0)-(2,1), plus dead end (0,1) off (0,0)."""
    m = Maze(3, 2)
    m.carve((0, 0), (1, 0)); m.carve((1, 0), (2, 0)); m.carve((2, 0), (2, 1)); m.carve((0, 0), (0, 1))
    m.open_entrance_and_exit((0, 0), (2, 1))
    return m


def test_path_walks_to_exit_and_completes(corridor):
    p = Path("blue", corridor)
    assert p.try_extend((1, 0)) is StepResult.MOVED
    assert p.try_extend((2, 0)) is StepResult.MOVED
    assert p.try_extend((2, 1)) is StepResult.COMPLETED
    assert p.completed


def test_wall_blocks_and_does_not_change_state(corridor):
    p = Path("blue", corridor)
    p.try_extend((1, 0))
    assert p.try_extend((1, 1)) is StepResult.BLOCKED_WALL
    assert p.cells == [(0, 0), (1, 0)]


def test_diagonal_and_far_cells_rejected(corridor):
    p = Path("red", corridor)
    assert p.try_extend((1, 1)) is StepResult.NOT_ADJACENT
    assert p.try_extend((2, 0)) is StepResult.NOT_ADJACENT
    assert p.try_extend((-1, 0)) is StepResult.NOT_ADJACENT
    assert p.cells == [(0, 0)]


def test_backtrack_and_unchanged(corridor):
    p = Path("green", corridor)
    p.try_extend((1, 0)); p.try_extend((2, 0))
    assert p.try_extend((2, 0)) is StepResult.UNCHANGED
    assert p.try_extend((1, 0)) is StepResult.BACKTRACKED
    assert p.cells == [(0, 0), (1, 0)]


def test_path_cannot_cross_itself():
    m = Maze(3, 2)
    for a, b in [((0, 0), (1, 0)), ((1, 0), (1, 1)), ((1, 1), (0, 1)), ((0, 1), (0, 0)), ((1, 0), (2, 0))]:
        m.carve(a, b)   # a 2x2 loop on the left plus the exit corridor
    m.open_entrance_and_exit((0, 0), (2, 0))
    p = Path("blue", m)
    for c in [(1, 0), (1, 1), (0, 1)]:
        assert p.try_extend(c) is StepResult.MOVED
    assert p.try_extend((0, 0)) is StepResult.BLOCKED_SELF
    assert p.cells == [(0, 0), (1, 0), (1, 1), (0, 1)]


def test_no_extension_past_exit(corridor):
    p = Path("blue", corridor)
    for c in [(1, 0), (2, 0), (2, 1)]:
        p.try_extend(c)
    assert p.try_extend((1, 1)) is StepResult.ALREADY_COMPLETE
    assert p.head == corridor.exit


def test_three_paths_are_independent(corridor):
    pm = PathManager(corridor)
    pm.select("blue"); pm.extend((1, 0)); pm.extend((2, 0))
    pm.select("green"); pm.extend((0, 1))
    pm.select("red")
    assert pm.path("blue").cells == [(0, 0), (1, 0), (2, 0)]
    assert pm.path("green").cells == [(0, 0), (0, 1)]
    assert pm.path("red").cells == [(0, 0)]


def test_switching_colour_never_deletes_other_paths(corridor):
    pm = PathManager(corridor)
    pm.extend((1, 0))
    before = pm.to_dict()
    for c in ("green", "red", "blue", "red"):
        pm.select(c)
    assert pm.to_dict() == before


def test_reset_is_per_path_and_completion_is_per_path(corridor):
    pm = PathManager(corridor)
    for color in ("blue", "green"):
        pm.select(color)
        for c in [(1, 0), (2, 0), (2, 1)]:
            pm.extend(c)
    assert pm.completed_colors() == ["blue", "green"] and not pm.all_completed
    pm.reset("blue")
    assert pm.completed_colors() == ["green"]
    assert pm.path("green").cells[-1] == (2, 1)
    pm.select("red")
    for c in [(1, 0), (2, 0), (2, 1)]:
        pm.extend(c)
    pm.select("blue")
    for c in [(1, 0), (2, 0), (2, 1)]:
        pm.extend(c)
    assert pm.all_completed
    pm.reset_all()
    assert pm.completed_colors() == []


def test_unknown_colour_rejected(corridor):
    with pytest.raises(KeyError):
        PathManager(corridor).select("pink")


def test_serialisation_roundtrip_and_rejects_invalid(corridor):
    pm = PathManager(corridor)
    pm.extend((1, 0)); pm.select("red"); pm.extend((0, 1))
    data = pm.to_dict()
    other = PathManager(corridor)
    other.load_dict(data)
    assert other.to_dict() == data
    bad = {"blue": [[0, 0], [1, 1]]}
    with pytest.raises(ValueError):
        other.load_dict(bad)
    with pytest.raises(ValueError):
        other.load_dict({"blue": [[1, 0]]})
    assert other.to_dict() == data   # failed load changed nothing


def test_full_solution_completes_on_generated_mazes():
    for seed in range(10):
        m = generate(12, 12, seed=seed, algorithm=("backtracker", "prim", "kruskal")[seed % 3])
        pm = PathManager(m)
        results = [pm.extend(c) for c in solve(m)[1:]]
        assert results[-1] is StepResult.COMPLETED
        assert pm.path("blue").completed


def test_keyboard_navigation(corridor):
    pm = PathManager(corridor)
    assert pm.move(E) is StepResult.MOVED
    assert pm.move(S) is StepResult.BLOCKED_WALL
