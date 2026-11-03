"""A single drawable path and its validation rules. Pure logic."""
from enum import Enum
from typing import List

from game.maze.maze import Cell, DELTA, Maze


class StepResult(Enum):
    MOVED = "moved"
    COMPLETED = "completed"          # head reached the exit
    BACKTRACKED = "backtracked"      # erased one cell
    UNCHANGED = "unchanged"          # same cell as the head
    BLOCKED_WALL = "blocked_wall"    # a wall is in the way
    BLOCKED_SELF = "blocked_self"    # would cross the path itself
    ALREADY_COMPLETE = "already_complete"
    NOT_ADJACENT = "not_adjacent"    # not a single orthogonal step (or out of bounds)


BLOCKING = {StepResult.BLOCKED_WALL, StepResult.BLOCKED_SELF, StepResult.ALREADY_COMPLETE}


class Path:
    """Ordered cells from the maze entrance. Never contains an invalid step."""

    def __init__(self, color: str, maze: Maze):
        self.color = color
        self.maze = maze
        self.cells: List[Cell] = [maze.start]

    @property
    def head(self) -> Cell:
        return self.cells[-1]

    @property
    def completed(self) -> bool:
        return self.head == self.maze.exit

    def reset(self) -> None:
        self.cells = [self.maze.start]

    def try_extend(self, cell: Cell) -> StepResult:
        cell = (int(cell[0]), int(cell[1]))
        if cell == self.head:
            return StepResult.UNCHANGED
        if not self.maze.in_bounds(cell):
            return StepResult.NOT_ADJACENT
        if len(self.cells) >= 2 and cell == self.cells[-2]:
            self.cells.pop()
            return StepResult.BACKTRACKED
        direction = self.maze.direction_between(self.head, cell)
        if direction is None:
            return StepResult.NOT_ADJACENT
        if self.completed:
            return StepResult.ALREADY_COMPLETE
        if self.maze.has_wall(self.head, direction):
            return StepResult.BLOCKED_WALL
        if cell in self.cells:
            return StepResult.BLOCKED_SELF
        self.cells.append(cell)
        return StepResult.COMPLETED if cell == self.maze.exit else StepResult.MOVED

    def step(self, direction: int) -> StepResult:
        dx, dy = DELTA[direction]
        return self.try_extend((self.head[0] + dx, self.head[1] + dy))
