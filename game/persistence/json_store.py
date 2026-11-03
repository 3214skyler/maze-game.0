"""Local JSON save file: atomic writes, schema version, corrupt-file quarantine."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from game.core.errors import SaveError

SCHEMA_VERSION = 1


def default_save_path() -> Path:
    base = os.environ.get("MAZE_SAVE_DIR")
    return (Path(base) if base else Path.home() / ".maze-game") / "progress.json"


class JsonProfileRepository:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else default_save_path()
        self.last_load_error: Optional[str] = None

    def load(self) -> Optional[Dict[str, Any]]:
        self.last_load_error = None
        if not self.path.exists():
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION \
                    or not isinstance(payload.get("profile"), dict):
                raise ValueError("unrecognised save format")
            return payload["profile"]
        except (OSError, ValueError) as exc:        # json.JSONDecodeError is a ValueError
            self.last_load_error = f"{type(exc).__name__}: {exc}"
            self.discard_corrupt()
            return None

    def save(self, data: Dict[str, Any]) -> None:
        payload = {"schema_version": SCHEMA_VERSION, "saved_at": time.time(), "profile": data}
        tmp_name = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(dir=str(self.path.parent), prefix=".progress-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)          # atomic: never a half-written save
        except (OSError, TypeError, ValueError) as exc:
            if tmp_name and os.path.exists(tmp_name):
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
            raise SaveError(f"could not write {self.path}: {exc}") from exc

    def discard_corrupt(self) -> None:
        if not self.path.exists():
            return
        target = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
        try:
            os.replace(self.path, target)
        except OSError:
            pass
