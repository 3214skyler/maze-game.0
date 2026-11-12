/** Client side of the daily challenge. All judging happens on the server; this only plays and submits. */
import { Cell, Maze } from "../core/maze";
import { ApiClient } from "./api";
import { ServerError } from "./errors";

export const REJECTIONS: Record<string, string> = {
  too_fast: "Submitted too quickly to be a legitimate run.",
  wall_crossed: "The submitted path crosses a wall.",
  self_crossing: "The path crosses itself.",
  exit_not_reached: "The path does not reach the exit.",
  run_expired: "This run took too long and expired.",
};

export const ERRORS: Record<string, string> = {
  no_challenge_today: "Today's challenge is not published yet. Try again later.",
  profile_required: "Choose a username before playing the daily challenge.",
  too_many_attempts: "Attempt limit reached for today. Come back tomorrow!",
  not_authenticated: "Sign in to play the daily challenge.",
};

export interface DailyRun {
  runId: string;
  day: string;
  maze: Maze;
}

export interface DailyResult {
  accepted: boolean;
  elapsedMs: number;
  rank: number | null;
  bestMs: number | null;
  reason: string | null;
  message: string;
}

export interface BoardRow {
  rank: number;
  username: string;
  elapsedMs: number;
  isMe: boolean;
}

export const friendly = (e: ServerError): string => ERRORS[e.code] ?? `Server error: ${e.code}`;

export function fmtMs(ms: number): string {
  const s = ms / 1000;
  return `${Math.floor(s / 60)}:${(s % 60).toFixed(2).padStart(5, "0")}`;
}

export class DailyClient {
  constructor(private api: ApiClient) {}

  async start(): Promise<DailyRun> {
    const body = await this.api.rpc<{ run_id: string; day: string }>("start_daily_run");
    return { runId: body.run_id, day: body.day, maze: Maze.fromJSON(body) }; // MazeFormatError if malformed
  }

  async submit(run: DailyRun, cells: readonly Cell[]): Promise<DailyResult> {
    const b = await this.api.rpc<{ accepted: boolean; elapsed_ms: number; rank?: number; best_ms?: number; reason?: string }>(
      "submit_daily_run",
      { p_run_id: run.runId, p_path: cells.map((c) => [c[0], c[1]]) },
    );
    const reason = b.reason ?? null;
    return {
      accepted: !!b.accepted,
      elapsedMs: Number(b.elapsed_ms),
      rank: b.rank ?? null,
      bestMs: b.best_ms ?? null,
      reason,
      message: b.accepted ? "" : REJECTIONS[reason ?? ""] ?? "The run was rejected.",
    };
  }

  async leaderboard(day: string | null = null, limit = 50): Promise<BoardRow[]> {
    const rows = await this.api.rpc<Array<{ rank: number; username: string; elapsed_ms: number; is_me: boolean }> | null>(
      "get_daily_leaderboard",
      { p_day: day, p_limit: limit },
      true,
    );
    return (rows ?? []).map((r) => ({ rank: Number(r.rank), username: String(r.username), elapsedMs: Number(r.elapsed_ms), isMe: !!r.is_me }));
  }
}
