"""Deterministic level definitions. NORMAL difficulty equals the original Classic curve."""
from dataclasses import dataclass

from game.maze.generators import generate
from game.maze.maze import Maze
from game.progression.difficulty import Difficulty, settings_for

ALGORITHM_CYCLE = ("backtracker", "prim", "kruskal")
BASE_SEED = 1000


@dataclass(frozen=True)
class LevelConfig:
    number: int
    width: int
    height: int
    seed: int
    algorithm: str
    difficulty: Difficulty = Difficulty.NORMAL


def level_config(number: int, difficulty: Difficulty = Difficulty.NORMAL) -> LevelConfig:
    if number < 1:
        raise ValueError("levels start at 1")
    s = settings_for(difficulty)
    size = max(4, min(5 + number + s.size_offset, s.size_cap))
    height = size + 2 if size < s.size_cap else size
    return LevelConfig(number, size, height, BASE_SEED + number + s.seed_stride,
                       s.algorithms[(number - 1) % len(s.algorithms)], Difficulty(difficulty))


def build_level(number: int, difficulty: Difficulty = Difficulty.NORMAL) -> Maze:
    c = level_config(number, difficulty)
    return generate(c.width, c.height, seed=c.seed, algorithm=c.algorithm)
