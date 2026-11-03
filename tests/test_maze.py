import pytest

from game.maze.generators import ALGORITHMS, generate
from game.maze.maze import E, Maze, N, S, W
from game.maze.solver import hint, is_solvable, solve

SIZES = [(2, 2), (5, 5), (12, 7), (30, 30)]


@pytest.mark.parametrize("algo", sorted(ALGORITHMS))
@pytest.mark.parametrize("w,h", SIZES)
def test_generated_maze_is_perfect_and_solvable(algo, w, h):
    for seed in range(5):
        m = generate(w, h, seed=seed, algorithm=algo)
        assert m.passage_count() == w * h - 1          # spanning tree: connected, no loops
        assert is_solvable(m)
        route = solve(m)
        assert route[0] == m.start and route[-1] == m.exit


@pytest.mark.parametrize("algo", sorted(ALGORITHMS))
def test_entrance_and_exit_valid(algo):
    for seed in range(20):
        m = generate(10, 10, seed=seed, algorithm=algo)
        assert m.start[0] == 0 and m.exit[0] == m.width - 1
        assert m.in_bounds(m.start) and m.in_bounds(m.exit)
        assert not m.has_wall(m.start, W)       # entrance opening
        assert not m.has_wall(m.exit, E)        # exit opening


@pytest.mark.parametrize("algo", sorted(ALGORITHMS))
def test_same_seed_reproduces_maze(algo):
    a = generate(15, 15, seed=42, algorithm=algo)
    b = generate(15, 15, seed=42, algorithm=algo)
    assert a.walls == b.walls and a.start == b.start and a.exit == b.exit


def test_different_seeds_differ():
    assert generate(15, 15, seed=1).walls != generate(15, 15, seed=2).walls


def test_unseeded_generation_records_seed_for_replay():
    m = generate(8, 8)
    assert generate(8, 8, seed=m.seed).walls == m.walls


def test_invalid_arguments():
    with pytest.raises(ValueError):
        generate(5, 5, algorithm="nope")
    with pytest.raises(ValueError):
        generate(1, 5)


def test_solver_returns_none_when_walled_off():
    m = Maze(3, 3)  # all walls standing
    m.open_entrance_and_exit((0, 0), (2, 2))
    assert solve(m) is None and not is_solvable(m)


def test_solver_shortest_path_and_hint():
    m = Maze(3, 2)
    m.carve((0, 0), (1, 0)); m.carve((1, 0), (2, 0)); m.carve((2, 0), (2, 1))
    m.carve((0, 0), (0, 1))   # dead end branch
    m.open_entrance_and_exit((0, 0), (2, 1))
    assert solve(m) == [(0, 0), (1, 0), (2, 0), (2, 1)]
    assert hint(m, (0, 1), steps=2) == [(0, 0), (1, 0)]
    assert hint(m, (1, 0), steps=5) == [(2, 0), (2, 1)]


def test_collision_detection_between_cells():
    m = Maze(2, 2)
    m.carve((0, 0), (1, 0))
    assert m.can_move((0, 0), (1, 0)) and m.can_move((1, 0), (0, 0))
    assert not m.can_move((0, 0), (0, 1))      # wall
    assert not m.can_move((0, 0), (1, 1))      # diagonal
    assert not m.can_move((0, 0), (-1, 0))     # outside
    assert m.has_wall((0, 0), N) and m.has_wall((0, 0), S)


def test_wall_segments_cover_all_standing_walls():
    m = generate(8, 6, seed=3)
    segs = m.wall_segments()
    assert segs
    # Every segment is axis-aligned and inside the grid lines.
    for (x1, y1), (x2, y2) in segs:
        assert (x1 == x2) != (y1 == y2)
        assert 0 <= x1 <= x2 <= m.width and 0 <= y1 <= y2 <= m.height
