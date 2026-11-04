"""Where the game finds its Supabase project. Nothing secret is stored in the source code.

The URL and the *anon* key are public by design (Row Level Security protects the data); the
service-role key must NEVER be placed here — it only exists in the publisher script's environment.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional


@dataclass(frozen=True)
class OnlineConfig:
    url: str
    anon_key: str

    def __post_init__(self):
        if not (self.url.startswith("https://") or self.url.startswith("http://localhost")
                or self.url.startswith("http://127.0.0.1")):
            raise ValueError("Supabase URL must use https")
        if not self.anon_key:
            raise ValueError("missing anon key")
        object.__setattr__(self, "url", self.url.rstrip("/"))

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> Optional["OnlineConfig"]:
        env = os.environ if env is None else env
        url, key = env.get("MAZE_SUPABASE_URL"), env.get("MAZE_SUPABASE_ANON_KEY")
        return cls(url, key) if url and key else None

    @classmethod
    def from_file(cls, path: Path) -> Optional["OnlineConfig"]:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return cls(data["url"], data["anon_key"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @classmethod
    def load(cls, *dirs: Path) -> Optional["OnlineConfig"]:
        """Environment first, then `online.json` in each given folder. None => offline-only mode."""
        found = cls.from_env()
        for d in dirs:
            if found:
                break
            found = cls.from_file(Path(d) / "online.json")
        return found
