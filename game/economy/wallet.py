"""Virtual currency. The only code allowed to change a coin balance (shop-ready: earn/spend)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from game.core.errors import InsufficientFundsError


@dataclass
class Wallet:
    balance: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    history_limit: int = 50

    def _log(self, amount: int, reason: str) -> None:
        self.history.append({"amount": amount, "reason": reason, "balance_after": self.balance})
        del self.history[:-self.history_limit]

    def earn(self, amount: int, reason: str) -> None:
        if amount < 0:
            raise ValueError("cannot earn a negative amount")
        if amount:
            self.balance += amount
            self._log(amount, reason)

    def can_afford(self, amount: int) -> bool:
        return self.balance >= amount

    def spend(self, amount: int, reason: str) -> None:
        if amount < 0:
            raise ValueError("cannot spend a negative amount")
        if amount > self.balance:
            raise InsufficientFundsError(f"need {amount} coins, have {self.balance}")
        if amount:
            self.balance -= amount
            self._log(-amount, reason)

    def to_dict(self) -> Dict[str, Any]:
        return {"balance": self.balance, "history": list(self.history)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any], history_limit: int = 50) -> "Wallet":
        balance = int(data["balance"])
        if balance < 0:
            raise ValueError("negative balance")
        history = [dict(h) for h in data.get("history", [])][-history_limit:]
        return cls(balance, history, history_limit)
