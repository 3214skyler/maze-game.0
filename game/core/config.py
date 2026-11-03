"""Global constants: neon palette and runtime settings. No rendering code here."""
import os
from dataclasses import dataclass, field

COLORS = {
    "bg_black": "#070A12",
    "bg_navy": "#10182B",
    "blue": "#00BFFF",
    "green": "#39FF88",
    "red": "#FF3158",
    "purple": "#A855F7",
    "cyan": "#00F5FF",
    "gold": "#FFD700",
}

# The three independent paths, in selection order (keys 1, 2, 3).
PATH_COLORS = ("blue", "green", "red")


def hex_to_rgba(value: str, alpha: float = 1.0):
    value = value.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (r, g, b, alpha)


@dataclass
class Settings:
    """Runtime options. `glow_enabled=False` is the low-end device mode."""
    glow_enabled: bool = field(default_factory=lambda: os.environ.get("MAZE_LOW_FX") != "1")
