"""Kivy screens for accounts and the daily challenge, wired to the fake Supabase (real PostgreSQL)."""
import os
from datetime import datetime, timezone

import pytest

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
pytest.importorskip("kivy")
pytest.importorskip("psycopg2")

from fake_supabase import ANON_KEY, URL, FakeSupabase, seconds_needed, today_maze  # noqa: E402
from game.maze.solver import solve  # noqa: E402
from game.online.account import Account  # noqa: E402
from game.online.cloud import CloudRepository  # noqa: E402
from game.online.config import OnlineConfig  # noqa: E402
from game.persistence.json_store import JsonProfileRepository  # noqa: E402
from game.progression.daily import build_daily_maze  # noqa: E402
from game.progression.service import ProgressService  # noqa: E402


class Clock:
    t = 7_000_000.0

    def __call__(self):
        return self.t


def texts(screen):
    out = []

    def walk(w):
        if getattr(w, "text", ""):
            out.append(w.text)
        for c in w.children:
            walk(c)
    walk(screen)
    return " | ".join(out)


@pytest.fixture
def env(dsn, tmp_path, monkeypatch):
    from kivy.uix.screenmanager import ScreenManager
    from interface.components import async_task
    from interface.screens.account import AccountScreen
    from interface.screens.daily import DailyPlayScreen, DailyScreen
    from interface.screens.menu import MenuScreen
    monkeypatch.setattr(async_task, "RUN_SYNC", True)
    server = FakeSupabase(dsn)
    repo = CloudRepository(JsonProfileRepository(tmp_path / "progress.json"), synchronous=True)
    svc = ProgressService(repo, clock=Clock())
    acc = Account(OnlineConfig(URL, ANON_KEY), tmp_path, transport=server)
    sm = ScreenManager()
    screens = {"menu": MenuScreen(service=svc, account=acc), "account": AccountScreen(acc, repo, svc),
               "daily": DailyScreen(acc), "daily_play": DailyPlayScreen(acc)}
    for s in screens.values():
        sm.add_widget(s)
    return sm, server, acc, repo, svc, screens


def fill(screen, email="ui@t.dev", pw="secret12", name="ui_player"):
    screen.email.text, screen.password.text, screen.username.text = email, pw, name


def test_sign_up_then_menu_shows_the_username(env):
    sm, server, acc, repo, svc, s = env
    s["menu"].on_enter()
    assert "guest" in s["menu"].summary.text
    fill(s["account"])
    s["account"].do_sign_up()
    assert acc.signed_in and acc.username == "ui_player"
    assert "Signed in as ui_player" in s["account"].state.text and repo.status in ("synced", "offline")
    s["menu"].on_enter()
    assert "ui_player" in s["menu"].summary.text
    assert s["account"].out_btn.disabled is False and s["account"].in_btn.disabled is True


def test_input_validation_messages_do_not_hit_the_network(env):
    sm, server, acc, repo, svc, s = env
    a = s["account"]
    calls = len(server.calls)
    fill(a, email="nope"); a.do_sign_up(); assert "valid e-mail" in a.message.text
    fill(a, pw="123"); a.do_sign_in(); assert "6 characters" in a.message.text
    fill(a, name="x"); a.do_sign_up(); assert "Username" in a.message.text
    assert len(server.calls) == calls


def test_errors_are_shown_in_plain_language(env):
    sm, server, acc, repo, svc, s = env
    a = s["account"]
    fill(a); a.do_sign_up(); a.do_sign_out()
    fill(a, email="other@t.dev", name="UI_player"); a.do_sign_up()
    assert "already taken" in a.message.text and acc.signed_in is True      # logged in, username must change
    a.username.text = "ui_player_2"; a.do_set_username()
    assert acc.username == "ui_player_2"
    a.do_sign_out()
    fill(a, pw="wrong-pass"); a.do_sign_in()
    assert "Invalid login credentials" in a.message.text
    server.offline = True
    fill(a); a.do_sign_in()
    assert "No connection" in a.message.text


def test_sign_out_keeps_local_progress_and_detaches_cloud(env):
    sm, server, acc, repo, svc, s = env
    fill(s["account"]); s["account"].do_sign_up()
    svc.profile.xp = 77
    svc.save()
    s["account"].do_sign_out()
    assert not acc.signed_in and repo.status == "local" and svc.xp == 77
    assert "guest" in s["account"].state.text


def test_unconfigured_build_degrades_gracefully(env):
    from interface.screens.account import AccountScreen
    from interface.screens.daily import DailyScreen
    sm, server, acc, repo, svc, s = env
    a, d = AccountScreen(None, repo, svc), DailyScreen(None)
    assert "not configured" in a.state.text and a.in_btn.disabled
    d.on_enter()
    assert "not configured" in d.message.text and d.play_btn.disabled


def test_daily_requires_sign_in(env):
    sm, server, acc, repo, svc, s = env
    server.publish_today(today_maze())
    s["daily"].on_enter()
    assert s["daily"].play_btn.disabled and "Sign in" in s["daily"].message.text


def test_daily_play_submit_and_leaderboard(env):
    sm, server, acc, repo, svc, s = env
    maze = today_maze()
    server.publish_today(maze)
    fill(s["account"]); s["account"].do_sign_up()
    d, p = s["daily"], s["daily_play"]
    d.on_enter()
    assert not d.play_btn.disabled and "No times yet" in texts(d.grid)
    d.play()
    assert p.run is not None and p.run.maze.walls == maze.walls
    server.age_run(p.run.run_id, seconds_needed(maze, 12))
    for cell in solve(p.run.maze)[1:]:
        p.paths.extend(cell)
    p.view.refresh()
    p.view.on_completed("blue")                    # what MazeView fires when the path reaches the exit
    assert "RANK #1" in p.status.text and p.view.disabled
    d.load_board()
    shown = texts(d.grid)
    assert "ui_player" in shown and "#1" in shown


def test_daily_rejection_is_explained(env):
    sm, server, acc, repo, svc, s = env
    server.publish_today(today_maze())
    fill(s["account"]); s["account"].do_sign_up()
    s["daily"].on_enter(); s["daily"].play()
    p = s["daily_play"]
    for cell in solve(p.run.maze)[1:]:
        p.paths.extend(cell)
    p.finish()                                     # instantly: the server must refuse it
    assert "rejected" in p.status.text and "quickly" in p.status.text


def test_daily_without_a_published_maze_shows_a_friendly_message(env):
    sm, server, acc, repo, svc, s = env
    fill(s["account"]); s["account"].do_sign_up()
    s["daily"].on_enter(); s["daily"].play()
    assert "not published yet" in s["daily"].message.text


def test_player_can_restart_and_reset_without_the_server(env):
    sm, server, acc, repo, svc, s = env
    server.publish_today(today_maze())
    fill(s["account"]); s["account"].do_sign_up()
    s["daily"].on_enter(); s["daily"].play()
    p = s["daily_play"]
    p.paths.extend(solve(p.run.maze)[1])
    assert len(p.paths.path("blue").cells) == 2
    p.reset()
    assert len(p.paths.path("blue").cells) == 1
