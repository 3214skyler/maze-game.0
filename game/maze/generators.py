"""Seeded maze generators. The same (size, seed, algorithm) always gives the same maze."""
import random
from typing import Callable, Dict, List, Optional, Tuple

from game.maze.maze import Cell, Maze
from game.maze.solver import is_solvable


class MazeGenerationError(RuntimeError):
    pass


def _recursive_backtracker(maze: Maze, rng: random.Random) -> None:
    first = (rng.randrange(maze.width), rng.randrange(maze.height))
    stack = [first]
    visited = {first}
    while stack:  # iterative: no recursion limit on large mazes
        cur = stack[-1]
        options = [n for n in maze.neighbors(cur) if n not in visited]
        if not options:
            stack.pop()
            continue
        nxt = rng.choice(options)
        maze.carve(cur, nxt)
        visited.add(nxt)
        stack.append(nxt)


def _prim(maze: Maze, rng: random.Random) -> None:
    first = (rng.randrange(maze.width), rng.randrange(maze.height))
    in_maze = {first}
    frontier: List[Tuple[Cell, Cell]] = [(first, n) for n in maze.neighbors(first)]
    while frontier:
        i = rng.randrange(len(frontier))
        frontier[i], frontier[-1] = frontier[-1], frontier[i]
        a, b = frontier.pop()
        if b in in_maze:
            continue
        maze.carve(a, b)
        in_maze.add(b)
        frontier.extend((b, n) for n in maze.neighbors(b) if n not in in_maze)


def _kruskal(maze: Maze, rng: random.Random) -> None:
    parent = {(x, y): (x, y) for y in range(maze.height) for x in range(maze.width)}

    def find(c: Cell) -> Cell:
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c

    edges = []
    for y in range(maze.height):
        for x in range(maze.width):
            if x + 1 < maze.width:
                edges.append(((x, y), (x + 1, y)))
            if y + 1 < maze.height:
                edges.append(((x, y), (x, y + 1)))
    rng.shuffle(edges)
    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            maze.carve(a, b)


ALGORITHMS: Dict[str, Callable[[Maze, random.Random], None]] = {
    "backtracker": _recursive_backtracker,
    "prim": _prim,
    "kruskal": _kruskal,
}


def generate(width: int, height: int, seed: Optional[int] = None,
             algorithm: str = "backtracker") -> Maze:
    """Generate a perfect (loop-free, fully connected) maze with entrance and exit."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unknown algorithm {algorithm!r}; choose from {sorted(ALGORITHMS)}")
    if seed is None:
        seed = random.SystemRandom().randrange(2 ** 32)
    rng = random.Random(seed)
    maze = Maze(width, height, seed=seed, algorithm=algorithm)
    ALGORITHMS[algorithm](maze, rng)
    maze.open_entrance_and_exit((0, rng.randrange(height)), (width - 1, rng.randrange(height)))
    if not is_solvable(maze):  # safety net: never hand out an unsolvable maze
        raise MazeGenerationError(f"{algorithm} produced an unsolvable maze (seed={seed})")
    return maze
