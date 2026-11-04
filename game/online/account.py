"""Player account facade used by the UI: sign up / in / out and the public username."""
from __future__ import annotations

import time
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from game.online.api import ApiClient
from game.online.auth import AuthClient, SessionStore
from game.online.config import OnlineConfig
from game.online.errors import AuthError, OnlineError, ServerError
from game.online.http import Transport, UrllibTransport


class AccountStatus(str, Enum):
    SIGNED_IN = "signed_in"
    CONFIRM_EMAIL = "confirm_email"      # the project requires e-mail confirmation before signing in
    NEEDS_USERNAME = "needs_username"    # authenticated, but no public profile yet


USERNAME_ERRORS = {
    "invalid_username": "Username must be 3-20 letters, digits or underscore.",
    "username_taken": "That username is already taken.",
    "profile_exists": "This account already has a username.",
}


class Account:
    def __init__(self, config: OnlineConfig, user_dir: Path, transport: Optional[Transport] = None,
                 clock: Callable[[], float] = time.time):
        self.config = config
        transport = transport or UrllibTransport()
        self.store = SessionStore(Path(user_dir) / "session.json")
        self.auth = AuthClient(config, transport, clock)
        self.api = ApiClient(config, transport, self.auth, self.store, self.store.load(), clock)
        self.username: Optional[str] = None

    @property
    def signed_in(self) -> bool:
        return self.api.signed_in

    def sign_up(self, email: str, password: str, username: str) -> AccountStatus:
        session = self.auth.sign_up(email, password)
        if session is None:
            return AccountStatus.CONFIRM_EMAIL
        self.api.set_session(session)
        self.set_username(username)
        return AccountStatus.SIGNED_IN

    def sign_in(self, email: str, password: str) -> AccountStatus:
        self.api.set_session(self.auth.sign_in(email, password))
        return self.refresh_profile()

    def refresh_profile(self) -> AccountStatus:
        profile = self.api.rpc("get_my_profile")
        self.username = profile.get("username") if isinstance(profile, dict) else None
        return AccountStatus.SIGNED_IN if self.username else AccountStatus.NEEDS_USERNAME

    def set_username(self, username: str) -> None:
        try:
            self.api.rpc("create_profile", {"p_username": username})
        except ServerError as exc:
            raise ServerError(exc.code, USERNAME_ERRORS.get(exc.code, str(exc))) from exc
        self.username = username

    def sign_out(self) -> None:
        self.api.set_session(None)
        self.username = None
