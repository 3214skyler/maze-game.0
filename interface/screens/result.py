"""Victory and defeat screens. They display a LevelResult and route the player onwards."""
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from game.core.errors import ProgressError
from game.progression.difficulty import settings_for
from game.progression.session import DefeatReason
from interface.components.hud import CountLabel, LivesBar, format_seconds
from interface.screens.menu import neon_button
from interface.themes import neon

REASONS = {DefeatReason.TIME_UP: "TIME RAN OUT"}


def _label(text="", rgba=(1, 1, 1, 1), size="16sp", height=30, bold=False):
    lbl = Label(text=text, color=rgba, font_size=size, bold=bold, size_hint_y=None, height=height,
                halign="center", valign="middle")
    lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
    return lbl


class _ResultScreen(Screen):
    def __init__(self, name, service, **kwargs):
        super().__init__(name=name, **kwargs)
        self.service = service
        self.result = None
        self.box = BoxLayout(orientation="vertical", padding=24, spacing=8)
        self.add_widget(self.box)

    def _game(self):
        return self.manager.get_screen("game")

    def replay(self, *_):
        r = self.result
        if r and self._game().begin(r.difficulty, r.level):
            self.manager.current = "game"
        else:
            self._refresh_extra()

    def _refresh_extra(self):
        pass


class VictoryScreen(_ResultScreen):
    def __init__(self, service, **kwargs):
        super().__init__("victory", service, **kwargs)

    def show(self, result):
        self.result = result
        b = self.box
        b.clear_widgets()
        b.add_widget(Label(size_hint_y=1))
        b.add_widget(_label("LEVEL CLEARED", neon.PATH_RGBA["green"], "32sp", 50, True))
        b.add_widget(_label(f"{settings_for(result.difficulty).label}  -  LEVEL {result.level}", neon.ACCENT))
        notes = f"TIME {format_seconds(result.elapsed)}   ERRORS {result.errors}   PATHS {result.paths_completed}/3"
        b.add_widget(_label(notes, (0.8, 0.85, 1, 1), "14sp"))
        if result.flawless:
            b.add_widget(_label("FLAWLESS", neon.GOLD, "18sp", 26, True))
        if result.new_best_time:
            b.add_widget(_label("NEW BEST TIME", neon.ACCENT, "14sp", 24))
        rw = result.rewards
        xp = CountLabel(prefix="+", suffix=" XP", color=neon.ACCENT, bold=True, font_size="28sp",
                        size_hint_y=None, height=44)
        coins = CountLabel(prefix="+", suffix=" COINS", color=neon.GOLD, bold=True, font_size="24sp",
                           size_hint_y=None, height=40)
        b.add_widget(xp)
        b.add_widget(coins)
        parts = "  ".join(f"{k} {v:+d}" for k, v in rw.xp_breakdown.items() if k != "base" or len(rw.xp_breakdown) > 1)
        b.add_widget(_label(parts, (0.6, 0.65, 0.8, 1), "11sp", 22))
        if not result.first_clear:
            b.add_widget(_label("Replay: reduced rewards", (0.6, 0.65, 0.8, 1), "12sp", 22))
        if result.level_ups:
            b.add_widget(_label(f"PLAYER LEVEL UP!  LV {result.level_ups[-1]}   +{result.level_up_coins} coins, +1 life",
                                neon.PATH_RGBA["green"], "16sp", 30, True))
        if result.unlocked_level:
            b.add_widget(_label(f"LEVEL {result.unlocked_level} UNLOCKED", neon.GOLD, "18sp", 30, True))
        if result.unlocked_difficulty:
            b.add_widget(_label("NIGHTMARE DIFFICULTY UNLOCKED", neon.PATH_RGBA["red"], "18sp", 30, True))
        b.add_widget(Label(size_hint_y=1))
        row = BoxLayout(size_hint_y=None, height=54, spacing=8)
        nxt = neon_button("NEXT LEVEL", neon.PATH_RGBA["green"])
        can_next = self.service.has_next_level(result.difficulty, result.level)
        nxt.disabled = not can_next
        nxt.opacity = 1.0 if can_next else 0.4
        nxt.bind(on_release=self._next)
        again = neon_button("REPLAY", neon.PATH_RGBA["blue"])
        again.bind(on_release=self.replay)
        row.add_widget(nxt)
        row.add_widget(again)
        b.add_widget(row)
        row2 = BoxLayout(size_hint_y=None, height=48, spacing=8)
        for text, target in (("LEVELS", "levels"), ("MENU", "menu")):
            btn = neon_button(text, neon.ACCENT)
            btn.bind(on_release=lambda _b, t=target: setattr(self.manager, "current", t))
            row2.add_widget(btn)
        b.add_widget(row2)
        xp.count_to(rw.xp)
        coins.count_to(rw.coins)

    def _next(self, *_):
        r = self.result
        if r and self._game().begin(r.difficulty, r.level + 1):
            self.manager.current = "game"


class DefeatScreen(_ResultScreen):
    def __init__(self, service, **kwargs):
        super().__init__("defeat", service, **kwargs)
        self._timer = None

    def show(self, result):
        self.result = result
        b = self.box
        b.clear_widgets()
        b.add_widget(Label(size_hint_y=1))
        b.add_widget(_label("DEFEAT", neon.PATH_RGBA["red"], "36sp", 56, True))
        b.add_widget(_label(REASONS.get(result.defeat_reason, "LEVEL FAILED"), neon.GOLD, "20sp", 32, True))
        b.add_widget(_label(f"{settings_for(result.difficulty).label}  -  LEVEL {result.level}   "
                            f"PATHS {result.paths_completed}", neon.ACCENT, "14sp"))
        b.add_widget(_label("You lost 1 life.", (0.8, 0.85, 1, 1), "16sp"))
        self.lives_bar = LivesBar(size_hint_y=None, height=34)
        self.lives_bar.max_lives = self.service.cfg.max_lives
        self.lives_bar.lives = self.service.lives()
        holder = BoxLayout(size_hint_y=None, height=34)
        holder.add_widget(Label())
        holder.add_widget(self.lives_bar)
        holder.add_widget(Label())
        b.add_widget(holder)
        self.info = _label("", (0.8, 0.85, 1, 1), "14sp", 30)
        b.add_widget(self.info)
        b.add_widget(Label(size_hint_y=1))
        self.retry = neon_button("TRY AGAIN", neon.PATH_RGBA["blue"], size_hint_y=None, height=54)
        self.retry.bind(on_release=self.replay)
        self.buy = neon_button("", neon.GOLD, size_hint_y=None, height=48)
        self.buy.bind(on_release=self._buy)
        b.add_widget(self.retry)
        b.add_widget(self.buy)
        row = BoxLayout(size_hint_y=None, height=48, spacing=8)
        for text, target in (("LEVELS", "levels"), ("MENU", "menu")):
            btn = neon_button(text, neon.ACCENT)
            btn.bind(on_release=lambda _b, t=target: setattr(self.manager, "current", t))
            row.add_widget(btn)
        b.add_widget(row)
        self._refresh_extra()

    def on_enter(self, *_):
        self._timer = Clock.schedule_interval(lambda _dt: self._refresh_extra(), 1.0)

    def on_leave(self, *_):
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _refresh_extra(self):
        if self.result is None or not hasattr(self, "retry"):
            return
        svc = self.service
        lives = svc.lives()
        self.lives_bar.lives = lives
        wait = svc.seconds_until_next_life()
        self.retry.disabled = lives <= 0
        self.retry.opacity = 0.4 if lives <= 0 else 1.0
        if lives <= 0:
            self.info.text = f"NO LIVES LEFT  -  next life in {format_seconds(wait or 0)}"
        elif wait is not None:
            self.info.text = f"{lives}/{svc.cfg.max_lives} lives  -  next in {format_seconds(wait)}"
        else:
            self.info.text = f"{lives}/{svc.cfg.max_lives} lives"
        can_buy = lives < svc.cfg.max_lives and svc.coins >= svc.cfg.life_cost_coins
        self.buy.text = f"BUY A LIFE  ({svc.cfg.life_cost_coins} coins, you have {svc.coins})"
        self.buy.disabled = not can_buy
        self.buy.opacity = 1.0 if can_buy else 0.4

    def _buy(self, *_):
        try:
            self.service.buy_life()
        except ProgressError:
            pass
        self._refresh_extra()
