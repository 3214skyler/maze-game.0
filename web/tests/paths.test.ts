import { describe, expect, it } from "vitest";
import { DrawingController, PointerEv, Viewport } from "../src/core/drawing";
import { generate } from "../src/core/generators";
import { E, Maze, S } from "../src/core/maze";
import { Path, PathManager } from "../src/core/paths";
import { solve } from "../src/core/solver";

/** 3x2 maze: (0,0)-(1,0)-(2,0)-(2,1), plus a dead end (0,1) off (0,0). */
function corridor(): Maze {
  const m = new Maze(3, 2);
  m.carve([0, 0], [1, 0]); m.carve([1, 0], [2, 0]); m.carve([2, 0], [2, 1]); m.carve([0, 0], [0, 1]);
  m.openEntranceAndExit([0, 0], [2, 1]);
  return m;
}

describe("Path rules", () => {
  it("walks to the exit and completes", () => {
    const p = new Path("blue", corridor());
    expect(p.tryExtend([1, 0])).toBe("moved");
    expect(p.tryExtend([2, 0])).toBe("moved");
    expect(p.tryExtend([2, 1])).toBe("completed");
    expect(p.completed).toBe(true);
  });

  it("a wall blocks and changes nothing", () => {
    const p = new Path("blue", corridor());
    p.tryExtend([1, 0]);
    expect(p.tryExtend([1, 1])).toBe("blocked_wall");
    expect(p.cells).toEqual([[0, 0], [1, 0]]);
  });

  it("rejects diagonal, far and outside cells", () => {
    const p = new Path("red", corridor());
    expect(p.tryExtend([1, 1])).toBe("not_adjacent");
    expect(p.tryExtend([2, 0])).toBe("not_adjacent");
    expect(p.tryExtend([-1, 0])).toBe("not_adjacent");
    expect(p.cells).toEqual([[0, 0]]);
  });

  it("backtracks one cell at a time", () => {
    const p = new Path("green", corridor());
    p.tryExtend([1, 0]); p.tryExtend([2, 0]);
    expect(p.tryExtend([2, 0])).toBe("unchanged");
    expect(p.tryExtend([1, 0])).toBe("backtracked");
    expect(p.cells).toEqual([[0, 0], [1, 0]]);
  });

  it("cannot cross itself", () => {
    const m = new Maze(3, 2);
    for (const [a, b] of [[[0, 0], [1, 0]], [[1, 0], [1, 1]], [[1, 1], [0, 1]], [[0, 1], [0, 0]], [[1, 0], [2, 0]]] as Array<[[number, number], [number, number]]>) m.carve(a, b);
    m.openEntranceAndExit([0, 0], [2, 0]);
    const p = new Path("blue", m);
    for (const c of [[1, 0], [1, 1], [0, 1]] as Array<[number, number]>) expect(p.tryExtend(c)).toBe("moved");
    expect(p.tryExtend([0, 0])).toBe("blocked_self");
    expect(p.cells).toEqual([[0, 0], [1, 0], [1, 1], [0, 1]]);
  });

  it("cannot extend past the exit", () => {
    const p = new Path("blue", corridor());
    for (const c of [[1, 0], [2, 0], [2, 1]] as Array<[number, number]>) p.tryExtend(c);
    expect(p.tryExtend([1, 1])).toBe("already_complete");
  });

  it("keyboard steps", () => {
    const pm = new PathManager(corridor());
    expect(pm.move(E)).toBe("moved");
    expect(pm.move(S)).toBe("blocked_wall");
  });
});

describe("three independent paths", () => {
  it("each keeps its own state; switching colour deletes nothing", () => {
    const pm = new PathManager(corridor());
    pm.select("blue"); pm.extend([1, 0]); pm.extend([2, 0]);
    pm.select("green"); pm.extend([0, 1]);
    pm.select("red");
    expect(pm.path("blue").cells).toEqual([[0, 0], [1, 0], [2, 0]]);
    expect(pm.path("green").cells).toEqual([[0, 0], [0, 1]]);
    expect(pm.path("red").cells).toEqual([[0, 0]]);
    const before = JSON.stringify(pm.paths);
    for (const c of ["green", "red", "blue", "red"] as const) pm.select(c);
    expect(JSON.stringify(pm.paths)).toBe(before);
  });

  it("reset and completion are per path", () => {
    const pm = new PathManager(corridor());
    const finish = () => { for (const c of [[1, 0], [2, 0], [2, 1]] as Array<[number, number]>) pm.extend(c); };
    for (const color of ["blue", "green"] as const) { pm.select(color); finish(); }
    expect(pm.completedColors()).toEqual(["blue", "green"]);
    expect(pm.allCompleted).toBe(false);
    pm.reset("blue");
    expect(pm.completedColors()).toEqual(["green"]);
    pm.select("red"); finish(); pm.select("blue"); finish();
    expect(pm.allCompleted).toBe(true);
    pm.resetAll();
    expect(pm.completedColors()).toEqual([]);
  });

  it("walking the real solution completes the path on generated mazes", () => {
    for (let seed = 0; seed < 10; seed++) {
      const m = generate(12, 12, seed, (["backtracker", "prim", "kruskal"] as const)[seed % 3]);
      const pm = new PathManager(m);
      const results = solve(m)!.slice(1).map((c) => pm.extend(c));
      expect(results[results.length - 1]).toBe("completed");
    }
  });
});

describe("DrawingController", () => {
  const CELL = 100;
  const vp = new Viewport(0, 0, CELL); // grid origin at the top-left, y down
  const centre = (cx: number, cy: number): [number, number] => [cx * CELL + CELL / 2, cy * CELL + CELL / 2];
  const ev = (phase: PointerEv["phase"], cell: [number, number], pointerId = 0): PointerEv => {
    const [x, y] = centre(...cell);
    return { phase, x, y, pointerId };
  };
  const make = () => {
    const pm = new PathManager(corridor());
    return { pm, dc: new DrawingController(pm, vp) };
  };

  it("draws a path with a drag", () => {
    const { pm, dc } = make();
    dc.handle(ev("press", [0, 0]));
    expect(dc.handle(ev("move", [1, 0]))).toEqual(["moved"]);
    expect(dc.handle(ev("move", [2, 0]))).toEqual(["moved"]);
    expect(pm.activePath.cells).toEqual([[0, 0], [1, 0], [2, 0]]);
    dc.handle(ev("release", [2, 0]));
    expect(dc.drawing).toBe(false);
  });

  it("a fast swipe does not skip cells", () => {
    const { pm, dc } = make();
    dc.handle(ev("press", [0, 0]));
    expect(dc.handle(ev("move", [2, 0]))).toEqual(["moved", "moved"]);
    expect(pm.activePath.cells).toEqual([[0, 0], [1, 0], [2, 0]]);
  });

  it("a diagonal swipe stops at the first wall", () => {
    const { pm, dc } = make();
    dc.handle(ev("press", [0, 0]));
    expect(dc.handle(ev("move", [2, 1]))).toEqual(["moved", "blocked_wall"]);
    expect(pm.activePath.cells).toEqual([[0, 0], [1, 0]]);
  });

  it("reports a wall once, not on every move event", () => {
    const { dc } = make();
    dc.handle(ev("press", [0, 0])); dc.handle(ev("move", [1, 0]));
    expect(dc.handle(ev("move", [1, 1]))).toEqual(["blocked_wall"]);
    expect(dc.handle(ev("move", [1, 1]))).toEqual([]);
  });

  it("ignores presses far from the head and extra fingers", () => {
    const a = make();
    a.dc.handle(ev("press", [2, 1]));
    expect(a.dc.drawing).toBe(false);
    const b = make();
    b.dc.handle(ev("press", [0, 0], 7)); b.dc.handle(ev("press", [0, 0], 8));
    expect(b.dc.handle(ev("move", [1, 0], 8))).toEqual([]);
    expect(b.dc.handle(ev("move", [1, 0], 7))).toEqual(["moved"]);
  });

  it("resumes from the head and backtracks by dragging back", () => {
    const { pm, dc } = make();
    dc.handle(ev("press", [0, 0])); dc.handle(ev("move", [1, 0])); dc.handle(ev("release", [1, 0]));
    dc.handle(ev("press", [1, 0]));
    expect(dc.handle(ev("move", [0, 0]))).toEqual(["backtracked"]);
    expect(pm.activePath.cells).toEqual([[0, 0]]);
  });

  it("only the active colour changes", () => {
    const { pm, dc } = make();
    pm.select("green");
    dc.handle(ev("press", [0, 0])); dc.handle(ev("move", [1, 0]));
    expect(pm.path("green").cells).toEqual([[0, 0], [1, 0]]);
    expect(pm.path("blue").cells).toEqual([[0, 0]]);
  });

  it("reports completion", () => {
    const { dc } = make();
    dc.handle(ev("press", [0, 0]));
    dc.handle(ev("move", [1, 0])); dc.handle(ev("move", [2, 0]));
    expect(dc.handle(ev("move", [2, 1]))).toEqual(["completed"]);
  });
});
