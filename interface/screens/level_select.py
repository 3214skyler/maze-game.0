"""Difficulty tabs + grid of levels (locked / cleared / available)."""
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import Screen

from game.progression.difficulty import Difficulty, settings_for
from interface.components.hud import LivesBar, format_seconds
from interface.screens.menu import neon_button
from interface.themes import neon

LOCKED = (0.18, 0.2, 0.28, 1)


class LevelSelectScreen(Screen):
    def __init__(self, service, **kwargs):
        super().__init__(name="levels", **kwargs)
        self.service = service
        self.difficulty = Difficulty.NORMAL
        self._timer = None
        root = BoxLayout(orientation="vertical", padding=10, spacing=8)
        top = BoxLayout(size_hint_y=None, height=44, spacing=6)
        back = neon_button("MENU", neon.ACCENT, size_hint_x=None, width=80)
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "menu"))
        self.info = Label(color=(0.8, 0.85, 1, 1), font_size="13sp")
        self.lives_bar = LivesBar(size_hint_y=None, height=30)
        top.add_widget(back)
        top.add_widget(self.info)
        top.add_widget(self.lives_bar)
        root.add_widget(top)
        self.tabs = BoxLayout(size_hint_y=None, height=44, spacing=6)
        self.tab_buttons = {}
        for d in Difficulty:
            b = neon_button(settings_for(d).label, neon.ACCENT)
            b.bind(on_release=lambda _b, dd=d: self.select_difficulty(dd))
            self.tab_buttons[d] = b
            self.tabs.add_widget(b)
        root.add_widget(self.tabs)
        self.message = Label(size_hint_y=None, height=26, color=neon.GOLD, font_size="13sp")
        root.add_widget(self.message)
        self.scroll = ScrollView()
        self.grid = GridLayout(cols=5, spacing=6, size_hint_y=None, padding=2)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.scroll.add_widget(self.grid)
        root.add_widget(self.scroll)
        self.add_widget(root)

    def on_enter(self, *_):
        self.rebuild()
        self._timer = Clock.schedule_interval(lambda _dt: self._refresh_top(), 1.0)

    def on_leave(self, *_):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def select_difficulty(self, difficulty):
        if not self.service.difficulty_unlocked(difficulty):
            need = self.service.cfg.nightmare_unlock_level
            self.message.text = f"Locked: clear HARD level {need} to unlock."
            return
        self.difficulty = difficulty
        self.rebuild()

    def _refresh_top(self):
        svc = self.service
        self.lives_bar.max_lives = svc.cfg.max_lives
        self.lives_bar.lives = svc.lives()
        wait = svc.seconds_until_next_life()
        extra = f"   next life {format_seconds(wait)}" if wait is not None else ""
        level, into, needed = svc.xp_progress()
        self.info.text = f"PLAYER LV {level}   $ {svc.coins}{extra}"

    def rebuild(self):
        svc, d = self.service, self.difficulty
        self.message.text = ""
        self._refresh_top()
        for diff, b in self.tab_buttons.items():
            unlocked = svc.difficulty_unlocked(diff)
            b.background_color = neon.ACCENT if diff == d else neon.dim(neon.ACCENT, 0.35)
            b.text = settings_for(diff).label + ("" if unlocked else "\n(LOCKED)")
            b.font_size = "11sp"
        self.grid.clear_widgets()
        highest = svc.highest_unlocked(d)
        for n in range(1, svc.cfg.max_level + 1):
            unlocked = n <= highest
            done = svc.is_level_completed(d, n)
            btn = neon_button(str(n), neon.PATH_RGBA["green"] if done else
                              (neon.PATH_RGBA["blue"] if unlocked else LOCKED),
                              size_hint_y=None, height=54)
            btn.disabled = not unlocked
            btn.bind(on_release=lambda _b, lvl=n: self.play(lvl))
            self.grid.add_widget(btn)

    def play(self, level):
        game = self.manager.get_screen("game")
        if game.begin(self.difficulty, level):
            self.manager.current = "game"
        else:
            self.message.text = game.status.text
