"""
Unit tests for the portfolio change monitoring system.

This module contains comprehensive tests for the PortfolioChangeMonitor class,
including data collection, analysis, alert generation, rate limiting, and
priority-based notifications.

Created: 2025-08-05
"""

import asyncio
import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from typing import Dict, List, Any

from binance_trade_bot.monitoring.portfolio_change_monitor import (
    PortfolioChangeMonitor,
    PortfolioChangeDirection
)
from binance_trade_bot.monitoring.base import AlertSeverity, AlertType, AlertStatus
from binance_trade_bot.monitoring.models import PortfolioMetric
from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger
from binance_trade_bot.notifications import NotificationHandler
from binance_trade_bot.statistics.manager import StatisticsManager


class TestPortfolioChangeMonitor(unittest.TestCase):
    """
    Test suite for PortfolioChangeMonitor class.
    """
    
    def setUp(self):
        """
        Set up test fixtures before each test method.
        """
        # Mock dependencies
        self.mock_database = Mock(spec=Database)
        self.mock_logger = Mock(spec=Logger)
        self.mock_notifications = Mock(spec=NotificationHandler)
        self.mock_statistics_manager = Mock(spec=StatisticsManager)
        
        # Mock database session
        self.mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = self.mock_session
        
        # Test configuration
        self.test_config = {
            'portfolio_change_thresholds': {
                'low': 0.05,
                'medium': 0.10,
                'high': 0.20,
                'critical': 0.30
            },
            'portfolio_change_periods': [1, 6, 24],
            'portfolio_metrics': [
                PortfolioMetric.TOTAL_VALUE_CHANGE.value,
                PortfolioMetric.ALLOCATION_CHANGE.value,
                PortfolioMetric.ROI_CHANGE.value
            ],
            'alert_cooldown_period': 60,
            'max_alerts_per_period': 3,
            'rate_limit_period': 60,
            'priority_weights': {
                'severity': 0.5,
                'frequency': 0.3,
                'impact': 0.2
            }
        }
        
        # Create monitor instance
        self.monitor = PortfolioChangeMonitor(
            database=self.mock_database,
            logger=self.mock_logger,
            notifications=self.mock_notifications,
            config=self.test_config,
            statistics_manager=self.mock_statistics_manager
        )
        
    def test_init(self):
        """
        Test PortfolioChangeMonitor initialization.
        """
        # Verify configuration is set correctly
        self.assertEqual(self.monitor.portfolio_change_thresholds, self.test_config['portfolio_change_thresholds'])
        self.assertEqual(self.monitor.portfolio_change_periods, self.test_config['portfolio_change_periods'])
        self.assertEqual(self.monitor.portfolio_metrics, self.test_config['portfolio_metrics'])
        self.assertEqual(self.monitor.alert_cooldown_period, self.test_config['alert_cooldown_period'])
        self.assertEqual(self.monitor.max_alerts_per_period, self.test_config['max_alerts_per_period'])
        self.assertEqual(self.monitor.rate_limit_period, self.test_config['rate_limit_period'])
        
    def test_determine_severity(self):
        """
        Test severity determination based on percentage change.
        """
        # Test critical threshold
        severity = self.monitor._determine_severity(0.35)  # 35%
        self.assertEqual(severity, AlertSeverity.CRITICAL)
        
        # Test high threshold
        severity = self.monitor._determine_severity(0.25)  # 25%
        self.assertEqual(severity, AlertSeverity.HIGH)
        
        # Test medium threshold
        severity = self.monitor._determine_severity(0.15)  # 15%
        self.assertEqual(severity, AlertSeverity.MEDIUM)
        
        # Test low threshold
        severity = self.monitor._determine_severity(0.07)  # 7%
        self.assertEqual(severity, AlertSeverity.LOW)
        
        # Test below threshold
        severity = self.monitor._determine_severity(0.03)  # 3%
        self.assertEqual(severity, AlertSeverity.LOW)
        
    def test_determine_severity_from_allocation(self):
        """
        Test severity determination based on allocation concentration.
        """
        # Test critical allocation
        severity = self.monitor._determine_severity_from_allocation(85.0)  # 85%
        self.assertEqual(severity, AlertSeverity.CRITICAL)
        
        # Test high allocation
        severity = self.monitor._determine_severity_from_allocation(65.0)  # 65%
        self.assertEqual(severity, AlertSeverity.HIGH)
        
        # Test medium allocation
        severity = self.monitor._determine_severity_from_allocation(55.0)  # 55%
        self.assertEqual(severity, AlertSeverity.MEDIUM)
        
        # Test low allocation
        severity = self.monitor._determine_severity_from_allocation(45.0)  # 45%
        self.assertEqual(severity, AlertSeverity.LOW)
        
    def test_determine_severity_from_roi_change(self):
        """
        Test severity determination based on ROI change.
        """
        # Test critical ROI change
        severity = self.monitor._determine_severity_from_roi_change(0.20)  # 20%
        self.assertEqual(severity, AlertSeverity.CRITICAL)
        
        # Test high ROI change
        severity = self.monitor._determine_severity_from_roi_change(0.12)  # 12%
        self.assertEqual(severity, AlertSeverity.HIGH)
        
        # Test medium ROI change
        severity = self.monitor._determine_severity_from_roi_change(0.07)  # 7%
        self.assertEqual(severity, AlertSeverity.MEDIUM)
        
        # Test low ROI change
        severity = self.monitor._determine_severity_from_roi_change(0.03)  # 3%
        self.assertEqual(severity, AlertSeverity.LOW)
        
    def test_determine_severity_from_risk_adjusted_change(self):
        """
        Test severity determination based on risk-adjusted return change.
        """
        # Test critical risk-adjusted change
        severity = self.monitor._determine_severity_from_risk_adjusted_change(0.6)  # 0.6
        self.assertEqual(severity, AlertSeverity.CRITICAL)
        
        # Test high risk-adjusted change
        severity = self.monitor._determine_severity_from_risk_adjusted_change(0.4)  # 0.4
        self.assertEqual(severity, AlertSeverity.HIGH)
        
        # Test medium risk-adjusted change
        severity = self.monitor._determine_severity_from_risk_adjusted_change(0.2)  # 0.2
        self.assertEqual(severity, AlertSeverity.MEDIUM)
        
        # Test low risk-adjusted change
        severity = self.monitor._determine_severity_from_risk_adjusted_change(0.1)  # 0.1
        self.assertEqual(severity, AlertSeverity.LOW)
        
    def test_get_suggested_actions_for_value_change_increase(self):
        """
        Test suggested actions for portfolio value increase.
        """
        # Test large increase (>20%)
        actions = self.monitor._get_suggested_actions_for_value_change(0.25, PortfolioChangeDirection.INCREASE)
        self.assertIn("Consider taking profits to lock in gains", actions)
        self.assertIn("Rebalance portfolio to maintain target allocations", actions)
        
        # Test medium increase (10-20%)
        actions = self.monitor._get_suggested_actions_for_value_change(0.15, PortfolioChangeDirection.INCREASE)
        self.assertIn("Monitor for potential overvaluation", actions)
        self.assertIn("Consider partial profit taking", actions)
        
    def test_get_suggested_actions_for_value_change_decrease(self):
        """
        Test suggested actions for portfolio value decrease.
        """
        # Test large decrease (<-20%)
        actions = self.monitor._get_suggested_actions_for_value_change(-0.25, PortfolioChangeDirection.DECREASE)
        self.assertIn("Review portfolio risk management strategy", actions)
        self.assertIn("Consider defensive positioning if market conditions have changed", actions)
        
        # Test medium decrease (-10 to -20%)
        actions = self.monitor._get_suggested_actions_for_value_change(-0.15, PortfolioChangeDirection.DECREASE)
        self.assertIn("Monitor for potential buying opportunities", actions)
        self.assertIn("Review individual coin fundamentals", actions)
        
    def test_get_suggested_actions_for_allocation_imbalance(self):
        """
        Test suggested actions for portfolio allocation imbalance.
        """
        extreme_allocations = [
            {'coin': 'BTC', 'allocation': 60.0, 'usd_value': 60000.0},
            {'coin': 'ETH', 'allocation': 30.0, 'usd_value': 30000.0}
        ]
        
        actions = self.monitor._get_suggested_actions_for_allocation_imbalance(extreme_allocations)
        self.assertIn("Consider rebalancing portfolio to reduce concentration risk", actions)
        self.assertIn("Review risk tolerance for concentrated positions", actions)
        self.assertIn("Dollar-cost averaging into underallocated coins", actions)
        
    def test_get_suggested_actions_for_roi_change_increase(self):
        """
        Test suggested actions for ROI increase.
        """
        actions = self.monitor._get_suggested_actions_for_roi_change(0.15, PortfolioChangeDirection.INCREASE)
        self.assertIn("Review successful strategies and consider scaling", actions)
        self.assertIn("Monitor for sustainability of high returns", actions)
        
    def test_get_suggested_actions_for_roi_change_decrease(self):
        """
        Test suggested actions for ROI decrease.
        """
        actions = self.monitor._get_suggested_actions_for_roi_change(-0.10, PortfolioChangeDirection.DECREASE)
        self.assertIn("Review underperforming positions", actions)
        self.assertIn("Consider adjusting trading parameters", actions)
        self.assertIn("Check for market regime changes", actions)
        
    def test_get_suggested_actions_for_risk_adjusted_change_increase(self):
        """
        Test suggested actions for risk-adjusted return increase.
        """
        actions = self.monitor._get_suggested_actions_for_risk_adjusted_change(0.3, PortfolioChangeDirection.INCREASE)
        self.assertIn("Consider maintaining current strategy if risk-adjusted returns improved", actions)
        self.assertIn("Review what factors contributed to improved risk-adjusted returns", actions)
        
    def test_get_suggested_actions_for_risk_adjusted_change_decrease(self):
        """
        Test suggested actions for risk-adjusted return decrease.
        """
        actions = self.monitor._get_suggested_actions_for_risk_adjusted_change(-0.2, PortfolioChangeDirection.DECREASE)
        self.assertIn("Review risk management and position sizing", actions)
        self.assertIn("Consider adjusting strategy parameters", actions)
        self.assertIn("Check for increased volatility or correlation", actions)
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._collect_current_portfolio_data')
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._collect_historical_portfolio_data')
    async def test_collect_data(self, mock_historical, mock_current):
        """
        Test data collection functionality.
        """
        # Mock current portfolio data
        mock_current.return_value = {
            'total_value': 10000.0,
            'total_profit_loss': 1000.0,
            'total_profit_loss_percentage': 10.0,
            'roi': 0.1,
            'coins': {
                'BTC': {'balance': 0.5, 'usd_value': 20000.0, 'allocation': 50.0, 'price': 40000.0, 'price_change_24h': 5.0},
                'ETH': {'balance': 10.0, 'usd_value': 20000.0, 'allocation': 50.0, 'price': 2000.0, 'price_change_24h': 3.0}
            }
        }
        
        # Mock historical portfolio data
        mock_historical.return_value = {
            1: {'total_value': 9500.0, 'roi': 0.05},
            6: {'total_value': 9000.0, 'roi': 0.0},
            24: {'total_value': 8000.0, 'roi': -0.1}
        }
        
        # Collect data
        data = await self.monitor.collect_data()
        
        # Verify data structure
        self.assertIn('current_portfolio', data)
        self.assertIn('historical_portfolio', data)
        self.assertIn('timestamp', data)
        
        # Verify current portfolio data
        current = data['current_portfolio']
        self.assertEqual(current['total_value'], 10000.0)
        self.assertEqual(len(current['coins']), 2)
        
        # Verify historical portfolio data
        historical = data['historical_portfolio']
        self.assertEqual(len(historical), 3)
        self.assertIn(1, historical)
        self.assertIn(6, historical)
        self.assertIn(24, historical)
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._analyze_portfolio_period')
    async def test_analyze_data(self, mock_analyze_period):
        """
        Test data analysis functionality.
        """
        # Mock portfolio data
        data = {
            'current_portfolio': {
                'total_value': 10000.0,
                'roi': 0.1,
                'coins': {'BTC': {'allocation': 60.0}}
            },
            'historical_portfolio': {
                1: {'total_value': 9500.0, 'roi': 0.05},
                6: {'total_value': 9000.0, 'roi': 0.0},
                24: {'total_value': 8000.0, 'roi': -0.1}
            }
        }
        
        # Mock period analysis results
        mock_alert1 = Mock()
        mock_alert1.alert_type = AlertType.MARKET_CONDITION_CHANGE
        mock_alert1.severity = AlertSeverity.HIGH
        mock_alert1.metadata = {'metric_type': 'TOTAL_VALUE_CHANGE', 'percentage_change': 0.05}
        
        mock_alert2 = Mock()
        mock_alert2.alert_type = AlertType.MARKET_CONDITION_CHANGE
        mock_alert2.severity = AlertSeverity.MEDIUM
        mock_alert2.metadata = {'metric_type': 'ROI_CHANGE', 'percentage_change': 0.15}
        
        mock_analyze_period.side_effect = [[mock_alert1], [mock_alert2], []]
        
        # Analyze data
        alerts = await self.monitor.analyze_data(data)
        
        # Verify alerts
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0].alert_type, AlertType.MARKET_CONDITION_CHANGE)
        self.assertEqual(alerts[1].alert_type, AlertType.MARKET_CONDITION_CHANGE)
        
        # Verify period analysis was called for each period
        self.assertEqual(mock_analyze_period.call_count, 3)
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._apply_rate_limiting')
    async def test_analyze_data_with_rate_limiting(self, mock_rate_limiting):
        """
        Test data analysis with rate limiting applied.
        """
        # Mock portfolio data
        data = {
            'current_portfolio': {'total_value': 10000.0},
            'historical_portfolio': {1: {'total_value': 9500.0}}
        }
        
        # Mock alerts
        mock_alert1 = Mock()
        mock_alert1.alert_type = AlertType.MARKET_CONDITION_CHANGE
        mock_alert1.severity = AlertSeverity.HIGH
        
        mock_alert2 = Mock()
        mock_alert2.alert_type = AlertType.MARKET_CONDITION_CHANGE
        mock_alert2.severity = AlertSeverity.HIGH
        
        # Mock rate limiting to filter out one alert
        mock_rate_limiting.return_value = [mock_alert1]
        
        # Analyze data
        alerts = await self.monitor.analyze_data(data)
        
        # Verify rate limiting was applied
        mock_rate_limiting.assert_called_once()
        self.assertEqual(len(alerts), 1)
        
    async def test_apply_rate_limiting(self):
        """
        Test rate limiting functionality.
        """
        # Create mock alerts
        alerts = []
        for i in range(5):
            alert = Mock()
            alert.alert_type = AlertType.MARKET_CONDITION_CHANGE
            alert.severity = AlertSeverity.HIGH if i < 3 else AlertSeverity.MEDIUM
            alerts.append(alert)
        
        # Apply rate limiting
        filtered_alerts = await self.monitor._apply_rate_limiting(alerts)
        
        # Verify rate limiting worked (should allow up to max_alerts_per_period)
        self.assertLessEqual(len(filtered_alerts), self.monitor.max_alerts_per_period)
        
    async def test_apply_rate_limiting_with_existing_alerts(self):
        """
        Test rate limiting with existing alerts in the rate limit period.
        """
        # Add existing alerts to simulate rate limit period
        current_time = datetime.utcnow()
        self.monitor.alert_counts['HIGH_CRITICAL'] = [
            current_time - timedelta(minutes=10),
            current_time - timedelta(minutes=20),
            current_time - timedelta(minutes=30)
        ]
        
        # Create mock alerts
        alerts = []
        for i in range(3):
            alert = Mock()
            alert.alert_type = AlertType.MARKET_CONDITION_CHANGE
            alert.severity = AlertSeverity.HIGH
            alerts.append(alert)
        
        # Apply rate limiting
        filtered_alerts = await self.monitor._apply_rate_limiting(alerts)
        
        # Verify rate limiting worked (should not exceed max_alerts_per_period)
        self.assertLessEqual(len(filtered_alerts), self.monitor.max_alerts_per_period - len(self.monitor.alert_counts['HIGH_CRITICAL']))
        
    def test_create_priority_summary_message(self):
        """
        Test priority summary message creation.
        """
        # Test critical priority
        alerts = [Mock(), Mock()]
        message = self.monitor._create_priority_summary_message(AlertSeverity.CRITICAL, alerts)
        self.assertIn("CRITICAL", message)
        self.assertIn("2", message)
        
        # Test high priority
        message = self.monitor._create_priority_summary_message(AlertSeverity.HIGH, alerts)
        self.assertIn("HIGH", message)
        self.assertIn("2", message)
        
        # Test medium priority
        message = self.monitor._create_priority_summary_message(AlertSeverity.MEDIUM, alerts)
        self.assertIn("MEDIUM", message)
        self.assertIn("2", message)
        
        # Test low priority
        message = self.monitor._create_priority_summary_message(AlertSeverity.LOW, alerts)
        self.assertIn("LOW", message)
        self.assertIn("2", message)
        
    def test_create_individual_alert_message(self):
        """
        Test individual alert message creation.
        """
        # Mock alert
        alert = Mock()
        alert.title = "Test Alert"
        alert.description = "This is a test alert description"
        alert.severity = AlertSeverity.HIGH
        alert.metadata = {
            'suggested_actions': [
                'Action 1: Review portfolio',
                'Action 2: Adjust settings',
                'Action 3: Monitor market'
            ]
        }
        
        # Create message
        message = self.monitor._create_individual_alert_message(alert)
        
        # Verify message content
        self.assertIn("Test Alert", message)
        self.assertIn("This is a test alert description", message)
        self.assertIn("HIGH", message)
        self.assertIn("Action 1: Review portfolio", message)
        self.assertIn("Action 2: Adjust settings", message)
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._create_portfolio_change_alert')
    async def test_analyze_total_value_change(self, mock_create_alert):
        """
        Test total value change analysis.
        """
        # Mock current and historical data
        current_portfolio = {'total_value': 10000.0}
        historical_data = {'total_value': 9000.0}
        
        # Mock alert creation
        mock_alert = Mock()
        mock_alert.alert_type = AlertType.MARKET_CONDITION_CHANGE
        mock_alert.severity = AlertSeverity.HIGH
        mock_alert.metadata = {'metric_type': 'TOTAL_VALUE_CHANGE', 'percentage_change': 0.11}
        mock_create_alert.return_value = mock_alert
        
        # Analyze value change
        alert = await self.monitor._analyze_total_value_change(
            current_portfolio=current_portfolio,
            historical_data=historical_data,
            period_hours=24
        )
        
        # Verify alert was created
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, AlertType.MARKET_CONDITION_CHANGE)
        self.assertEqual(alert.severity, AlertSeverity.HIGH)
        
        # Verify alert creation was called with correct parameters
        mock_create_alert.assert_called_once()
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._create_portfolio_change_alert')
    async def test_analyze_total_value_change_below_threshold(self, mock_create_alert):
        """
        Test total value change analysis when change is below threshold.
        """
        # Mock current and historical data (small change)
        current_portfolio = {'total_value': 9450.0}  # 5% increase from 9000
        historical_data = {'total_value': 9000.0}
        
        # Analyze value change
        alert = await self.monitor._analyze_total_value_change(
            current_portfolio=current_portfolio,
            historical_data=historical_data,
            period_hours=24
        )
        
        # Verify no alert was created
        self.assertIsNone(alert)
        mock_create_alert.assert_not_called()
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._create_portfolio_change_alert')
    async def test_analyze_allocation_change(self, mock_create_alert):
        """
        Test allocation change analysis.
        """
        # Mock current portfolio with extreme allocation
        current_portfolio = {
            'coins': {
                'BTC': {'allocation': 70.0, 'usd_value': 70000.0},
                'ETH': {'allocation': 20.0, 'usd_value': 20000.0},
                'SOL': {'allocation': 10.0, 'usd_value': 10000.0}
            }
        }
        historical_data = {'total_value': 100000.0}
        
        # Mock alert creation
        mock_alert = Mock()
        mock_alert.alert_type = AlertType.MARKET_CONDITION_CHANGE
        mock_alert.severity = AlertSeverity.HIGH
        mock_alert.metadata = {'metric_type': 'ALLOCATION_CHANGE', 'percentage_change': 70.0}
        mock_create_alert.return_value = mock_alert
        
        # Analyze allocation change
        alert = await self.monitor._analyze_allocation_change(
            current_portfolio=current_portfolio,
            historical_data=historical_data,
            period_hours=24
        )
        
        # Verify alert was created
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, AlertType.MARKET_CONDITION_CHANGE)
        self.assertEqual(alert.severity, AlertSeverity.HIGH)
        
        # Verify alert creation was called with correct parameters
        mock_create_alert.assert_called_once()
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._create_portfolio_change_alert')
    async def test_analyze_roi_change(self, mock_create_alert):
        """
        Test ROI change analysis.
        """
        # Mock current and historical data
        current_portfolio = {'roi': 0.15}
        historical_data = {'roi': 0.05}
        
        # Mock alert creation
        mock_alert = Mock()
        mock_alert.alert_type = AlertType.MARKET_CONDITION_CHANGE
        mock_alert.severity = AlertSeverity.HIGH
        mock_alert.metadata = {'metric_type': 'ROI_CHANGE', 'percentage_change': 0.10}
        mock_create_alert.return_value = mock_alert
        
        # Analyze ROI change
        alert = await self.monitor._analyze_roi_change(
            current_portfolio=current_portfolio,
            historical_data=historical_data,
            period_hours=24
        )
        
        # Verify alert was created
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, AlertType.MARKET_CONDITION_CHANGE)
        self.assertEqual(alert.severity, AlertSeverity.HIGH)
        
        # Verify alert creation was called with correct parameters
        mock_create_alert.assert_called_once()
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._create_portfolio_change_alert')
    async def test_analyze_risk_adjusted_return_change(self, mock_create_alert):
        """
        Test risk-adjusted return change analysis.
        """
        # Mock current and historical data
        current_portfolio = {'roi': 0.15, 'volatility': 0.1}
        historical_data = {'roi': 0.05, 'volatility': 0.15}
        
        # Mock alert creation
        mock_alert = Mock()
        mock_alert.alert_type = AlertType.MARKET_CONDITION_CHANGE
        mock_alert.severity = AlertSeverity.MEDIUM
        mock_alert.metadata = {'metric_type': 'RISK_ADJUSTED_RETURN', 'percentage_change': 0.2}
        mock_create_alert.return_value = mock_alert
        
        # Analyze risk-adjusted return change
        alert = await self.monitor._analyze_risk_adjusted_return_change(
            current_portfolio=current_portfolio,
            historical_data=historical_data,
            period_hours=24
        )
        
        # Verify alert was created
        self.assertIsNotNone(alert)
        self.assertEqual(alert.alert_type, AlertType.MARKET_CONDITION_CHANGE)
        self.assertEqual(alert.severity, AlertSeverity.MEDIUM)
        
        # Verify alert creation was called with correct parameters
        mock_create_alert.assert_called_once()
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._send_priority_notifications')
    async def test_send_notifications(self, mock_send_priority):
        """
        Test notification sending functionality.
        """
        # Mock alerts
        alerts = []
        for severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.MEDIUM, AlertSeverity.LOW]:
            alert = Mock()
            alert.severity = severity
            alerts.append(alert)
        
        # Send notifications
        await self.monitor._send_notifications(alerts)
        
        # Verify priority notifications were sent for each severity
        self.assertEqual(mock_send_priority.call_count, 4)
        mock_send_priority.assert_any_call(AlertSeverity.CRITICAL, [alerts[0]])
        mock_send_priority.assert_any_call(AlertSeverity.HIGH, [alerts[1]])
        mock_send_priority.assert_any_call(AlertSeverity.MEDIUM, [alerts[2]])
        mock_send_priority.assert_any_call(AlertSeverity.LOW, [alerts[3]])
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._send_priority_notifications')
    async def test_send_notifications_empty_alerts(self, mock_send_priority):
        """
        Test notification sending with empty alerts list.
        """
        # Send notifications with empty list
        await self.monitor._send_notifications([])
        
        # Verify no notifications were sent
        mock_send_priority.assert_not_called()
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._send_priority_notifications')
    async def test_send_notifications_grouped_by_severity(self, mock_send_priority):
        """
        Test notification sending with alerts grouped by severity.
        """
        # Mock multiple alerts of same severity
        alerts = []
        for i in range(3):
            alert = Mock()
            alert.severity = AlertSeverity.HIGH
            alerts.append(alert)
        
        # Send notifications
        await self.monitor._send_notifications(alerts)
        
        # Verify single priority notification was sent with all alerts
        mock_send_priority.assert_called_once_with(AlertSeverity.HIGH, alerts)
        
    def test_generate_report_no_alerts(self):
        """
        Test report generation when no alerts are present.
        """
        # Generate report with no alerts
        report = self.monitor.generate_report([])
        
        # Verify report content
        self.assertIn("No portfolio change alerts generated", report)
        self.assertIn("Portfolio value changes are within normal ranges", report)
        
    def test_generate_report_with_alerts(self):
        """
        Test report generation with alerts present.
        """
        # Mock alerts
        alerts = []
        for i, severity in enumerate([AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.MEDIUM]):
            alert = Mock()
            alert.severity = severity
            alert.title = f"Test Alert {i+1}"
            alert.metadata = {
                'metric_type': 'TOTAL_VALUE_CHANGE',
                'percentage_change': 0.15 + i * 0.05,
                'period_hours': 24,
                'suggested_actions': [f'Action {i+1}', f'Action {i+1} alternative']
            }
            alerts.append(alert)
        
        # Generate report
        report = self.monitor.generate_report(alerts)
        
        # Verify report content
        self.assertIn("Portfolio Change Monitoring Report", report)
        self.assertIn(f"Total Alerts: {len(alerts)}", report)
        self.assertIn("CRITICAL Severity Alerts: 1", report)
        self.assertIn("HIGH Severity Alerts: 1", report)
        self.assertIn("MEDIUM Severity Alerts: 1", report)
        self.assertIn("Test Alert 1", report)
        self.assertIn("Test Alert 2", report)
        self.assertIn("Test Alert 3", report)
        
    def test_generate_report_summary_statistics(self):
        """
        Test report generation includes summary statistics.
        """
        # Mock alerts
        alerts = [Mock()]
        alerts[0].severity = AlertSeverity.HIGH
        alerts[0].metadata = {'metric_type': 'TOTAL_VALUE_CHANGE', 'percentage_change': 0.15}
        
        # Generate report
        report = self.monitor.generate_report(alerts)
        
        # Verify summary statistics are included
        self.assertIn("Summary Statistics", report)
        self.assertIn("Total portfolio changes monitored", report)
        self.assertIn("Alert cooldown", report)
        self.assertIn("Rate limit", report)
        self.assertIn("Change thresholds", report)


class TestPortfolioChangeMonitorIntegration(unittest.TestCase):
    """
    Integration tests for PortfolioChangeMonitor with real dependencies.
    """
    
    def setUp(self):
        """
        Set up test fixtures for integration tests.
        """
        # This would normally use real database and other dependencies
        # For now, we'll keep it simple and focus on the integration points
        pass
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._collect_current_portfolio_data')
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._collect_historical_portfolio_data')
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._analyze_portfolio_period')
    async def test_full_monitoring_cycle(self, mock_analyze_period, mock_historical, mock_current):
        """
        Test the complete monitoring cycle from data collection to report generation.
        """
        # Mock dependencies
        mock_database = Mock(spec=Database)
        mock_logger = Mock(spec=Logger)
        mock_notifications = Mock(spec=NotificationHandler)
        mock_statistics_manager = Mock(spec=StatisticsManager)
        
        # Mock database session
        mock_session = Mock()
        mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test configuration
        test_config = {
            'portfolio_change_thresholds': {
                'low': 0.05,
                'medium': 0.10,
                'high': 0.20,
                'critical': 0.30
            },
            'portfolio_change_periods': [1, 6],
            'portfolio_metrics': ['TOTAL_VALUE_CHANGE', 'ROI_CHANGE'],
            'alert_cooldown_period': 60,
            'max_alerts_per_period': 3,
            'rate_limit_period': 60
        }
        
        # Create monitor instance
        monitor = PortfolioChangeMonitor(
            database=mock_database,
            logger=mock_logger,
            notifications=mock_notifications,
            config=test_config,
            statistics_manager=mock_statistics_manager
        )
        
        # Mock current portfolio data
        mock_current.return_value = {
            'total_value': 10000.0,
            'roi': 0.1,
            'coins': {'BTC': {'allocation': 60.0}}
        }
        
        # Mock historical portfolio data
        mock_historical.return_value = {
            1: {'total_value': 9500.0, 'roi': 0.05},
            6: {'total_value': 9000.0, 'roi': 0.0}
        }
        
        # Mock period analysis results
        mock_alert = Mock()
        mock_alert.alert_type = AlertType.MARKET_CONDITION_CHANGE
        mock_alert.severity = AlertSeverity.HIGH
        mock_alert.metadata = {'metric_type': 'TOTAL_VALUE_CHANGE', 'percentage_change': 0.05}
        mock_analyze_period.return_value = [mock_alert]
        
        # Run complete monitoring cycle
        result = await monitor.run_monitoring_cycle()
        
        # Verify cycle results
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['alerts_generated'], 1)
        self.assertEqual(result['total_alerts'], 1)
        self.assertIn('report', result)
        self.assertIn('timestamp', result)
        
        # Verify data collection was called
        mock_current.assert_called_once()
        mock_historical.assert_called_once()
        
        # Verify analysis was called for each period
        self.assertEqual(mock_analyze_period.call_count, 2)
        
        # Verify report was generated
        self.assertIn('Portfolio Change Monitoring Report', result['report'])
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._collect_current_portfolio_data')
    async def test_monitoring_cycle_error_handling(self, mock_collect_data):
        """
        Test error handling in the monitoring cycle.
        """
        # Mock dependencies
        mock_database = Mock(spec=Database)
        mock_logger = Mock(spec=Logger)
        mock_notifications = Mock(spec=NotificationHandler)
        mock_statistics_manager = Mock(spec=StatisticsManager)
        
        # Mock database session
        mock_session = Mock()
        mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test configuration
        test_config = {
            'portfolio_change_thresholds': {'low': 0.05, 'medium': 0.10, 'high': 0.20, 'critical': 0.30},
            'portfolio_change_periods': [1, 6],
            'portfolio_metrics': ['TOTAL_VALUE_CHANGE', 'ROI_CHANGE'],
            'alert_cooldown_period': 60,
            'max_alerts_per_period': 3,
            'rate_limit_period': 60
        }
        
        # Create monitor instance
        monitor = PortfolioChangeMonitor(
            database=mock_database,
            logger=mock_logger,
            notifications=mock_notifications,
            config=test_config,
            statistics_manager=mock_statistics_manager
        )
        
        # Mock data collection to raise exception
        mock_collect_data.side_effect = Exception("Data collection failed")
        
        # Run monitoring cycle (should handle error gracefully)
        result = await monitor.run_monitoring_cycle()
        
        # Verify error result
        self.assertEqual(result['status'], 'error')
        self.assertIn('Data collection failed', result['message'])
        self.assertIn('timestamp', result)
        
        # Verify error was logged
        mock_logger.error.assert_called()
        
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._collect_current_portfolio_data')
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._collect_historical_portfolio_data')
    @patch('binance_trade_bot.monitoring.portfolio_change_monitor.PortfolioChangeMonitor._analyze_portfolio_period')
    async def test_monitoring_cycle_already_running(self, mock_analyze_period, mock_historical, mock_current):
        """
        Test monitoring cycle when already running.
        """
        # Mock dependencies
        mock_database = Mock(spec=Database)
        mock_logger = Mock(spec=Logger)
        mock_notifications = Mock(spec=NotificationHandler)
        mock_statistics_manager = Mock(spec=StatisticsManager)
        
        # Mock database session
        mock_session = Mock()
        mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test configuration
        test_config = {
            'portfolio_change_thresholds': {'low': 0.05, 'medium': 0.10, 'high': 0.20, 'critical': 0.30},
            'portfolio_change_periods': [1],
            'portfolio_metrics': ['TOTAL_VALUE_CHANGE'],
            'alert_cooldown_period': 60,
            'max_alerts_per_period': 3,
            'rate_limit_period': 60
        }
        
        # Create monitor instance
        monitor = PortfolioChangeMonitor(
            database=mock_database,
            logger=mock_logger,
            notifications=mock_notifications,
            config=test_config,
            statistics_manager=mock_statistics_manager
        )
        
        # Set monitor as already running
        monitor.is_running = True
        
        # Run monitoring cycle (should detect it's already running)
        result = await monitor.run_monitoring_cycle()
        
        # Verify error result
        self.assertEqual(result['status'], 'error')
        self.assertIn('Monitoring already in progress', result['message'])
        
        # Verify data collection was not called
        mock_current.assert_not_called()
        mock_historical.assert_not_called()
        mock_analyze_period.assert_not_called()


if __name__ == '__main__':
    # Run the tests
    unittest.main()