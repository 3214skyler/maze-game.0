from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from interface.themes import neon


def neon_button(text, rgba, **kwargs):
    return Button(text=text, background_normal="", background_color=rgba, color=(0.03, 0.04, 0.07, 1),
                  bold=True, **kwargs)


class MenuScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(name="menu", **kwargs)
        box = BoxLayout(orientation="vertical", padding=40, spacing=16)
        box.add_widget(Label(text="MAZE GAME", font_size="40sp", bold=True, color=neon.ACCENT, size_hint_y=2))
        play = neon_button("PLAY  -  CLASSIC", neon.PATH_RGBA["blue"], size_hint_y=None, height=64)
        play.bind(on_release=self._play)
        quit_ = neon_button("QUIT", neon.PATH_RGBA["red"], size_hint_y=None, height=56)
        quit_.bind(on_release=lambda *_: App.get_running_app().stop())
        box.add_widget(play)
        box.add_widget(quit_)
        box.add_widget(Label(size_hint_y=1))
        self.add_widget(box)

    def _play(self, *_):
        self.manager.get_screen("game").start_level(1)
        self.manager.current = "game"
