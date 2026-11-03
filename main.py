"""MAZE GAME entry point (desktop and Android via Buildozer)."""
from kivy.config import Config

Config.set("graphics", "width", "480")
Config.set("graphics", "height", "820")
Config.set("input", "mouse", "mouse,disable_multitouch")  # no red multitouch dots from right click

from interface.app import MazeGameApp  # noqa: E402  (must come after Config)

if __name__ == "__main__":
    MazeGameApp().run()
