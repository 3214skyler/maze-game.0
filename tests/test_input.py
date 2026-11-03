from game.maze.maze import Maze
from game.input.drawing import DrawingController, Phase, PointerEvent, Viewport
from game.paths.manager import PathManager
from game.paths.path import StepResult

CELL = 100.0
VP = Viewport(origin_x=0, top_y=300, cell_size=CELL)   # 3x2 maze: x 0..300, y 300..100


def make():
    m = Maze(3, 2)
    m.carve((0, 0), (1, 0)); m.carve((1, 0), (2, 0)); m.carve((2, 0), (2, 1)); m.carve((0, 0), (0, 1))
    m.open_entrance_and_exit((0, 0), (2, 1))
    pm = PathManager(m)
    return pm, DrawingController(pm, VP)


def center(cx, cy):   # screen centre of grid cell
    return (cx * CELL + CELL / 2, 300 - (cy * CELL + CELL / 2))


def ev(phase, cell, pid=0, source="mouse"):
    x, y = center(*cell)
    return PointerEvent(phase, x, y, pid, source)


def test_viewport_roundtrip():
    gx, gy = VP.to_grid(*VP.to_screen(1.25, 0.5))
    assert (round(gx, 6), round(gy, 6)) == (1.25, 0.5)


def test_mouse_drag_draws_path():
    pm, dc = make()
    dc.handle(ev(Phase.PRESS, (0, 0)))
    assert dc.handle(ev(Phase.MOVE, (1, 0))) == [StepResult.MOVED]
    assert dc.handle(ev(Phase.MOVE, (2, 0))) == [StepResult.MOVED]
    assert pm.active_path.cells == [(0, 0), (1, 0), (2, 0)]
    dc.handle(ev(Phase.RELEASE, (2, 0)))
    assert not dc.drawing


def test_fast_swipe_does_not_skip_cells():
    pm, dc = make()
    dc.handle(ev(Phase.PRESS, (0, 0)))
    results = dc.handle(ev(Phase.MOVE, (2, 0)))   # two cells in a single event
    assert pm.active_path.cells == [(0, 0), (1, 0), (2, 0)]
    assert results == [StepResult.MOVED, StepResult.MOVED]


def test_fast_diagonal_swipe_stops_at_first_wall():
    pm, dc = make()
    dc.handle(ev(Phase.PRESS, (0, 0)))
    results = dc.handle(ev(Phase.MOVE, (2, 1)))   # line clips through the wall below (1,0)
    assert pm.active_path.cells == [(0, 0), (1, 0)]
    assert results == [StepResult.MOVED, StepResult.BLOCKED_WALL]


def test_drag_into_wall_reports_blocked_once():
    pm, dc = make()
    dc.handle(ev(Phase.PRESS, (0, 0)))
    dc.handle(ev(Phase.MOVE, (1, 0)))
    first = dc.handle(ev(Phase.MOVE, (1, 1)))
    again = dc.handle(ev(Phase.MOVE, (1, 1)))
    assert first == [StepResult.BLOCKED_WALL]
    assert again == []                               # no feedback spam
    assert pm.active_path.cells == [(0, 0), (1, 0)]


def test_press_far_from_head_is_ignored():
    pm, dc = make()
    dc.handle(ev(Phase.PRESS, (2, 1)))
    assert not dc.drawing
    assert dc.handle(ev(Phase.MOVE, (1, 0))) == []


def test_second_finger_ignored_and_touch_source_works():
    pm, dc = make()
    dc.handle(ev(Phase.PRESS, (0, 0), pid=7, source="touch"))
    dc.handle(ev(Phase.PRESS, (0, 0), pid=8, source="touch"))
    assert dc.handle(ev(Phase.MOVE, (1, 0), pid=8, source="touch")) == []
    assert dc.handle(ev(Phase.MOVE, (1, 0), pid=7, source="touch")) == [StepResult.MOVED]


def test_resume_drawing_and_backtrack_by_dragging_back():
    pm, dc = make()
    dc.handle(ev(Phase.PRESS, (0, 0)));  dc.handle(ev(Phase.MOVE, (1, 0)))
    dc.handle(ev(Phase.RELEASE, (1, 0)))
    dc.handle(ev(Phase.PRESS, (1, 0)))
    assert dc.handle(ev(Phase.MOVE, (0, 0))) == [StepResult.BACKTRACKED]
    assert pm.active_path.cells == [(0, 0)]


def test_drawing_only_affects_active_colour():
    pm, dc = make()
    pm.select("green")
    dc.handle(ev(Phase.PRESS, (0, 0))); dc.handle(ev(Phase.MOVE, (1, 0)))
    assert pm.path("green").cells == [(0, 0), (1, 0)]
    assert pm.path("blue").cells == [(0, 0)] and pm.path("red").cells == [(0, 0)]


def test_completion_reported():
    pm, dc = make()
    dc.handle(ev(Phase.PRESS, (0, 0)))
    for cell in [(1, 0), (2, 0)]:
        dc.handle(ev(Phase.MOVE, cell))
    assert dc.handle(ev(Phase.MOVE, (2, 1))) == [StepResult.COMPLETED]
