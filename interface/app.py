import os
from pathlib import Path

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from game.core.config import Settings
from game.persistence.json_store import JsonProfileRepository
from game.progression.service import ProgressService
from interface.screens.gameplay import GameplayScreen
from interface.screens.level_select import LevelSelectScreen
from interface.screens.menu import MenuScreen
from interface.screens.result import DefeatScreen, VictoryScreen
from interface.screens.splash import SplashScreen
from interface.themes import neon


class MazeGameApp(App):
    title = "MAZE GAME"
    service = None

    def build(self):
        Window.clearcolor = neon.BG
        # user_data_dir is the correct writable location on Android, Windows and Linux alike
        save_dir = os.environ.get("MAZE_SAVE_DIR") or self.user_data_dir
        self.service = ProgressService(JsonProfileRepository(Path(save_dir) / "progress.json"))
        sm = ScreenManager(transition=FadeTransition(duration=0.25))
        for screen in (SplashScreen(), MenuScreen(service=self.service), LevelSelectScreen(self.service),
                       GameplayScreen(service=self.service, settings=Settings()),
                       VictoryScreen(self.service), DefeatScreen(self.service)):
            sm.add_widget(screen)
        return sm

    def on_stop(self):
        game = self.root.get_screen("game") if self.root else None
        if game is not None and game.session is not None:
            self.service.abandon(game.session)      # records play time, costs nothing
