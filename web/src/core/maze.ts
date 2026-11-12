/** Maze data structure. Same wall bitmask as the server and the Python game: N=1 E=2 S=4 W=8. */
export const N = 1;
export const E = 2;
export const S = 4;
export const W = 8;
export const DIRECTIONS = [N, E, S, W] as const;
export const DELTA: Record<number, readonly [number, number]> = {
  [N]: [0, -1],
  [E]: [1, 0],
  [S]: [0, 1],
  [W]: [-1, 0],
};
export const OPPOSITE: Record<number, number> = { [N]: S, [E]: W, [S]: N, [W]: E };

export type Cell = readonly [number, number];

export interface MazeJSON {
  width: number;
  height: number;
  start: [number, number];
  exit: [number, number];
  walls: number[][];
  seed?: number | null;
  algorithm?: string;
}

export class MazeFormatError extends Error {}

export const sameCell = (a: Cell, b: Cell): boolean => a[0] === b[0] && a[1] === b[1];

export class Maze {
  walls: number[][];
  start: Cell;
  exit: Cell;

  constructor(
    readonly width: number,
    readonly height: number,
    public seed: number | null = null,
    public algorithm = "unknown",
  ) {
    if (width < 2 || height < 2) throw new RangeError("maze must be at least 2x2");
    this.walls = Array.from({ length: height }, () => new Array<number>(width).fill(N | E | S | W));
    this.start = [0, 0];
    this.exit = [width - 1, height - 1];
  }

  private cellWalls(c: Cell): number {
    return (this.walls[c[1]] as number[])[c[0]] as number;
  }

  inBounds(c: Cell): boolean {
    return c[0] >= 0 && c[0] < this.width && c[1] >= 0 && c[1] < this.height;
  }

  static directionBetween(a: Cell, b: Cell): number | null {
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    for (const d of DIRECTIONS) {
      const delta = DELTA[d] as readonly [number, number];
      if (delta[0] === dx && delta[1] === dy) return d;
    }
    return null;
  }

  hasWall(c: Cell, direction: number): boolean {
    return (this.cellWalls(c) & direction) !== 0;
  }

  *neighbors(c: Cell): Generator<Cell> {
    for (const d of DIRECTIONS) {
      const delta = DELTA[d] as readonly [number, number];
      const n: Cell = [c[0] + delta[0], c[1] + delta[1]];
      if (this.inBounds(n)) yield n;
    }
  }

  canMove(a: Cell, b: Cell): boolean {
    if (!this.inBounds(a) || !this.inBounds(b)) return false;
    const d = Maze.directionBetween(a, b);
    return d !== null && !this.hasWall(a, d);
  }

  *openNeighbors(c: Cell): Generator<Cell> {
    for (const n of this.neighbors(c)) if (this.canMove(c, n)) yield n;
  }

  /** Open passages between cells (a perfect maze has width*height-1). */
  passageCount(): number {
    let total = 0;
    for (let y = 0; y < this.height; y++) {
      for (let x = 0; x < this.width; x++) {
        if (x + 1 < this.width && !this.hasWall([x, y], E)) total++;
        if (y + 1 < this.height && !this.hasWall([x, y], S)) total++;
      }
    }
    return total;
  }

  carve(a: Cell, b: Cell): void {
    const d = Maze.directionBetween(a, b);
    if (d === null || !this.inBounds(a) || !this.inBounds(b)) throw new RangeError(`cells ${a} and ${b} are not adjacent`);
    (this.walls[a[1]] as number[])[a[0]] = this.cellWalls(a) & ~d;
    (this.walls[b[1]] as number[])[b[0]] = this.cellWalls(b) & ~(OPPOSITE[d] as number);
  }

  openEntranceAndExit(start: Cell, exit: Cell): void {
    this.start = start;
    this.exit = exit;
    (this.walls[start[1]] as number[])[start[0]] = this.cellWalls(start) & ~W;
    (this.walls[exit[1]] as number[])[exit[0]] = this.cellWalls(exit) & ~E;
  }

  private hWall(x: number, y: number): boolean {
    return y < this.height ? this.hasWall([x, y], N) : this.hasWall([x, this.height - 1], S);
  }

  private vWall(x: number, y: number): boolean {
    return x < this.width ? this.hasWall([x, y], W) : this.hasWall([this.width - 1, y], E);
  }

  /** Wall segments on grid lines, merged into long runs (for renderers). */
  wallSegments(): Array<[Cell, Cell]> {
    const segs: Array<[Cell, Cell]> = [];
    for (let y = 0; y <= this.height; y++) {
      let x = 0;
      while (x < this.width) {
        if (this.hWall(x, y)) {
          const x0 = x;
          while (x < this.width && this.hWall(x, y)) x++;
          segs.push([[x0, y], [x, y]]);
        } else x++;
      }
    }
    for (let x = 0; x <= this.width; x++) {
      let y = 0;
      while (y < this.height) {
        if (this.vWall(x, y)) {
          const y0 = y;
          while (y < this.height && this.vWall(x, y)) y++;
          segs.push([[x, y0], [x, y]]);
        } else y++;
      }
    }
    return segs;
  }

  toJSON(): MazeJSON {
    return {
      width: this.width,
      height: this.height,
      start: [this.start[0], this.start[1]],
      exit: [this.exit[0], this.exit[1]],
      walls: this.walls.map((r) => [...r]),
      seed: this.seed,
      algorithm: this.algorithm,
    };
  }

  /** Rebuild from untrusted data (e.g. the server response). Throws MazeFormatError when malformed. */
  static fromJSON(data: unknown): Maze {
    const d = data as Partial<MazeJSON> | null;
    if (!d || typeof d !== "object") throw new MazeFormatError("maze data is not an object");
    const { width, height, walls, start, exit } = d;
    if (!Number.isInteger(width) || !Number.isInteger(height) || (width as number) < 2 || (height as number) < 2) {
      throw new MazeFormatError("invalid maze size");
    }
    const w = width as number;
    const h = height as number;
    if (!Array.isArray(walls) || walls.length !== h) throw new MazeFormatError("wall grid does not match the size");
    for (const row of walls) {
      if (!Array.isArray(row) || row.length !== w || row.some((v) => !Number.isInteger(v) || v < 0 || v > 15)) {
        throw new MazeFormatError("wall grid does not match the size");
      }
    }
    const cell = (c: unknown): Cell => {
      if (!Array.isArray(c) || c.length !== 2 || !c.every((v) => Number.isInteger(v))) {
        throw new MazeFormatError("invalid entrance or exit");
      }
      return [c[0] as number, c[1] as number];
    };
    const maze = new Maze(w, h, d.seed ?? null, d.algorithm ?? "server");
    maze.walls = walls.map((r) => [...r]);
    maze.start = cell(start);
    maze.exit = cell(exit);
    if (!maze.inBounds(maze.start) || !maze.inBounds(maze.exit)) throw new MazeFormatError("entrance or exit outside the maze");
    return maze;
  }
}
