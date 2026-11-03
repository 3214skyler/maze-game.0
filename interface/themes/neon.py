"""Kivy-ready neon theme values derived from the shared palette."""
from game.core.config import COLORS, hex_to_rgba

BG = hex_to_rgba(COLORS["bg_black"])
PANEL = hex_to_rgba(COLORS["bg_navy"])
WALL = hex_to_rgba(COLORS["purple"])
ACCENT = hex_to_rgba(COLORS["cyan"])
GOLD = hex_to_rgba(COLORS["gold"])
PATH_RGBA = {name: hex_to_rgba(COLORS[name]) for name in ("blue", "green", "red")}


def dim(rgba, factor=0.35):
    return (rgba[0], rgba[1], rgba[2], rgba[3] * factor)
