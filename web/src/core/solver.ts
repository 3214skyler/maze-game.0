import { Cell, Maze, sameCell } from "./maze";

/** Shortest path (BFS) from start (default: entrance) to goal (default: exit), or null. */
export function solve(maze: Maze, start: Cell = maze.start, goal: Cell = maze.exit): Cell[] | null {
  if (!maze.inBounds(start) || !maze.inBounds(goal)) return null;
  const key = (c: Cell) => c[1] * maze.width + c[0];
  const parent = new Map<number, Cell | null>([[key(start), null]]);
  const queue: Cell[] = [start];
  for (let head = 0; head < queue.length; head++) {
    const cur = queue[head] as Cell;
    if (sameCell(cur, goal)) {
      const path: Cell[] = [];
      let node: Cell | null = cur;
      while (node) {
        path.push(node);
        node = parent.get(key(node)) ?? null;
      }
      return path.reverse();
    }
    for (const n of maze.openNeighbors(cur)) {
      if (!parent.has(key(n))) {
        parent.set(key(n), cur);
        queue.push(n);
      }
    }
  }
  return null;
}

export const isSolvable = (maze: Maze): boolean => solve(maze) !== null;

/** The next `steps` cells of the shortest route from `from` to the exit. */
export function hint(maze: Maze, from: Cell, steps = 3): Cell[] {
  const route = solve(maze, from);
  return route ? route.slice(1, 1 + steps) : [];
}
