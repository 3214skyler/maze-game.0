import { ApiClient } from "./api";
import { AuthClient, SessionStore, StorageLike } from "./auth";
import { OnlineConfig } from "./config";
import { ServerError } from "./errors";
import { HttpClient } from "./http";

export type AccountStatus = "signed_in" | "confirm_email" | "needs_username";

export const USERNAME_ERRORS: Record<string, string> = {
  invalid_username: "Username must be 3-20 letters, digits or underscore.",
  username_taken: "That username is already taken.",
  profile_exists: "This account already has a username.",
};

export const USERNAME_RE = /^[A-Za-z0-9_]{3,20}$/;

export class Account {
  readonly auth: AuthClient;
  readonly api: ApiClient;
  username: string | null = null;

  constructor(cfg: OnlineConfig, storage: StorageLike, http: HttpClient = new HttpClient(), clock: () => number = Date.now) {
    this.auth = new AuthClient(cfg, http, clock);
    this.api = new ApiClient(cfg, http, this.auth, new SessionStore(storage), undefined, clock);
  }

  get signedIn(): boolean {
    return this.api.signedIn;
  }

  async signUp(email: string, password: string, username: string): Promise<AccountStatus> {
    const session = await this.auth.signUp(email, password);
    if (!session) return "confirm_email";
    this.api.setSession(session);
    await this.setUsername(username);
    return "signed_in";
  }

  async signIn(email: string, password: string): Promise<AccountStatus> {
    this.api.setSession(await this.auth.signIn(email, password));
    return this.refreshProfile();
  }

  async refreshProfile(): Promise<AccountStatus> {
    const profile = await this.api.rpc<{ username?: string } | null>("get_my_profile");
    this.username = profile?.username ?? null;
    return this.username ? "signed_in" : "needs_username";
  }

  async setUsername(username: string): Promise<void> {
    try {
      await this.api.rpc("create_profile", { p_username: username });
    } catch (e) {
      if (e instanceof ServerError) throw new ServerError(e.code, USERNAME_ERRORS[e.code] ?? e.message);
      throw e;
    }
    this.username = username;
  }

  signOut(): void {
    this.api.setSession(null);
    this.username = null;
  }
}
