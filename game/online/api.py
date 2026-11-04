"""Calls the database functions (`/rest/v1/rpc/...`) with automatic token refresh."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from game.online.auth import AuthClient, Session, SessionStore
from game.online.config import OnlineConfig
from game.online.errors import AuthError, ServerError
from game.online.http import Transport


def _error_from(status: int, body: Any) -> ServerError:
    if isinstance(body, dict):
        message = str(body.get("message") or "")
        code = str(body.get("code") or "")
        if code == "42501":
            return ServerError("permission_denied", message)
        if code == "PGRST202" or status == 404:
            return ServerError("rpc_not_found", message)
        if code == "P0001" and message:               # `raise exception 'xxx'` inside our functions
            return ServerError(message, message)
        return ServerError(code or "server_error", message)
    return ServerError("server_error", f"HTTP {status}")


class ApiClient:
    def __init__(self, config: OnlineConfig, transport: Transport, auth: AuthClient,
                 store: Optional[SessionStore] = None, session: Optional[Session] = None,
                 clock: Callable[[], float] = time.time):
        self.config, self.transport, self.auth, self.store, self.clock = config, transport, auth, store, clock
        self.session = session

    @property
    def signed_in(self) -> bool:
        return self.session is not None

    def set_session(self, session: Optional[Session]) -> None:
        self.session = session
        if self.store:
            self.store.save(session) if session else self.store.clear()

    def _refresh(self) -> None:
        if self.session is None:
            raise AuthError("not signed in")
        try:
            self.set_session(self.auth.refresh(self.session))
        except AuthError:
            self.set_session(None)                    # refresh token rejected: the player must sign in again
            raise

    def _send(self, name: str, args: Dict[str, Any], public: bool):
        token = self.config.anon_key if (public and self.session is None) else self.session.access_token
        headers = {"apikey": self.config.anon_key, "Authorization": f"Bearer {token}",
                   "Content-Type": "application/json"}
        return self.transport.request("POST", f"{self.config.url}/rest/v1/rpc/{name}", headers, args)

    def rpc(self, name: str, args: Optional[Dict[str, Any]] = None, public: bool = False) -> Any:
        """`public=True` allows anonymous use (e.g. reading the leaderboard)."""
        args = args or {}
        if self.session is None and not public:
            raise AuthError("not signed in")
        if self.session is not None and self.session.expiring(self.clock()):
            self._refresh()
        status, body = self._send(name, args, public)
        if status == 401 and self.session is not None:      # token rejected: refresh once and retry
            self._refresh()
            status, body = self._send(name, args, public)
        if status == 401:
            raise AuthError("session rejected")
        if status >= 400:
            raise _error_from(status, body)
        return body
