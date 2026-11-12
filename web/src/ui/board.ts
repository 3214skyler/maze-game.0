/** The interactive board: canvas + pointer/keyboard input -> DrawingController -> PathManager. */
import { DrawingController, Phase, Viewport } from "../core/drawing";
import { Maze, E, N, S, W } from "../core/maze";
import { BLOCKING, PATH_COLORS, PathColor, PathManager, StepResult } from "../core/paths";
import { drawBoard, layoutFor } from "./render";

export interface BoardCallbacks {
  onBlocked?: (r: StepResult) => void;
  onCompleted?: (color: PathColor) => void;
  onChange?: () => void;
}

const ARROWS: Record<string, number> = { ArrowUp: N, ArrowRight: E, ArrowDown: S, ArrowLeft: W };

export class GameBoard {
  readonly canvas = document.createElement("canvas");
  manager: PathManager;
  disabled = false;
  private ctx: CanvasRenderingContext2D;
  private vp: Viewport;
  private controller: DrawingController;
  private w = 1;
  private h = 1;
  private raf = 0;
  private dirty = true;
  private ro: ResizeObserver;

  constructor(private parent: HTMLElement, public maze: Maze, private cb: BoardCallbacks = {}, private glow = true) {
    this.canvas.className = "board";
    this.canvas.setAttribute("aria-label", "Maze board: draw a path from the cyan start to the gold exit");
    const ctx = this.canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas 2D is not available in this browser");
    this.ctx = ctx;
    this.manager = new PathManager(maze);
    this.vp = layoutFor(1, 1, maze);
    this.controller = new DrawingController(this.manager, this.vp);
    parent.appendChild(this.canvas);
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(parent);
    for (const [type, phase] of [["pointerdown", "press"], ["pointermove", "move"], ["pointerup", "release"], ["pointercancel", "release"]] as const) {
      this.canvas.addEventListener(type, (e) => this.pointer(phase, e));
    }
    window.addEventListener("keydown", this.onKey);
    this.resize();
    this.loop();
  }

  setGlow(on: boolean): void {
    this.glow = on;
    this.dirty = true;
  }

  select(color: PathColor): void {
    this.manager.select(color);
    this.dirty = true;
    this.cb.onChange?.();
  }

  resetActive(): void {
    this.manager.reset(this.manager.active);
    this.dirty = true;
    this.cb.onChange?.();
  }

  private resize(): void {
    const w = Math.max(1, this.parent.clientWidth);
    const h = Math.max(1, this.parent.clientHeight);
    const dpr = window.devicePixelRatio || 1;
    this.w = w;
    this.h = h;
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.vp = layoutFor(w, h, this.maze);
    this.controller = new DrawingController(this.manager, this.vp);
    this.dirty = true;
  }

  private loop = (): void => {
    if (this.dirty) {
      this.dirty = false;
      drawBoard(this.ctx, this.w, this.h, this.vp, this.maze, this.manager, { glow: this.glow });
    }
    this.raf = requestAnimationFrame(this.loop);
  };

  private pointer(phase: Phase, e: PointerEvent): void {
    if (this.disabled) return;
    if (e.pointerType === "mouse" && e.button !== 0 && phase === "press") return; // left button only
    if (phase === "press") this.canvas.setPointerCapture(e.pointerId);
    e.preventDefault();
    const rect = this.canvas.getBoundingClientRect();
    const wasDone = this.manager.activePath.completed;
    const results = this.controller.handle({ phase, x: e.clientX - rect.left, y: e.clientY - rect.top, pointerId: e.pointerId });
    this.after(results, wasDone);
  }

  private onKey = (e: KeyboardEvent): void => {
    if (this.disabled || e.ctrlKey || e.metaKey || e.altKey) return;
    const target = e.target as HTMLElement | null;
    if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
    const idx = ["1", "2", "3"].indexOf(e.key);
    if (idx >= 0) return this.select(PATH_COLORS[idx] as PathColor);
    if (e.key === "r" || e.key === "R") return this.resetActive();
    const dir = ARROWS[e.key];
    if (dir !== undefined) {
      e.preventDefault();
      const wasDone = this.manager.activePath.completed;
      this.after([this.manager.move(dir)], wasDone);
    }
  };

  private after(results: StepResult[], wasDone: boolean): void {
    if (!results.length) return;
    this.dirty = true;
    this.cb.onChange?.();
    for (const r of results) if (BLOCKING.has(r)) this.cb.onBlocked?.(r);
    if (!wasDone && this.manager.activePath.completed) this.cb.onCompleted?.(this.manager.active);
  }

  destroy(): void {
    cancelAnimationFrame(this.raf);
    this.ro.disconnect();
    window.removeEventListener("keydown", this.onKey);
    this.canvas.remove();
  }
}
