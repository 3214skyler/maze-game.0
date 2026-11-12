import { describe, expect, it } from "vitest";
import { generate } from "../src/core/generators";
import { Maze, MazeFormatError } from "../src/core/maze";
import { solve } from "../src/core/solver";
import { buildLevel, levelConfig, MAX_LEVEL } from "../src/game/levels";
import { ProgressStore } from "../src/game/progress";
import { Account } from "../src/net/account";
import { ApiClient } from "../src/net/api";
import { AuthClient, Session, SessionStore, StorageLike } from "../src/net/auth";
import { makeConfig } from "../src/net/config";
import { DailyClient, fmtMs } from "../src/net/daily";
import { AuthError, NetworkError, ServerError } from "../src/net/errors";
import { HttpClient } from "../src/net/http";

const CFG = { url: "https://x.supabase.co", anonKey: "sb_publishable_test" };
const FAR_FUTURE = 8_000_000_000_000; // year 2225: a session that never needs refreshing in a test

interface Call {
  url: string;
  headers: Record<string, string>;
  body: unknown;
}

/** Scripted fetch: handler(call) -> [status, body]. Records every call. */
function scripted(handler: (c: Call, n: number) => [number, unknown] | Error) {
  const calls: Call[] = [];
  const fetchImpl = async (url: string, init?: RequestInit): Promise<Response> => {
    const call: Call = { url, headers: (init?.headers ?? {}) as Record<string, string>, body: init?.body ? JSON.parse(init.body as string) : undefined };
    calls.push(call);
    const r = handler(call, calls.length);
    if (r instanceof Error) throw r;
    return new Response(r[1] === null || r[1] === undefined ? "" : JSON.stringify(r[1]), { status: r[0] });
  };
  return { http: new HttpClient(fetchImpl), calls };
}

const memStorage = (): StorageLike & { data: Map<string, string> } => {
  const data = new Map<string, string>();
  return { data, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v), removeItem: (k) => void data.delete(k) };
};

const tokenBody = (n: number, expiresIn = 3600) => ({ access_token: `access-${n}`, refresh_token: `refresh-${n}`, expires_in: expiresIn, user: { id: "u1" } });
const session = (expiresAt: number): Session => ({ accessToken: "access-0", refreshToken: "refresh-0", expiresAt, userId: "u1" });

describe("config", () => {
  it("validates the public project settings", () => {
    expect(makeConfig(undefined, undefined)).toBeNull();
    expect(makeConfig("https://x.supabase.co/", "k")).toEqual({ url: "https://x.supabase.co", anonKey: "k" });
    expect(makeConfig("http://127.0.0.1:5000", "k")?.url).toBe("http://127.0.0.1:5000");
    expect(() => makeConfig("http://evil.example.com", "k")).toThrow();
  });
});

describe("SessionStore", () => {
  it("round-trips, survives corrupt data and a blocked storage", () => {
    const st = memStorage();
    const store = new SessionStore(st);
    expect(store.load()).toBeNull();
    store.save(session(123));
    expect(new SessionStore(st).load()).toEqual(session(123));
    st.setItem("maze.session.v1", "garbage");
    expect(store.load()).toBeNull();
    st.setItem("maze.session.v1", JSON.stringify({ accessToken: 1 }));
    expect(store.load()).toBeNull();
    const blocked: StorageLike = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); }, removeItem: () => { throw new Error("blocked"); } };
    const s2 = new SessionStore(blocked);
    expect(s2.load()).toBeNull();
    expect(() => { s2.save(session(1)); s2.clear(); }).not.toThrow();
  });
});

describe("AuthClient", () => {
  it("signs in and sends only the public key", async () => {
    const { http, calls } = scripted(() => [200, tokenBody(1)]);
    const s = await new AuthClient(CFG, http, () => 1000).signIn("a@b.co", "pw12345");
    expect(s).toEqual({ accessToken: "access-1", refreshToken: "refresh-1", expiresAt: 1000 + 3_600_000, userId: "u1" });
    expect(calls[0]?.url).toBe("https://x.supabase.co/auth/v1/token?grant_type=password");
    expect(calls[0]?.headers.apikey).toBe("sb_publishable_test");
    expect(calls[0]?.headers.Authorization).toBeUndefined();
  });

  it("maps failures to AuthError with the server's message", async () => {
    const { http } = scripted(() => [400, { error_description: "Invalid login credentials" }]);
    await expect(new AuthClient(CFG, http).signIn("a@b.co", "x")).rejects.toThrow("Invalid login credentials");
    await expect(new AuthClient(CFG, http).signIn("a@b.co", "x")).rejects.toBeInstanceOf(AuthError);
  });

  it("sign up returns null when the project requires e-mail confirmation", async () => {
    const { http } = scripted(() => [200, { id: "u1", email: "a@b.co" }]);
    expect(await new AuthClient(CFG, http).signUp("a@b.co", "pw12345")).toBeNull();
  });

  it("a dropped connection is a NetworkError", async () => {
    const { http } = scripted(() => new TypeError("fetch failed"));
    await expect(new AuthClient(CFG, http).signIn("a", "b")).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("ApiClient", () => {
  const make = (handler: Parameters<typeof scripted>[0], s: Session | null, clock = () => 0) => {
    const sc = scripted(handler);
    const store = new SessionStore(memStorage());
    const api = new ApiClient(CFG, sc.http, new AuthClient(CFG, sc.http, clock), store, s, clock);
    return { api, store, ...sc };
  };

  it("anonymous calls send ONLY apikey (publishable keys are not JWTs)", async () => {
    const { api, calls } = make(() => [200, []], null);
    await api.rpc("get_daily_leaderboard", {}, true);
    expect(calls[0]?.headers.apikey).toBe("sb_publishable_test");
    expect(calls[0]?.headers.Authorization).toBeUndefined();
    expect(calls[0]?.url).toBe("https://x.supabase.co/rest/v1/rpc/get_daily_leaderboard");
  });

  it("signed-in calls send the user's token, and refuse to run when signed out", async () => {
    const { api, calls } = make(() => [200, { ok: 1 }], session(FAR_FUTURE));
    await api.rpc("get_my_profile");
    expect(calls[0]?.headers.Authorization).toBe("Bearer access-0");
    await expect(make(() => [200, null], null).api.rpc("get_my_profile")).rejects.toBeInstanceOf(AuthError);
  });

  it("refreshes a token that is about to expire", async () => {
    const { api, calls } = make((c) => (c.url.includes("/auth/v1/token") ? [200, tokenBody(1)] : [200, { ok: 1 }]), session(30_000), () => 0);
    await api.rpc("get_my_profile");
    expect(calls.map((c) => c.url.split("/").slice(-1)[0])).toEqual(["token?grant_type=refresh_token", "get_my_profile"]);
    expect(calls[1]?.headers.Authorization).toBe("Bearer access-1");
    expect(api.session?.accessToken).toBe("access-1");
  });

  it("a 401 refreshes once and retries", async () => {
    let first = true;
    const { api, calls } = make((c) => {
      if (c.url.includes("/auth/v1/token")) return [200, tokenBody(2)];
      if (first) { first = false; return [401, { message: "JWT expired" }]; }
      return [200, { ok: 1 }];
    }, session(FAR_FUTURE));
    expect(await api.rpc("get_my_profile")).toEqual({ ok: 1 });
    expect(calls).toHaveLength(3);
  });

  it("a rejected refresh token signs the player out", async () => {
    const { api, store } = make((c) => (c.url.includes("/auth/v1/token") ? [400, { error_description: "Invalid Refresh Token" }] : [401, {}]), session(FAR_FUTURE));
    store.save(session(FAR_FUTURE));
    await expect(api.rpc("get_my_profile")).rejects.toBeInstanceOf(AuthError);
    expect(api.signedIn).toBe(false);
    expect(store.load()).toBeNull();
  });

  it.each([
    [400, { code: "P0001", message: "username_taken" }, "username_taken"],
    [403, { code: "42501", message: "permission denied" }, "permission_denied"],
    [404, { code: "PGRST202", message: "not found" }, "rpc_not_found"],
    [500, { code: "XX000", message: "boom" }, "XX000"],
    [502, "<html>bad gateway</html>", "server_error"],
  ])("maps HTTP %i to ServerError(%s)", async (status, body, code) => {
    const { api } = make(() => [status, body], session(FAR_FUTURE));
    await expect(api.rpc("x")).rejects.toMatchObject({ code });
    await expect(api.rpc("x")).rejects.toBeInstanceOf(ServerError);
  });
});

describe("Account", () => {
  const setup = (handler: Parameters<typeof scripted>[0]) => {
    const sc = scripted(handler);
    return { account: new Account(CFG, memStorage(), sc.http), ...sc };
  };

  it("sign up creates the session and the profile", async () => {
    const { account, calls } = setup((c) => (c.url.endsWith("/auth/v1/signup") ? [200, tokenBody(1)] : [200, null]));
    expect(await account.signUp("a@b.co", "pw12345", "neo_01")).toBe("signed_in");
    expect(account.signedIn && account.username).toBe("neo_01");
    expect(calls[1]?.body).toEqual({ p_username: "neo_01" });
  });

  it("e-mail confirmation and missing username are reported as states", async () => {
    expect(await setup(() => [200, { id: "u" }]).account.signUp("a@b.co", "pw12345", "neo_01")).toBe("confirm_email");
    const { account } = setup((c) => (c.url.includes("/token") ? [200, tokenBody(1)] : [200, null]));
    expect(await account.signIn("a@b.co", "pw12345")).toBe("needs_username");
  });

  it("username errors become friendly messages; sign out clears everything", async () => {
    const { account } = setup((c) => {
      if (c.url.endsWith("/auth/v1/signup")) return [200, tokenBody(1)];
      return [400, { code: "P0001", message: "username_taken" }];
    });
    await expect(account.signUp("a@b.co", "pw12345", "taken_1")).rejects.toThrow("already taken");
    expect(account.signedIn).toBe(true);
    account.signOut();
    expect(account.signedIn).toBe(false);
  });
});

describe("DailyClient", () => {
  const maze = generate(10, 10, 5);
  const startBody = { run_id: "r1", day: "2026-11-06", ...maze.toJSON() };
  const client = (handler: Parameters<typeof scripted>[0]) => {
    const sc = scripted(handler);
    const api = new ApiClient(CFG, sc.http, new AuthClient(CFG, sc.http), null, session(FAR_FUTURE));
    return { daily: new DailyClient(api), ...sc };
  };

  it("start parses the maze the server sends; malformed data is rejected", async () => {
    const run = await client(() => [200, startBody]).daily.start();
    expect(run.runId).toBe("r1");
    expect(run.maze.walls).toEqual(maze.walls);
    await expect(client(() => [200, { ...startBody, walls: [[1]] }]).daily.start()).rejects.toBeInstanceOf(MazeFormatError);
  });

  it("submit sends the path as [x,y] pairs and maps accept/reject", async () => {
    const { daily, calls } = client((_c, n) => (n === 1 ? [200, { accepted: true, elapsed_ms: 12345, best_ms: 12345, rank: 2 }] : [200, { accepted: false, reason: "too_fast", elapsed_ms: 900 }]));
    const run = { runId: "r1", day: "d", maze };
    const ok = await daily.submit(run, solve(maze)!);
    expect(ok).toMatchObject({ accepted: true, rank: 2, elapsedMs: 12345, message: "" });
    expect((calls[0]?.body as { p_path: unknown[] }).p_path[0]).toEqual([...maze.start]);
    const bad = await daily.submit(run, solve(maze)!);
    expect(bad).toMatchObject({ accepted: false, reason: "too_fast" });
    expect(bad.message).toContain("quickly");
  });

  it("leaderboard maps rows and tolerates an empty/null board", async () => {
    const rows = await client(() => [200, [{ rank: 1, username: "ana", elapsed_ms: 41010, is_me: true }]]).daily.leaderboard();
    expect(rows).toEqual([{ rank: 1, username: "ana", elapsedMs: 41010, isMe: true }]);
    expect(await client(() => [200, null]).daily.leaderboard()).toEqual([]);
  });

  it("formats times", () => {
    expect(fmtMs(41010)).toBe("0:41.01");
    expect(fmtMs(78000)).toBe("1:18.00");
  });
});

describe("levels", () => {
  it("follow the Android NORMAL size curve, deterministic and solvable", () => {
    expect([1, 5, 10, 50].map((n) => levelConfig(n).width)).toEqual([6, 10, 15, 24]);
    expect(levelConfig(1).height).toBe(8);
    for (let n = 1; n <= 30; n++) {
      const a = buildLevel(n);
      expect(a.walls).toEqual(buildLevel(n).walls);
      expect(solve(a)).not.toBeNull();
    }
    expect(() => levelConfig(0)).toThrow(RangeError);
  });
});

describe("ProgressStore", () => {
  it("unlocks the next level after a win and keeps the best time", () => {
    const st = memStorage();
    const p = new ProgressStore(st);
    expect(p.isUnlocked(1) && !p.isUnlocked(2)).toBe(true);
    expect(() => p.recordWin(2, 1000)).toThrow(RangeError);
    expect(p.recordWin(1, 9000)).toEqual({ newBest: true, unlocked: 2 });
    expect(p.recordWin(1, 12000)).toEqual({ newBest: false, unlocked: null });
    expect(p.recordWin(1, 7000)).toEqual({ newBest: true, unlocked: null });
    expect(p.bestTime(1)).toBe(7000);
    expect(p.isCompleted(1) && !p.isCompleted(2)).toBe(true);
    const again = new ProgressStore(st); // "reopen the browser"
    expect(again.progress).toEqual({ highest: 2, best: { "1": 7000 } });
  });

  it("recovers from corrupt or tampered storage and stops at the last level", () => {
    const st = memStorage();
    st.setItem("maze.progress.v1", "{nope");
    expect(new ProgressStore(st).progress).toEqual({ highest: 1, best: {} });
    st.setItem("maze.progress.v1", JSON.stringify({ highest: 99999, best: { "1": -5, x: 3, "2": "no", "3": 4000 } }));
    expect(new ProgressStore(st).progress).toEqual({ highest: MAX_LEVEL, best: { "3": 4000 } });
    const p = new ProgressStore(st);
    expect(p.recordWin(MAX_LEVEL, 5000).unlocked).toBeNull();
  });
});

describe("Maze import", () => {
  it("fromJSON(toJSON) is stable for every algorithm", () => {
    for (const algo of ["backtracker", "prim", "kruskal"] as const) {
      const m = generate(11, 9, 3, algo);
      expect(Maze.fromJSON(m.toJSON()).walls).toEqual(m.walls);
    }
  });
});
