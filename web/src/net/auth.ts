/** Supabase Auth (GoTrue) over REST: sign up, sign in, refresh. Sessions live in localStorage. */
import { OnlineConfig } from "./config";
import { AuthError } from "./errors";
import { HttpClient } from "./http";

export interface Session {
  accessToken: string;
  refreshToken: string;
  expiresAt: number; // epoch ms
  userId: string;
}

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export const isExpiring = (s: Session, now: number, marginMs = 60_000): boolean => now >= s.expiresAt - marginMs;

export class SessionStore {
  constructor(private storage: StorageLike, private key = "maze.session.v1") {}

  load(): Session | null {
    try {
      const raw = this.storage.getItem(this.key);
      if (!raw) return null;
      const d = JSON.parse(raw) as Partial<Session>;
      if (typeof d.accessToken !== "string" || typeof d.refreshToken !== "string" || typeof d.userId !== "string" || typeof d.expiresAt !== "number") return null;
      return { accessToken: d.accessToken, refreshToken: d.refreshToken, userId: d.userId, expiresAt: d.expiresAt };
    } catch {
      return null; // corrupt or blocked storage: signed out, never a crash
    }
  }

  save(s: Session): void {
    try {
      this.storage.setItem(this.key, JSON.stringify(s));
    } catch {
      /* private mode / quota: not being able to remember the login is not fatal */
    }
  }

  clear(): void {
    try {
      this.storage.removeItem(this.key);
    } catch {
      /* ignore */
    }
  }
}

function message(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    for (const k of ["msg", "error_description", "message", "error"]) if (b[k]) return String(b[k]);
  }
  return `authentication failed (HTTP ${status})`;
}

function toSession(body: unknown, now: number): Session | null {
  const b = body as { access_token?: string; refresh_token?: string; expires_in?: number; user?: { id?: string } } | null;
  if (!b || !b.access_token || !b.refresh_token || !b.user?.id) return null;
  return { accessToken: b.access_token, refreshToken: b.refresh_token, expiresAt: now + (b.expires_in ?? 3600) * 1000, userId: b.user.id };
}

export class AuthClient {
  constructor(private cfg: OnlineConfig, private http: HttpClient, private clock: () => number = Date.now) {}

  private call(path: string, body: unknown) {
    return this.http.request("POST", `${this.cfg.url}/auth/v1/${path}`, { apikey: this.cfg.anonKey, "Content-Type": "application/json" }, body);
  }

  /** Returns a Session, or null when the project requires e-mail confirmation first. */
  async signUp(email: string, password: string): Promise<Session | null> {
    const { status, body } = await this.call("signup", { email, password });
    if (status >= 400) throw new AuthError(message(body, status));
    return toSession(body, this.clock());
  }

  async signIn(email: string, password: string): Promise<Session> {
    const { status, body } = await this.call("token?grant_type=password", { email, password });
    const s = status < 400 ? toSession(body, this.clock()) : null;
    if (!s) throw new AuthError(message(body, status));
    return s;
  }

  async refresh(session: Session): Promise<Session> {
    const { status, body } = await this.call("token?grant_type=refresh_token", { refresh_token: session.refreshToken });
    const s = status < 400 ? toSession(body, this.clock()) : null;
    if (!s) throw new AuthError(message(body, status));
    return s;
  }
}
