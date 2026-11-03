from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from game.core.config import PATH_COLORS, Settings
from game.maze.maze import E, N, S, W
from game.paths.manager import PathManager
from game.paths.path import StepResult
from game.progression.levels import build_level
from interface.components.maze_view import MazeView
from interface.screens.menu import neon_button
from interface.themes import neon

ARROWS = {273: N, 274: S, 275: E, 276: W}          # Kivy keycodes
DIGITS = {49: 0, 50: 1, 51: 2, 257: 0, 258: 1, 259: 2}


class GameplayScreen(Screen):
    def __init__(self, settings=None, **kwargs):
        super().__init__(name="game", **kwargs)
        self.settings = settings or Settings()
        self.level = 1
        root = BoxLayout(orientation="vertical", padding=8, spacing=6)

        top = BoxLayout(size_hint_y=None, height=48, spacing=6)
        back = neon_button("MENU", neon.ACCENT, size_hint_x=None, width=90)
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "menu"))
        self.level_label = Label(color=neon.ACCENT, bold=True)
        top.add_widget(back)
        top.add_widget(self.level_label)
        root.add_widget(top)

        maze = build_level(1)
        self.manager_paths = PathManager(maze)
        self.view = MazeView(maze, self.manager_paths, self.settings)
        self.view.on_blocked = self._blocked
        self.view.on_completed = self._completed
        self.view.on_change = self._sync_ui
        root.add_widget(self.view)

        self.status = Label(size_hint_y=None, height=40, color=(0.8, 0.85, 1, 1), halign="center", valign="middle")
        self.status.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.status)

        bar = BoxLayout(size_hint_y=None, height=56, spacing=6)
        self.color_buttons = {}
        for i, color in enumerate(PATH_COLORS):
            b = neon_button(color.upper(), neon.PATH_RGBA[color])
            b.bind(on_release=lambda _b, c=color: self._select(c))
            self.color_buttons[color] = b
            bar.add_widget(b)
        reset = neon_button("RESET", neon.GOLD, size_hint_x=0.7)
        reset.bind(on_release=lambda *_: self._reset())
        nxt = neon_button("NEXT", neon.ACCENT, size_hint_x=0.7)
        nxt.bind(on_release=lambda *_: self.start_level(self.level + 1))
        bar.add_widget(reset)
        bar.add_widget(nxt)
        root.add_widget(bar)
        self.add_widget(root)
        self._sync_ui()

    # --- level lifecycle ------------------------------------------------------
    def start_level(self, number):
        self.level = number
        maze = build_level(number)
        self.manager_paths = PathManager(maze)
        self.view.set_maze(maze, self.manager_paths)
        self.status.text = "Draw from cyan to gold.  Keys: 1-3 colour, arrows, R reset, N next"
        self._sync_ui()

    # --- feedback -----------------------------------------------------------------
    def _sync_ui(self):
        m = self.view.maze
        self.level_label.text = f"LEVEL {self.level}   {m.width}x{m.height}   seed {m.seed}   {m.algorithm}"
        done = set(self.manager_paths.completed_colors())
        for color, b in self.color_buttons.items():
            rgba = neon.PATH_RGBA[color]
            b.background_color = rgba if color == self.manager_paths.active else neon.dim(rgba, 0.4)
            b.text = color.upper() + ("  OK" if color in done else "")

    def _blocked(self, result):
        self.status.text = "Wall! Pull back and try another route." if result is StepResult.BLOCKED_WALL \
            else "A path cannot cross itself." if result is StepResult.BLOCKED_SELF \
            else "This path is complete - drag back to edit it."

    def _completed(self, color):
        n = len(self.manager_paths.completed_colors())
        self.status.text = "LEVEL CLEARED - all three paths reached the exit!" if self.manager_paths.all_completed \
            else f"{color.upper()} path reached the exit  ({n}/3)"
        self._sync_ui()

    def _select(self, color):
        self.manager_paths.select(color)
        self.view.refresh()
        self._sync_ui()

    def _reset(self):
        self.manager_paths.reset(self.manager_paths.active)
        self.view.refresh()
        self._sync_ui()
        self.status.text = f"{self.manager_paths.active.upper()} path reset"

    # --- keyboard (desktop) -------------------------------------------------------
    def on_enter(self, *_):
        Window.bind(on_key_down=self._on_key)

    def on_leave(self, *_):
        Window.unbind(on_key_down=self._on_key)

    def _on_key(self, _win, key, _scan, text, _mods):
        if key in DIGITS:
            self._select(PATH_COLORS[DIGITS[key]])
        elif key in ARROWS:
            result = self.manager_paths.move(ARROWS[key])
            self.view.refresh()
            self._sync_ui()
            if result in (StepResult.BLOCKED_WALL, StepResult.BLOCKED_SELF, StepResult.ALREADY_COMPLETE):
                self._blocked(result)
            elif result is StepResult.COMPLETED:
                self._completed(self.manager_paths.active)
        elif text == "r":
            self._reset()
        elif text == "n":
            self.start_level(self.level + 1)
        elif key == 27:
            self.manager.current = "menu"
            return True
        return False
