"""Breadth-first solver. Validates generated mazes and powers the hint system."""
from collections import deque
from typing import Dict, List, Optional

from game.maze.maze import Cell, Maze


def solve(maze: Maze, start: Optional[Cell] = None, goal: Optional[Cell] = None) -> Optional[List[Cell]]:
    """Shortest path from start (default: maze entrance) to goal (default: exit), or None."""
    start = start or maze.start
    goal = goal or maze.exit
    if not (maze.in_bounds(start) and maze.in_bounds(goal)):
        return None
    parents: Dict[Cell, Optional[Cell]] = {start: None}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur == goal:
            path: List[Cell] = []
            node: Optional[Cell] = cur
            while node is not None:
                path.append(node)
                node = parents[node]
            return path[::-1]
        for nxt in maze.open_neighbors(cur):
            if nxt not in parents:
                parents[nxt] = cur
                queue.append(nxt)
    return None


def is_solvable(maze: Maze) -> bool:
    return solve(maze) is not None


def hint(maze: Maze, from_cell: Cell, steps: int = 3) -> List[Cell]:
    """The next `steps` cells of the shortest route from `from_cell` to the exit."""
    route = solve(maze, start=from_cell)
    return route[1:1 + steps] if route else []
