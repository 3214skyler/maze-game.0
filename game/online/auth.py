"""Supabase Auth (GoTrue) over REST: sign up, sign in, refresh. Sessions are kept in a local file."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from game.online.config import OnlineConfig
from game.online.errors import AuthError
from game.online.http import Transport


@dataclass
class Session:
    access_token: str
    refresh_token: str
    expires_at: float
    user_id: str

    def expiring(self, now: float, margin: float = 60.0) -> bool:
        return now >= self.expires_at - margin

    def to_dict(self) -> Dict[str, Any]:
        return {"access_token": self.access_token, "refresh_token": self.refresh_token,
                "expires_at": self.expires_at, "user_id": self.user_id}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Session":
        return cls(str(d["access_token"]), str(d["refresh_token"]), float(d["expires_at"]), str(d["user_id"]))

    @classmethod
    def from_token_response(cls, data: Dict[str, Any], now: float) -> "Session":
        return cls(data["access_token"], data["refresh_token"],
                   now + float(data.get("expires_in", 3600)), data["user"]["id"])


class SessionStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> Optional[Session]:
        try:
            return Session.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save(self, session: Session) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(session.to_dict()), encoding="utf-8")
            try:
                os.chmod(tmp, 0o600)             # the refresh token is a credential
            except OSError:
                pass
            os.replace(tmp, self.path)
        except OSError:
            pass                                 # not being able to remember the login is not fatal

    def clear(self) -> None:
        try:
            self.path.unlink()
        except OSError:
            pass


def _message(body: Any, status: int) -> str:
    if isinstance(body, dict):
        for key in ("msg", "error_description", "message", "error"):
            if body.get(key):
                return str(body[key])
    return f"authentication failed (HTTP {status})"


class AuthClient:
    def __init__(self, config: OnlineConfig, transport: Transport, clock: Callable[[], float] = time.time):
        self.config, self.transport, self.clock = config, transport, clock

    def _headers(self) -> Dict[str, str]:
        return {"apikey": self.config.anon_key, "Content-Type": "application/json"}

    def _call(self, path: str, body: Dict[str, Any]):
        return self.transport.request("POST", f"{self.config.url}/auth/v1/{path}", self._headers(), body)

    def sign_up(self, email: str, password: str) -> Optional[Session]:
        """Returns a Session, or None when the project requires e-mail confirmation first."""
        status, body = self._call("signup", {"email": email, "password": password})
        if status >= 400:
            raise AuthError(_message(body, status))
        if isinstance(body, dict) and body.get("access_token"):
            return Session.from_token_response(body, self.clock())
        return None

    def sign_in(self, email: str, password: str) -> Session:
        status, body = self._call("token?grant_type=password", {"email": email, "password": password})
        if status >= 400 or not isinstance(body, dict) or not body.get("access_token"):
            raise AuthError(_message(body, status))
        return Session.from_token_response(body, self.clock())

    def refresh(self, session: Session) -> Session:
        status, body = self._call("token?grant_type=refresh_token", {"refresh_token": session.refresh_token})
        if status >= 400 or not isinstance(body, dict) or not body.get("access_token"):
            raise AuthError(_message(body, status))
        return Session.from_token_response(body, self.clock())
