/** Classic levels (web). Deterministic from the level number; sizes follow the Android NORMAL curve. */
import { Algorithm, generate } from "../core/generators";
import { Maze } from "../core/maze";

export const MAX_LEVEL = 100;
export const BASE_SEED = 1000;
const CYCLE: readonly Algorithm[] = ["backtracker", "prim", "kruskal"];

export interface LevelConfig {
  number: number;
  width: number;
  height: number;
  seed: number;
  algorithm: Algorithm;
}

export function levelConfig(n: number): LevelConfig {
  if (!Number.isInteger(n) || n < 1) throw new RangeError("levels start at 1");
  const size = Math.min(5 + n, 24);
  return { number: n, width: size, height: size < 24 ? size + 2 : size, seed: BASE_SEED + n, algorithm: CYCLE[(n - 1) % CYCLE.length] as Algorithm };
}

export function buildLevel(n: number): Maze {
  const c = levelConfig(n);
  return generate(c.width, c.height, c.seed, c.algorithm);
}
