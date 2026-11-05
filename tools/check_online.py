#!/usr/bin/env python3
"""Diagnose your Supabase setup from YOUR machine (the one with internet access to your project).

    python tools/check_online.py                      # public checks, uses config/online.json
    python tools/check_online.py --email you@x.com --password '...'   # also tests sign-in + today's challenge

It only uses the PUBLIC key, never the service-role key, and changes nothing except (with --email) it
starts one daily run, which counts as one of your 30 attempts and is harmless.
"""
import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.online.api import ApiClient  # noqa: E402
from game.online.auth import AuthClient  # noqa: E402
from game.online.config import OnlineConfig  # noqa: E402
from game.online.errors import AuthError, NetworkError, OnlineError, ServerError  # noqa: E402
from game.online.http import UrllibTransport  # noqa: E402

OK, WARN, FAIL = "OK", "WARN", "FAIL"


@dataclass
class Check:
    status: str
    name: str
    detail: str = ""


def run_checks(config, transport, email=None, password=None):
    out = []
    hdr = {"apikey": config.anon_key}
    # 1. can we reach the project, and how is Auth configured?
    try:
        status, body = transport.request("GET", f"{config.url}/auth/v1/settings", hdr)
    except NetworkError as exc:
        return [Check(FAIL, "Connection", f"cannot reach {config.url}: {exc}")]
    if status != 200 or not isinstance(body, dict):
        return [Check(FAIL, "Connection / public key", f"HTTP {status}: wrong URL or wrong key? {body}")]
    out.append(Check(OK, "Connection", "project reachable, public key accepted"))
    if body.get("disable_signup"):
        out.append(Check(WARN, "Sign-ups", "sign-ups are DISABLED in Supabase: nobody can create an account"))
    if body.get("mailer_autoconfirm"):
        out.append(Check(OK, "E-mail confirmation", "off: players can play right after signing up"))
    else:
        out.append(Check(WARN, "E-mail confirmation", "ON: players must click the e-mail link before signing in. "
                         "Supabase's built-in e-mail sender is heavily rate-limited; fine for tests, "
                         "configure your own SMTP before launch"))
    # 2. was the migration applied? (public function from the migration)
    api = ApiClient(config, transport, AuthClient(config, transport))
    try:
        api.rpc("get_daily_leaderboard", {"p_day": None, "p_limit": 1}, public=True)
        out.append(Check(OK, "Database migration", "get_daily_leaderboard exists: 0001_online.sql was applied"))
    except ServerError as exc:
        hint = "run backend/migrations/0001_online.sql in the Supabase SQL Editor" if exc.code == "rpc_not_found" else ""
        out.append(Check(FAIL, "Database migration", f"{exc.code} {hint}".strip()))
    except OnlineError as exc:
        out.append(Check(FAIL, "Database migration", str(exc)))
    # 3. security: anonymous visitors must NOT read the tables directly
    for table in ("daily_challenges", "leaderboard_entries", "player_progress", "challenge_runs", "profiles"):
        status, body = transport.request("GET", f"{config.url}/rest/v1/{table}?select=*&limit=1", hdr)
        if status in (401, 403):
            out.append(Check(OK, f"Security: {table}", "not readable by anonymous visitors"))
        elif status == 200 and body == []:
            out.append(Check(WARN, f"Security: {table}", "readable but empty: check that Row Level Security is ON"))
        elif status == 200:
            out.append(Check(FAIL, f"Security: {table}", "ANONYMOUS VISITORS CAN READ DATA. Re-run the migration "
                             "and make sure RLS is enabled"))
        elif status == 404:
            out.append(Check(FAIL, f"Security: {table}", "table not found: the migration was not applied"))
        else:
            out.append(Check(WARN, f"Security: {table}", f"unexpected HTTP {status}"))
    # 4. optional: a real sign-in and today's challenge
    if email and password:
        try:
            api.set_session(api.auth.sign_in(email, password))
            profile = api.rpc("get_my_profile")
            out.append(Check(OK, "Sign in", "signed in" + (f" as {profile['username']}" if profile else
                                                           " (no username yet: set one in the game)")))
            if profile:
                try:
                    run = api.rpc("start_daily_run")
                    out.append(Check(OK, "Today's challenge", f"published ({run['width']}x{run['height']})"))
                except ServerError as exc:
                    if exc.code == "no_challenge_today":
                        out.append(Check(FAIL, "Today's challenge", "NOT published: run tools/publish_daily.py"))
                    else:
                        out.append(Check(FAIL, "Today's challenge", exc.code))
        except AuthError as exc:
            out.append(Check(FAIL, "Sign in", str(exc)))
        except OnlineError as exc:
            out.append(Check(FAIL, "Sign in", str(exc)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email")
    ap.add_argument("--password")
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    config = OnlineConfig.load(root / "config")
    if config is None:
        sys.exit("No configuration found: create config/online.json (see config/online.json.example).")
    print(f"Project: {config.url}\n")
    results = run_checks(config, UrllibTransport(), args.email, args.password)
    for c in results:
        print(f"[{c.status:4}] {c.name}: {c.detail}")
    bad = sum(c.status == FAIL for c in results)
    print("\n" + ("All good." if not bad else f"{bad} problem(s) to fix."))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
