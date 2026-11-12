# Web version (`web/`)

TypeScript + Vite + Canvas, no framework. It talks to the **same Supabase project** as the Android game, so
accounts, the daily challenge and the leaderboard are shared between web and Android.

## Run it locally
```bash
cd web
cp .env.example .env.local      # fill in VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY (public values)
npm install
npm run dev                     # http://localhost:5173
```
Without those two variables the game still runs as an offline guest build (Account/Daily say "not configured").

## Deploy on Vercel
1. **Add New → Project** → import the repository.
2. **Root Directory: `web`** (Framework Preset: Vite — `web/vercel.json` already sets build command and output).
3. **Environment Variables** (Production *and* Preview), set **before** the first deploy because Vite inlines them at build time:
   * `VITE_SUPABASE_URL` — your project URL
   * `VITE_SUPABASE_ANON_KEY` — the **public** key (`sb_publishable_…`/anon). **Never** the secret key.
4. Deploy. Then in Supabase: *Authentication → URL Configuration* → set **Site URL** to your Vercel URL (and add it to
   *Redirect URLs*), so the e-mail confirmation link lands on the game instead of an error page.

`web/vercel.json` also sends security headers (Content-Security-Policy, nosniff, referrer policy). The CSP allows
connections only to `'self'` and `https://*.supabase.co`: if you later use a **custom Supabase domain**, add it to `connect-src`.

## Tests
```bash
cd web
npm test            # 95 tests: rules, generators, solver, drawing, rendering (pixel checks), network client,
                    # and HTTP end-to-end tests against the REAL SQL migration (needs python3 + PostgreSQL; skipped otherwise)
npm run typecheck && npm run build
```
Optional real-browser test (headless Chromium: mouse, touch, keyboard, CORS, production CSP, account, daily challenge,
anti-cheat): `cd web/e2e-browser && npm install && npm run e2e` (also needs python3 + PostgreSQL).

## What is different from the Android game (v0.1)
| | Web v0.1 | Android |
|---|---|---|
| Three paths, mouse/touch/keyboard | yes | yes |
| Classic levels + unlocking, best times | yes (saved in the browser) | yes |
| Accounts, daily challenge, global leaderboard | yes (shared) | yes (shared) |
| XP, coins, lives, difficulties, stats | **not yet** | yes |
| Cloud save of classic progress | **not yet** (browser only) | yes |
| Audio | not yet | not yet |

* Classic levels use the web's own seeded generator, so **level N is a different maze on web and on Android**.
  The daily challenge is identical everywhere because the server stores the maze.
* Anti-cheat is unchanged and entirely server-side (server clock, path replay, speed limit, attempt limit).
