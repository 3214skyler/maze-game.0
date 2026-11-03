"""Small reusable visual effects (floating text, screen flash). No game logic."""
from kivy.animation import Animation
from kivy.graphics import Color, Rectangle
from kivy.properties import NumericProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget


def float_text(layer, text, rgba, center, size="22sp", rise=90, duration=1.0):
    """Show `text` at `center` (window coords of `layer`), drift upward and fade out."""
    lbl = Label(text=text, color=rgba, bold=True, font_size=size, size_hint=(None, None))
    lbl.texture_update()
    lbl.size = lbl.texture_size
    lbl.center = center
    layer.add_widget(lbl)
    anim = Animation(y=lbl.y + rise, opacity=0, duration=duration, t="out_quad")
    anim.bind(on_complete=lambda *_: layer.remove_widget(lbl))
    anim.start(lbl)
    return lbl


class FlashLayer(Widget):
    """Full-size coloured overlay used for a quick damage / success flash."""
    alpha = NumericProperty(0.0)

    def __init__(self, rgba, **kwargs):
        super().__init__(**kwargs)
        with self.canvas:
            self._color = Color(rgba[0], rgba[1], rgba[2], 0)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync, alpha=self._sync)

    def _sync(self, *_):
        self._rect.pos, self._rect.size = self.pos, self.size
        self._color.a = self.alpha


def flash(layer, rgba, peak=0.35, duration=0.5):
    fl = FlashLayer(rgba, size_hint=(1, 1))
    layer.add_widget(fl)
    anim = Animation(alpha=peak, duration=0.08) + Animation(alpha=0, duration=duration)
    anim.bind(on_complete=lambda *_: layer.remove_widget(fl))
    anim.start(fl)


def pulse(widget, scale_opacity=0.3, duration=0.18, times=3):
    """Blink a widget's opacity a few times."""
    anim = Animation(opacity=scale_opacity, duration=duration) + Animation(opacity=1.0, duration=duration)
    for _ in range(times - 1):
        anim += Animation(opacity=scale_opacity, duration=duration) + Animation(opacity=1.0, duration=duration)
    anim.start(widget)
