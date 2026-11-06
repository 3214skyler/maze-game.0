"""Python client <-> fake Supabase (real PostgreSQL behind it): accounts, cloud save, daily challenge."""
import time
from datetime import datetime, timezone

import pytest

pytest.importorskip("psycopg2")

from fake_supabase import ANON_KEY, URL, FakeSupabase, seconds_needed, today_maze, wall_crossing_path  # noqa: E402
from game.maze.solver import solve  # noqa: E402
from game.online.account import Account, AccountStatus  # noqa: E402
from game.online.cloud import CloudRepository  # noqa: E402
from game.online.config import OnlineConfig  # noqa: E402
from game.online.daily_client import DailyClient, friendly  # noqa: E402
from game.online.errors import AuthError, NetworkError, ServerError  # noqa: E402
from game.persistence.json_store import JsonProfileRepository  # noqa: E402
from game.persistence.repository import MemoryRepository  # noqa: E402
from game.progression.daily import build_daily_maze  # noqa: E402
from game.progression.difficulty import Difficulty  # noqa: E402
from game.progression.service import ProgressService  # noqa: E402

CONFIG = OnlineConfig(URL, ANON_KEY)


class Clock:
    t = 3_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def server(dsn):
    return FakeSupabase(dsn)


@pytest.fixture
def clock():
    return Clock()


def account(server, tmp_path, name="dev", clock=None):
    return Account(CONFIG, tmp_path / name, transport=server, clock=clock or Clock())


def signed_up(server, tmp_path, email="a@t.dev", username="player_a", name="dev", clock=None):
    acc = account(server, tmp_path, name, clock)
    assert acc.sign_up(email, "secret12", username) is AccountStatus.SIGNED_IN
    return acc


# ----------------------------------------------------------------------------- config
def test_config_rules(tmp_path):
    with pytest.raises(ValueError):
        OnlineConfig("http://evil.example.com", "k")
    with pytest.raises(ValueError):
        OnlineConfig("https://x.supabase.co", "")
    assert OnlineConfig("https://x.supabase.co/", "k").url == "https://x.supabase.co"
    assert OnlineConfig.from_env({}) is None
    assert OnlineConfig.from_env({"MAZE_SUPABASE_URL": "https://x.co", "MAZE_SUPABASE_ANON_KEY": "k"}).anon_key == "k"
    (tmp_path / "online.json").write_text('{"url": "https://y.co", "anon_key": "kk"}')
    assert OnlineConfig.from_file(tmp_path / "online.json").url == "https://y.co"
    assert OnlineConfig.from_file(tmp_path / "missing.json") is None
    (tmp_path / "bad.json").write_text("{nope")
    assert OnlineConfig.from_file(tmp_path / "bad.json") is None


# ----------------------------------------------------------------------------- accounts
def test_sign_up_creates_profile_and_persists_session(server, tmp_path):
    acc = signed_up(server, tmp_path)
    assert acc.signed_in and acc.username == "player_a"
    again = account(server, tmp_path)                       # "restart the game" on the same device
    assert again.signed_in and again.refresh_profile() is AccountStatus.SIGNED_IN
    assert again.username == "player_a"


def test_username_errors_are_friendly(server, tmp_path):
    signed_up(server, tmp_path)
    other = account(server, tmp_path, "dev2")
    with pytest.raises(ServerError) as exc:
        other.sign_up("b@t.dev", "secret12", "PLAYER_A")
    assert exc.value.code == "username_taken" and "already taken" in str(exc.value)
    assert other.signed_in                                   # the login itself worked; username must be changed
    with pytest.raises(ServerError) as exc:
        other.set_username("x")
    assert exc.value.code == "invalid_username"
    other.set_username("player_b")
    assert other.username == "player_b"


def test_sign_in_failures_and_email_confirmation(dsn, tmp_path):
    server = FakeSupabase(dsn, confirm_email=True)
    acc = account(server, tmp_path)
    assert acc.sign_up("c@t.dev", "secret12", "confirm_me") is AccountStatus.CONFIRM_EMAIL
    with pytest.raises(AuthError):
        acc.sign_in("c@t.dev", "secret12")                   # not confirmed yet
    server.confirm("c@t.dev")
    assert acc.sign_in("c@t.dev", "secret12") is AccountStatus.NEEDS_USERNAME
    acc.set_username("confirm_me")
    with pytest.raises(AuthError):
        acc.sign_in("c@t.dev", "wrong-password")
    with pytest.raises(AuthError):
        account(server, tmp_path, "x").sign_up("c@t.dev", "secret12", "dup_user")   # duplicate e-mail


def test_calls_require_sign_in_and_sign_out_clears_session(server, tmp_path):
    acc = account(server, tmp_path)
    with pytest.raises(AuthError):
        acc.api.rpc("get_my_profile")
    acc = signed_up(server, tmp_path, name="dev3")
    acc.sign_out()
    assert not acc.signed_in and not account(server, tmp_path, "dev3").signed_in
    with pytest.raises(AuthError):
        acc.api.rpc("get_my_profile")


def test_token_refresh_before_expiry_and_after_401(server, tmp_path, clock):
    acc = signed_up(server, tmp_path, clock=clock)
    first = acc.api.session.access_token
    clock.t += 3600 - 30                                     # inside the 60 s safety margin
    acc.refresh_profile()
    assert acc.api.session.access_token != first
    server.revoke_access_tokens()                            # server rejects the token: 401 -> refresh -> retry
    assert acc.refresh_profile() is AccountStatus.SIGNED_IN


def test_refresh_token_rejected_signs_the_player_out(server, tmp_path, clock):
    acc = signed_up(server, tmp_path, clock=clock)
    server.revoke_access_tokens(); server.revoke_refresh_tokens()
    with pytest.raises(AuthError):
        acc.refresh_profile()
    assert not acc.signed_in and not account(server, tmp_path).signed_in


def test_network_failure_is_a_clean_error(server, tmp_path):
    acc = signed_up(server, tmp_path)
    server.offline = True
    with pytest.raises(NetworkError):
        acc.refresh_profile()
    server.offline = False
    assert acc.refresh_profile() is AccountStatus.SIGNED_IN


def test_corrupt_session_file_means_signed_out_not_a_crash(server, tmp_path):
    (tmp_path / "dev").mkdir()
    (tmp_path / "dev" / "session.json").write_text("garbage")
    assert not account(server, tmp_path).signed_in


# ----------------------------------------------------------------------------- cloud save
def play_win(svc, clock):
    s = svc.start_level(Difficulty.NORMAL, svc.highest_unlocked(Difficulty.NORMAL))
    clock.t += 6
    s.update(1, svc.now())
    return svc.conclude(s)


def device(server, tmp_path, name, acc_name, clock, synchronous=True):
    """A phone: own local save file, shares the account via the same cloud."""
    repo = CloudRepository(JsonProfileRepository(tmp_path / name / "progress.json"), synchronous=synchronous)
    svc = ProgressService(repo, clock=clock)
    return repo, svc


def test_progress_follows_the_player_to_a_second_device(server, tmp_path, clock):
    acc_a = signed_up(server, tmp_path, name="phoneA")
    repo_a, svc_a = device(server, tmp_path, "phoneA", "a", clock)
    repo_a.attach(acc_a.api); svc_a.reload()
    play_win(svc_a, clock); play_win(svc_a, clock)
    assert repo_a.status == "synced" and svc_a.xp > 0

    acc_b = account(server, tmp_path, "phoneB")
    acc_b.sign_in("a@t.dev", "secret12")
    repo_b, svc_b = device(server, tmp_path, "phoneB", "b", clock)
    assert svc_b.xp == 0                                      # fresh install, guest
    repo_b.attach(acc_b.api); svc_b.reload()
    assert (svc_b.xp, svc_b.coins, svc_b.highest_unlocked(Difficulty.NORMAL)) == \
           (svc_a.xp, svc_a.coins, svc_a.highest_unlocked(Difficulty.NORMAL))


def test_guest_progress_is_uploaded_when_signing_in(server, tmp_path, clock):
    repo, svc = device(server, tmp_path, "guest", "g", clock)         # plays as guest first
    play_win(svc, clock)
    xp = svc.xp
    acc = signed_up(server, tmp_path, name="guest")
    repo.attach(acc.api); svc.reload()
    assert svc.xp == xp and repo.status == "synced"
    fresh_repo, fresh_svc = device(server, tmp_path, "other", "o", clock)
    other = account(server, tmp_path, "other"); other.sign_in("a@t.dev", "secret12")
    fresh_repo.attach(other.api); fresh_svc.reload()
    assert fresh_svc.xp == xp


def test_offline_play_never_blocks_and_syncs_later(server, tmp_path, clock):
    acc = signed_up(server, tmp_path)
    repo, svc = device(server, tmp_path, "p", "a", clock)
    repo.attach(acc.api); svc.reload()
    server.offline = True
    play_win(svc, clock)                                      # no exception, progress kept locally
    assert repo.status == "offline" and svc.xp > 0
    local_xp = svc.xp
    server.offline = False
    play_win(svc, clock)                                      # next save pushes the newest state
    assert repo.status == "synced"
    assert acc.api.rpc("load_progress")["xp"] == svc.xp > local_xp


def test_conflict_never_overwrites_a_more_advanced_cloud_copy(server, tmp_path, clock):
    acc1 = signed_up(server, tmp_path, name="d1")
    repo1, svc1 = device(server, tmp_path, "d1", "a", clock)
    repo1.attach(acc1.api); svc1.reload()
    acc2 = account(server, tmp_path, "d2"); acc2.sign_in("a@t.dev", "secret12")
    repo2, svc2 = device(server, tmp_path, "d2", "a", clock)
    repo2.attach(acc2.api); svc2.reload()
    play_win(svc1, clock); play_win(svc1, clock); play_win(svc1, clock)      # device 1 gets far ahead
    ahead = svc1.xp
    play_win(svc2, clock)                                                    # device 2 (stale) pushes a smaller state
    assert repo2.status == "cloud_newer" and repo2.cloud_newer["xp"] == ahead
    assert acc1.api.rpc("load_progress")["xp"] == ahead                      # cloud kept the better copy
    play_win(svc2, clock)                                                    # keeps playing: still must not push
    assert acc1.api.rpc("load_progress")["xp"] == ahead and repo2.status == "cloud_newer"
    svc2.reload()                                                            # next load adopts it
    assert svc2.xp == ahead and repo2.status == "synced"


def test_server_refuses_a_lower_xp_even_from_a_buggy_client(server, tmp_path):
    acc = signed_up(server, tmp_path)
    v = acc.api.rpc("save_progress", {"p_data": {"xp": 500}, "p_expected_version": 0})
    with pytest.raises(ServerError) as exc:
        acc.api.rpc("save_progress", {"p_data": {"xp": 10}, "p_expected_version": v})
    assert exc.value.code == "xp_regression"
    assert acc.api.rpc("load_progress")["xp"] == 500


def test_background_sync_coalesces_to_the_latest_state(server, tmp_path, clock):
    acc = signed_up(server, tmp_path)
    repo, svc = device(server, tmp_path, "bg", "a", clock, synchronous=False)
    repo.attach(acc.api)
    svc.reload()
    for _ in range(4):
        play_win(svc, clock)
    deadline = time.time() + 5
    while time.time() < deadline and (repo._running or acc.api.rpc("load_progress") is None
                                      or acc.api.rpc("load_progress")["xp"] != svc.xp):
        time.sleep(0.05)
    assert acc.api.rpc("load_progress")["xp"] == svc.xp and repo.status == "synced"


def test_detach_returns_to_local_only(server, tmp_path, clock):
    acc = signed_up(server, tmp_path)
    repo, svc = device(server, tmp_path, "d", "a", clock)
    repo.attach(acc.api); repo.detach()
    before = len(server.calls)
    play_win(svc, clock)
    assert repo.status == "local" and len(server.calls) == before


# ----------------------------------------------------------------------------- daily challenge
def test_daily_challenge_full_flow(server, tmp_path):
    maze = today_maze()
    server.publish_today(maze)
    a = signed_up(server, tmp_path, "a@t.dev", "daily_a", "da")
    b = signed_up(server, tmp_path, "b@t.dev", "daily_b", "db")
    da, db_ = DailyClient(a.api), DailyClient(b.api)

    run_a = da.start()
    assert run_a.maze.walls == maze.walls and solve(run_a.maze) == solve(maze)
    server.age_run(run_a.run_id, seconds_needed(maze, 18))
    res = da.submit(run_a, solve(run_a.maze))
    assert res.accepted and res.rank == 1 and res.message == ""

    run_b = db_.start()
    server.age_run(run_b.run_id, seconds_needed(maze, 7))
    assert db_.submit(run_b, solve(run_b.maze)).rank == 1                  # b is faster

    board = da.leaderboard()
    assert [(r.rank, r.username, r.is_me) for r in board] == [(1, "daily_b", False), (2, "daily_a", True)]
    assert board[0].elapsed_ms < board[1].elapsed_ms


def test_daily_cheating_is_rejected_with_a_readable_reason(server, tmp_path):
    maze = today_maze()
    server.publish_today(maze)
    acc = signed_up(server, tmp_path)
    client = DailyClient(acc.api)
    run = client.start()
    res = client.submit(run, solve(run.maze))                              # perfect path, but instantly
    assert not res.accepted and res.reason == "too_fast" and "quickly" in res.message
    run = client.start()
    server.age_run(run.run_id, 30)
    res = client.submit(run, [tuple(c) for c in wall_crossing_path(run.maze)])
    assert res.reason == "wall_crossed"
    assert client.leaderboard() == []


def test_daily_errors_have_friendly_messages(server, tmp_path):
    acc = signed_up(server, tmp_path)
    client = DailyClient(acc.api)
    with pytest.raises(ServerError) as exc:
        client.start()
    assert exc.value.code == "no_challenge_today" and "not published" in friendly(exc.value)
    server.publish_today(today_maze())
    guest_client = DailyClient(account(server, tmp_path, "guest").api)
    with pytest.raises(AuthError):
        guest_client.start()
    assert guest_client.leaderboard() == []                                # the board can be viewed without signing in


def test_clients_cannot_reach_tables_or_private_functions(server, tmp_path):
    acc = signed_up(server, tmp_path)
    with pytest.raises(ServerError) as exc:
        acc.api.rpc("validate_maze_path", {"p_walls": [], "p_w": 1, "p_h": 1, "p_start": [0, 0],
                                           "p_exit": [0, 0], "p_path": []})
    assert exc.value.code in ("permission_denied", "rpc_not_found")
