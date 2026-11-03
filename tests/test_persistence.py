import json
import os

import pytest

from game.core.errors import SaveError
from game.persistence.json_store import SCHEMA_VERSION, JsonProfileRepository
from game.persistence.repository import MemoryRepository
from game.progression.difficulty import Difficulty
from game.progression.service import ProgressService


class Clock:
    t = 2_000_000.0

    def __call__(self):
        return self.t


def play_win(svc, clock, level=1):
    s = svc.start_level(Difficulty.NORMAL, level)
    clock.t += 6
    s.update(1, svc.now())
    return svc.conclude(s)


def test_progress_survives_restart(tmp_path):
    path = tmp_path / "save" / "progress.json"
    clock = Clock()
    a = ProgressService(JsonProfileRepository(path), clock=clock)
    play_win(a, clock, 1); play_win(a, clock, 2)
    s = a.start_level(Difficulty.NORMAL, 3)
    clock.t += s.time_limit + 1
    s.update(0, a.now()); a.conclude(s)
    snapshot = (a.xp, a.coins, a.lives(), a.highest_unlocked(Difficulty.NORMAL),
                a.stats.to_dict(), a.player_level())

    b = ProgressService(JsonProfileRepository(path), clock=clock)          # "reopen the game"
    assert (b.xp, b.coins, b.lives(), b.highest_unlocked(Difficulty.NORMAL),
            b.stats.to_dict(), b.player_level()) == snapshot
    assert b.stats.best_time("normal:1") == 6.0 and b.load_warning is None


def test_lives_regenerate_while_the_game_is_closed(tmp_path):
    path, clock = tmp_path / "p.json", Clock()
    a = ProgressService(JsonProfileRepository(path), clock=clock)
    s = a.start_level(Difficulty.NORMAL, 1)
    clock.t += s.time_limit + 1; s.update(0, a.now()); a.conclude(s)
    assert a.lives() == a.cfg.max_lives - 1
    clock.t += a.cfg.life_regen_seconds * 2                                # closed for a while
    assert ProgressService(JsonProfileRepository(path), clock=clock).lives() == a.cfg.max_lives


def test_save_file_is_versioned_valid_json_and_leaves_no_temp_files(tmp_path):
    path, clock = tmp_path / "p.json", Clock()
    svc = ProgressService(JsonProfileRepository(path), clock=clock)
    play_win(svc, clock)
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == SCHEMA_VERSION and payload["profile"]["xp"] > 0
    assert [f.name for f in tmp_path.iterdir()] == ["p.json"]


def test_corrupt_file_is_quarantined_and_game_starts_fresh(tmp_path):
    path = tmp_path / "p.json"
    path.write_text("{ this is not json")
    repo = JsonProfileRepository(path)
    svc = ProgressService(repo, clock=Clock())
    assert svc.xp == 0 and svc.lives() == svc.cfg.max_lives
    assert repo.last_load_error is not None
    assert any(".corrupt-" in f.name for f in tmp_path.iterdir()) and not path.exists()
    assert svc.save() and path.exists()                                     # can write a clean save again


def test_wellformed_json_with_invalid_content_is_reset_not_crashing(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"schema_version": SCHEMA_VERSION,
                                "profile": {"xp": -5, "wallet": {}, "lives": {}, "stats": {}, "unlocks": {}}}))
    svc = ProgressService(JsonProfileRepository(path), clock=Clock())
    assert svc.xp == 0 and svc.load_warning
    assert any(".corrupt-" in f.name for f in tmp_path.iterdir())


def test_unknown_schema_version_is_not_loaded(tmp_path):
    path = tmp_path / "p.json"
    path.write_text(json.dumps({"schema_version": 999, "profile": {}}))
    assert JsonProfileRepository(path).load() is None


def test_missing_file_starts_fresh_without_warning(tmp_path):
    svc = ProgressService(JsonProfileRepository(tmp_path / "nope.json"), clock=Clock())
    assert svc.xp == 0 and svc.load_warning is None


def test_save_failure_does_not_crash_the_game(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    repo = JsonProfileRepository(blocker / "sub" / "p.json")               # parent is a file: cannot mkdir
    with pytest.raises(SaveError):
        repo.save({"a": 1})
    clock = Clock()
    svc = ProgressService(repo, clock=clock)
    play_win(svc, clock)                                                    # must not raise
    assert svc.save_error and svc.xp > 0                                    # progress kept in memory


def test_memory_repository_roundtrip():
    repo, clock = MemoryRepository(), Clock()
    a = ProgressService(repo, clock=clock)
    play_win(a, clock)
    assert ProgressService(repo, clock=clock).xp == a.xp


def test_tampered_negative_values_are_rejected(tmp_path):
    path, clock = tmp_path / "p.json", Clock()
    svc = ProgressService(JsonProfileRepository(path), clock=clock)
    play_win(svc, clock)
    payload = json.loads(path.read_text())
    payload["profile"]["wallet"]["balance"] = -100
    path.write_text(json.dumps(payload))
    again = ProgressService(JsonProfileRepository(path), clock=clock)
    assert again.coins == 0 and again.load_warning
