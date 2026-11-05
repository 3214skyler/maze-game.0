"""Tiny HTTP layer on the standard library (no extra dependency to ship on Android)."""
from __future__ import annotations

import json
import socket
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from game.online.errors import NetworkError

try:
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore


class Transport(Protocol):
    def request(self, method: str, url: str, headers: Dict[str, str],
                body: Optional[Any] = None) -> Tuple[int, Any]:
        """Return (status_code, parsed_json_or_None). Raise NetworkError when unreachable."""


def make_ssl_context() -> ssl.SSLContext:
    """Android's Python has no system CA store: use certifi's bundle when it is installed."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:                                   # certifi missing/unreadable: fall back to the OS store
        return ssl.create_default_context()


class UrllibTransport:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._ctx = make_ssl_context()

    def request(self, method, url, headers, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method, headers=dict(headers))
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as resp:
                return resp.status, self._parse(resp.read())
        except urllib.error.HTTPError as exc:               # 4xx / 5xx still carry a JSON body
            return exc.code, self._parse(exc.read())
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as exc:
            raise NetworkError(str(exc)) from exc

    @staticmethod
    def _parse(raw: bytes) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
