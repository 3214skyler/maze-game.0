"""What the Android Back button (or Esc on desktop) does on each screen. Pure logic, no Kivy."""
from typing import Optional

BACK_TARGETS = {
    "game": "levels", "victory": "levels", "defeat": "levels", "levels": "menu",
    "daily_play": "daily", "daily": "menu", "account": "menu",
}


def back_target(screen: str) -> Optional[str]:
    """Screen to go back to, or None when Back should close the app (menu/splash)."""
    return BACK_TARGETS.get(screen)
