import { describe, expect, it } from "vitest";
import { ALGORITHMS, generate } from "../src/core/generators";
import { E, Maze, MazeFormatError, N, S, W } from "../src/core/maze";
import { Rng } from "../src/core/rng";
import { hint, isSolvable, solve } from "../src/core/solver";

const SIZES: Array<[number, number]> = [[2, 2], [5, 5], [12, 7], [30, 30]];

describe("Rng", () => {
  it("is deterministic and well spread", () => {
    const a = new Rng(42);
    const b = new Rng(42);
    const seq = Array.from({ length: 50 }, () => a.next());
    expect(seq).toEqual(Array.from({ length: 50 }, () => b.next()));
    expect(seq.every((v) => v >= 0 && v < 1)).toBe(true);
    expect(new Set(seq).size).toBe(50);
    expect(new Rng(1).next()).not.toBe(new Rng(2).next());
  });
  it("shuffle keeps all elements", () => {
    const items = Array.from({ length: 20 }, (_, i) => i);
    expect(new Rng(7).shuffle([...items]).sort((x, y) => x - y)).toEqual(items);
  });
});

describe.each(ALGORITHMS)("generator %s", (algo) => {
  it.each(SIZES)("makes perfect, solvable %ix%i mazes", (w, h) => {
    for (let seed = 0; seed < 5; seed++) {
      const m = generate(w, h, seed, algo);
      expect(m.passageCount()).toBe(w * h - 1); // spanning tree: connected, no loops
      expect(isSolvable(m)).toBe(true);
      const route = solve(m)!;
      expect(route[0]).toEqual(m.start);
      expect(route[route.length - 1]).toEqual(m.exit);
    }
  });

  it("has a valid entrance on the left and an exit on the right", () => {
    for (let seed = 0; seed < 20; seed++) {
      const m = generate(10, 10, seed, algo);
      expect(m.start[0]).toBe(0);
      expect(m.exit[0]).toBe(9);
      expect(m.hasWall(m.start, W)).toBe(false);
      expect(m.hasWall(m.exit, E)).toBe(false);
    }
  });

  it("reproduces the same maze from the same seed", () => {
    const a = generate(15, 15, 42, algo);
    const b = generate(15, 15, 42, algo);
    expect(a.walls).toEqual(b.walls);
    expect([a.start, a.exit]).toEqual([b.start, b.exit]);
  });
});

describe("maze", () => {
  it("different seeds give different mazes; an unseeded maze records its seed", () => {
    expect(generate(15, 15, 1).walls).not.toEqual(generate(15, 15, 2).walls);
    const m = generate(8, 8);
    expect(generate(8, 8, m.seed!).walls).toEqual(m.walls);
  });

  it("rejects bad arguments", () => {
    expect(() => generate(1, 5)).toThrow(RangeError);
    expect(() => generate(5, 5, 1, "nope" as never)).toThrow(RangeError);
  });

  it("collision rules between cells", () => {
    const m = new Maze(2, 2);
    m.carve([0, 0], [1, 0]);
    expect(m.canMove([0, 0], [1, 0]) && m.canMove([1, 0], [0, 0])).toBe(true);
    expect(m.canMove([0, 0], [0, 1])).toBe(false); // wall
    expect(m.canMove([0, 0], [1, 1])).toBe(false); // diagonal
    expect(m.canMove([0, 0], [-1, 0])).toBe(false); // outside
    expect(m.hasWall([0, 0], N) && m.hasWall([0, 0], S)).toBe(true);
  });

  it("solver: none when walled off, shortest path, hints", () => {
    const walled = new Maze(3, 3);
    walled.openEntranceAndExit([0, 0], [2, 2]);
    expect(solve(walled)).toBeNull();
    const m = new Maze(3, 2);
    m.carve([0, 0], [1, 0]); m.carve([1, 0], [2, 0]); m.carve([2, 0], [2, 1]); m.carve([0, 0], [0, 1]);
    m.openEntranceAndExit([0, 0], [2, 1]);
    expect(solve(m)).toEqual([[0, 0], [1, 0], [2, 0], [2, 1]]);
    expect(hint(m, [0, 1], 2)).toEqual([[0, 0], [1, 0]]);
    expect(hint(m, [1, 0], 5)).toEqual([[2, 0], [2, 1]]);
  });

  it("wall segments are axis-aligned and inside the grid", () => {
    const m = generate(8, 6, 3);
    const segs = m.wallSegments();
    expect(segs.length).toBeGreaterThan(0);
    for (const [[x1, y1], [x2, y2]] of segs) {
      expect((x1 === x2) !== (y1 === y2)).toBe(true);
      expect(x1 >= 0 && x2 <= 8 && y1 >= 0 && y2 <= 6 && x1 <= x2 && y1 <= y2).toBe(true);
    }
  });
});

describe("maze JSON (the format the server sends)", () => {
  it("round-trips", () => {
    const m = generate(9, 7, 5, "kruskal");
    const r = Maze.fromJSON(JSON.parse(JSON.stringify(m.toJSON())));
    expect(r.walls).toEqual(m.walls);
    expect([r.start, r.exit]).toEqual([m.start, m.exit]);
    expect(solve(r)).toEqual(solve(m));
  });

  it.each([
    [{}],
    [null],
    [{ width: 3, height: 3 }],
    [{ width: 4, height: 4, walls: [[0]], start: [0, 0], exit: [1, 1] }],
    [{ width: 4, height: 4, walls: Array(4).fill(Array(4).fill(99)), start: [0, 0], exit: [3, 3] }],
    [{ width: 4, height: 4, walls: Array(4).fill(Array(4).fill(15)), start: [9, 9], exit: [3, 3] }],
    [{ width: "x", height: 4, walls: [], start: [0, 0], exit: [3, 3] }],
    [{ width: 4, height: 4, walls: Array(4).fill(Array(4).fill(15)), start: "a", exit: [3, 3] }],
  ])("rejects malformed data %#", (bad) => {
    expect(() => Maze.fromJSON(bad)).toThrow(MazeFormatError);
  });
});
