import json
from datetime import date, datetime, timedelta, timezone

import pytest

from game.maze.generators import generate
from game.maze.maze import Maze
from game.maze.solver import is_solvable, solve
from game.progression.daily import build_daily_maze, daily_row, daily_seed

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import publish_daily  # noqa: E402


def test_maze_dict_roundtrip_preserves_everything():
    m = generate(9, 7, seed=5, algorithm="kruskal")
    r = Maze.from_dict(json.loads(json.dumps(m.to_dict())))
    assert r.walls == m.walls and r.start == m.start and r.exit == m.exit and solve(r) == solve(m)


@pytest.mark.parametrize("bad", [
    {}, {"width": 3, "height": 3}, {"width": 4, "height": 4, "walls": [[0]], "start": [0, 0], "exit": [1, 1]},
    {"width": 4, "height": 4, "walls": [[99] * 4] * 4, "start": [0, 0], "exit": [3, 3]},
    {"width": 4, "height": 4, "walls": [[15] * 4] * 4, "start": [9, 9], "exit": [3, 3]},
    {"width": "x", "height": 4, "walls": [], "start": [0, 0], "exit": [3, 3]},
])
def test_malformed_maze_data_is_rejected(bad):
    with pytest.raises(ValueError):
        Maze.from_dict(bad)


def test_daily_maze_is_the_same_for_everyone_and_solvable():
    day = date(2026, 11, 4)
    assert daily_seed(day) == 20261104
    a, b = build_daily_maze(day), build_daily_maze(day)
    assert a.walls == b.walls
    seen = set()
    for i in range(60):
        m = build_daily_maze(day + timedelta(days=i))
        assert is_solvable(m) and m.width >= 10
        seen.add(repr(m.walls))
    assert len(seen) == 60


def test_published_rows_are_well_formed():
    row = daily_row(date(2026, 11, 4))
    assert row["day"] == "2026-11-04" and len(row["walls"]) == row["height"]
    json.dumps(row)


def test_publisher_sends_ignore_duplicates_and_uses_service_key():
    sent = {}

    class T:
        def request(self, method, url, headers, body=None):
            sent.update(method=method, url=url, headers=headers, body=body)
            return 201, None

    days = publish_daily.publish("https://x.supabase.co/", "SERVICE", 3, T(), start=date(2026, 1, 1))
    assert days == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert sent["method"] == "POST" and sent["url"].endswith("/rest/v1/daily_challenges?on_conflict=day")
    assert "ignore-duplicates" in sent["headers"]["Prefer"] and len(sent["body"]) == 3

    class Bad:
        def request(self, *a, **k):
            return 401, {"message": "bad key"}

    with pytest.raises(RuntimeError):
        publish_daily.publish("https://x.supabase.co", "nope", 1, Bad())


def test_published_row_is_accepted_by_the_real_database(dsn):
    psycopg2 = pytest.importorskip("psycopg2")
    from fake_supabase import ANON_KEY, URL, FakeSupabase
    from game.online.account import Account
    from game.online.daily_client import DailyClient
    import tempfile
    server = FakeSupabase(dsn)
    today = datetime.now(timezone.utc).date()
    row = daily_row(today)
    server.admin.cursor().execute(
        "insert into public.daily_challenges (day, seed, algorithm, width, height, start_cell, exit_cell, walls) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s)",
        (row["day"], row["seed"], row["algorithm"], row["width"], row["height"], json.dumps(row["start_cell"]),
         json.dumps(row["exit_cell"]), json.dumps(row["walls"])))
    from game.online.config import OnlineConfig
    acc = Account(OnlineConfig(URL, ANON_KEY), Path(tempfile.mkdtemp()), transport=server)
    acc.sign_up("p@t.dev", "secret12", "publisher_t")
    run = DailyClient(acc.api).start()
    assert run.maze.walls == build_daily_maze(today).walls
