from datetime import datetime
from typing import Callable, Dict, List, Optional


class AlertManager:
    """Centralized alerting system for monitoring and notifications."""

    def __init__(
        self,
        notifier: Callable[[str, str], None],
        *,
        volatility_threshold: float = 0.05,
        exceptional_change: float = 0.1,
        trade_frequency_threshold: float = 10.0,
        api_error_threshold: int = 5,
        portfolio_change_threshold: float = 0.1,
        rate_limit_seconds: int = 60,
    ) -> None:
        self.notifier = notifier
        self.volatility_threshold = volatility_threshold
        self.exceptional_change = exceptional_change
        self.trade_frequency_threshold = trade_frequency_threshold
        self.api_error_threshold = api_error_threshold
        self.portfolio_change_threshold = portfolio_change_threshold
        self.rate_limit_seconds = rate_limit_seconds

        self._last_alert: Dict[str, datetime] = {}
        self._api_error_count = 0
        self._portfolio_value: Optional[float] = None

    # ------------------------------------------------------------------
    # Core alert helper
    # ------------------------------------------------------------------
    def _should_alert(self, key: str, priority: str) -> bool:
        """Return True if an alert should be emitted for the given key."""
        if priority == "critical":
            return True

        last = self._last_alert.get(key)
        now = datetime.utcnow()
        if last is None or (now - last).total_seconds() >= self.rate_limit_seconds:
            self._last_alert[key] = now
            return True
        return False

    def _alert(self, message: str, *, priority: str = "info", key: Optional[str] = None) -> None:
        key = key or message
        if self._should_alert(key, priority):
            self.notifier(message, priority)

    # ------------------------------------------------------------------
    # 8.1 Intelligent Alert System
    # ------------------------------------------------------------------
    def check_market_volatility(self, prices: List[float], symbol: str) -> None:
        """Emit alert when price range exceeds configured volatility threshold."""
        if len(prices) < 2:
            return
        low, high = min(prices), max(prices)
        if low == 0:
            return
        change = (high - low) / low
        if change >= self.volatility_threshold:
            self._alert(
                f"{symbol} volatility {change:.1%}",
                priority="warning",
                key=f"volatility:{symbol}",
            )

    def notify_coin_performance(self, symbol: str, change_pct: float) -> None:
        """Notify when a coin moves exceptionally."""
        if abs(change_pct) >= self.exceptional_change:
            direction = "up" if change_pct > 0 else "down"
            self._alert(
                f"{symbol} moved {direction} {change_pct:.1%}",
                priority="warning",
                key=f"performance:{symbol}",
            )

    def monitor_trade_frequency(self, trade_times: List[datetime]) -> None:
        """Alert when trade frequency exceeds threshold trades per hour."""
        if len(trade_times) < 2:
            return
        start, end = min(trade_times), max(trade_times)
        hours = (end - start).total_seconds() / 3600
        if hours == 0:
            return
        freq = len(trade_times) / hours
        if freq >= self.trade_frequency_threshold:
            self._alert(
                f"High trading frequency {freq:.2f}/hr",
                priority="warning",
                key="trade_frequency",
            )

    def track_api_error(self, error: Exception) -> None:
        """Track API errors and emit critical alert when threshold exceeded."""
        self._api_error_count += 1
        if self._api_error_count >= self.api_error_threshold:
            self._alert(
                f"API errors exceeded threshold: {self._api_error_count}",
                priority="critical",
                key="api_errors",
            )
            self._api_error_count = 0

    # ------------------------------------------------------------------
    # 8.2 Portfolio Change Monitoring
    # ------------------------------------------------------------------
    def check_portfolio_change(self, current_value: float) -> None:
        """Detect 10% portfolio value changes and notify with suggestion."""
        if self._portfolio_value is None:
            self._portfolio_value = current_value
            return
        if self._portfolio_value == 0:
            self._portfolio_value = current_value
            return

        change = (current_value - self._portfolio_value) / self._portfolio_value
        if abs(change) >= self.portfolio_change_threshold:
            suggestion = (
                "consider rebalancing" if change > 0 else "review positions"
            )
            self._alert(
                f"Portfolio value changed {change:.1%}, {suggestion}",
                priority="warning",
                key="portfolio_change",
            )
            self._portfolio_value = current_value

    # Utility for tests
    def reset_rate_limits(self) -> None:
        self._last_alert.clear()
