"""Static checks for the Android build (the APK itself needs the Android SDK, which CI provides)."""
import configparser
import json
import ssl
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def spec():
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(ROOT / "buildozer.spec")
    return cp["app"]


def test_spec_has_the_essentials(spec):
    reqs = [r.strip() for r in spec["requirements"].split(",")]
    assert "kivy==2.3.0" in reqs and "certifi" in reqs and "python3" in reqs
    assert "INTERNET" in spec["android.permissions"]
    assert spec["orientation"] == "portrait" and int(spec["android.minapi"]) >= 21
    assert (ROOT / "main.py").exists()                       # buildozer's entry point


def png_size(path):
    """(width, height) read from the PNG header: standard library only, no Pillow needed."""
    import struct
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR", f"{path} is not a PNG"
    return struct.unpack(">II", head[16:24])


def test_icon_and_presplash_exist_and_are_valid_images():
    for name in ("assets/icon.png", "assets/presplash.png"):
        w, h = png_size(ROOT / name)
        assert w == h >= 512


def test_spec_assets_point_at_real_files(spec):
    for key in ("icon.filename", "presplash.filename"):
        assert (ROOT / spec[key].replace("%(source.dir)s/", "")).exists()


def test_bundle_excludes_tests_backend_and_secrets(spec):
    excluded = {d.strip() for d in spec["source.exclude_dirs"].split(",")}
    assert {"tests", "backend", "tools", ".github", ".git"} <= excluded
    patterns = spec["source.exclude_patterns"]
    assert "*.sql" in patterns and ".env*" in patterns
    assert "json" in spec["source.include_exts"]              # config/online.json must be bundled


def test_no_secret_keys_in_anything_that_gets_bundled():
    # every bundled text file must be free of secret-key patterns
    bundled = [p for d in ("game", "interface", "config") for p in (ROOT / d).rglob("*") if p.is_file()]
    bundled += [ROOT / "main.py", ROOT / "buildozer.spec"]
    for p in bundled:
        if p.suffix in (".png", ".pyc") or "__pycache__" in p.parts or p.name == "online.json":
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        assert "sb_secret_" not in text and "service_role" not in text.replace("MAZE_SUPABASE_SERVICE_KEY", ""), p
    online = ROOT / "config" / "online.json"
    if online.exists():                                       # the player's local file: must be the PUBLIC key
        data = json.loads(online.read_text())
        assert not data["anon_key"].startswith("sb_secret_")
        assert "service_role" not in data["anon_key"]


def test_game_imports_nothing_that_android_lacks():
    banned = ("psycopg2", "requests", "numpy", "pytest")
    for d in ("game", "interface"):
        for p in (ROOT / d).rglob("*.py"):
            text = p.read_text()
            for name in banned:
                assert f"import {name}" not in text and f"from {name}" not in text, (p, name)


def test_ssl_context_uses_certifi_and_degrades_without_it(monkeypatch):
    from game.online import http
    assert isinstance(http.make_ssl_context(), ssl.SSLContext)
    import builtins
    real_import = builtins.__import__

    def no_certifi(name, *a, **k):
        if name == "certifi":
            raise ImportError("simulated: not installed")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_certifi)
    assert isinstance(http.make_ssl_context(), ssl.SSLContext)      # falls back, never crashes
    assert http.UrllibTransport()._ctx is not None


def test_back_button_navigation_map():
    from interface.navigation import back_target
    assert back_target("game") == "levels" and back_target("levels") == "menu"
    assert back_target("daily_play") == "daily" and back_target("daily") == "menu"
    assert back_target("account") == "menu"
    assert back_target("menu") is None and back_target("splash") is None     # Back closes the app here
    from interface.navigation import BACK_TARGETS
    seen = set()
    for screen in BACK_TARGETS:                                              # no loops: Back always ends at the menu
        cur, steps = screen, 0
        while cur is not None and steps < 10:
            cur, steps = back_target(cur), steps + 1
        assert cur is None and steps < 10
