"""A fake Supabase project for tests: Auth + PostgREST RPC in front of a REAL PostgreSQL.
The SQL, the roles and Row Level Security are the real thing; only the HTTP envelope is simulated."""
import itertools
import uuid

import psycopg2
import psycopg2.extras

from game.online.errors import NetworkError

ANON_KEY = "anon-test-key"
URL = "https://example.supabase.co"
ARG_TYPES = {"p_data": "jsonb", "p_expected_version": "int", "p_username": "text", "p_run_id": "uuid",
             "p_path": "jsonb", "p_day": "date", "p_limit": "int",
             "p_walls": "jsonb", "p_w": "int", "p_h": "int", "p_start": "jsonb", "p_exit": "jsonb"}


class FakeSupabase:
    def __init__(self, dsn, confirm_email=False):
        self.dsn = dsn
        self.confirm_email = confirm_email
        self.users = {}              # email -> {"id", "password", "confirmed"}
        self.access = {}             # access token -> user id
        self.refresh = {}            # refresh token -> user id
        self.offline = False
        self.calls = []              # (path, status) log
        self.expires_in = 3600
        self._ids = itertools.count(1)
        self.admin = psycopg2.connect(dsn)
        self.admin.autocommit = True
        cur = self.admin.cursor()
        cur.execute("truncate public.leaderboard_entries, public.challenge_runs, public.player_progress, "
                    "public.profiles, public.daily_challenges cascade")
        cur.execute("delete from auth.users")

    # ---- helpers used by tests ------------------------------------------------------
    def revoke_access_tokens(self):
        self.access.clear()

    def revoke_refresh_tokens(self):
        self.refresh.clear()

    def confirm(self, email):
        self.users[email]["confirmed"] = True

    def age_run(self, run_id, seconds):
        self.admin.cursor().execute(
            "update public.challenge_runs set started_at = now() - make_interval(secs => %s) where id = %s",
            (seconds, run_id))

    def publish_today(self, maze):
        import json
        self.admin.cursor().execute(
            "insert into public.daily_challenges (day, seed, algorithm, width, height, start_cell, exit_cell, walls) "
            "values ((now() at time zone 'utc')::date, %s, %s, %s, %s, %s, %s, %s)",
            (maze.seed, maze.algorithm, maze.width, maze.height, json.dumps(list(maze.start)),
             json.dumps(list(maze.exit)), json.dumps(maze.walls)))

    # ---- Transport ------------------------------------------------------------------------
    def request(self, method, url, headers, body=None):
        if self.offline:
            raise NetworkError("simulated: no connection")
        assert url.startswith(URL)
        assert headers.get("apikey") == ANON_KEY
        path = url[len(URL):]
        status, out = self._route(method, path, headers, body)
        self.calls.append((path, status))
        return status, out

    def _tokens(self, uid):
        n = next(self._ids)
        access, refresh = f"access-{n}-{uuid.uuid4().hex[:6]}", f"refresh-{n}-{uuid.uuid4().hex[:6]}"
        self.access[access], self.refresh[refresh] = uid, uid
        return {"access_token": access, "refresh_token": refresh, "expires_in": self.expires_in,
                "user": {"id": uid}}

    def _route(self, method, path, headers, body):
        if method == "GET" and path == "/auth/v1/settings":
            return 200, {"disable_signup": False, "mailer_autoconfirm": not self.confirm_email}
        if method == "GET" and path.startswith("/rest/v1/") and not path.startswith("/rest/v1/rpc/"):
            return self._table_read(path[len("/rest/v1/"):].split("?")[0], headers)
        if path == "/auth/v1/signup":
            email = body["email"]
            if email in self.users:
                return 422, {"msg": "User already registered"}
            if len(body["password"]) < 6:
                return 422, {"msg": "Password should be at least 6 characters"}
            uid = str(uuid.uuid4())
            self.users[email] = {"id": uid, "password": body["password"], "confirmed": not self.confirm_email}
            self.admin.cursor().execute("insert into auth.users (id, email) values (%s, %s)", (uid, email))
            return 200, (self._tokens(uid) if not self.confirm_email else {"id": uid, "email": email})
        if path == "/auth/v1/token?grant_type=password":
            u = self.users.get(body["email"])
            if not u or u["password"] != body["password"]:
                return 400, {"error_description": "Invalid login credentials"}
            if not u["confirmed"]:
                return 400, {"error_description": "Email not confirmed"}
            return 200, self._tokens(u["id"])
        if path == "/auth/v1/token?grant_type=refresh_token":
            uid = self.refresh.pop(body["refresh_token"], None)
            if uid is None:
                return 400, {"error_description": "Invalid Refresh Token"}
            return 200, self._tokens(uid)
        if path.startswith("/rest/v1/rpc/"):
            return self._rpc(path.rsplit("/", 1)[1], headers, body or {})
        return 404, {"message": "not found"}

    def _table_read(self, table, headers):
        token = headers.get("Authorization", "").removeprefix("Bearer ")
        role, uid = ("authenticated", self.access[token]) if token in self.access else ("anon", "")
        conn = psycopg2.connect(self.dsn)
        try:
            cur = conn.cursor()
            cur.execute(f"set local role {role}")
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (uid,))
            try:
                cur.execute(f"select * from public.{table} limit 1")
            except psycopg2.Error as exc:
                return 401 if role == "anon" else 403, {"code": exc.pgcode, "message": exc.diag.message_primary}
            return 200, [list(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def _rpc(self, name, headers, args):
        token = headers.get("Authorization", "").removeprefix("Bearer ")
        assert token != ANON_KEY, "the public key must never be sent as a Bearer token"
        if not token:
            role, uid = "anon", ""
        elif token in self.access:
            role, uid = "authenticated", self.access[token]
        else:
            return 401, {"message": "JWT expired", "code": "PGRST301"}
        conn = psycopg2.connect(self.dsn)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(f"set local role {role}")
            cur.execute("select set_config('request.jwt.claim.sub', %s, true)", (uid,))
            params = {k: (psycopg2.extras.Json(v) if ARG_TYPES[k] == "jsonb" else v) for k, v in args.items()}
            named = ", ".join(f"{k} => %({k})s::{ARG_TYPES[k]}" for k in args)
            try:
                cur.execute(f"select public.{name}({named}) as r", params)
            except psycopg2.errors.UndefinedFunction as exc:
                return 404, {"code": "PGRST202", "message": str(exc)}
            except psycopg2.Error as exc:
                conn.rollback()
                status = 403 if exc.pgcode == "42501" else 400
                return status, {"code": exc.pgcode, "message": (exc.diag.message_primary or str(exc))}
            result = cur.fetchone()["r"]
            conn.commit()
            return 200, result
        finally:
            conn.close()
