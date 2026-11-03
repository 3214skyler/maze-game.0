"""Maze data structure. Pure logic: no rendering, no input."""
from typing import Iterator, List, Optional, Tuple

Cell = Tuple[int, int]  # (x, y), y grows downward

N, E, S, W = 1, 2, 4, 8
DELTA = {N: (0, -1), E: (1, 0), S: (0, 1), W: (-1, 0)}
OPPOSITE = {N: S, E: W, S: N, W: E}
DIRECTIONS = (N, E, S, W)


class Maze:
    """Grid of cells; each cell stores a bitmask of the walls still standing."""

    def __init__(self, width: int, height: int, seed: Optional[int] = None,
                 algorithm: str = "unknown"):
        if width < 2 or height < 2:
            raise ValueError("maze must be at least 2x2")
        self.width = width
        self.height = height
        self.seed = seed
        self.algorithm = algorithm
        self.walls: List[List[int]] = [[N | E | S | W] * width for _ in range(height)]
        self.start: Cell = (0, 0)
        self.exit: Cell = (width - 1, height - 1)

    # --- queries ---------------------------------------------------------
    def in_bounds(self, cell: Cell) -> bool:
        x, y = cell
        return 0 <= x < self.width and 0 <= y < self.height

    @staticmethod
    def direction_between(a: Cell, b: Cell) -> Optional[int]:
        """Direction from a to b if they are orthogonally adjacent, else None."""
        d = (b[0] - a[0], b[1] - a[1])
        for direction, delta in DELTA.items():
            if delta == d:
                return direction
        return None

    def has_wall(self, cell: Cell, direction: int) -> bool:
        return bool(self.walls[cell[1]][cell[0]] & direction)

    def neighbors(self, cell: Cell) -> Iterator[Cell]:
        """In-bounds orthogonal neighbours, ignoring walls (fixed N,E,S,W order)."""
        for direction in DIRECTIONS:
            dx, dy = DELTA[direction]
            nxt = (cell[0] + dx, cell[1] + dy)
            if self.in_bounds(nxt):
                yield nxt

    def can_move(self, a: Cell, b: Cell) -> bool:
        """True when b is adjacent to a and no wall separates them."""
        if not (self.in_bounds(a) and self.in_bounds(b)):
            return False
        direction = self.direction_between(a, b)
        return direction is not None and not self.has_wall(a, direction)

    def open_neighbors(self, cell: Cell) -> Iterator[Cell]:
        for nxt in self.neighbors(cell):
            if self.can_move(cell, nxt):
                yield nxt

    def passage_count(self) -> int:
        """Number of open passages between cells (a perfect maze has w*h-1)."""
        total = 0
        for y in range(self.height):
            for x in range(self.width):
                if x + 1 < self.width and not self.has_wall((x, y), E):
                    total += 1
                if y + 1 < self.height and not self.has_wall((x, y), S):
                    total += 1
        return total

    # --- mutation (used by generators) -----------------------------------
    def carve(self, a: Cell, b: Cell) -> None:
        direction = self.direction_between(a, b)
        if direction is None or not (self.in_bounds(a) and self.in_bounds(b)):
            raise ValueError(f"cells {a} and {b} are not adjacent")
        self.walls[a[1]][a[0]] &= ~direction
        self.walls[b[1]][b[0]] &= ~OPPOSITE[direction]

    def open_entrance_and_exit(self, start: Cell, exit_: Cell) -> None:
        """Place entrance (left edge) and exit (right edge) and open the outer walls."""
        self.start, self.exit = start, exit_
        self.walls[start[1]][start[0]] &= ~W
        self.walls[exit_[1]][exit_[0]] &= ~E

    # --- geometry for renderers ------------------------------------------
    def _h_wall(self, x: int, y: int) -> bool:
        if y < self.height:
            return bool(self.walls[y][x] & N)
        return bool(self.walls[self.height - 1][x] & S)

    def _v_wall(self, x: int, y: int) -> bool:
        if x < self.width:
            return bool(self.walls[y][x] & W)
        return bool(self.walls[y][self.width - 1] & E)

    def wall_segments(self) -> List[Tuple[Cell, Cell]]:
        """Wall segments in grid-line coordinates, merged into long runs."""
        segs: List[Tuple[Cell, Cell]] = []
        for y in range(self.height + 1):
            x = 0
            while x < self.width:
                if self._h_wall(x, y):
                    x0 = x
                    while x < self.width and self._h_wall(x, y):
                        x += 1
                    segs.append(((x0, y), (x, y)))
                else:
                    x += 1
        for x in range(self.width + 1):
            y = 0
            while y < self.height:
                if self._v_wall(x, y):
                    y0 = y
                    while y < self.height and self._v_wall(x, y):
                        y += 1
                    segs.append(((x, y0), (x, y)))
                else:
                    y += 1
        return segs
