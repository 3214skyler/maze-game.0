"""Deterministic level definitions for Classic mode (Phase 4 extends this)."""
from dataclasses import dataclass

from game.maze.generators import generate
from game.maze.maze import Maze

ALGORITHM_CYCLE = ("backtracker", "prim", "kruskal")
BASE_SEED = 1000


@dataclass(frozen=True)
class LevelConfig:
    number: int
    width: int
    height: int
    seed: int
    algorithm: str


def level_config(number: int) -> LevelConfig:
    if number < 1:
        raise ValueError("levels start at 1")
    size = min(5 + number, 24)
    return LevelConfig(number, size, size + 2 if size < 24 else size, BASE_SEED + number,
                       ALGORITHM_CYCLE[(number - 1) % len(ALGORITHM_CYCLE)])


def build_level(number: int) -> Maze:
    c = level_config(number)
    return generate(c.width, c.height, seed=c.seed, algorithm=c.algorithm)
