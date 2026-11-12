/** TypeScript web client -> real HTTP -> fake Supabase -> REAL PostgreSQL (the production SQL migration).
 * Skipped automatically when Python/PostgreSQL are not available. */
import { ChildProcess, spawn } from "node:child_process";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { Cell } from "../src/core/maze";
import { solve } from "../src/core/solver";
import { Account } from "../src/net/account";
import { StorageLike } from "../src/net/auth";
import { DailyClient } from "../src/net/daily";
import { AuthError, NetworkError, ServerError } from "../src/net/errors";
import { HttpClient } from "../src/net/http";
import { Maze } from "../src/core/maze";

const ANON = "anon-test-key";
const ROOT = path.resolve(__dirname, "../..");
let proc: ChildProcess | null = null;
let base = "";

const memStorage = (): StorageLike => {
  const m = new Map<string, string>();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v), removeItem: (k) => void m.delete(k) };
};

async function control(name: string, body: unknown = {}) {
  const r = await fetch(`${base}/__test__/${name}`, { method: "POST", body: JSON.stringify(body) });
  expect(r.status).toBe(200);
}

const newAccount = (storage: StorageLike = memStorage(), clock?: () => number) => new Account({ url: base, anonKey: ANON }, storage, new HttpClient(), clock);

async function signedUp(email: string, username: string, storage?: StorageLike) {
  const acc = newAccount(storage);
  expect(await acc.signUp(email, "secret12", username)).toBe("signed_in");
  return acc;
}

/** A path that follows the real solution and then steps THROUGH a wall. */
function wallCrossing(maze: Maze): Cell[] {
  const route = solve(maze)!;
  for (let i = 0; i < route.length; i++) {
    for (const n of maze.neighbors(route[i] as Cell)) if (!maze.canMove(route[i] as Cell, n)) return [...route.slice(0, i + 1), n];
  }
  throw new Error("no wall next to the solution");
}

const secondsNeeded = (maze: Maze, extra = 2) => solve(maze)!.length * 0.08 + extra;

beforeAll(async () => {
  try {
    proc = spawn("python3", [path.join(ROOT, "tests", "http_fake_supabase.py")], { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"] });
    base = await new Promise<string>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("fake Supabase did not start")), 20000);
      proc!.stdout!.on("data", (d: Buffer) => {
        const m = /PORT=(\d+)/.exec(d.toString());
        if (m) { clearTimeout(timer); resolve(`http://127.0.0.1:${m[1]}`); }
      });
      proc!.on("exit", () => { clearTimeout(timer); reject(new Error("fake Supabase exited (no Python/PostgreSQL?)")); });
      proc!.on("error", reject);
    });
  } catch (e) {
    console.warn(`e2e tests skipped: ${(e as Error).message}`);
    proc?.kill();
    proc = null;
  }
}, 30000);

afterAll(() => void proc?.kill());

const e2e = (name: string, fn: () => Promise<void>) =>
  it(name, async (ctx) => {
    if (!proc) return ctx.skip();
    await control("reset");
    await fn();
  });

describe("accounts over real HTTP", () => {
  e2e("sign up, profile, session persistence and sign in on another device", async () => {
    const storage = memStorage();
    const a = await signedUp("web@t.dev", "web_player", storage);
    expect(a.username).toBe("web_player");
    const reopened = newAccount(storage); // same browser, page reloaded
    expect(reopened.signedIn).toBe(true);
    expect(await reopened.refreshProfile()).toBe("signed_in");
    expect(reopened.username).toBe("web_player");
    const other = newAccount(); // another browser
    expect(await other.signIn("web@t.dev", "secret12")).toBe("signed_in");
    expect(other.username).toBe("web_player");
  });

  e2e("username rules, wrong password and a dead connection give clean errors", async () => {
    await signedUp("one@t.dev", "taken_name");
    const b = newAccount();
    await expect(b.signUp("two@t.dev", "secret12", "TAKEN_name")).rejects.toThrow("already taken");
    expect(b.signedIn).toBe(true);
    await expect(b.setUsername("x")).rejects.toThrow("3-20");
    await b.setUsername("free_name");
    await expect(newAccount().signIn("one@t.dev", "wrong-password")).rejects.toBeInstanceOf(AuthError);
    await control("offline", { offline: true });
    await expect(newAccount().signIn("one@t.dev", "secret12")).rejects.toBeInstanceOf(NetworkError);
    await control("offline", { offline: false });
    expect(await newAccount().signIn("one@t.dev", "secret12")).toBe("signed_in");
  });

  e2e("a token about to expire is refreshed against the real auth endpoint", async () => {
    const storage = memStorage();
    const first = await signedUp("tok@t.dev", "tok_player", storage);
    const before = first.api.session!.accessToken;
    const later = newAccount(storage, () => Date.now() + 3_599_000);
    await later.refreshProfile();
    expect(later.api.session!.accessToken).not.toBe(before);
    expect(later.username).toBe("tok_player");
  });
});

describe("daily challenge over real HTTP", () => {
  e2e("play, rank, leaderboard: the server accepts the web client's run", async () => {
    await control("publish");
    const a = new DailyClient((await signedUp("a@t.dev", "daily_a")).api);
    const b = new DailyClient((await signedUp("b@t.dev", "daily_b")).api);
    const runA = await a.start();
    await control("age_run", { run_id: runA.runId, seconds: secondsNeeded(runA.maze, 18) });
    const resA = await a.submit(runA, solve(runA.maze)!);
    expect(resA).toMatchObject({ accepted: true, rank: 1 });
    const runB = await b.start();
    await control("age_run", { run_id: runB.runId, seconds: secondsNeeded(runB.maze, 7) });
    expect((await b.submit(runB, solve(runB.maze)!)).rank).toBe(1); // faster
    const board = await a.leaderboard();
    expect(board.map((r) => [r.rank, r.username, r.isMe])).toEqual([[1, "daily_b", false], [2, "daily_a", true]]);
  });

  e2e("cheating is rejected with readable reasons and never reaches the board", async () => {
    await control("publish");
    const acc = await signedUp("c@t.dev", "cheater_w");
    const client = new DailyClient(acc.api);
    const instant = await client.start();
    const r1 = await client.submit(instant, solve(instant.maze)!); // perfect path, submitted instantly
    expect(r1).toMatchObject({ accepted: false, reason: "too_fast" });
    expect(r1.message).toContain("quickly");
    const run = await client.start();
    await control("age_run", { run_id: run.runId, seconds: 30 });
    expect(await client.submit(run, wallCrossing(run.maze))).toMatchObject({ accepted: false, reason: "wall_crossed" });
    expect(await client.leaderboard()).toEqual([]);
  });

  e2e("the server maze round-trips into the web Maze class", async () => {
    await control("publish");
    const client = new DailyClient((await signedUp("d@t.dev", "maze_w")).api);
    const run = await client.start();
    expect(run.maze.width).toBeGreaterThanOrEqual(10);
    expect(solve(run.maze)).not.toBeNull();
    expect(run.maze.passageCount()).toBe(run.maze.width * run.maze.height - 1);
  });

  e2e("friendly errors: no challenge published, and the public board works signed out", async () => {
    const client = new DailyClient((await signedUp("e@t.dev", "early_w")).api);
    await expect(client.start()).rejects.toMatchObject({ code: "no_challenge_today" });
    const guest = new DailyClient(newAccount().api);
    expect(await guest.leaderboard()).toEqual([]);
    await expect(guest.start()).rejects.toBeInstanceOf(AuthError);
  });

  e2e("security: anonymous callers are refused by the database itself", async () => {
    const acc = newAccount();
    await expect(acc.api.rpc("start_daily_run", {}, true)).rejects.toMatchObject({ code: "permission_denied" });
    await expect(acc.api.rpc("load_progress", {}, true)).rejects.toBeInstanceOf(ServerError);
    for (const table of ["daily_challenges", "leaderboard_entries", "player_progress", "challenge_runs", "profiles"]) {
      const r = await fetch(`${base}/rest/v1/${table}?select=*`, { headers: { apikey: ANON } });
      expect([401, 403]).toContain(r.status);
    }
  });
});
