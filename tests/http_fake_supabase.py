#!/usr/bin/env python3
"""HTTP front for the fake Supabase (real PostgreSQL behind it), so the TypeScript web client can be
tested over real HTTP against the real SQL. TEST TOOL ONLY.

    python tests/http_fake_supabase.py       # prints PORT=<n> and serves until killed

Control endpoints (POST): /__test__/reset /publish /age_run /confirm /offline
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import psycopg2  # noqa: E402

from fake_supabase import URL, FakeSupabase, today_maze  # noqa: E402
from game.online.errors import NetworkError  # noqa: E402

ADMIN_DSN = os.environ.get("MAZE_TEST_PG_DSN", "dbname=postgres user=postgres password=pg host=localhost")
DB = "maze_web_test"
STATE = {"server": None, "lock": threading.Lock(), "dsn": None}


def prepare_database() -> str:
    admin = psycopg2.connect(ADMIN_DSN, connect_timeout=3)
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f"drop database if exists {DB}")
    cur.execute(f"create database {DB}")
    admin.close()
    dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={DB}")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    c = conn.cursor()
    c.execute((ROOT / "backend" / "tests" / "supabase_stub.sql").read_text())
    c.execute((ROOT / "backend" / "migrations" / "0001_online.sql").read_text())
    conn.close()
    return dsn


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, status, body):
        data = json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        # browsers do NOT accept "*" for the Authorization header: list the headers explicitly (like Supabase does)
        for k, v in (("Access-Control-Allow-Origin", "*"),
                     ("Access-Control-Allow-Headers", "authorization, apikey, content-type, x-client-info"),
                     ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"), ("Content-Length", "0")):
            self.send_header(k, v)
        self.end_headers()

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        return json.loads(raw) if raw else None

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def _handle(self):
        body = self._body()
        path = self.path
        with STATE["lock"]:
            if path.startswith("/__test__/"):
                return self._control(path[len("/__test__/"):], body or {})
            headers = {k: v for k, v in (("apikey", self.headers.get("apikey")),
                                         ("Authorization", self.headers.get("Authorization"))) if v}
            try:
                status, out = STATE["server"].request(self.command, URL + path, headers, body)
            except NetworkError:
                self.connection.close()                     # simulate a dropped connection
                self.close_connection = True
                return
        self._send(status, out)

    def _control(self, name, args):
        srv = STATE["server"]
        if name == "reset":
            STATE["server"] = FakeSupabase(STATE["dsn"], confirm_email=bool(args.get("confirm_email")))
        elif name == "publish":
            srv.publish_today(today_maze())
        elif name == "age_run":
            srv.age_run(args["run_id"], float(args["seconds"]))
        elif name == "confirm":
            srv.confirm(args["email"])
        elif name == "offline":
            srv.offline = bool(args.get("offline"))
        else:
            return self._send(404, {"error": "unknown control"})
        self._send(200, {"ok": True})


def main():
    STATE["dsn"] = prepare_database()
    STATE["server"] = FakeSupabase(STATE["dsn"])
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(f"PORT={httpd.server_address[1]}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
