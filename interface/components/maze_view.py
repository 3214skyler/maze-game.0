"""Kivy widget that renders a maze and its three paths and forwards pointer input."""
from kivy.graphics import Color, Ellipse, InstructionGroup, Line, Rectangle
from kivy.uix.widget import Widget

from game.input.drawing import DrawingController, Phase, PointerEvent, Viewport
from game.paths.path import BLOCKING, StepResult
from interface.themes import neon


class MazeView(Widget):
    def __init__(self, maze, manager, settings, **kwargs):
        super().__init__(**kwargs)
        self.settings = settings
        self.on_blocked = None      # callback(StepResult)
        self.on_completed = None    # callback(color)
        self.on_change = None       # callback()
        self._walls = InstructionGroup()
        self._paths = InstructionGroup()
        self.canvas.add(self._walls)
        self.canvas.add(self._paths)
        self.viewport = None
        self.controller = None
        self.set_maze(maze, manager)
        self.bind(pos=self._layout, size=self._layout)

    def set_maze(self, maze, manager):
        self.maze, self.manager = maze, manager
        self._layout()

    # --- layout & drawing --------------------------------------------------
    def _layout(self, *_):
        if self.width <= 1 or self.height <= 1:
            return
        cell = min(self.width / self.maze.width, self.height / self.maze.height) * 0.94
        origin_x = self.x + (self.width - cell * self.maze.width) / 2
        top_y = self.y + self.height - (self.height - cell * self.maze.height) / 2
        self.viewport = Viewport(origin_x, top_y, cell)
        self.controller = DrawingController(self.manager, self.viewport)
        self._draw_walls()
        self.refresh()

    def _draw_walls(self):
        g, vp = self._walls, self.viewport
        g.clear()
        g.add(Color(*neon.PANEL))
        g.add(Rectangle(pos=(vp.origin_x, vp.top_y - vp.cell_size * self.maze.height),
                        size=(vp.cell_size * self.maze.width, vp.cell_size * self.maze.height)))
        segments = [(vp.to_screen(*a), vp.to_screen(*b)) for a, b in self.maze.wall_segments()]
        layers = [(neon.dim(neon.WALL, 0.25), vp.cell_size * 0.22), (neon.WALL, max(1.5, vp.cell_size * 0.07))] \
            if self.settings.glow_enabled else [(neon.WALL, max(1.5, vp.cell_size * 0.07))]
        for rgba, width in layers:
            g.add(Color(*rgba))
            for (x1, y1), (x2, y2) in segments:
                g.add(Line(points=[x1, y1, x2, y2], width=width, cap="round"))
        # entrance / exit markers
        for cell, rgba in ((self.maze.start, neon.ACCENT), (self.maze.exit, neon.GOLD)):
            cx, cy = vp.to_screen(cell[0] + 0.5, cell[1] + 0.5)
            r = vp.cell_size * 0.22
            g.add(Color(*neon.dim(rgba, 0.5)))
            g.add(Ellipse(pos=(cx - r * 1.6, cy - r * 1.6), size=(r * 3.2, r * 3.2)))
            g.add(Color(*rgba))
            g.add(Ellipse(pos=(cx - r, cy - r), size=(r * 2, r * 2)))

    def refresh(self):
        """Redraw only the paths (cheap); walls are cached."""
        if self.viewport is None:
            return
        g, vp = self._paths, self.viewport
        g.clear()
        for color, path in self.manager.paths.items():
            rgba = neon.PATH_RGBA[color]
            pts = []
            for cx, cy in path.cells:
                pts.extend(vp.to_screen(cx + 0.5, cy + 0.5))
            active = color == self.manager.active
            base = vp.cell_size * (0.30 if active else 0.20)
            if self.settings.glow_enabled and len(pts) >= 4:
                g.add(Color(*neon.dim(rgba, 0.22 if active else 0.12)))
                g.add(Line(points=pts, width=base * 2.2, cap="round", joint="round"))
            g.add(Color(*neon.dim(rgba, 1.0 if active else 0.75)))
            if len(pts) >= 4:
                g.add(Line(points=pts, width=base, cap="round", joint="round"))
            hx, hy = pts[-2], pts[-1]
            r = base * (0.9 if path.completed else 0.7)
            g.add(Color(1, 1, 1, 0.9 if path.completed else 0.0))
            g.add(Ellipse(pos=(hx - r, hy - r), size=(r * 2, r * 2)))
            g.add(Color(*rgba))
            g.add(Ellipse(pos=(hx - r * 0.7, hy - r * 0.7), size=(r * 1.4, r * 1.4)))

    # --- input: translate Kivy touches into device-independent events -------
    def _event(self, phase, touch):
        source = "mouse" if "button" in touch.profile else "touch"
        return PointerEvent(phase, touch.x, touch.y, touch.uid, source)

    def _dispatch(self, phase, touch):
        if self.controller is None:
            return
        was_done = {c for c, p in self.manager.paths.items() if p.completed}
        results = self.controller.handle(self._event(phase, touch))
        if not results:
            return
        self.refresh()
        if self.on_change:
            self.on_change()
        for r in results:
            if r in BLOCKING and self.on_blocked:
                self.on_blocked(r)
        active = self.manager.active
        if self.manager.path(active).completed and active not in was_done and self.on_completed:
            self.on_completed(active)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        if "button" in touch.profile and touch.button != "left":
            return False
        touch.grab(self)
        self._dispatch(Phase.PRESS, touch)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self._dispatch(Phase.MOVE, touch)
            return True
        return False

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            self._dispatch(Phase.RELEASE, touch)
            touch.ungrab(self)
            return True
        return False
