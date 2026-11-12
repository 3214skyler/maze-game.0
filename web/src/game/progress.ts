/** Local progress for the web build (unlocked level + best times). Stored in localStorage, validated on load. */
import { StorageLike } from "../net/auth";
import { MAX_LEVEL } from "./levels";

export interface Progress {
  highest: number;
  best: Record<string, number>; // level -> best time in ms
}

export interface WinInfo {
  newBest: boolean;
  unlocked: number | null;
}

export class ProgressStore {
  progress: Progress = { highest: 1, best: {} };

  constructor(private storage: StorageLike, private key = "maze.progress.v1") {
    this.progress = this.load();
  }

  private load(): Progress {
    try {
      const raw = this.storage.getItem(this.key);
      if (!raw) return { highest: 1, best: {} };
      const d = JSON.parse(raw) as { highest?: unknown; best?: unknown };
      const highest = Number.isInteger(d.highest) ? Math.min(Math.max(d.highest as number, 1), MAX_LEVEL) : 1;
      const best: Record<string, number> = {};
      if (d.best && typeof d.best === "object") {
        for (const [k, v] of Object.entries(d.best as Record<string, unknown>)) {
          if (/^\d+$/.test(k) && typeof v === "number" && Number.isFinite(v) && v > 0) best[k] = v;
        }
      }
      return { highest, best };
    } catch {
      return { highest: 1, best: {} }; // corrupt or blocked storage: start fresh instead of crashing
    }
  }

  private save(): void {
    try {
      this.storage.setItem(this.key, JSON.stringify(this.progress));
    } catch {
      /* private mode / quota: progress stays in memory for this session */
    }
  }

  isUnlocked(level: number): boolean {
    return level >= 1 && level <= this.progress.highest;
  }

  isCompleted(level: number): boolean {
    return String(level) in this.progress.best;
  }

  bestTime(level: number): number | null {
    return this.progress.best[String(level)] ?? null;
  }

  recordWin(level: number, ms: number): WinInfo {
    if (!this.isUnlocked(level)) throw new RangeError(`level ${level} is locked`);
    const prev = this.bestTime(level);
    const newBest = prev === null || ms < prev;
    if (newBest) this.progress.best[String(level)] = Math.round(ms);
    let unlocked: number | null = null;
    if (level === this.progress.highest && level < MAX_LEVEL) {
      this.progress.highest = level + 1;
      unlocked = level + 1;
    }
    this.save();
    return { newBest, unlocked };
  }
}
