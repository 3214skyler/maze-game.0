import { NetworkError } from "./errors";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface HttpResult {
  status: number;
  body: unknown;
}

export class HttpClient {
  constructor(private fetchImpl: FetchLike = (i, init) => fetch(i, init), private timeoutMs = 10_000) {}

  async request(method: string, url: string, headers: Record<string, string>, body?: unknown): Promise<HttpResult> {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), this.timeoutMs);
    try {
      const res = await this.fetchImpl(url, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctl.signal,
      });
      const text = await res.text();
      let parsed: unknown = null;
      if (text) {
        try {
          parsed = JSON.parse(text);
        } catch {
          parsed = null;
        }
      }
      return { status: res.status, body: parsed };
    } catch (e) {
      throw new NetworkError(e instanceof Error ? e.message : String(e)); // offline, DNS, timeout, CORS
    } finally {
      clearTimeout(timer);
    }
  }
}
