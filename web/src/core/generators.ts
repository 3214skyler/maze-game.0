import { Cell, Maze } from "./maze";
import { Rng } from "./rng";
import { isSolvable } from "./solver";

export type Algorithm = "backtracker" | "prim" | "kruskal";
export const ALGORITHMS: readonly Algorithm[] = ["backtracker", "prim", "kruskal"];

export class MazeGenerationError extends Error {}

const key = (m: Maze, c: Cell) => c[1] * m.width + c[0];

function backtracker(m: Maze, rng: Rng): void {
  const first: Cell = [rng.int(m.width), rng.int(m.height)];
  const visited = new Set<number>([key(m, first)]);
  const stack: Cell[] = [first];
  while (stack.length) {
    const cur = stack[stack.length - 1] as Cell;
    const options = [...m.neighbors(cur)].filter((n) => !visited.has(key(m, n)));
    if (!options.length) {
      stack.pop();
      continue;
    }
    const next = rng.pick(options);
    m.carve(cur, next);
    visited.add(key(m, next));
    stack.push(next);
  }
}

function prim(m: Maze, rng: Rng): void {
  const first: Cell = [rng.int(m.width), rng.int(m.height)];
  const inMaze = new Set<number>([key(m, first)]);
  const frontier: Array<[Cell, Cell]> = [...m.neighbors(first)].map((n) => [first, n]);
  while (frontier.length) {
    const i = rng.int(frontier.length);
    const last = frontier.length - 1;
    [frontier[i], frontier[last]] = [frontier[last] as [Cell, Cell], frontier[i] as [Cell, Cell]];
    const [a, b] = frontier.pop() as [Cell, Cell];
    if (inMaze.has(key(m, b))) continue;
    m.carve(a, b);
    inMaze.add(key(m, b));
    for (const n of m.neighbors(b)) if (!inMaze.has(key(m, n))) frontier.push([b, n]);
  }
}

function kruskal(m: Maze, rng: Rng): void {
  const parent = Array.from({ length: m.width * m.height }, (_, i) => i);
  const find = (i: number): number => {
    while (parent[i] !== i) {
      parent[i] = parent[parent[i] as number] as number;
      i = parent[i] as number;
    }
    return i;
  };
  const edges: Array<[Cell, Cell]> = [];
  for (let y = 0; y < m.height; y++) {
    for (let x = 0; x < m.width; x++) {
      if (x + 1 < m.width) edges.push([[x, y], [x + 1, y]]);
      if (y + 1 < m.height) edges.push([[x, y], [x, y + 1]]);
    }
  }
  rng.shuffle(edges);
  for (const [a, b] of edges) {
    const ra = find(key(m, a));
    const rb = find(key(m, b));
    if (ra !== rb) {
      parent[ra] = rb;
      m.carve(a, b);
    }
  }
}

const IMPL: Record<Algorithm, (m: Maze, rng: Rng) => void> = { backtracker, prim, kruskal };

/** Perfect (loop-free, fully connected) maze with an entrance on the left and an exit on the right. */
export function generate(width: number, height: number, seed?: number, algorithm: Algorithm = "backtracker"): Maze {
  if (!(algorithm in IMPL)) throw new RangeError(`unknown algorithm ${algorithm}`);
  const usedSeed = seed ?? Math.floor(Math.random() * 2 ** 32);
  const rng = new Rng(usedSeed);
  const maze = new Maze(width, height, usedSeed, algorithm);
  IMPL[algorithm](maze, rng);
  maze.openEntranceAndExit([0, rng.int(height)], [width - 1, rng.int(height)]);
  if (!isSolvable(maze)) throw new MazeGenerationError(`${algorithm} produced an unsolvable maze (seed=${usedSeed})`);
  return maze;
}
