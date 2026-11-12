import { createCanvas } from "@napi-rs/canvas";
import { describe, expect, it } from "vitest";
import { Maze } from "../src/core/maze";
import { PathManager } from "../src/core/paths";
import { COLORS, drawBoard, layoutFor } from "../src/ui/render";

/** 3x2 maze with a corridor (0,0)-(1,0)-(2,0)-(2,1). */
function corridor(): Maze {
  const m = new Maze(3, 2);
  m.carve([0, 0], [1, 0]); m.carve([1, 0], [2, 0]); m.carve([2, 0], [2, 1]); m.carve([0, 0], [0, 1]);
  m.openEntranceAndExit([0, 0], [2, 1]);
  return m;
}

const hex = (h: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number];

function render(glow: boolean, withPaths = true) {
  const W = 360;
  const H = 280;
  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext("2d");
  const maze = corridor();
  const pm = new PathManager(maze);
  if (withPaths) {
    pm.extend([1, 0]); pm.extend([2, 0]);
    pm.select("green"); pm.extend([0, 1]);
    pm.select("blue");
  }
  const vp = layoutFor(W, H, maze);
  drawBoard(ctx as unknown as CanvasRenderingContext2D, W, H, vp, maze, withPaths ? pm : null, { glow });
  const px = (x: number, y: number) => Array.from(ctx.getImageData(Math.round(x), Math.round(y), 1, 1).data) as number[];
  return { px, vp, maze };
}

const close = (a: number[], b: [number, number, number], tol = 6) => [0, 1, 2].every((i) => Math.abs((a[i] as number) - b[i]!) <= tol);

describe("layoutFor", () => {
  it("centres the maze and keeps a margin", () => {
    const maze = corridor();
    const vp = layoutFor(300, 200, maze);
    expect(vp.cellSize).toBeCloseTo(Math.min(300 / 3, 200 / 2) * 0.94);
    expect(vp.originX + (vp.cellSize * 3) / 2).toBeCloseTo(150);
    expect(vp.originY + (vp.cellSize * 2) / 2).toBeCloseTo(100);
  });
});

describe("drawBoard", () => {
  it("paints the palette: background, panel, walls and the active path on top", () => {
    const { px, vp } = render(false);
    const at = (gx: number, gy: number) => px(...vp.toScreen(gx, gy));
    expect(close(px(2, 2), hex(COLORS.bgBlack), 3)).toBe(true);        // outside the maze
    expect(close(at(1.5, 1.5), hex(COLORS.bgNavy), 3)).toBe(true);     // an untouched cell: navy panel
    expect(close(at(1.5, 0), hex(COLORS.purple), 6)).toBe(true);       // a wall on the top edge
    expect(close(at(1.5, 0.5), hex(COLORS.blue), 6)).toBe(true);       // the ACTIVE path (blue) is fully opaque
    expect(close(at(2.5, 0.5), hex(COLORS.blue), 6)).toBe(true);
  });

  it("inactive paths are drawn dimmer (75% opacity) so the active one stands out", () => {
    const { px, vp } = render(false);
    const g = hex(COLORS.green);
    const n = hex(COLORS.bgNavy);
    const blended = g.map((c, i) => 0.75 * c + 0.25 * n[i]!) as [number, number, number];
    const mid = px(...vp.toScreen(0.5, 1.0));                          // middle of the green path's second segment
    expect(close(mid, blended, 8)).toBe(true);
    expect(mid[1]!).toBeLessThan(g[1]);                                // strictly dimmer than a pure green
  });

  it("glow adds a soft halo around neon lines; without glow there is none", () => {
    const on = render(true);
    const off = render(false);
    const [x, y] = on.vp.toScreen(1.5, 0);                                      // centre of the top wall
    const halo = (r: ReturnType<typeof render>) => r.px(x, y - r.vp.cellSize * 0.12);
    const withGlow = halo(on);
    const noGlow = halo(off);
    expect(close(noGlow, hex(COLORS.bgBlack), 3)).toBe(true);                   // crisp: pure background next to the wall
    expect(withGlow[0]! + withGlow[2]! > noGlow[0]! + noGlow[2]! + 20).toBe(true); // purple halo bleeds out
  });

  it("an empty board shows the cyan entrance and the gold exit", () => {
    const { px, vp } = render(false, false);
    expect(close(px(...vp.toScreen(0.5, 0.5)), hex(COLORS.cyan), 6)).toBe(true);
    expect(close(px(...vp.toScreen(2.5, 1.5)), hex(COLORS.gold), 6)).toBe(true);
  });
});
