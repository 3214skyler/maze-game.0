/** Canvas drawing of the maze and the three paths. Pure functions of a 2D context (testable in Node). */
import { Viewport } from "../core/drawing";
import { Maze } from "../core/maze";
import { PATH_COLORS, PathManager } from "../core/paths";

export const COLORS = {
  bgBlack: "#070A12",
  bgNavy: "#10182B",
  blue: "#00BFFF",
  green: "#39FF88",
  red: "#FF3158",
  purple: "#A855F7",
  cyan: "#00F5FF",
  gold: "#FFD700",
} as const;

export interface RenderOptions {
  glow: boolean;
}

/** Fits the maze inside width x height (CSS pixels) with a small margin, centred. */
export function layoutFor(width: number, height: number, maze: Maze): Viewport {
  const cell = Math.max(1, Math.min(width / maze.width, height / maze.height) * 0.94);
  return new Viewport((width - cell * maze.width) / 2, (height - cell * maze.height) / 2, cell);
}

function dot(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, color: string, glow: boolean) {
  ctx.save();
  if (glow) {
    ctx.shadowColor = color;
    ctx.shadowBlur = r * 2.2;
  }
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

export function drawBoard(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  vp: Viewport,
  maze: Maze,
  paths: PathManager | null,
  opts: RenderOptions,
): void {
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = COLORS.bgBlack;
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = COLORS.bgNavy;
  ctx.fillRect(vp.originX, vp.originY, vp.cellSize * maze.width, vp.cellSize * maze.height);

  // walls: one batched path, neon purple with a soft glow
  ctx.save();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = COLORS.purple;
  ctx.lineWidth = Math.max(1.5, vp.cellSize * 0.07);
  if (opts.glow) {
    ctx.shadowColor = COLORS.purple;
    ctx.shadowBlur = vp.cellSize * 0.45;
  }
  ctx.beginPath();
  for (const [a, b] of maze.wallSegments()) {
    const [x1, y1] = vp.toScreen(a[0], a[1]);
    const [x2, y2] = vp.toScreen(b[0], b[1]);
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
  }
  ctx.stroke();
  ctx.restore();

  // entrance (cyan) and exit (gold)
  const r = vp.cellSize * 0.22;
  const [sx, sy] = vp.toScreen(maze.start[0] + 0.5, maze.start[1] + 0.5);
  const [ex, ey] = vp.toScreen(maze.exit[0] + 0.5, maze.exit[1] + 0.5);
  dot(ctx, sx, sy, r, COLORS.cyan, opts.glow);
  dot(ctx, ex, ey, r, COLORS.gold, opts.glow);

  if (!paths) return;
  // inactive paths first so the active one is always on top
  const order = [...PATH_COLORS].sort((a, b) => Number(a === paths.active) - Number(b === paths.active));
  for (const color of order) {
    const path = paths.path(color);
    const active = color === paths.active;
    const pts = path.cells.map((c) => vp.toScreen(c[0] + 0.5, c[1] + 0.5));
    ctx.save();
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.globalAlpha = active ? 1 : 0.75;
    ctx.strokeStyle = COLORS[color];
    ctx.lineWidth = vp.cellSize * (active ? 0.3 : 0.2);
    if (opts.glow) {
      ctx.shadowColor = COLORS[color];
      ctx.shadowBlur = vp.cellSize * 0.6;
    }
    if (pts.length >= 2) {
      ctx.beginPath();
      pts.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
      ctx.stroke();
    }
    ctx.restore();
    const [hx, hy] = pts[pts.length - 1] as [number, number];
    const hr = vp.cellSize * (active ? 0.26 : 0.18);
    if (path.completed) dot(ctx, hx, hy, hr * 1.2, "#ffffff", opts.glow);
    dot(ctx, hx, hy, hr * 0.7, COLORS[color], false);
  }
}
