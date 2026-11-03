"""Headless end-to-end checks of the Kivy screens wired to a real ProgressService."""
import os

import pytest

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
pytest.importorskip("kivy")

from game.maze.solver import solve  # noqa: E402
from game.persistence.repository import MemoryRepository  # noqa: E402
from game.progression.difficulty import Difficulty  # noqa: E402
from game.progression.service import ProgressService  # noqa: E402

N, H = Difficulty.NORMAL, Difficulty.HARD


class FakeKivyClock:
    """Runs scheduled callbacks immediately so tests need no event loop."""
    class _Ev:
        def cancel(self):
            pass

    def schedule_once(self, fn, _t=0):
        fn(0)
        return self._Ev()

    def schedule_interval(self, fn, _t=0):
        return self._Ev()


class TimeSource:
    t = 5_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def ui(monkeypatch):
    from kivy.uix.screenmanager import ScreenManager
    from interface.screens.gameplay import GameplayScreen
    from interface.screens.level_select import LevelSelectScreen
    from interface.screens.menu import MenuScreen
    from interface.screens.result import DefeatScreen, VictoryScreen
    monkeypatch.setattr("interface.screens.gameplay.Clock", FakeKivyClock())
    time_source = TimeSource()
    svc = ProgressService(MemoryRepository(), clock=time_source)
    sm = ScreenManager()
    screens = {"menu": MenuScreen(service=svc), "levels": LevelSelectScreen(svc),
               "game": GameplayScreen(service=svc), "victory": VictoryScreen(svc), "defeat": DefeatScreen(svc)}
    for s in screens.values():
        sm.add_widget(s)
    sm.current = "levels"
    return sm, svc, time_source, screens


def draw_solution(game, paths):
    route = solve(game.session.maze)
    for color in ("blue", "green", "red")[:paths]:
        game.manager_paths.select(color)
        for cell in route[1:]:
            game.manager_paths.extend(cell)
    game.view.refresh()
    game._changed()            # what MazeView.on_change triggers after real touch input


def texts(screen):
    out = []

    def walk(w):
        if hasattr(w, "text") and w.text:
            out.append(w.text)
        for c in w.children:
            walk(c)
    walk(screen)
    return out


def test_victory_flow_unlocks_next_level_and_shows_rewards(ui):
    sm, svc, clock, s = ui
    game = s["game"]
    assert game.begin(N, 1)
    assert game.next_btn.disabled                       # cannot skip ahead
    clock.t += 4
    draw_solution(game, 1)
    assert sm.current == "victory" and svc.highest_unlocked(N) == 2
    shown = " ".join(texts(s["victory"]))
    assert "LEVEL CLEARED" in shown and "LEVEL 2 UNLOCKED" in shown and "FLAWLESS" in shown
    assert svc.xp > 0 and svc.coins > 0 and svc.stats.levels_completed == 1


def test_victory_screen_next_and_replay(ui):
    sm, svc, clock, s = ui
    game = s["game"]
    game.begin(N, 1); clock.t += 3; draw_solution(game, 1)
    s["victory"]._next()
    assert sm.current == "game" and game.session.level == 2 and game.session.active
    game.leave("levels")
    s["victory"].replay()
    assert game.session.level == 1


def test_defeat_on_timeout_costs_a_life_and_shows_reason(ui):
    sm, svc, clock, s = ui
    game = s["game"]
    game.begin(N, 1)
    clock.t += game.session.time_limit + 1
    game._tick(0)
    assert sm.current == "defeat" and svc.lives() == svc.cfg.max_lives - 1
    shown = " ".join(texts(s["defeat"]))
    assert "DEFEAT" in shown and "TIME RAN OUT" in shown
    assert not s["defeat"].retry.disabled


def test_no_lives_blocks_playing_and_retry(ui):
    sm, svc, clock, s = ui
    game = s["game"]
    for _ in range(svc.cfg.max_lives):
        assert game.begin(N, 1)
        clock.t += game.session.time_limit + 1
        game._tick(0)
    assert svc.lives() == 0 and sm.current == "defeat"
    assert s["defeat"].retry.disabled and "NO LIVES" in " ".join(texts(s["defeat"]))
    assert game.begin(N, 1) is False and "no lives" in game.status.text.lower()
    s["levels"].play(1)                                   # level select cannot bypass it either
    assert sm.current == "defeat"


def test_buy_life_button_on_defeat_screen(ui):
    sm, svc, clock, s = ui
    game = s["game"]
    game.begin(N, 1)
    clock.t += game.session.time_limit + 1
    game._tick(0)
    assert s["defeat"].buy.disabled                       # no coins yet
    svc.profile.wallet.earn(svc.cfg.life_cost_coins, "test")
    s["defeat"]._refresh_extra()
    assert not s["defeat"].buy.disabled
    s["defeat"]._buy()
    assert svc.lives() == svc.cfg.max_lives


def test_wall_errors_are_counted_but_never_lose_a_life(ui):
    sm, svc, clock, s = ui
    game = s["game"]
    game.begin(N, 1)
    from game.paths.path import StepResult
    for _ in range(10):
        game._blocked(StepResult.BLOCKED_WALL)
    assert game.session.errors == 10 and svc.lives() == svc.cfg.max_lives and game.session.active
    clock.t += 3
    draw_solution(game, 1)
    assert "FLAWLESS" not in " ".join(texts(s["victory"]))


def test_n_key_cannot_skip_levels(ui):
    sm, svc, clock, s = ui
    game = s["game"]
    game.begin(N, 1)
    game._on_key(None, 110, 0, "n", [])
    assert game.session.level == 1 and svc.highest_unlocked(N) == 1
    game.next_btn.dispatch("on_release")
    assert game.session.level == 1
    clock.t += 3; draw_solution(game, 1)                  # clear it...
    game.begin(N, 1)                                      # ...replay: now level 2 is unlocked
    assert not game.next_btn.disabled
    game._on_key(None, 110, 0, "n", [])
    assert game.session.level == 2


def test_hard_requires_two_paths_and_all_three_gives_bonus(ui):
    sm, svc, clock, s = ui
    game = s["game"]
    game.begin(H, 1)
    assert game.session.required_paths == 2
    clock.t += 5
    draw_solution(game, 1)
    assert sm.current == "levels" and game.session.active          # one path is not enough
    game.manager_paths.select("green")
    for cell in solve(game.session.maze)[1:]:
        game.manager_paths.extend(cell)
    game._changed()
    assert sm.current == "victory"


def test_leaving_a_level_is_free_and_recorded_as_play_time(ui):
    sm, svc, clock, s = ui
    game = s["game"]
    game.begin(N, 1)
    clock.t += 8
    game.leave("levels")
    assert sm.current == "levels" and svc.lives() == svc.cfg.max_lives
    assert svc.stats.total_play_seconds == pytest.approx(8.0) and svc.stats.levels_played == 0


def test_level_select_shows_locks_and_nightmare_lock(ui):
    sm, svc, clock, s = ui
    ls = s["levels"]
    ls.rebuild()
    enabled = [not b.disabled for b in reversed(ls.grid.children)]
    assert enabled[:3] == [True, False, False] and sum(enabled) == 1
    ls.select_difficulty(Difficulty.NIGHTMARE)
    assert ls.difficulty is N and "Locked" in ls.message.text
    game = s["game"]
    game.begin(N, 1); clock.t += 3; draw_solution(game, 1)
    ls.rebuild()
    assert sum(not b.disabled for b in ls.grid.children) == 2


def test_hud_reflects_service_state(ui):
    sm, svc, clock, s = ui
    game = s["game"]
    svc.profile.wallet.earn(42, "t")
    svc.profile.xp = 150
    game.begin(N, 1)
    assert game.coin_label.value == 42 and game.player_label.text == "LV 2"
    assert game.lives_bar.lives == svc.cfg.max_lives
    assert 0 < game.xp_bar.fraction < 1
    assert ":" in game.timer_label.text and "NORMAL" in game.level_label.text
