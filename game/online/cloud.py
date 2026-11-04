"""Local-first cloud save. The local file is always written first; the cloud copy is pushed in the
background so a slow network can never freeze the game.

Conflict rule (simple and predictable): the copy with MORE XP wins. XP never decreases, so it is a
safe "most progress" marker. When the cloud copy is ahead it replaces the local one on the next load.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from game.online.api import ApiClient
from game.online.errors import OnlineError, ServerError
from game.persistence.repository import ProfileRepository


def _xp(data: Optional[Dict[str, Any]]) -> int:
    try:
        return int((data or {}).get("xp", 0))
    except (TypeError, ValueError):
        return 0


class CloudRepository:
    def __init__(self, local: ProfileRepository, synchronous: bool = False):
        self.local = local
        self.synchronous = synchronous          # tests: push inline instead of in a thread
        self.api: Optional[ApiClient] = None
        self.version = 0
        self.status = "local"                   # local | synced | offline | cloud_newer | error:<code>
        self._lock = threading.Lock()
        self._pending: Optional[Dict[str, Any]] = None
        self._running = False
        self.cloud_newer: Optional[Dict[str, Any]] = None

    # --- account attach/detach -------------------------------------------------------
    def attach(self, api: ApiClient) -> None:
        self.api = api
        self.status = "offline"

    def detach(self) -> None:
        self.api, self.version, self.cloud_newer = None, 0, None
        self.status = "local"

    # --- ProfileRepository -------------------------------------------------------------
    def load(self) -> Optional[Dict[str, Any]]:
        data = self.local.load()
        if self.api is None:
            return data
        try:
            cloud = self.api.rpc("load_progress")
        except OnlineError as exc:
            self.status = "offline" if exc.__class__.__name__ == "NetworkError" else f"error:{exc}"
            return data
        if not cloud:                                        # nothing in the cloud yet: upload ours
            self.version = 0
            if data is not None:
                self._schedule(data)
            else:
                self.status = "synced"
            return data
        self.version = int(cloud["version"])
        self.cloud_newer = None
        if _xp(cloud["data"]) > _xp(data):                   # cloud has more progress: adopt it locally
            try:
                self.local.save(cloud["data"])
            except Exception:
                pass
            self.status = "synced"
            return cloud["data"]
        if _xp(data) > _xp(cloud["data"]):
            self._schedule(data)
        else:
            self.status = "synced"
        return data

    def save(self, data: Dict[str, Any]) -> None:
        self.local.save(data)                                # raises SaveError if the disk write fails
        if self.api is not None:
            self._schedule(data)

    def discard_corrupt(self) -> None:
        self.local.discard_corrupt()

    # --- background push --------------------------------------------------------------------
    def _schedule(self, data: Dict[str, Any]) -> None:
        if self.synchronous:
            self._push(data)
            return
        with self._lock:
            self._pending = data                              # only the newest state matters
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        while True:
            with self._lock:
                data, self._pending = self._pending, None
                if data is None:
                    self._running = False
                    return
            self._push(data)

    def _push(self, data: Dict[str, Any], retry: bool = True) -> None:
        api = self.api
        if api is None or self.cloud_newer is not None:
            return                      # the cloud is ahead: never push over it, wait for the next load()
        try:
            self.version = int(api.rpc("save_progress", {"p_data": data, "p_expected_version": self.version}))
            self.status = "synced"
        except ServerError as exc:
            if exc.code in ("version_conflict", "xp_regression"):
                self._resolve_conflict(data, retry and exc.code == "version_conflict")
            else:
                self.status = f"error:{exc.code}"
        except OnlineError as exc:
            self.status = "offline" if exc.__class__.__name__ == "NetworkError" else f"error:{exc}"

    def _resolve_conflict(self, data: Dict[str, Any], retry: bool) -> None:
        try:
            cloud = self.api.rpc("load_progress")
        except OnlineError:
            self.status = "offline"
            return
        if not cloud:
            self.version = 0
        else:
            if _xp(cloud["data"]) > _xp(data):               # another device is ahead: do not overwrite it
                self.cloud_newer = cloud["data"]             # (keep the old version: pushes stay blocked)
                self.status = "cloud_newer"
                return
            self.version = int(cloud["version"])
        if retry:
            self._push(data, retry=False)
