"""
Unit tests for monitoring manager module.

This module contains comprehensive unit tests for the monitoring manager
functionality that coordinates all monitoring services.

Created: 2025-08-05
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import asyncio
import uuid

from binance_trade_bot.monitoring.monitoring_manager import MonitoringManager
from binance_trade_bot.monitoring.base import MonitoringAlert, AlertSeverity, AlertType
from binance_trade_bot.monitoring.models import (
    VolatilityMetric,
    PerformanceMetric,
    TradingFrequencyMetric,
    ApiErrorType
)
from binance_trade_bot.models import Coin, Pair


class TestMonitoringManager(unittest.TestCase):
    """Test cases for MonitoringManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock()
        self.mock_logger = Mock()
        self.mock_notifications = Mock()
        self.mock_binance_manager = Mock()
        
        self.test_config = {
            'monitoring': {
                'enabled': True,
                'check_interval': 60,  # 1 minute
                'alert_cooldown_period': 30,
                'volatility_detection': {
                    'enabled': True,
                    'thresholds': {
                        'standard_deviation': {
                            'low': 0.02,
                            'medium': 0.05,
                            'high': 0.10,
                            'critical': 0.20
                        }
                    }
                },
                'performance_analysis': {
                    'enabled': True,
                    'thresholds': {
                        'price_change_24h': {
                            'low': 0.05,
                            'medium': 0.10,
                            'high': 0.20,
                            'critical': 0.40
                        }
                    }
                },
                'trading_frequency': {
                    'enabled': True,
                    'thresholds': {
                        'trades_per_hour': {
                            'low': 5,
                            'medium': 10,
                            'high': 20,
                            'critical': 50
                        }
                    }
                },
                'api_error_tracking': {
                    'enabled': True,
                    'thresholds': {
                        'rate_limit': {
                            'low': 0.05,
                            'medium': 0.10,
                            'high': 0.20,
                            'critical': 0.40
                        }
                    }
                }
            },
            'enabled_coins': ['BTC', 'ETH', 'BNB'],
            'enabled_pairs': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
        }
        
        # Mock monitoring services
        self.mock_volatility_detector = Mock()
        self.mock_performance_analyzer = Mock()
        self.mock_frequency_monitor = Mock()
        self.mock_api_tracker = Mock()
        
        # Create monitoring manager
        self.monitoring_manager = MonitoringManager(
            database=self.mock_database,
            logger=self.mock_logger,
            notifications=self.mock_notifications,
            config=self.test_config,
            binance_manager=self.mock_binance_manager
        )
        
        # Replace services with mocks
        self.monitoring_manager.volatility_detector = self.mock_volatility_detector
        self.monitoring_manager.performance_analyzer = self.mock_performance_analyzer
        self.monitoring_manager.frequency_monitor = self.mock_frequency_monitor
        self.monitoring_manager.api_tracker = self.mock_api_tracker
        
        # Create test coins
        self.test_coin_btc = Coin('BTC')
        self.test_coin_eth = Coin('ETH')
        self.test_coin_bnb = Coin('BNB')
        
        # Create test pairs
        self.test_pair_btc_eth = Pair(self.test_coin_btc, self.test_coin_eth)
        self.test_pair_eth_btc = Pair(self.test_coin_eth, self.test_coin_btc)
        
    def test_monitoring_manager_initialization(self):
        """Test monitoring manager initialization."""
        self.assertEqual(self.monitoring_manager.database, self.mock_database)
        self.assertEqual(self.monitoring_manager.logger, self.mock_logger)
        self.assertEqual(self.monitoring_manager.notifications, self.mock_notifications)
        self.assertEqual(self.monitoring_manager.config, self.test_config)
        self.assertTrue(self.monitoring_manager.enabled)
        
        # Check configuration
        self.assertEqual(
            self.monitoring_manager.check_interval,
            self.test_config['monitoring']['check_interval']
        )
        self.assertEqual(
            self.monitoring_manager.alert_cooldown_period,
            self.test_config['monitoring']['alert_cooldown_period']
        )
        
        # Check service initialization
        self.assertIsNotNone(self.monitoring_manager.volatility_detector)
        self.assertIsNotNone(self.monitoring_manager.performance_analyzer)
        self.assertIsNotNone(self.monitoring_manager.frequency_monitor)
        self.assertIsNotNone(self.monitoring_manager.api_tracker)
    
    async def test_collect_all_data(self):
        """Test data collection from all services."""
        # Mock service data collection
        mock_volatility_data = {
            'coins': [{'symbol': 'BTC', 'price': 50000.0, 'price_history': [50000, 50100, 49900]}],
            'pairs': [{'from_coin': 'BTC', 'to_coin': 'ETH', 'price_history': [16.67, 16.16, 17.21]}],
            'timestamp': datetime.utcnow()
        }
        
        mock_performance_data = {
            'coins': [{'symbol': 'BTC', 'price': 50000.0, 'balance': 1.0, 'price_history': [50000, 50100, 49900]}],
            'timestamp': datetime.utcnow()
        }
        
        mock_frequency_data = {
            'coins': [{'symbol': 'BTC', 'trades_count': 5, 'last_trade_time': datetime.utcnow()}],
            'pairs': [{'from_coin': 'BTC', 'to_coin': 'ETH', 'trades_count': 3, 'last_trade_time': datetime.utcnow()}],
            'trade_history': [],
            'timestamp': datetime.utcnow()
        }
        
        mock_api_data = {
            'error_history': [],
            'endpoint_stats': {},
            'timestamp': datetime.utcnow()
        }
        
        # Set up mock return values
        self.mock_volatility_detector.collect_data.return_value = mock_volatility_data
        self.mock_performance_analyzer.collect_data.return_value = mock_performance_data
        self.mock_frequency_monitor.collect_data.return_value = mock_frequency_data
        self.mock_api_tracker.collect_data.return_value = mock_api_data
        
        data = await self.monitoring_manager.collect_all_data()
        
        # Verify data structure
        self.assertIn('volatility_data', data)
        self.assertIn('performance_data', data)
        self.assertIn('frequency_data', data)
        self.assertIn('api_data', data)
        self.assertIn('timestamp', data)
        
        # Verify service calls
        self.mock_volatility_detector.collect_data.assert_called_once()
        self.mock_performance_analyzer.collect_data.assert_called_once()
        self.mock_frequency_monitor.collect_data.assert_called_once()
        self.mock_api_tracker.collect_data.assert_called_once()
    
    async def test_collect_all_data_service_error(self):
        """Test data collection when a service fails."""
        # Mock one service to fail
        self.mock_volatility_detector.collect_data.side_effect = Exception("Service error")
        
        # Other services return data
        mock_performance_data = {
            'coins': [{'symbol': 'BTC', 'price': 50000.0, 'balance': 1.0, 'price_history': [50000, 50100, 49900]}],
            'timestamp': datetime.utcnow()
        }
        
        mock_frequency_data = {
            'coins': [{'symbol': 'BTC', 'trades_count': 5, 'last_trade_time': datetime.utcnow()}],
            'timestamp': datetime.utcnow()
        }
        
        mock_api_data = {
            'error_history': [],
            'endpoint_stats': {},
            'timestamp': datetime.utcnow()
        }
        
        self.mock_performance_analyzer.collect_data.return_value = mock_performance_data
        self.mock_frequency_monitor.collect_data.return_value = mock_frequency_data
        self.mock_api_tracker.collect_data.return_value = mock_api_data
        
        data = await self.monitoring_manager.collect_all_data()
        
        # Should still return data from working services
        self.assertNotIn('volatility_data', data)
        self.assertIn('performance_data', data)
        self.assertIn('frequency_data', data)
        self.assertIn('api_data', data)
        
        # Verify error was logged
        self.mock_logger.error.assert_called()
    
    async def test_analyze_all_data(self):
        """Test data analysis from all services."""
        # Mock service data analysis
        mock_volatility_alerts = [
            MonitoringAlert(
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.HIGH,
                title="High Volatility Alert",
                description="High volatility detected"
            )
        ]
        
        mock_performance_alerts = [
            MonitoringAlert(
                alert_type=AlertType.EXCEPTIONAL_PERFORMANCE,
                severity=AlertSeverity.MEDIUM,
                title="Performance Alert",
                description="Exceptional performance detected"
            )
        ]
        
        mock_frequency_alerts = [
            MonitoringAlert(
                alert_type=AlertType.HIGH_TRADING_FREQUENCY,
                severity=AlertSeverity.LOW,
                title="Frequency Alert",
                description="High trading frequency detected"
            )
        ]
        
        mock_api_alerts = [
            MonitoringAlert(
                alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                severity=AlertSeverity.CRITICAL,
                title="API Error Alert",
                description="High API error rate detected"
            )
        ]
        
        # Set up mock return values
        self.mock_volatility_detector.analyze_data.return_value = mock_volatility_alerts
        self.mock_performance_analyzer.analyze_data.return_value = mock_performance_alerts
        self.mock_frequency_monitor.analyze_data.return_value = mock_frequency_alerts
        self.mock_api_tracker.analyze_data.return_value = mock_api_alerts
        
        # Mock data
        test_data = {
            'volatility_data': {'coins': [], 'pairs': []},
            'performance_data': {'coins': []},
            'frequency_data': {'coins': [], 'pairs': [], 'trade_history': []},
            'api_data': {'error_history': [], 'endpoint_stats': {}}
        }
        
        alerts = await self.monitoring_manager.analyze_all_data(test_data)
        
        # Verify alerts are combined
        self.assertEqual(len(alerts), 4)
        
        # Verify service calls
        self.mock_volatility_detector.analyze_data.assert_called_once()
        self.mock_performance_analyzer.analyze_data.assert_called_once()
        self.mock_frequency_monitor.analyze_data.assert_called_once()
        self.mock_api_tracker.analyze_data.assert_called_once()
    
    async def test_analyze_all_data_service_error(self):
        """Test data analysis when a service fails."""
        # Mock one service to fail
        self.mock_volatility_detector.analyze_data.side_effect = Exception("Analysis error")
        
        # Other services return alerts
        mock_performance_alerts = [
            MonitoringAlert(
                alert_type=AlertType.EXCEPTIONAL_PERFORMANCE,
                severity=AlertSeverity.MEDIUM,
                title="Performance Alert",
                description="Exceptional performance detected"
            )
        ]
        
        self.mock_performance_analyzer.analyze_data.return_value = mock_performance_alerts
        
        # Mock data
        test_data = {
            'volatility_data': {'coins': [], 'pairs': []},
            'performance_data': {'coins': []},
            'frequency_data': {'coins': [], 'pairs': [], 'trade_history': []},
            'api_data': {'error_history': [], 'endpoint_stats': {}}
        }
        
        alerts = await self.monitoring_manager.analyze_all_data(test_data)
        
        # Should still return alerts from working services
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, AlertType.EXCEPTIONAL_PERFORMANCE)
        
        # Verify error was logged
        self.mock_logger.error.assert_called()
    
    async def test_process_alerts(self):
        """Test alert processing."""
        # Mock alerts
        test_alerts = [
            MonitoringAlert(
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.HIGH,
                title="High Volatility Alert",
                description="High volatility detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.EXCEPTIONAL_PERFORMANCE,
                severity=AlertSeverity.MEDIUM,
                title="Performance Alert",
                description="Exceptional performance detected"
            )
        ]
        
        # Mock notification handler
        self.mock_notifications.send_notification = AsyncMock()
        
        await self.monitoring_manager.process_alerts(test_alerts)
        
        # Verify notifications are sent
        self.assertEqual(self.mock_notifications.send_notification.call_count, 2)
        
        # Verify notification calls
        call_args_list = self.mock_notifications.send_notification.call_args_list
        self.assertIn("High Volatility Alert", call_args_list[0][0][0])
        self.assertIn("Performance Alert", call_args_list[1][0][0])
    
    async def test_process_alerts_with_cooldown(self):
        """Test alert processing with cooldown."""
        # Mock alerts with same type
        test_alerts = [
            MonitoringAlert(
                alert_uuid=str(uuid.uuid4()),
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.HIGH,
                title="High Volatility Alert",
                description="High volatility detected"
            ),
            MonitoringAlert(
                alert_uuid=str(uuid.uuid4()),
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.HIGH,
                title="High Volatility Alert",
                description="High volatility detected"
            )
        ]
        
        # Mock notification handler
        self.mock_notifications.send_notification = AsyncMock()
        
        await self.monitoring_manager.process_alerts(test_alerts)
        
        # Only one notification should be sent due to cooldown
        self.assertEqual(self.mock_notifications.send_notification.call_count, 1)
    
    async def test_generate_comprehensive_report(self):
        """Test comprehensive report generation."""
        # Mock alerts
        test_alerts = [
            MonitoringAlert(
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.HIGH,
                title="High Volatility Alert",
                description="High volatility detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.EXCEPTIONAL_PERFORMANCE,
                severity=AlertSeverity.MEDIUM,
                title="Performance Alert",
                description="Exceptional performance detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.HIGH_TRADING_FREQUENCY,
                severity=AlertSeverity.LOW,
                title="Frequency Alert",
                description="High trading frequency detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                severity=AlertSeverity.CRITICAL,
                title="API Error Alert",
                description="High API error rate detected"
            )
        ]
        
        # Mock service reports
        mock_volatility_report = "📈 Volatility Detection Report\nTotal Alerts: 1"
        mock_performance_report = "📈 Performance Analysis Report\nTotal Alerts: 1"
        mock_frequency_report = "📊 Trading Frequency Report\nTotal Alerts: 1"
        mock_api_report = "🔧 API Error Tracking Report\nTotal Alerts: 1"
        
        self.mock_volatility_detector.generate_report.return_value = mock_volatility_report
        self.mock_performance_analyzer.generate_report.return_value = mock_performance_report
        self.mock_frequency_monitor.generate_report.return_value = mock_frequency_report
        self.mock_api_tracker.generate_report.return_value = mock_api_report
        
        report = await self.monitoring_manager.generate_comprehensive_report(test_alerts)
        
        # Verify report structure
        self.assertIn("📊 Comprehensive Monitoring Report", report)
        self.assertIn("📈 Volatility Detection Report", report)
        self.assertIn("📈 Performance Analysis Report", report)
        self.assertIn("📊 Trading Frequency Report", report)
        self.assertIn("🔧 API Error Tracking Report", report)
        self.assertIn("Summary Statistics:", report)
        self.assertIn("Total Alerts: 4", report)
        self.assertIn("CRITICAL Severity Alerts: 1", report)
        self.assertIn("HIGH Severity Alerts: 1", report)
        self.assertIn("MEDIUM Severity Alerts: 1", report)
        self.assertIn("LOW Severity Alerts: 1", report)
        
        # Verify service calls
        self.mock_volatility_detector.generate_report.assert_called_once()
        self.mock_performance_analyzer.generate_report.assert_called_once()
        self.mock_frequency_monitor.generate_report.assert_called_once()
        self.mock_api_tracker.generate_report.assert_called_once()
    
    async def test_generate_comprehensive_report_no_alerts(self):
        """Test comprehensive report generation when no alerts are present."""
        report = await self.monitoring_manager.generate_comprehensive_report([])
        
        self.assertIn("📊 Comprehensive Monitoring Report", report)
        self.assertIn("No monitoring alerts generated", report)
    
    async def test_run_monitoring_cycle(self):
        """Test complete monitoring cycle."""
        # Mock data collection
        mock_data = {
            'volatility_data': {'coins': [], 'pairs': []},
            'performance_data': {'coins': []},
            'frequency_data': {'coins': [], 'pairs': [], 'trade_history': []},
            'api_data': {'error_history': [], 'endpoint_stats': {}}
        }
        
        # Mock analysis
        mock_alerts = [
            MonitoringAlert(
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.HIGH,
                title="High Volatility Alert",
                description="High volatility detected"
            )
        ]
        
        # Set up mock return values
        self.monitoring_manager.collect_all_data.return_value = mock_data
        self.monitoring_manager.analyze_all_data.return_value = mock_alerts
        
        # Mock notification handler
        self.mock_notifications.send_notification = AsyncMock()
        
        # Run monitoring cycle
        result = await self.monitoring_manager.run_monitoring_cycle()
        
        # Verify result
        self.assertTrue(result)
        
        # Verify service calls
        self.monitoring_manager.collect_all_data.assert_called_once()
        self.monitoring_manager.analyze_all_data.assert_called_once()
        self.monitoring_manager.process_alerts.assert_called_once()
    
    async def test_run_monitoring_cycle_analysis_error(self):
        """Test monitoring cycle when analysis fails."""
        # Mock data collection
        mock_data = {
            'volatility_data': {'coins': [], 'pairs': []},
            'performance_data': {'coins': []},
            'frequency_data': {'coins': [], 'pairs': [], 'trade_history': []},
            'api_data': {'error_history': [], 'endpoint_stats': {}}
        }
        
        # Mock analysis to fail
        self.monitoring_manager.analyze_all_data.side_effect = Exception("Analysis error")
        
        # Run monitoring cycle
        result = await self.monitoring_manager.run_monitoring_cycle()
        
        # Should return False on error
        self.assertFalse(result)
        
        # Verify error was logged
        self.mock_logger.error.assert_called()
    
    async def test_run_monitoring_cycle_processing_error(self):
        """Test monitoring cycle when alert processing fails."""
        # Mock data collection
        mock_data = {
            'volatility_data': {'coins': [], 'pairs': []},
            'performance_data': {'coins': []},
            'frequency_data': {'coins': [], 'pairs': [], 'trade_history': []},
            'api_data': {'error_history': [], 'endpoint_stats': {}}
        }
        
        # Mock analysis
        mock_alerts = [
            MonitoringAlert(
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.HIGH,
                title="High Volatility Alert",
                description="High volatility detected"
            )
        ]
        
        # Set up mock return values
        self.monitoring_manager.collect_all_data.return_value = mock_data
        self.monitoring_manager.analyze_all_data.return_value = mock_alerts
        
        # Mock alert processing to fail
        self.monitoring_manager.process_alerts.side_effect = Exception("Processing error")
        
        # Run monitoring cycle
        result = await self.monitoring_manager.run_monitoring_cycle()
        
        # Should return False on error
        self.assertFalse(result)
        
        # Verify error was logged
        self.mock_logger.error.assert_called()
    
    async def test_get_alert_statistics(self):
        """Test alert statistics calculation."""
        # Mock alerts
        test_alerts = [
            MonitoringAlert(
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.HIGH,
                title="High Volatility Alert",
                description="High volatility detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.EXCEPTIONAL_PERFORMANCE,
                severity=AlertSeverity.MEDIUM,
                title="Performance Alert",
                description="Exceptional performance detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.HIGH_TRADING_FREQUENCY,
                severity=AlertSeverity.LOW,
                title="Frequency Alert",
                description="High trading frequency detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                severity=AlertSeverity.CRITICAL,
                title="API Error Alert",
                description="High API error rate detected"
            )
        ]
        
        stats = self.monitoring_manager.get_alert_statistics(test_alerts)
        
        # Verify statistics
        self.assertEqual(stats['total_alerts'], 4)
        self.assertEqual(stats['severity_breakdown']['CRITICAL'], 1)
        self.assertEqual(stats['severity_breakdown']['HIGH'], 1)
        self.assertEqual(stats['severity_breakdown']['MEDIUM'], 1)
        self.assertEqual(stats['severity_breakdown']['LOW'], 1)
        self.assertEqual(stats['type_breakdown']['MARKET_VOLATILITY_DETECTED'], 1)
        self.assertEqual(stats['type_breakdown']['EXCEPTIONAL_PERFORMANCE'], 1)
        self.assertEqual(stats['type_breakdown']['HIGH_TRADING_FREQUENCY'], 1)
        self.assertEqual(stats['type_breakdown']['API_ERROR_RATE_EXCEEDED'], 1)
    
    async def test_get_alert_statistics_empty(self):
        """Test alert statistics calculation with no alerts."""
        stats = self.monitoring_manager.get_alert_statistics([])
        
        # Verify empty statistics
        self.assertEqual(stats['total_alerts'], 0)
        self.assertEqual(stats['severity_breakdown'], {})
        self.assertEqual(stats['type_breakdown'], {})
    
    async def test_filter_alerts_by_severity(self):
        """Test alert filtering by severity."""
        # Mock alerts
        test_alerts = [
            MonitoringAlert(
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.HIGH,
                title="High Volatility Alert",
                description="High volatility detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.EXCEPTIONAL_PERFORMANCE,
                severity=AlertSeverity.MEDIUM,
                title="Performance Alert",
                description="Exceptional performance detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.HIGH_TRADING_FREQUENCY,
                severity=AlertSeverity.LOW,
                title="Frequency Alert",
                description="High trading frequency detected"
            )
        ]
        
        # Filter by HIGH severity
        high_alerts = self.monitoring_manager.filter_alerts_by_severity(test_alerts, AlertSeverity.HIGH)
        self.assertEqual(len(high_alerts), 1)
        self.assertEqual(high_alerts[0].severity, AlertSeverity.HIGH)
        
        # Filter by MEDIUM severity
        medium_alerts = self.monitoring_manager.filter_alerts_by_severity(test_alerts, AlertSeverity.MEDIUM)
        self.assertEqual(len(medium_alerts), 1)
        self.assertEqual(medium_alerts[0].severity, AlertSeverity.MEDIUM)
        
        # Filter by LOW severity
        low_alerts = self.monitoring_manager.filter_alerts_by_severity(test_alerts, AlertSeverity.LOW)
        self.assertEqual(len(low_alerts), 1)
        self.assertEqual(low_alerts[0].severity, AlertSeverity.LOW)
        
        # Filter by non-existent severity
        critical_alerts = self.monitoring_manager.filter_alerts_by_severity(test_alerts, AlertSeverity.CRITICAL)
        self.assertEqual(len(critical_alerts), 0)
    
    async def test_filter_alerts_by_type(self):
        """Test alert filtering by type."""
        # Mock alerts
        test_alerts = [
            MonitoringAlert(
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.HIGH,
                title="High Volatility Alert",
                description="High volatility detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.EXCEPTIONAL_PERFORMANCE,
                severity=AlertSeverity.MEDIUM,
                title="Performance Alert",
                description="Exceptional performance detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.LOW,
                title="Low Volatility Alert",
                description="Low volatility detected"
            )
        ]
        
        # Filter by MARKET_VOLATILITY_DETECTED type
        volatility_alerts = self.monitoring_manager.filter_alerts_by_type(test_alerts, AlertType.MARKET_VOLATILITY_DETECTED)
        self.assertEqual(len(volatility_alerts), 2)
        for alert in volatility_alerts:
            self.assertEqual(alert.alert_type, AlertType.MARKET_VOLATILITY_DETECTED)
        
        # Filter by EXCEPTIONAL_PERFORMANCE type
        performance_alerts = self.monitoring_manager.filter_alerts_by_type(test_alerts, AlertType.EXCEPTIONAL_PERFORMANCE)
        self.assertEqual(len(performance_alerts), 1)
        self.assertEqual(performance_alerts[0].alert_type, AlertType.EXCEPTIONAL_PERFORMANCE)
        
        # Filter by non-existent type
        error_alerts = self.monitoring_manager.filter_alerts_by_type(test_alerts, AlertType.API_ERROR_RATE_EXCEEDED)
        self.assertEqual(len(error_alerts), 0)


if __name__ == '__main__':
    unittest.main()