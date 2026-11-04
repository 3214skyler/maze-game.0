"""Daily challenge: same maze for everyone, fastest valid time wins. Judged by the server."""
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.scrollview import ScrollView

from game.core.config import Settings
from game.online.daily_client import DailyClient, friendly
from game.online.errors import AuthError, ServerError
from game.paths.manager import PathManager
from game.progression.daily import today_utc
from interface.components import async_task
from interface.components.maze_view import MazeView
from interface.screens.account import describe
from interface.screens.menu import neon_button
from interface.themes import neon


def fmt_ms(ms: int) -> str:
    s = ms / 1000
    return f"{int(s // 60)}:{s % 60:05.2f}"


def error_text(exc: Exception) -> str:
    return friendly(exc) if isinstance(exc, ServerError) else describe(exc)


class DailyScreen(Screen):
    def __init__(self, account, **kwargs):
        super().__init__(name="daily", **kwargs)
        self.account = account
        self.client = DailyClient(account.api) if account else None
        box = BoxLayout(orientation="vertical", padding=16, spacing=8)
        box.add_widget(Label(text="DAILY CHALLENGE", font_size="26sp", bold=True, color=neon.ACCENT,
                             size_hint_y=None, height=50))
        self.info = Label(color=neon.GOLD, size_hint_y=None, height=34, font_size="14sp")
        box.add_widget(self.info)
        self.play_btn = neon_button("PLAY TODAY'S MAZE", neon.PATH_RGBA["green"], size_hint_y=None, height=56)
        self.play_btn.bind(on_release=lambda *_: self.play())
        box.add_widget(self.play_btn)
        self.message = Label(color=(0.8, 0.85, 1, 1), size_hint_y=None, height=40, halign="center")
        self.message.bind(size=lambda w, s: setattr(w, "text_size", s))
        box.add_widget(self.message)
        self.grid = GridLayout(cols=3, spacing=4, size_hint_y=None, row_default_height=30, row_force_default=True)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.grid)
        box.add_widget(scroll)
        row = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.refresh_btn = neon_button("REFRESH", neon.PATH_RGBA["blue"])
        self.refresh_btn.bind(on_release=lambda *_: self.load_board())
        self.account_btn = neon_button("ACCOUNT", neon.GOLD)
        self.account_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "account"))
        back = neon_button("BACK", neon.ACCENT)
        back.bind(on_release=lambda *_: setattr(self.manager, "current", "menu"))
        for b in (self.refresh_btn, self.account_btn, back):
            row.add_widget(b)
        box.add_widget(row)
        self.add_widget(box)

    def on_enter(self, *_):
        self.info.text = f"{today_utc().isoformat()} (UTC)   same maze for every player"
        if self.account is None:
            self.message.text = "Online features are not configured in this build."
            self.play_btn.disabled = self.refresh_btn.disabled = True
            return
        signed = self.account.signed_in and bool(self.account.username)
        self.play_btn.disabled = not signed
        self.message.text = "" if signed else "Sign in (and pick a username) to play and appear on the board."
        self.load_board()

    def load_board(self):
        if self.client is None:
            return
        async_task.run_async(lambda: self.client.leaderboard(), self._show_board,
                             lambda exc: setattr(self.message, "text", error_text(exc)))

    def _show_board(self, rows):
        g = self.grid
        g.clear_widgets()
        if not rows:
            g.add_widget(Label(text="No times yet today - be the first!", color=neon.ACCENT))
            g.add_widget(Label()); g.add_widget(Label())
            return
        for r in rows:
            color = neon.GOLD if r.is_me else (0.85, 0.9, 1, 1)
            g.add_widget(Label(text=f"#{r.rank}", color=color, bold=r.is_me, size_hint_x=0.2))
            g.add_widget(Label(text=r.username, color=color, bold=r.is_me))
            g.add_widget(Label(text=fmt_ms(r.elapsed_ms), color=color, bold=r.is_me, size_hint_x=0.3))

    def play(self):
        self.play_btn.disabled = True
        self.message.text = "Starting..."

        def failed(exc):
            self.play_btn.disabled = False
            self.message.text = error_text(exc)

        def started(run):
            self.play_btn.disabled = False
            self.message.text = ""
            self.manager.get_screen("daily_play").begin(run)
            self.manager.current = "daily_play"

        async_task.run_async(self.client.start, started, failed)


class DailyPlayScreen(Screen):
    def __init__(self, account, settings=None, **kwargs):
        super().__init__(name="daily_play", **kwargs)
        self.client = DailyClient(account.api) if account else None
        self.settings = settings or Settings()
        self.run = None
        self.paths = None
        self.elapsed = 0.0
        self._clock = None
        self.submitted = False
        root = BoxLayout(orientation="vertical", padding=8, spacing=6)
        top = BoxLayout(size_hint_y=None, height=44, spacing=6)
        back = neon_button("BACK", neon.ACCENT, size_hint_x=None, width=80)
        back.bind(on_release=lambda *_: self.leave())
        self.title = Label(text="DAILY", color=neon.ACCENT, bold=True)
        self.timer = Label(text="0:00.0", color=neon.GOLD, bold=True, font_size="22sp", size_hint_x=None, width=110)
        for w in (back, self.title, self.timer):
            top.add_widget(w)
        root.add_widget(top)
        from game.maze.generators import generate
        placeholder = generate(4, 4, seed=1)
        self.view = MazeView(placeholder, PathManager(placeholder), self.settings)
        self.view.disabled = True
        self.view.on_completed = lambda _c: self.finish()
        root.add_widget(self.view)
        self.status = Label(size_hint_y=None, height=48, color=(0.8, 0.85, 1, 1), halign="center", valign="middle")
        self.status.bind(size=lambda w, s: setattr(w, "text_size", s))
        root.add_widget(self.status)
        bar = BoxLayout(size_hint_y=None, height=52, spacing=8)
        self.reset_btn = neon_button("RESET", neon.GOLD)
        self.reset_btn.bind(on_release=lambda *_: self.reset())
        self.board_btn = neon_button("LEADERBOARD", neon.PATH_RGBA["blue"])
        self.board_btn.bind(on_release=lambda *_: setattr(self.manager, "current", "daily"))
        bar.add_widget(self.reset_btn)
        bar.add_widget(self.board_btn)
        root.add_widget(bar)
        self.add_widget(root)

    def begin(self, run):
        self.run, self.submitted, self.elapsed = run, False, 0.0
        self.paths = PathManager(run.maze)
        self.view.set_maze(run.maze, self.paths)
        self.view.disabled = False
        self.title.text = f"DAILY {run.day.isoformat()}"
        self.status.text = "Draw the blue path from start to exit. The clock is already running!"
        self.timer.text = "0:00.0"

    def on_enter(self, *_):
        self._clock = Clock.schedule_interval(self._tick, 0.1)

    def on_leave(self, *_):
        if self._clock:
            self._clock.cancel()
            self._clock = None

    def _tick(self, dt):
        if self.run and not self.submitted:
            self.elapsed += dt
            self.timer.text = fmt_ms(int(self.elapsed * 1000))[:-1]    # display only; the SERVER measures

    def reset(self):
        if self.paths and not self.submitted:
            self.paths.reset("blue")
            self.view.refresh()

    def leave(self):
        self.manager.current = "daily"

    def finish(self):
        if self.submitted or self.run is None:
            return
        self.submitted = True
        self.view.disabled = True
        cells = list(self.paths.path("blue").cells)
        self.status.text = "Submitting to the server..."

        def done(res):
            if res.accepted:
                self.status.text = f"RANK #{res.rank}   your time {fmt_ms(res.elapsed_ms)}" \
                                   f"   (best {fmt_ms(res.best_ms)})"
            else:
                self.status.text = f"Run rejected: {res.message}"

        def failed(exc):
            self.status.text = f"Could not submit: {error_text(exc)}"

        async_task.run_async(lambda: self.client.submit(self.run, cells), done, failed)
