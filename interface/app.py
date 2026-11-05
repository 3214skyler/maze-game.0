import os
from pathlib import Path

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.screenmanager import FadeTransition, ScreenManager

from game.core.config import Settings
from game.online.account import Account
from game.online.config import OnlineConfig
from game.online.cloud import CloudRepository
from game.persistence.json_store import JsonProfileRepository
from game.progression.service import ProgressService
from interface.components.async_task import run_async
from interface.navigation import back_target
from interface.screens.account import AccountScreen
from interface.screens.daily import DailyPlayScreen, DailyScreen
from interface.screens.gameplay import GameplayScreen
from interface.screens.level_select import LevelSelectScreen
from interface.screens.menu import MenuScreen
from interface.screens.result import DefeatScreen, VictoryScreen
from interface.screens.splash import SplashScreen
from interface.themes import neon


class MazeGameApp(App):
    title = "MAZE GAME"
    service = None
    account = None
    repo = None

    def build(self):
        Window.clearcolor = neon.BG
        Window.softinput_mode = "below_target"          # Android: keep the focused text field above the keyboard
        Window.bind(on_keyboard=self._on_back)
        # user_data_dir is the correct writable location on Android, Windows and Linux alike
        data_dir = Path(os.environ.get("MAZE_SAVE_DIR") or self.user_data_dir)
        self.repo = CloudRepository(JsonProfileRepository(data_dir / "progress.json"))
        self.service = ProgressService(self.repo)                    # starts from the local save, instantly
        config = OnlineConfig.load(data_dir, Path(__file__).resolve().parent.parent / "config")
        self.account = Account(config, data_dir) if config else None  # None => offline/guest-only build
        if self.account and self.account.signed_in:
            self.repo.attach(self.account.api)
            # fetch the cloud copy in the background; apply it on the UI thread when it arrives
            run_async(self.repo.load, self.service.reload)

        sm = ScreenManager(transition=FadeTransition(duration=0.25))
        for screen in (SplashScreen(), MenuScreen(service=self.service, account=self.account),
                       LevelSelectScreen(self.service),
                       GameplayScreen(service=self.service, settings=Settings()),
                       VictoryScreen(self.service), DefeatScreen(self.service),
                       AccountScreen(self.account, self.repo, self.service),
                       DailyScreen(self.account), DailyPlayScreen(self.account)):
            sm.add_widget(screen)
        return sm

    def _on_back(self, _window, key, *_args):
        """Android Back button / Esc: go back one screen; on the menu let the system close the app."""
        if key != 27 or self.root is None:
            return False
        target = back_target(self.root.current)
        if target is None:
            return False
        if self.root.current == "game":
            self.root.get_screen("game").leave(target)     # abandoning a level is free
        else:
            self.root.current = target
        return True

    def on_pause(self):
        return True            # Android: stay alive in the background instead of being killed on app switch

    def on_resume(self):
        pass

    def on_stop(self):
        game = self.root.get_screen("game") if self.root else None
        if game is not None and game.session is not None:
            self.service.abandon(game.session)      # records play time, costs nothing
