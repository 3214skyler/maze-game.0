"""Runs the real migration on a local PostgreSQL and attacks it the way a hostile client would.
Skipped automatically when no PostgreSQL is reachable (set MAZE_TEST_PG_DSN to point at one)."""
import json
import os
import uuid
from pathlib import Path

import pytest

psycopg2 = pytest.importorskip("psycopg2")
import psycopg2.extras  # noqa: E402

from game.maze.maze import Maze  # noqa: E402
from game.maze.solver import solve  # noqa: E402
from game.progression.daily import build_daily_maze  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent / "backend"
ADMIN_DSN = os.environ.get("MAZE_TEST_PG_DSN", "dbname=postgres user=postgres password=pg host=localhost")
DB = "maze_test"


class Db:
    def __init__(self, conn):
        self.conn, self.cur = conn, conn.cursor()
        self._n = 0

    def admin(self):
        self.cur.execute("reset role")
        self.cur.execute("select set_config('request.jwt.claim.sub', '', true)")

    def as_user(self, uid):
        self.admin()
        self.cur.execute("set local role authenticated")
        self.cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (str(uid),))

    def as_anon(self):
        self.admin()
        self.cur.execute("set local role anon")

    def new_user(self, name=None):
        self.admin()
        uid = uuid.uuid4()
        self.cur.execute("insert into auth.users (id, email) values (%s, %s)", (str(uid), f"{uid}@t.dev"))
        if name:
            self.as_user(uid)
            self.cur.execute("select public.create_profile(%s)", (name,))
            self.admin()
        return uid

    def q(self, sql, args=None):
        self.cur.execute(sql, args)
        return self.cur.fetchall()

    def one(self, sql, args=None):
        return self.q(sql, args)[0][0]

    def fails(self, sql, args=None, contains=""):
        self._n += 1
        self.cur.execute(f"savepoint s{self._n}")
        with pytest.raises(psycopg2.Error) as exc:
            self.cur.execute(sql, args)
        self.cur.execute(f"rollback to savepoint s{self._n}")
        assert contains in str(exc.value), f"expected {contains!r} in {exc.value}"

    def publish_today(self, maze=None):
        self.admin()
        maze = maze or build_daily_maze(datetime.now(timezone.utc).date())
        self.cur.execute(
            "insert into public.daily_challenges (day, seed, algorithm, width, height, start_cell, exit_cell, walls) "
            "values ((now() at time zone 'utc')::date, %s, %s, %s, %s, %s, %s, %s)",
            (maze.seed, maze.algorithm, maze.width, maze.height, json.dumps(list(maze.start)),
             json.dumps(list(maze.exit)), json.dumps(maze.walls)))
        return maze

    def start_run(self, uid):
        self.as_user(uid)
        return self.one("select public.start_daily_run()")

    def age_run(self, run_id, seconds):
        self.admin()
        self.cur.execute("update public.challenge_runs set started_at = now() - make_interval(secs => %s) where id = %s",
                         (seconds, run_id))

    def submit(self, uid, run_id, path):
        self.as_user(uid)
        return self.one("select public.submit_daily_run(%s, %s)", (run_id, json.dumps(path)))


@pytest.fixture
def db(dsn):
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
    d = Db(conn)
    yield d
    conn.rollback()
    conn.close()


def solution(maze):
    return [list(c) for c in solve(maze)]


# ------------------------------------------------------------------ profiles
def test_create_profile_rules(db):
    a, b = db.new_user(), db.new_user()
    db.as_user(a)
    db.cur.execute("select public.create_profile('Neo_01')")
    assert db.one("select public.get_my_profile()")["username"] == "Neo_01"
    db.fails("select public.create_profile('Other')", contains="profile_exists")
    db.as_user(b)
    db.fails("select public.create_profile('neo_01')", contains="username_taken")     # case-insensitive
    for bad in ("ab", "x" * 21, "has space", "emoji😀", "a-b-c", ""):
        db.fails("select public.create_profile(%s)", (bad,), contains="invalid_username")
    db.admin()
    db.fails("select public.create_profile('Valid_Name')", contains="not_authenticated")


def test_anonymous_cannot_call_player_functions(db):
    db.as_anon()
    for fn in ("select public.start_daily_run()", "select public.load_progress()",
               "select public.create_profile('hacker')"):
        db.fails(fn, contains="permission denied")


# ------------------------------------------------------------------ RLS / direct table access
def test_clients_cannot_write_tables_directly(db):
    u = db.new_user("player_one")
    db.publish_today()
    db.as_user(u)
    db.fails("insert into public.leaderboard_entries (user_id, day, elapsed_ms, path_length) "
             "values (%s, current_date, 1, 1)", (str(u),), contains="permission denied")
    db.fails("insert into public.player_progress (user_id, data, xp) values (%s, '{}', 999999)",
             (str(u),), contains="permission denied")
    db.fails("update public.profiles set username = 'renamed'", contains="permission denied")
    db.fails("insert into public.challenge_runs (user_id, day) values (%s, current_date)",
             (str(u),), contains="permission denied")
    db.fails("select * from public.daily_challenges", contains="permission denied")     # no pre-solving
    db.fails("select * from public.leaderboard_entries", contains="permission denied")


def test_players_only_see_their_own_rows(db):
    a, b = db.new_user("alice_a"), db.new_user("bob_b")
    db.as_user(a)
    db.cur.execute("select public.save_progress(%s, 0)", (json.dumps({"xp": 50}),))
    db.publish_today()
    db.start_run(a)
    db.as_user(b)
    assert db.q("select * from public.player_progress") == []
    assert db.q("select * from public.challenge_runs") == []
    assert [r[0] for r in db.q("select username from public.profiles")] == ["bob_b"]
    assert db.one("select public.load_progress()") is None
    db.as_user(a)
    assert db.one("select public.load_progress()")["xp"] == 50


# ------------------------------------------------------------------ cloud save
def test_save_progress_versions_and_conflicts(db):
    u = db.new_user()
    db.as_user(u)
    assert db.one("select public.save_progress(%s, 0)", (json.dumps({"xp": 10, "x": 1}),)) == 1
    assert db.one("select public.save_progress(%s, 1)", (json.dumps({"xp": 20}),)) == 2
    db.fails("select public.save_progress(%s, 1)", (json.dumps({"xp": 30}),), contains="version_conflict")
    db.fails("select public.save_progress(%s, 2)", (json.dumps({"xp": 5}),), contains="xp_regression")
    loaded = db.one("select public.load_progress()")
    assert loaded["version"] == 2 and loaded["xp"] == 20 and loaded["data"] == {"xp": 20}


def test_save_progress_validation(db):
    u = db.new_user()
    db.as_user(u)
    for bad in ('[]', '"text"', '{"xp": -5}', '{"xp": "abc"}', '{}', 'null'):
        db.fails("select public.save_progress(%s::jsonb, 0)", (bad,), contains="invalid_data")
    db.fails("select public.save_progress(%s, 0)", (json.dumps({"xp": 1, "blob": "z" * 250000}),),
             contains="data_too_large")
    assert db.q("select 1 from public.player_progress") == []


# ------------------------------------------------------------------ daily challenge
def test_start_requires_profile_and_a_published_challenge(db):
    u = db.new_user()
    db.as_user(u)
    db.fails("select public.start_daily_run()", contains="profile_required")
    u2 = db.new_user("has_profile")
    db.as_user(u2)
    db.fails("select public.start_daily_run()", contains="no_challenge_today")


def test_start_returns_the_maze_and_it_round_trips(db):
    u = db.new_user("runner_1")
    maze = db.publish_today()
    run = db.start_run(u)
    rebuilt = Maze.from_dict({"width": run["width"], "height": run["height"], "start": run["start"],
                              "exit": run["exit"], "walls": run["walls"]})
    assert rebuilt.walls == maze.walls and solve(rebuilt) == solve(maze)


def test_valid_solution_is_accepted_and_ranked(db):
    u = db.new_user("fast_one")
    maze = db.publish_today()
    run = db.start_run(u)
    db.age_run(run["run_id"], 12)
    res = db.submit(u, run["run_id"], solution(maze))
    assert res["accepted"] is True and res["rank"] == 1 and 11500 <= res["elapsed_ms"] <= 12500


def test_cheating_attempts_are_rejected(db):
    u = db.new_user("cheater_1")
    maze = db.publish_today()
    good = solution(maze)
    wall_jump = [good[0], good[-1]]
    cases = {
        "too_fast": good,                                              # valid path, submitted instantly
        "wall_crossed": None, "not_adjacent": wall_jump,
        "bad_start": good[1:], "exit_not_reached": good[:-1],
        "bad_path": {"not": "a list"}, "bad_length": [good[0]], "bad_cell": [good[0], "x"],
        "out_of_bounds": [good[0], [999, 999]],
    }
    # wall_crossed: take a real neighbour of the start that is separated by a wall
    start = tuple(good[0])
    for n in maze.neighbors(start):
        if not maze.can_move(start, n):
            cases["wall_crossed"] = [list(start), list(n)]
            break
    for reason, path in cases.items():
        assert path is not None, reason
        run = db.start_run(u)
        db.age_run(run["run_id"], 30 if reason != "too_fast" else 0)
        res = db.submit(u, run["run_id"], path)
        assert res["accepted"] is False and res["reason"] == reason, (reason, res)
    db.admin()
    assert db.q("select 1 from public.leaderboard_entries") == []      # nothing reached the board


def test_self_crossing_path_is_rejected(db):
    u = db.new_user("loopy_1")
    m = Maze(4, 4)
    for a, b in [((0, 0), (1, 0)), ((1, 0), (1, 1)), ((1, 1), (0, 1)), ((0, 1), (0, 0)), ((1, 0), (2, 0)),
                 ((2, 0), (3, 0)), ((3, 0), (3, 1)), ((3, 1), (3, 2)), ((3, 2), (3, 3)),
                 ((0, 1), (0, 2)), ((0, 2), (0, 3)), ((0, 3), (1, 3)), ((1, 3), (2, 3)), ((2, 3), (3, 3)),
                 ((1, 1), (1, 2)), ((1, 2), (2, 2)), ((2, 2), (2, 1))]:
        m.carve(a, b)
    m.open_entrance_and_exit((0, 0), (3, 3))
    m.seed, m.algorithm = 1, "test"
    db.publish_today(m)
    run = db.start_run(u)
    db.age_run(run["run_id"], 30)
    loop = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    assert db.submit(u, run["run_id"], loop)["reason"] == "self_crossing"


def test_run_expiry_and_double_submit_and_foreign_run(db):
    a, b = db.new_user("owner_a"), db.new_user("thief_b")
    maze = db.publish_today()
    r1 = db.start_run(a)
    db.age_run(r1["run_id"], 3601)
    assert db.submit(a, r1["run_id"], solution(maze))["reason"] == "run_expired"
    r2 = db.start_run(a)
    db.age_run(r2["run_id"], 20)
    db.as_user(b)
    db.fails("select public.submit_daily_run(%s, %s)", (r2["run_id"], json.dumps(solution(maze))),
             contains="run_not_found")                                   # cannot use someone else's run
    assert db.submit(a, r2["run_id"], solution(maze))["accepted"] is True
    db.as_user(a)
    db.fails("select public.submit_daily_run(%s, %s)", (r2["run_id"], json.dumps(solution(maze))),
             contains="already_submitted")


def test_board_keeps_only_the_best_time_and_ranks_players(db):
    a, b, c = db.new_user("player_aa"), db.new_user("player_bb"), db.new_user("player_cc")
    maze = db.publish_today()
    for uid, secs in ((a, 30), (b, 10), (c, 20)):
        run = db.start_run(uid)
        db.age_run(run["run_id"], secs)
        db.submit(uid, run["run_id"], solution(maze))
    run = db.start_run(a)                       # a tries again and is slower: must not replace the 30 s time
    db.age_run(run["run_id"], 45)
    assert db.submit(a, run["run_id"], solution(maze))["best_ms"] < 31000
    run = db.start_run(a)                       # a improves to 5 s -> becomes first
    db.age_run(run["run_id"], 5)
    res = db.submit(a, run["run_id"], solution(maze))
    assert "rank" in res, f"Submission result: {res}"
    assert res["rank"] == 1
    db.as_user(b)
    board = db.one("select public.get_daily_leaderboard()")
    assert [r["username"] for r in board] == ["player_aa", "player_bb", "player_cc"]
    assert [r["rank"] for r in board] == [1, 2, 3]
    assert [r["is_me"] for r in board] == [False, True, False]
    db.as_anon()
    assert len(db.one("select public.get_daily_leaderboard()")) == 3     # the board is public
    assert len(db.one("select public.get_daily_leaderboard(null, 1)")) == 1


def test_attempt_limit(db):
    u = db.new_user("spammer_1")
    db.publish_today()
    for _ in range(30):
        db.start_run(u)
    db.as_user(u)
    db.fails("select public.start_daily_run()", contains="too_many_attempts")
