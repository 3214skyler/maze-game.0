"""Shared fixtures. A local PostgreSQL (if reachable) is prepared once per test session."""
import os
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent / "backend"
ADMIN_DSN = os.environ.get("MAZE_TEST_PG_DSN", "dbname=postgres user=postgres password=pg host=localhost")
DB = "maze_test"


@pytest.fixture(scope="session")
def dsn():
    psycopg2 = pytest.importorskip("psycopg2")
    try:
        admin = psycopg2.connect(ADMIN_DSN, connect_timeout=2)
    except psycopg2.OperationalError:
        pytest.skip("no PostgreSQL available for backend tests")
    admin.autocommit = True
    cur = admin.cursor()
    cur.execute(f"drop database if exists {DB}")
    cur.execute(f"create database {DB}")
    admin.close()
    test_dsn = ADMIN_DSN.replace("dbname=postgres", f"dbname={DB}")
    conn = psycopg2.connect(test_dsn)
    conn.autocommit = True
    c = conn.cursor()
    c.execute((BACKEND / "tests" / "supabase_stub.sql").read_text())
    c.execute((BACKEND / "migrations" / "0001_online.sql").read_text())
    conn.close()
    return test_dsn


