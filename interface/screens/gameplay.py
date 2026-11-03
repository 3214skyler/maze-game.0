"""Gameplay screen: presentation + glue only. All rules live in game/progression."""
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from game.core.config import PATH_COLORS, Settings
from game.core.errors import ProgressError
from game.maze.maze import E, N, S, W
from game.paths.manager import PathManager
from game.paths.path import BLOCKING, StepResult
from game.persistence.repository import MemoryRepository
from game.progression.difficulty import Difficulty, settings_for
from game.progression.levels import build_level
from game.progression.service import ProgressService
from game.progression.session import Outcome
from interface.animations.effects import flash, float_text, pulse
from interface.components.hud import CountLabel, LivesBar, XPBar, format_seconds
from interface.components.maze_view import MazeView
from interface.screens.menu import neon_button
from interface.themes import neon

ARROWS = {273: N, 274: S, 275: E, 276: W}          # Kivy keycodes
DIGITS = {49: 0, 50: 1, 51: 2, 257: 0, 258: 1, 259: 2}
TICK = 0.2


class GameplayScreen(Screen):
    def __init__(self, service=None, settings=None, **kwargs):
        super().__init__(name="game", **kwargs)
        self.service = service or ProgressService(MemoryRepository())
        self.settings = settings or Settings()
        self.session = None
        self._tick_event = None
        self._pending_end = None
        self._xp_shown = None

        root = BoxLayout(orientation="vertical", padding=8, spacing=4)
        # --- HUD row 1: menu, level/difficulty, timer
        row1 = BoxLayout(size_hint_y=None, height=44, spacing=6)
        back = neon_button("MENU", neon.ACCENT, size_hint_x=None, width=80)
        back.bind(on_release=lambda *_: self.leave("levels"))
        self.level_label = Label(color=neon.ACCENT, bold=True, font_size="14sp")
        self.timer_label = Label(color=neon.GOLD, bold=True, font_size="22sp", size_hint_x=None, width=90)
        for w in (back, self.level_label, self.timer_label):
            row1.add_widget(w)
        root.add_widget(row1)
        # --- HUD row 2: player level + XP bar, coins, lives
        row2 = BoxLayout(size_hint_y=None, height=30, spacing=6)
        self.player_label = Label(color=neon.ACCENT, bold=True, font_size="13sp", size_hint_x=None, width=60)
        self.xp_bar = XPBar()
        self.coin_label = CountLabel(prefix="$ ", color=neon.GOLD, bold=True, font_size="14sp",
                                     size_hint_x=None, width=80)
        self.lives_bar = LivesBar()
        for w in (self.player_label, self.xp_bar, self.coin_label, self.lives_bar):
            row2.add_widget(w)
        root.add_widget(row2)

        self.view = MazeView(build_level(1), PathManager(build_level(1)), self.settings)
        self.view.disabled = True              # enabled by begin()
        self.view.on_blocked = self._blocked
        self.view.on_completed = self._path_completed
        self.view.on_change = self._changed
        root.add_widget(self.view)

        self.status = Label(size_hint_y=None, height=36, color=(0.8, 0.85, 1, 1), halign="center", valign="middle")
        self.status.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.status)

        bar = BoxLayout(size_hint_y=None, height=54, spacing=6)
        self.color_buttons = {}
        for color in PATH_COLORS:
            b = neon_button(color.upper(), neon.PATH_RGBA[color])
            b.bind(on_release=lambda _b, c=color: self._select(c))
            self.color_buttons[color] = b
            bar.add_widget(b)
        reset = neon_button("RESET", neon.GOLD, size_hint_x=0.7)
        reset.bind(on_release=lambda *_: self._reset())
        self.next_btn = neon_button("NEXT", neon.ACCENT, size_hint_x=0.7)
        self.next_btn.bind(on_release=lambda *_: self.go_next())
        bar.add_widget(reset)
        bar.add_widget(self.next_btn)
        root.add_widget(bar)
        self.add_widget(root)
        self.overlay = FloatLayout()          # floating text / flashes live above everything
        self.add_widget(self.overlay)
        self._refresh_hud()

    # --- lifecycle --------------------------------------------------------------------------
    def begin(self, difficulty, level) -> bool:
        """Start (or restart) a level through the service. Returns False if the rules forbid it."""
        self.leave(None)                                  # close any running session first
        try:
            self.session = self.service.start_level(difficulty, level)
        except ProgressError as exc:
            self.status.text = str(exc)
            return False
        self.view.disabled = False
        self.manager_paths = PathManager(self.session.maze)
        self.view.set_maze(self.session.maze, self.manager_paths)
        req = self.session.required_paths
        self.status.text = f"Reach the gold exit with {req} path{'s' if req > 1 else ''}" \
                           f"{' (all 3 = bonus XP)' if req < 3 else ''}"
        self._xp_shown = None
        self._refresh_hud()
        return True

    def leave(self, target):
        """Abandon a running session (no penalty) and optionally switch screen."""
        self._cancel_pending()
        if self.session is not None and self.session.active:
            self.service.abandon(self.session)
        if target and self.manager:
            self.manager.current = target

    def go_next(self):
        s = self.session
        if s and self.service.has_next_level(s.difficulty, s.level):
            self.begin(s.difficulty, s.level + 1)
        else:
            self.status.text = "Clear this level first to unlock the next one."

    def on_enter(self, *_):
        Window.bind(on_key_down=self._on_key)
        self._tick_event = Clock.schedule_interval(self._tick, TICK)

    def on_leave(self, *_):
        Window.unbind(on_key_down=self._on_key)
        if self._tick_event:
            self._tick_event.cancel()
            self._tick_event = None

    def _cancel_pending(self):
        if self._pending_end:
            self._pending_end.cancel()
            self._pending_end = None

    # --- game loop glue -------------------------------------------------------------------------
    def _paths_done(self) -> int:
        return len(self.manager_paths.completed_colors())

    def _tick(self, _dt):
        if self.session is None or not self.session.active:
            return
        self._check_outcome()
        self._refresh_timer()

    def _check_outcome(self):
        s = self.session
        if s is None or not s.active:
            return
        if s.update(self._paths_done(), self.service.now()) in (Outcome.VICTORY, Outcome.DEFEAT):
            self._finish()

    def _finish(self):
        result = self.service.conclude(self.session)
        self.view.disabled = True
        c = self.overlay.center
        if result.victory:
            flash(self.overlay, neon.PATH_RGBA["green"], 0.25)
            float_text(self.overlay, f"+{result.rewards.xp} XP", neon.ACCENT, (c[0], c[1] + 20), "30sp")
            float_text(self.overlay, f"+{result.rewards.coins} COINS", neon.GOLD, (c[0], c[1] - 30), "24sp")
            if result.level_ups:
                float_text(self.overlay, f"LEVEL UP!  {result.level_ups[-1]}", neon.PATH_RGBA["green"],
                           (c[0], c[1] + 80), "28sp")
        else:
            flash(self.overlay, neon.PATH_RGBA["red"], 0.45)
            pulse(self.lives_bar)
            float_text(self.overlay, "-1 LIFE", neon.PATH_RGBA["red"], c, "34sp")
        self._refresh_hud(animate=True)
        target = "victory" if result.victory else "defeat"
        self._pending_end = Clock.schedule_once(lambda _dt: self._show_result(target, result), 1.1)

    def _show_result(self, target, result):
        self._pending_end = None
        self.manager.get_screen(target).show(result)
        self.manager.current = target

    # --- callbacks from the view -----------------------------------------------------------------
    def _blocked(self, result):
        if self.session is not None:
            self.session.record_error()
        self.status.text = {
            StepResult.BLOCKED_WALL: "Wall! Pull back and try another route.",
            StepResult.BLOCKED_SELF: "A path cannot cross itself.",
        }.get(result, "This path is complete - drag back to edit it.")
        if result in (StepResult.BLOCKED_WALL, StepResult.BLOCKED_SELF):
            flash(self.overlay, neon.PATH_RGBA["red"], 0.12, 0.25)

    def _path_completed(self, color):
        c = self.overlay.center
        float_text(self.overlay, f"{color.upper()} PATH!", neon.PATH_RGBA[color], (c[0], c[1] + 40))
        self._changed()

    def _changed(self):
        self._refresh_hud()
        self._check_outcome()

    # --- controls ----------------------------------------------------------------------------------
    def _select(self, color):
        self.manager_paths.select(color)
        self.view.refresh()
        self._refresh_hud()

    def _reset(self):
        self.manager_paths.reset(self.manager_paths.active)
        self.view.refresh()
        self._refresh_hud()
        self.status.text = f"{self.manager_paths.active.upper()} path reset"

    def _on_key(self, _win, key, _scan, text, _mods):
        if self.session is None or not self.session.active:
            return False
        if key in DIGITS:
            self._select(PATH_COLORS[DIGITS[key]])
        elif key in ARROWS:
            result = self.manager_paths.move(ARROWS[key])
            self.view.refresh()
            if result in BLOCKING:
                self._blocked(result)
            elif result is StepResult.COMPLETED:
                self._path_completed(self.manager_paths.active)
            self._changed()
        elif text == "r":
            self._reset()
        elif text == "n":
            self.go_next()                      # guarded: only works if the next level is unlocked
        elif key == 27:
            self.leave("levels")
            return True
        return False

    # --- HUD ----------------------------------------------------------------------------------------
    def _refresh_timer(self):
        s = self.session
        if s is None:
            self.timer_label.text = "--:--"
            return
        left = s.time_left(self.service.now())
        self.timer_label.text = format_seconds(left)
        self.timer_label.color = neon.PATH_RGBA["red"] if left <= 10 else neon.GOLD

    def _refresh_hud(self, animate=False):
        svc, s = self.service, self.session
        level, into, needed = svc.xp_progress()
        frac = 1.0 if needed == 0 else into / needed
        self.player_label.text = f"LV {level}"
        if animate:
            self.xp_bar.animate_to(frac)
            self.coin_label.count_to(svc.coins)
        else:
            self.xp_bar.fraction = frac
            self.coin_label.value = svc.coins
        self.lives_bar.max_lives = svc.cfg.max_lives
        self.lives_bar.lives = svc.lives()
        if s is not None:
            diff = settings_for(s.difficulty).label
            self.level_label.text = f"{diff}  L{s.level}   PATHS {self._paths_done()}/{s.required_paths}"
            self.next_btn.disabled = not svc.has_next_level(s.difficulty, s.level)
            self.next_btn.opacity = 0.4 if self.next_btn.disabled else 1.0
        self._refresh_timer()
        done = set(self.manager_paths.completed_colors()) if hasattr(self, "manager_paths") else set()
        active = getattr(getattr(self, "manager_paths", None), "active", PATH_COLORS[0])
        for color, b in self.color_buttons.items():
            rgba = neon.PATH_RGBA[color]
            b.background_color = rgba if color == active else neon.dim(rgba, 0.4)
            b.text = color.upper() + ("  OK" if color in done else "")
