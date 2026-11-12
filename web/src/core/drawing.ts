/** Device-independent drawing: pointer events in, path steps out (mouse and touch use the same code). */
import { Cell } from "./maze";
import { BLOCKING, PathManager, StepResult } from "./paths";

export type Phase = "press" | "move" | "release";
export interface PointerEv {
  phase: Phase;
  x: number;
  y: number;
  pointerId: number;
}

export class Viewport {
  constructor(readonly originX: number, readonly originY: number, readonly cellSize: number) {}

  toGrid(px: number, py: number): [number, number] {
    return [(px - this.originX) / this.cellSize, (py - this.originY) / this.cellSize];
  }

  toScreen(gx: number, gy: number): [number, number] {
    return [this.originX + gx * this.cellSize, this.originY + gy * this.cellSize];
  }
}

export class DrawingController {
  static readonly SAMPLE_STEP = 0.2; // cells
  private pointer: number | null = null;
  private lastGrid: [number, number] | null = null;
  private lastCell: Cell | null = null;

  constructor(private manager: PathManager, private viewport: Viewport, private grabRadius = 1.5) {}

  get drawing(): boolean {
    return this.pointer !== null;
  }

  handle(ev: PointerEv): StepResult[] {
    if (ev.phase === "press") return this.press(ev);
    if (ev.pointerId !== this.pointer) return [];
    if (ev.phase === "release") {
      this.pointer = this.lastGrid = this.lastCell = null;
      return [];
    }
    return this.move(ev);
  }

  private press(ev: PointerEv): StepResult[] {
    if (this.pointer !== null) return []; // extra fingers are ignored
    const [gx, gy] = this.viewport.toGrid(ev.x, ev.y);
    const [hx, hy] = this.manager.activePath.head;
    if (Math.hypot(gx - (hx + 0.5), gy - (hy + 0.5)) > this.grabRadius) return []; // must start near the head
    this.pointer = ev.pointerId;
    this.lastGrid = [gx, gy];
    this.lastCell = [Math.floor(gx), Math.floor(gy)];
    return [];
  }

  private move(ev: PointerEv): StepResult[] {
    const [gx, gy] = this.viewport.toGrid(ev.x, ev.y);
    const [lx, ly] = this.lastGrid as [number, number];
    const steps = Math.max(1, Math.ceil(Math.hypot(gx - lx, gy - ly) / DrawingController.SAMPLE_STEP));
    const results: StepResult[] = [];
    for (let i = 1; i <= steps; i++) {
      const t = i / steps;
      const cell: Cell = [Math.floor(lx + (gx - lx) * t), Math.floor(ly + (gy - ly) * t)];
      if (this.lastCell && cell[0] === this.lastCell[0] && cell[1] === this.lastCell[1]) continue;
      this.lastCell = cell;
      const r = this.manager.extend(cell);
      if (r === "unchanged" || r === "not_adjacent") continue;
      results.push(r);
      if (BLOCKING.has(r)) break;
    }
    this.lastGrid = [gx, gy];
    return results;
  }
}
