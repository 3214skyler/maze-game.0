export interface OnlineConfig {
  url: string;
  anonKey: string;
}

/** Validates the (public) project settings. Returns null when the web build has none => offline-only. */
export function makeConfig(url: string | undefined, anonKey: string | undefined): OnlineConfig | null {
  if (!url || !anonKey) return null;
  const ok = url.startsWith("https://") || url.startsWith("http://localhost") || url.startsWith("http://127.0.0.1");
  if (!ok) throw new Error("Supabase URL must use https");
  return { url: url.replace(/\/+$/, ""), anonKey };
}

export function configFromEnv(): OnlineConfig | null {
  const env = import.meta.env as Record<string, string | undefined>;
  return makeConfig(env.VITE_SUPABASE_URL, env.VITE_SUPABASE_ANON_KEY);
}
