"""Storage contract. A future SupabaseRepository only has to implement these three methods."""
from __future__ import annotations

from typing import Any, Dict, Optional

try:                                   # Python 3.8+
    from typing import Protocol
except ImportError:                    # pragma: no cover
    Protocol = object  # type: ignore


class ProfileRepository(Protocol):
    def load(self) -> Optional[Dict[str, Any]]:
        """Return the stored profile dict, or None when nothing (usable) is stored."""

    def save(self, data: Dict[str, Any]) -> None:
        """Persist the profile dict. Raise SaveError on failure."""

    def discard_corrupt(self) -> None:
        """Set aside stored data that could not be interpreted, so it is not overwritten blindly."""


class MemoryRepository:
    """In-memory repository for tests and previews."""

    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self.data = data

    def load(self) -> Optional[Dict[str, Any]]:
        return self.data

    def save(self, data: Dict[str, Any]) -> None:
        self.data = data

    def discard_corrupt(self) -> None:
        self.data = None
