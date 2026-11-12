/** The three independent paths and their rules. Mirrors game/paths in the Python game. */
import { Cell, DELTA, Maze, sameCell } from "./maze";

export const PATH_COLORS = ["blue", "green", "red"] as const;
export type PathColor = (typeof PATH_COLORS)[number];

export type StepResult =
  | "moved"
  | "completed"
  | "backtracked"
  | "unchanged"
  | "blocked_wall"
  | "blocked_self"
  | "already_complete"
  | "not_adjacent";

export const BLOCKING: ReadonlySet<StepResult> = new Set<StepResult>(["blocked_wall", "blocked_self", "already_complete"]);

export class Path {
  cells: Cell[];

  constructor(readonly color: PathColor, readonly maze: Maze) {
    this.cells = [maze.start];
  }

  get head(): Cell {
    return this.cells[this.cells.length - 1] as Cell;
  }

  get completed(): boolean {
    return sameCell(this.head, this.maze.exit);
  }

  reset(): void {
    this.cells = [this.maze.start];
  }

  tryExtend(cell: Cell): StepResult {
    if (sameCell(cell, this.head)) return "unchanged";
    if (!this.maze.inBounds(cell)) return "not_adjacent";
    if (this.cells.length >= 2 && sameCell(cell, this.cells[this.cells.length - 2] as Cell)) {
      this.cells.pop();
      return "backtracked";
    }
    const d = Maze.directionBetween(this.head, cell);
    if (d === null) return "not_adjacent";
    if (this.completed) return "already_complete";
    if (this.maze.hasWall(this.head, d)) return "blocked_wall";
    if (this.cells.some((c) => sameCell(c, cell))) return "blocked_self";
    this.cells.push(cell);
    return sameCell(cell, this.maze.exit) ? "completed" : "moved";
  }

  step(direction: number): StepResult {
    const delta = DELTA[direction] as readonly [number, number];
    return this.tryExtend([this.head[0] + delta[0], this.head[1] + delta[1]]);
  }
}

export class PathManager {
  readonly paths: Record<PathColor, Path>;
  active: PathColor = "blue";

  constructor(readonly maze: Maze) {
    this.paths = { blue: new Path("blue", maze), green: new Path("green", maze), red: new Path("red", maze) };
  }

  select(color: PathColor): void {
    if (!(color in this.paths)) throw new RangeError(`unknown path colour ${color}`);
    this.active = color; // switching never touches any path's cells
  }

  path(color: PathColor): Path {
    return this.paths[color];
  }

  get activePath(): Path {
    return this.paths[this.active];
  }

  extend(cell: Cell): StepResult {
    return this.activePath.tryExtend(cell);
  }

  move(direction: number): StepResult {
    return this.activePath.step(direction);
  }

  reset(color: PathColor): void {
    this.paths[color].reset();
  }

  resetAll(): void {
    for (const c of PATH_COLORS) this.paths[c].reset();
  }

  completedColors(): PathColor[] {
    return PATH_COLORS.filter((c) => this.paths[c].completed);
  }

  get allCompleted(): boolean {
    return PATH_COLORS.every((c) => this.paths[c].completed);
  }
}
