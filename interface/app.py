from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from game.core.config import Settings
from interface.screens.gameplay import GameplayScreen
from interface.screens.menu import MenuScreen
from interface.screens.splash import SplashScreen
from interface.themes import neon


class MazeGameApp(App):
    title = "MAZE GAME"

    def build(self):
        Window.clearcolor = neon.BG
        settings = Settings()
        sm = ScreenManager(transition=FadeTransition(duration=0.25))
        sm.add_widget(SplashScreen())
        sm.add_widget(MenuScreen())
        sm.add_widget(GameplayScreen(settings=settings))
        return sm
