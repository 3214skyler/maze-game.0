/** Calls the database functions (`/rest/v1/rpc/...`) with automatic token refresh. */
import { AuthClient, isExpiring, Session, SessionStore } from "./auth";
import { OnlineConfig } from "./config";
import { AuthError, ServerError } from "./errors";
import { HttpClient } from "./http";

function errorFrom(status: number, body: unknown): ServerError {
  if (body && typeof body === "object") {
    const b = body as { code?: string; message?: string };
    const message = String(b.message ?? "");
    const code = String(b.code ?? "");
    if (code === "42501") return new ServerError("permission_denied", message);
    if (code === "PGRST202" || status === 404) return new ServerError("rpc_not_found", message);
    if (code === "P0001" && message) return new ServerError(message, message); // `raise exception 'xxx'` in our functions
    return new ServerError(code || "server_error", message);
  }
  return new ServerError("server_error", `HTTP ${status}`);
}

export class ApiClient {
  constructor(
    private cfg: OnlineConfig,
    private http: HttpClient,
    private auth: AuthClient,
    private store: SessionStore | null = null,
    public session: Session | null = store?.load() ?? null,
    private clock: () => number = Date.now,
  ) {}

  get signedIn(): boolean {
    return this.session !== null;
  }

  setSession(s: Session | null): void {
    this.session = s;
    if (this.store) {
      if (s) this.store.save(s);
      else this.store.clear();
    }
  }

  private async refreshSession(): Promise<void> {
    if (!this.session) throw new AuthError("not signed in");
    try {
      this.setSession(await this.auth.refresh(this.session));
    } catch (e) {
      if (e instanceof AuthError) this.setSession(null); // refresh token rejected: the player must sign in again
      throw e;
    }
  }

  private send(name: string, args: unknown) {
    // Anonymous calls send ONLY `apikey`: new-style keys (sb_publishable_...) are not JWTs and must never be a Bearer token.
    const headers: Record<string, string> = { apikey: this.cfg.anonKey, "Content-Type": "application/json" };
    if (this.session) headers.Authorization = `Bearer ${this.session.accessToken}`;
    return this.http.request("POST", `${this.cfg.url}/rest/v1/rpc/${name}`, headers, args);
  }

  /** `publicCall: true` allows anonymous use (e.g. reading the leaderboard). */
  async rpc<T = unknown>(name: string, args: Record<string, unknown> = {}, publicCall = false): Promise<T> {
    if (!this.session && !publicCall) throw new AuthError("not signed in");
    if (this.session && isExpiring(this.session, this.clock())) await this.refreshSession();
    let res = await this.send(name, args);
    if (res.status === 401 && this.session) {
      await this.refreshSession(); // token rejected: refresh once and retry
      res = await this.send(name, args);
    }
    if (res.status === 401) throw new AuthError("session rejected");
    if (res.status >= 400) throw errorFrom(res.status, res.body);
    return res.body as T;
  }
}
