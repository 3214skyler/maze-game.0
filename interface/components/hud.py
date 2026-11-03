"""HUD widgets: lives, XP bar, animated counters. They only display values they are given."""
from kivy.animation import Animation
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from interface.themes import neon


class CountLabel(Label):
    """Label that can count up to a value with an animation."""
    value = NumericProperty(0)
    prefix = StringProperty("")
    suffix = StringProperty("")

    def on_value(self, *_):
        self.text = f"{self.prefix}{int(round(self.value))}{self.suffix}"

    def count_to(self, target, duration=0.7):
        Animation.cancel_all(self, "value")
        Animation(value=target, duration=duration, t="out_quad").start(self)


class LivesBar(Widget):
    """Row of neon dots: filled = life available."""
    lives = NumericProperty(0)
    max_lives = NumericProperty(5)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size_hint_x = None
        self.bind(lives=self._redraw, max_lives=self._redraw, pos=self._redraw, size=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        n = int(self.max_lives)
        self.width = n * dp(24)
        self.canvas.clear()
        d = min(self.height * 0.6, dp(18))
        with self.canvas:
            for i in range(n):
                cx = self.x + dp(12) + i * dp(24)
                cy = self.center_y
                if i < int(self.lives):
                    Color(*neon.dim(neon.PATH_RGBA["red"], 0.3))
                    Ellipse(pos=(cx - d * 0.8, cy - d * 0.8), size=(d * 1.6, d * 1.6))
                    Color(*neon.PATH_RGBA["red"])
                    Ellipse(pos=(cx - d / 2, cy - d / 2), size=(d, d))
                else:
                    Color(*neon.dim(neon.PATH_RGBA["red"], 0.5))
                    Line(circle=(cx, cy, d / 2), width=1.2)


class XPBar(Widget):
    """Horizontal progress bar with a soft glow; `fraction` is 0..1 and animatable."""
    fraction = NumericProperty(0.0)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(fraction=self._redraw, pos=self._redraw, size=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        h = min(self.height, dp(10))
        y = self.center_y - h / 2
        frac = max(0.0, min(1.0, self.fraction))
        with self.canvas:
            Color(*neon.PANEL)
            Rectangle(pos=(self.x, y), size=(self.width, h))
            Color(*neon.dim(neon.ACCENT, 0.3))
            Rectangle(pos=(self.x, y - 2), size=(self.width * frac, h + 4))
            Color(*neon.ACCENT)
            Rectangle(pos=(self.x, y), size=(self.width * frac, h))

    def animate_to(self, fraction, duration=0.6):
        Animation.cancel_all(self, "fraction")
        Animation(fraction=fraction, duration=duration, t="out_quad").start(self)


def format_seconds(seconds: float) -> str:
    seconds = max(0, int(seconds + 0.999))
    return f"{seconds // 60}:{seconds % 60:02d}"
