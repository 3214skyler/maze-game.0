# Online setup (Supabase)

The game works fully offline as a guest. These steps switch on accounts, cloud save, the daily
challenge and its leaderboard. Nothing below needs code changes.

## 1. Create the project
1. Create a free project at <https://supabase.com>.
2. **SQL Editor → New query**, paste `backend/migrations/0001_online.sql`, run it.
   (Or with the CLI: `supabase db push`.) It creates the tables, Row Level Security and the functions.
3. **Authentication → Providers → Email**: decide whether *Confirm email* is on.
   On = fewer fake accounts (recommended once you have players); the game handles both.

## 2. Give the game its public keys
From **Project Settings → API** copy the *Project URL* and the **anon (public)** key into
`config/online.json` (copy `config/online.json.example`) — or set `MAZE_SUPABASE_URL` and
`MAZE_SUPABASE_ANON_KEY`. These two values are public by design; Row Level Security protects the data.

**Never** put the `service_role` key in the game, in `online.json`, or in Git.

## 3. Publish the daily challenges
The server only hands out a maze that you published (so nobody can pre-solve it):

```bash
export MAZE_SUPABASE_URL=https://YOUR-PROJECT.supabase.co
export MAZE_SUPABASE_SERVICE_KEY=...   # service_role key, only in this shell / a CI secret
python tools/publish_daily.py --days 5
```

To automate it, add both values as GitHub repository secrets
(`MAZE_SUPABASE_URL`, `MAZE_SUPABASE_SERVICE_KEY`); `.github/workflows/daily-challenge.yml` then
publishes the next 5 days every night at 00:05 UTC. Already published days are never overwritten.

## 4. Check that everything is right
Run this on your own computer (it needs access to your project):

```bash
python tools/check_online.py
python tools/check_online.py --email you@example.com --password '...'   # also tests sign-in + today's challenge
```
It reports `OK` / `WARN` / `FAIL` for: connection and key, sign-up settings, whether the migration was applied,
that anonymous visitors cannot read your tables, and (with an account) that today's challenge is published.

Tip: in Supabase *Authentication → URL Configuration* set **Site URL** to a real page (e.g. your portfolio),
otherwise the confirmation e-mail link ends on a "localhost" error page (the account is still confirmed).

## 5. Android
When the Buildozer build is added, the app needs the `INTERNET` permission
(`android.permissions = INTERNET` in `buildozer.spec`).

## How cheating is handled
* The **server** measures the time (from `start_daily_run` to `submit_daily_run`); the phone's clock is ignored.
* The server **replays the submitted path** against the stored walls (walls, adjacency, self-crossing, exit).
* Times faster than 80 ms per cell (min 1.5 s) are rejected; a run expires after 1 hour; 30 attempts/day.
* Players cannot read or write the leaderboard tables directly; the maze is only revealed when the clock starts.
* Cloud save refuses a lower XP than the one stored, and a stale device can never overwrite a newer save.

## Known limits (be aware before launching)
* A bot can still wait the minimum time and submit a perfect path. Stronger defences (device attestation,
  e-mail confirmation, reporting, moderation) are a later step.
* Coins, XP and lives are still **calculated on the phone** and only *stored* in the cloud. They do not
  affect the leaderboard (that is judged by the server), but they must move server-side before you sell
  anything for coins.
* If a guest signs in on a new account that has *less* XP than the cloud copy of an existing account, the
  account with more XP wins on that device.
