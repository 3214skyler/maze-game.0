"""Headless UI checks: build the widgets and push touch events through them."""
import os
import types

import pytest

os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
pytest.importorskip("kivy")

from game.core.config import Settings  # noqa: E402
from game.maze.solver import solve  # noqa: E402


@pytest.fixture
def view():
    from interface.components.maze_view import MazeView
    from game.paths.manager import PathManager
    from game.progression.levels import build_level
    maze = build_level(1)
    mv = MazeView(maze, PathManager(maze), Settings(), size=(480, 640), pos=(0, 0))
    mv._layout()
    return mv


def touch(x, y, uid=1, mouse=False):
    t = types.SimpleNamespace(x=x, y=y, pos=(x, y), uid=uid, grab_current=None,
                              profile=["button"] if mouse else [], button="left")
    t.grab = lambda w: setattr(t, "grab_current", w)
    t.ungrab = lambda w: setattr(t, "grab_current", None)
    return t


def centre(mv, cell):
    return mv.viewport.to_screen(cell[0] + 0.5, cell[1] + 0.5)


@pytest.mark.parametrize("mouse", [True, False])
def test_drawing_the_solution_with_touches_completes_blue_path(view, mouse):
    route = solve(view.maze)
    done = []
    view.on_completed = done.append
    t = touch(*centre(view, route[0]), mouse=mouse)
    assert view.on_touch_down(t)
    for cell in route[1:]:
        t.x, t.y = centre(view, cell)
        t.pos = (t.x, t.y)
        t.grab_current = view
        view.on_touch_move(t)
    view.on_touch_up(t)
    assert done == ["blue"]
    assert view.manager.path("blue").cells == route
    assert view.manager.path("green").cells == [view.maze.start]


def test_drawing_into_wall_triggers_blocked_callback(view):
    blocked = []
    view.on_blocked = blocked.append
    start = view.maze.start
    t = touch(*centre(view, start))
    view.on_touch_down(t)
    # find a wall-separated neighbour of the start
    target = next(n for n in view.maze.neighbors(start) if not view.maze.can_move(start, n))
    t.x, t.y = centre(view, target)
    t.pos = (t.x, t.y)
    view.on_touch_move(t)
    assert blocked and view.manager.active_path.cells == [start]


def test_screens_build():
    from interface.screens.gameplay import GameplayScreen
    from interface.screens.menu import MenuScreen
    from interface.screens.splash import SplashScreen
    for cls in (SplashScreen, MenuScreen, GameplayScreen):
        assert cls() is not None
