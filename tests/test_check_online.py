import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import check_online  # noqa: E402
from game.online.config import OnlineConfig  # noqa: E402
from game.online.errors import NetworkError  # noqa: E402

CFG = OnlineConfig("https://x.supabase.co", "sb_publishable_test")


class Scripted:
    """Transport answering from a table of (method, path-prefix) -> (status, body)."""
    def __init__(self, routes):
        self.routes = routes

    def request(self, method, url, headers, body=None):
        for (m, prefix), resp in self.routes.items():
            if m == method and url.startswith(CFG.url + prefix):
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return 404, {"message": "nothing"}


def by_name(results):
    return {c.name: c for c in results}


def test_unreachable_project():
    r = check_online.run_checks(CFG, Scripted({("GET", "/auth/v1/settings"): NetworkError("dns")}))
    assert len(r) == 1 and r[0].status == "FAIL" and "cannot reach" in r[0].detail


def test_wrong_key_is_reported():
    r = check_online.run_checks(CFG, Scripted({("GET", "/auth/v1/settings"): (401, {"message": "Invalid API key"})}))
    assert r[0].status == "FAIL" and "wrong" in r[0].detail


def test_missing_migration_is_reported_with_the_fix():
    routes = {("GET", "/auth/v1/settings"): (200, {"mailer_autoconfirm": True}),
              ("POST", "/rest/v1/rpc/get_daily_leaderboard"): (404, {"code": "PGRST202", "message": "not found"}),
              ("GET", "/rest/v1/"): (404, {})}
    r = by_name(check_online.run_checks(CFG, Scripted(routes)))
    assert r["Database migration"].status == "FAIL" and "SQL Editor" in r["Database migration"].detail
    assert r["Security: profiles"].status == "FAIL"


def test_exposed_table_is_flagged_as_a_security_failure():
    routes = {("GET", "/auth/v1/settings"): (200, {"mailer_autoconfirm": False}),
              ("POST", "/rest/v1/rpc/get_daily_leaderboard"): (200, []),
              ("GET", "/rest/v1/daily_challenges"): (200, [{"day": "2026-01-01"}]),
              ("GET", "/rest/v1/"): (401, {"code": "42501"})}
    r = by_name(check_online.run_checks(CFG, Scripted(routes)))
    assert r["Security: daily_challenges"].status == "FAIL" and "CAN READ" in r["Security: daily_challenges"].detail
    assert r["Security: profiles"].status == "OK"
    assert r["E-mail confirmation"].status == "WARN"


def test_against_the_real_database_everything_passes(dsn):
    pytest.importorskip("psycopg2")
    from fake_supabase import ANON_KEY, URL, FakeSupabase
    from game.progression.daily import build_daily_maze
    server = FakeSupabase(dsn)
    cfg = OnlineConfig(URL, ANON_KEY)
    results = check_online.run_checks(cfg, server)
    assert [c.status for c in results if c.status == "FAIL"] == []
    assert by_name(results)["Database migration"].status == "OK"
    assert all(by_name(results)[f"Security: {t}"].status == "OK" for t in
               ("daily_challenges", "leaderboard_entries", "player_progress", "challenge_runs", "profiles"))
    # full check with a real sign-in: first the challenge is missing, then published
    from game.online.account import Account
    import tempfile
    acc = Account(cfg, Path(tempfile.mkdtemp()), transport=server)
    acc.sign_up("chk@t.dev", "secret12", "checker_1")
    missing = by_name(check_online.run_checks(cfg, server, "chk@t.dev", "secret12"))
    assert missing["Today's challenge"].status == "FAIL" and "publish_daily" in missing["Today's challenge"].detail
    server.publish_today(build_daily_maze(datetime.now(timezone.utc).date()))
    done = by_name(check_online.run_checks(cfg, server, "chk@t.dev", "secret12"))
    assert done["Today's challenge"].status == "OK" and done["Sign in"].status == "OK"
    wrong = by_name(check_online.run_checks(cfg, server, "chk@t.dev", "bad-password"))
    assert wrong["Sign in"].status == "FAIL"
