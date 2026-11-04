#!/usr/bin/env python3
"""Publish the next daily challenges to Supabase. ADMIN TOOL: needs the service-role key.

    MAZE_SUPABASE_URL=https://xxxx.supabase.co MAZE_SUPABASE_SERVICE_KEY=... python tools/publish_daily.py --days 3

The service-role key must live ONLY in this script's environment (e.g. a GitHub Actions secret) and
never in the game, the repository or an .env that gets committed. Days that already exist are left
untouched (players may already have run them).
"""
import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.online.http import UrllibTransport  # noqa: E402
from game.progression.daily import daily_row, today_utc  # noqa: E402


def publish(url, service_key, days, transport=None, start=None):
    transport = transport or UrllibTransport(timeout=30)
    start = start or today_utc()
    headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}",
               "Content-Type": "application/json", "Prefer": "resolution=ignore-duplicates,return=minimal"}
    rows = [daily_row(start + timedelta(days=i)) for i in range(days)]
    status, body = transport.request("POST", f"{url.rstrip('/')}/rest/v1/daily_challenges?on_conflict=day",
                                     headers, rows)
    if status >= 300:
        raise RuntimeError(f"publish failed (HTTP {status}): {body}")
    return [r["day"] for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3, help="how many days to publish, starting today (UTC)")
    args = ap.parse_args()
    url, key = os.environ.get("MAZE_SUPABASE_URL"), os.environ.get("MAZE_SUPABASE_SERVICE_KEY")
    if not url or not key:
        sys.exit("Set MAZE_SUPABASE_URL and MAZE_SUPABASE_SERVICE_KEY in the environment.")
    print("published:", ", ".join(publish(url, key, args.days)))


if __name__ == "__main__":
    main()
