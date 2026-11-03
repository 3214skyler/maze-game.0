"""Owns the three independent paths. Each has its own state, reset and completion."""
from typing import Dict, List, Sequence

from game.core.config import PATH_COLORS
from game.maze.maze import Cell, Maze
from game.paths.path import Path, StepResult


class PathManager:
    def __init__(self, maze: Maze, colors: Sequence[str] = PATH_COLORS):
        self.maze = maze
        self.paths: Dict[str, Path] = {c: Path(c, maze) for c in colors}
        self.active: str = colors[0]

    def select(self, color: str) -> None:
        if color not in self.paths:
            raise KeyError(f"unknown path colour {color!r}")
        self.active = color  # switching never touches any path's cells

    def path(self, color: str) -> Path:
        return self.paths[color]

    @property
    def active_path(self) -> Path:
        return self.paths[self.active]

    def extend(self, cell: Cell) -> StepResult:
        return self.active_path.try_extend(cell)

    def move(self, direction: int) -> StepResult:
        """Keyboard navigation: one step from the active path's head."""
        return self.active_path.step(direction)

    def reset(self, color: str) -> None:
        self.paths[color].reset()

    def reset_all(self) -> None:
        for p in self.paths.values():
            p.reset()

    def completed_colors(self) -> List[str]:
        return [c for c, p in self.paths.items() if p.completed]

    @property
    def all_completed(self) -> bool:
        return all(p.completed for p in self.paths.values())

    # --- storage: each path is serialised and validated on its own ---------
    def to_dict(self) -> Dict[str, List[List[int]]]:
        return {c: [list(cell) for cell in p.cells] for c, p in self.paths.items()}

    def load_dict(self, data: Dict[str, List[List[int]]]) -> None:
        """Replay stored cells through the rules; raises ValueError on any invalid step."""
        staged: Dict[str, Path] = {}
        for color, cells in data.items():
            if color not in self.paths:
                raise ValueError(f"unknown path colour {color!r}")
            if not cells or tuple(cells[0]) != self.maze.start:
                raise ValueError(f"{color} path must begin at the maze entrance")
            p = Path(color, self.maze)
            for cell in cells[1:]:
                if p.try_extend(tuple(cell)) not in (StepResult.MOVED, StepResult.COMPLETED):
                    raise ValueError(f"{color} path contains an invalid step at {cell}")
            staged[color] = p
        self.paths.update(staged)  # only applied if every path was valid
