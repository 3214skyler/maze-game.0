# MAZE GAME

Futuristic neon maze puzzle: draw **three independent paths** (blue, green, red) from the entrance to the exit
with a finger or mouse. Python 3 + Kivy (Android / Windows / Linux); a TypeScript/Phaser web client is planned.

![gameplay](docs/screenshots/gameplay.png)

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py              # needs a display
MAZE_LOW_FX=1 python main.py   # disable glow for low-end devices
```

Controls — mouse/touch: press near the head of the active path and drag. Keyboard: `1` `2` `3` choose colour,
arrow keys step, `R` reset the active path, `N` next level, `Esc` menu.

Headless (CI / Codespaces): `xvfb-run -a python main.py`.

## Test

```bash
KIVY_NO_ARGS=1 python -m pytest -q
```

## Architecture (Phase 1–3 foundation)

| Package | Responsibility | Depends on Kivy? |
|---|---|---|
| `game/maze` | `Maze`, seeded generators (backtracker, Prim, Kruskal), BFS solver + hints | no |
| `game/paths` | `Path` rules (walls, self-crossing, backtracking, completion), `PathManager` (3 independent paths, per-path reset/serialisation) | no |
| `game/input` | `PointerEvent`, `Viewport`, `DrawingController` — device-independent drawing | no |
| `game/progression` | deterministic level configs | no |
| `interface/` | Kivy screens, `MazeView` renderer, neon theme | yes |

Game logic never imports rendering code; the UI only translates Kivy touches into `PointerEvent`s.

## Roadmap

See the specification phases 4–9: lives and game modes, effects and audio, Supabase (auth, RLS, leaderboards,
server-side economy), monetisation (AdMob, billing, premium), Android/Web builds, release hardening.
Secrets belong in `.env` (see `.env.example`) and **never** in client code.
