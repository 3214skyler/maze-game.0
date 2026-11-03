from kivy.animation import Animation
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from interface.themes import neon


class SplashScreen(Screen):
    name_ = "splash"

    def __init__(self, **kwargs):
        super().__init__(name="splash", **kwargs)
        box = BoxLayout(orientation="vertical", padding=40, spacing=10)
        self.title = Label(text="MAZE GAME", font_size="44sp", bold=True, color=(*neon.ACCENT[:3], 0))
        self.sub = Label(text="three paths. one exit.", font_size="16sp", color=(*neon.GOLD[:3], 0))
        box.add_widget(self.title)
        box.add_widget(self.sub)
        self.add_widget(box)

    def on_enter(self, *_):
        Animation(color=neon.ACCENT, duration=0.8).start(self.title)
        Animation(color=neon.GOLD, duration=1.2).start(self.sub)
        self._event = Clock.schedule_once(lambda dt: setattr(self.manager, "current", "menu"), 2.0)

    def on_leave(self, *_):
        self._event.cancel()
