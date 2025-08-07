"""
Monitoring and Alert System for Advanced Trading Bot

This module provides intelligent monitoring and alerting capabilities including:
- Market volatility detection and alerts
- Exceptional coin performance notifications  
- Trading frequency monitoring with alerts
- API error tracking and notifications

Created: 2025-08-05
"""

from .base import MonitoringService
from .volatility_detector import VolatilityDetector
from .performance_analyzer import PerformanceAnalyzer
from .trading_frequency_monitor import TradingFrequencyMonitor
from .api_error_tracker import APIErrorTracker
from .portfolio_change_monitor import PortfolioChangeMonitor
from .models import *

__all__ = [
    'MonitoringService',
    'VolatilityDetector',
    'PerformanceAnalyzer',
    'TradingFrequencyMonitor',
    'APIErrorTracker',
    'PortfolioChangeMonitor',
]