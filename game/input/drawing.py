"""Input abstraction layer: devices produce PointerEvents, the game never sees raw devices."""
import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from game.paths.manager import PathManager
from game.paths.path import BLOCKING, StepResult


class Phase(Enum):
    PRESS = "press"
    MOVE = "move"
    RELEASE = "release"


@dataclass(frozen=True)
class PointerEvent:
    phase: Phase
    x: float
    y: float
    pointer_id: int = 0       # touch uid, or 0 for the mouse
    source: str = "mouse"     # "mouse" | "touch"


@dataclass(frozen=True)
class Viewport:
    """Maps screen pixels (y up, Kivy style) to fractional grid coordinates."""
    origin_x: float   # screen x of the maze's left edge
    top_y: float      # screen y of the maze's top edge
    cell_size: float

    def to_grid(self, px: float, py: float) -> Tuple[float, float]:
        return ((px - self.origin_x) / self.cell_size, (self.top_y - py) / self.cell_size)

    def to_screen(self, gx: float, gy: float) -> Tuple[float, float]:
        return (self.origin_x + gx * self.cell_size, self.top_y - gy * self.cell_size)


class DrawingController:
    """Turns a stream of pointer events into path steps on the active path.

    * Fast drags are sampled along the segment so no cell is skipped.
    * Only one pointer draws at a time; extra fingers are ignored.
    * A stroke must begin near the path's head so the player can resume drawing.
    """
    SAMPLE_STEP = 0.2  # in cells

    def __init__(self, manager: PathManager, viewport: Viewport, grab_radius: float = 1.5):
        self.manager = manager
        self.viewport = viewport
        self.grab_radius = grab_radius
        self._pointer: Optional[int] = None
        self._last_grid: Optional[Tuple[float, float]] = None
        self._last_cell: Optional[Tuple[int, int]] = None

    @property
    def drawing(self) -> bool:
        return self._pointer is not None

    def handle(self, ev: PointerEvent) -> List[StepResult]:
        if ev.phase is Phase.PRESS:
            return self._press(ev)
        if ev.pointer_id != self._pointer:
            return []
        if ev.phase is Phase.RELEASE:
            self._pointer = self._last_grid = self._last_cell = None
            return []
        return self._move(ev)

    def _press(self, ev: PointerEvent) -> List[StepResult]:
        if self._pointer is not None:
            return []
        gx, gy = self.viewport.to_grid(ev.x, ev.y)
        hx, hy = self.manager.active_path.head
        if math.hypot(gx - (hx + 0.5), gy - (hy + 0.5)) > self.grab_radius:
            return []
        self._pointer = ev.pointer_id
        self._last_grid = (gx, gy)
        self._last_cell = (math.floor(gx), math.floor(gy))
        return []

    def _move(self, ev: PointerEvent) -> List[StepResult]:
        gx, gy = self.viewport.to_grid(ev.x, ev.y)
        (lx, ly) = self._last_grid
        dist = math.hypot(gx - lx, gy - ly)
        steps = max(1, math.ceil(dist / self.SAMPLE_STEP))
        results: List[StepResult] = []
        for i in range(1, steps + 1):
            t = i / steps
            cell = (math.floor(lx + (gx - lx) * t), math.floor(ly + (gy - ly) * t))
            if cell == self._last_cell:
                continue
            self._last_cell = cell
            result = self.manager.extend(cell)
            if result in (StepResult.UNCHANGED, StepResult.NOT_ADJACENT):
                continue
            results.append(result)
            if result in BLOCKING:
                break
        self._last_grid = (gx, gy)
        return results
