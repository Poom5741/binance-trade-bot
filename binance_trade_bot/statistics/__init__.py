"""
Statistics Manager for performance tracking.

This module provides comprehensive statistics calculation engine for trading performance
including daily, weekly, and total performance calculations, profit/loss tracking,
win/loss ratio, trade frequency metrics, and advanced metrics like ROI, Sharpe ratio,
and maximum drawdown.
"""

from .base import StatisticsBase

# Models require SQLAlchemy; they may be unavailable in some test environments.
try:  # pragma: no cover
    from .models import Statistics, DailyPerformance, WeeklyPerformance, TotalPerformance
except Exception:  # pragma: no cover
    Statistics = DailyPerformance = WeeklyPerformance = TotalPerformance = None  # type: ignore

from .calculators import (
    DailyPerformanceCalculator,
    WeeklyPerformanceCalculator,
    TotalPerformanceCalculator,
    ProfitLossCalculator,
    WinLossCalculator,
    AdvancedMetricsCalculator,
)
from .manager import StatisticsManager

__all__ = [
    "StatisticsBase",
    "Statistics",
    "DailyPerformance",
    "WeeklyPerformance",
    "TotalPerformance",
    "DailyPerformanceCalculator",
    "WeeklyPerformanceCalculator",
    "TotalPerformanceCalculator",
    "ProfitLossCalculator",
    "WinLossCalculator",
    "AdvancedMetricsCalculator",
    "StatisticsManager",
]