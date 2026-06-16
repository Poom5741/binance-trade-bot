from abc import ABC, abstractmethod


class Exchange(ABC):
    @abstractmethod
    def position(self, coin):
        """Return dict {side, notional, entry} or None."""

    @abstractmethod
    def balance_value(self):
        """Return realized cash balance (float)."""

    @abstractmethod
    def open(self, coin, side, notional, price):
        """Open a position. side: +1 long, -1 short."""

    @abstractmethod
    def close(self, coin, price):
        """Close the position at price. Return realized price pnl (before close fee)."""
