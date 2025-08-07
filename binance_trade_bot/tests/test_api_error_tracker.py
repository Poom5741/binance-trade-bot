"""
Unit tests for API error tracker module.

This module contains comprehensive unit tests for the API error tracker
functionality.

Created: 2025-08-05
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import pandas as pd
import numpy as np

from binance_trade_bot.monitoring.api_error_tracker import ApiErrorTracker
from binance_trade_bot.monitoring.base import MonitoringAlert, AlertSeverity, AlertType
from binance_trade_bot.monitoring.models import ApiErrorType, ApiErrorSeverity
from binance_trade_bot.models import Coin, Pair


class TestApiErrorTracker(unittest.TestCase):
    """Test cases for ApiErrorTracker class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock()
        self.mock_logger = Mock()
        self.mock_notifications = Mock()
        self.test_config = {
            'error_thresholds': {
                'rate_limit': {
                    'low': 0.05,
                    'medium': 0.10,
                    'high': 0.20,
                    'critical': 0.40
                },
                'connection_errors': {
                    'low': 0.02,
                    'medium': 0.05,
                    'high': 0.10,
                    'critical': 0.20
                },
                'timeout_errors': {
                    'low': 0.03,
                    'medium': 0.07,
                    'high': 0.15,
                    'critical': 0.30
                },
                'invalid_response': {
                    'low': 0.01,
                    'medium': 0.03,
                    'high': 0.05,
                    'critical': 0.10
                },
                'authentication_errors': {
                    'low': 0.001,
                    'medium': 0.005,
                    'high': 0.01,
                    'critical': 0.02
                }
            },
            'monitoring_periods': {
                ApiErrorType.RATE_LIMIT.value: 60,
                ApiErrorType.CONNECTION_ERROR.value: 60,
                ApiErrorType.TIMEOUT_ERROR.value: 60,
                ApiErrorType.INVALID_RESPONSE.value: 60,
                ApiErrorType.AUTHENTICATION_ERROR.value: 60
            },
            'alert_cooldown_period': 30,
            'enabled_endpoints': [
                'get_ticker_price',
                'get_order_book',
                'get_klines',
                'get_account_info',
                'create_order',
                'cancel_order'
            ],
            'error_tracking_window': 300,  # 5 minutes
            'max_errors_per_window': 100,
            'error_severity_weights': {
                ApiErrorType.RATE_LIMIT.value: 1.0,
                ApiErrorType.CONNECTION_ERROR.value: 2.0,
                ApiErrorType.TIMEOUT_ERROR.value: 1.5,
                ApiErrorType.INVALID_RESPONSE.value: 1.2,
                ApiErrorType.AUTHENTICATION_ERROR.value: 3.0
            }
        }
        
        self.api_error_tracker = ApiErrorTracker(
            database=self.mock_database,
            logger=self.mock_logger,
            notifications=self.mock_notifications,
            config=self.test_config,
            binance_manager=Mock()
        )
        
        # Create test coins
        self.test_coin_btc = Coin('BTC')
        self.test_coin_eth = Coin('ETH')
        
        # Create test pairs
        self.test_pair_btc_eth = Pair(self.test_coin_btc, self.test_coin_eth)
        
    def test_api_error_tracker_initialization(self):
        """Test API error tracker initialization."""
        self.assertEqual(self.api_error_tracker.database, self.mock_database)
        self.assertEqual(self.api_error_tracker.logger, self.mock_logger)
        self.assertEqual(self.api_error_tracker.notifications, self.mock_notifications)
        self.assertEqual(self.api_error_tracker.config, self.test_config)
        self.assertTrue(self.api_error_tracker.enabled)
        
        # Check configuration
        self.assertEqual(
            self.api_error_tracker.error_thresholds,
            self.test_config['error_thresholds']
        )
        self.assertEqual(
            self.api_error_tracker.monitoring_periods,
            self.test_config['monitoring_periods']
        )
        self.assertEqual(
            self.api_error_tracker.alert_cooldown_period,
            self.test_config['alert_cooldown_period']
        )
        self.assertEqual(
            self.api_error_tracker.enabled_endpoints,
            self.test_config['enabled_endpoints']
        )
        self.assertEqual(
            self.api_error_tracker.error_tracking_window,
            self.test_config['error_tracking_window']
        )
        self.assertEqual(
            self.api_error_tracker.max_errors_per_window,
            self.test_config['max_errors_per_window']
        )
        self.assertEqual(
            self.api_error_tracker.error_severity_weights,
            self.test_config['error_severity_weights']
        )
    
    async def test_collect_data(self):
        """Test data collection for API error tracking."""
        # Mock database session
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        # Mock error history data
        mock_error_history = [
            Mock(
                id=1,
                endpoint='get_ticker_price',
                error_type=ApiErrorType.RATE_LIMIT.value,
                datetime=datetime.utcnow() - timedelta(minutes=10),
                resolved=True
            ),
            Mock(
                id=2,
                endpoint='get_klines',
                error_type=ApiErrorType.CONNECTION_ERROR.value,
                datetime=datetime.utcnow() - timedelta(minutes=20),
                resolved=False
            ),
            Mock(
                id=3,
                endpoint='get_account_info',
                error_type=ApiErrorType.TIMEOUT_ERROR.value,
                datetime=datetime.utcnow() - timedelta(minutes=30),
                resolved=True
            )
        ]
        
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_error_history
        
        data = await self.api_error_tracker.collect_data()
        
        # Verify data structure
        self.assertIn('error_history', data)
        self.assertIn('endpoint_stats', data)
        self.assertIn('timestamp', data)
        
        # Verify error history
        self.assertEqual(len(data['error_history']), 3)
        
        # Verify endpoint stats
        self.assertIn('get_ticker_price', data['endpoint_stats'])
        self.assertIn('get_klines', data['endpoint_stats'])
        self.assertIn('get_account_info', data['endpoint_stats'])
        
        # Verify timestamp
        self.assertIsInstance(data['timestamp'], datetime)
    
    async def test_collect_data_no_errors(self):
        """Test data collection when no errors are present."""
        # Mock database session
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        # Mock empty error history
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        
        data = await self.api_error_tracker.collect_data()
        
        self.assertEqual(len(data['error_history']), 0)
        self.assertEqual(len(data['endpoint_stats']), 0)
    
    async def test_analyze_data(self):
        """Test data analysis for API error tracking."""
        # Create test data with high error rate
        test_data = {
            'error_history': [
                Mock(
                    id=1,
                    endpoint='get_ticker_price',
                    error_type=ApiErrorType.RATE_LIMIT.value,
                    datetime=datetime.utcnow() - timedelta(minutes=10),
                    resolved=True
                ),
                Mock(
                    id=2,
                    endpoint='get_ticker_price',
                    error_type=ApiErrorType.RATE_LIMIT.value,
                    datetime=datetime.utcnow() - timedelta(minutes=20),
                    resolved=False
                ),
                Mock(
                    id=3,
                    endpoint='get_klines',
                    error_type=ApiErrorType.CONNECTION_ERROR.value,
                    datetime=datetime.utcnow() - timedelta(minutes=30),
                    resolved=False
                )
            ],
            'endpoint_stats': {
                'get_ticker_price': {
                    'total_calls': 100,
                    'error_calls': 15,
                    'success_rate': 0.85
                },
                'get_klines': {
                    'total_calls': 50,
                    'error_calls': 10,
                    'success_rate': 0.80
                }
            },
            'timestamp': datetime.utcnow()
        }
        
        alerts = await self.api_error_tracker.analyze_data(test_data)
        
        # Verify alerts are generated
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertIn(alert.alert_type, [AlertType.API_ERROR_RATE_EXCEEDED, AlertType.API_CONNECTION_ISSUES])
            self.assertIn(alert.severity, [AlertSeverity.LOW, AlertSeverity.MEDIUM, AlertSeverity.HIGH, AlertSeverity.CRITICAL])
    
    async def test_analyze_data_normal_errors(self):
        """Test data analysis when error rates are normal."""
        # Create test data with normal error rates
        test_data = {
            'error_history': [
                Mock(
                    id=1,
                    endpoint='get_ticker_price',
                    error_type=ApiErrorType.RATE_LIMIT.value,
                    datetime=datetime.utcnow() - timedelta(minutes=10),
                    resolved=True
                )
            ],
            'endpoint_stats': {
                'get_ticker_price': {
                    'total_calls': 100,
                    'error_calls': 2,
                    'success_rate': 0.98
                }
            },
            'timestamp': datetime.utcnow()
        }
        
        alerts = await self.api_error_tracker.analyze_data(test_data)
        
        # No alerts should be generated for normal error rates
        self.assertEqual(len(alerts), 0)
    
    async def test_calculate_error_rate(self):
        """Test error rate calculation."""
        # Test error rate calculation
        total_calls = 100
        error_calls = 15
        
        error_rate = await self.api_error_tracker._calculate_error_rate(total_calls, error_calls)
        
        # Should be 0.15 (15/100)
        self.assertEqual(error_rate, 0.15)
    
    async def test_calculate_error_rate_zero_calls(self):
        """Test error rate calculation with zero calls."""
        error_rate = await self.api_error_tracker._calculate_error_rate(0, 0)
        
        # Should be 0.0 when no calls
        self.assertEqual(error_rate, 0.0)
    
    async def test_calculate_error_rate_zero_errors(self):
        """Test error rate calculation with zero errors."""
        error_rate = await self.api_error_tracker._calculate_error_rate(100, 0)
        
        # Should be 0.0 when no errors
        self.assertEqual(error_rate, 0.0)
    
    async def test_determine_error_severity(self):
        """Test error severity determination."""
        thresholds = {
            'low': 0.05,
            'medium': 0.10,
            'high': 0.20,
            'critical': 0.40
        }
        
        # Test various error rates
        test_cases = [
            (0.03, None),  # Below low threshold
            (0.07, AlertSeverity.LOW),
            (0.15, AlertSeverity.MEDIUM),
            (0.25, AlertSeverity.HIGH),
            (0.45, AlertSeverity.CRITICAL)
        ]
        
        for error_rate, expected_severity in test_cases:
            result = self.api_error_tracker._determine_error_severity(error_rate, thresholds)
            self.assertEqual(result, expected_severity)
    
    async def test_check_endpoint_errors(self):
        """Test endpoint error checking."""
        # Create test endpoint stats with high error rate
        endpoint_stats = {
            'get_ticker_price': {
                'total_calls': 100,
                'error_calls': 25,
                'success_rate': 0.75
            },
            'get_klines': {
                'total_calls': 50,
                'error_calls': 5,
                'success_rate': 0.90
            }
        }
        
        alerts = await self.api_error_tracker._check_endpoint_errors(endpoint_stats)
        
        # Alerts should be generated for high error rate
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertIn(alert.alert_type, [AlertType.API_ERROR_RATE_EXCEEDED, AlertType.API_CONNECTION_ISSUES])
    
    async def test_check_endpoint_errors_normal(self):
        """Test endpoint error checking with normal error rates."""
        # Create test endpoint stats with normal error rates
        endpoint_stats = {
            'get_ticker_price': {
                'total_calls': 100,
                'error_calls': 2,
                'success_rate': 0.98
            }
        }
        
        alerts = await self.api_error_tracker._check_endpoint_errors(endpoint_stats)
        
        # No alerts should be generated for normal error rates
        self.assertEqual(len(alerts), 0)
    
    async def test_check_connection_errors(self):
        """Test connection error checking."""
        # Create test error history with connection errors
        error_history = [
            Mock(
                id=1,
                endpoint='get_klines',
                error_type=ApiErrorType.CONNECTION_ERROR.value,
                datetime=datetime.utcnow() - timedelta(minutes=10),
                resolved=False
            ),
            Mock(
                id=2,
                endpoint='get_account_info',
                error_type=ApiErrorType.CONNECTION_ERROR.value,
                datetime=datetime.utcnow() - timedelta(minutes=20),
                resolved=False
            )
        ]
        
        alerts = await self.api_error_tracker._check_connection_errors(error_history)
        
        # Alerts should be generated for connection errors
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertEqual(alert.alert_type, AlertType.API_CONNECTION_ISSUES)
    
    async def test_check_connection_errors_normal(self):
        """Test connection error checking with normal connection."""
        # Create test error history with no connection errors
        error_history = [
            Mock(
                id=1,
                endpoint='get_ticker_price',
                error_type=ApiErrorType.RATE_LIMIT.value,
                datetime=datetime.utcnow() - timedelta(minutes=10),
                resolved=True
            )
        ]
        
        alerts = await self.api_error_tracker._check_connection_errors(error_history)
        
        # No alerts should be generated for normal connection
        self.assertEqual(len(alerts), 0)
    
    async def test_store_error_data(self):
        """Test error data storage."""
        # Create test alert
        test_alert = MonitoringAlert(
            alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
            severity=AlertSeverity.HIGH,
            title="Test API Error Alert",
            description="Test API error alert"
        )
        
        # Create test error data
        error_data = {
            'endpoint': 'get_ticker_price',
            'error_type': ApiErrorType.RATE_LIMIT.value,
            'error_rate': 0.25,
            'threshold_value': 0.20,
            'total_calls': 100,
            'error_calls': 25
        }
        
        # Mock database session
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        await self.api_error_tracker._store_error_data(test_alert, error_data)
        
        # Verify database operation
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
    
    async def test_generate_report(self):
        """Test report generation."""
        # Create test alerts
        test_alerts = [
            MonitoringAlert(
                alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                severity=AlertSeverity.HIGH,
                title="High Error Rate Alert",
                description="High error rate detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.API_CONNECTION_ISSUES,
                severity=AlertSeverity.MEDIUM,
                title="Connection Issues Alert",
                description="Connection issues detected"
            )
        ]
        
        report = await self.api_error_tracker.generate_report(test_alerts)
        
        # Verify report structure
        self.assertIn("🔧 API Error Tracking Report", report)
        self.assertIn("Total Alerts: 2", report)
        self.assertIn("HIGH Severity Alerts: 1", report)
        self.assertIn("MEDIUM Severity Alerts: 1", report)
        self.assertIn("Summary Statistics:", report)
    
    async def test_generate_report_no_alerts(self):
        """Test report generation when no alerts are present."""
        report = await self.api_error_tracker.generate_report([])
        
        self.assertIn("No API error alerts generated", report)
    
    async def test_calculate_weighted_error_score(self):
        """Test weighted error score calculation."""
        # Test weighted error score calculation
        error_counts = {
            ApiErrorType.RATE_LIMIT.value: 10,
            ApiErrorType.CONNECTION_ERROR.value: 5,
            ApiErrorType.TIMEOUT_ERROR.value: 3
        }
        
        weights = {
            ApiErrorType.RATE_LIMIT.value: 1.0,
            ApiErrorType.CONNECTION_ERROR.value: 2.0,
            ApiErrorType.TIMEOUT_ERROR.value: 1.5
        }
        
        score = await self.api_error_tracker._calculate_weighted_error_score(error_counts, weights)
        
        # Should be (10*1.0 + 5*2.0 + 3*1.5) / (10+5+3) = 22.0 / 18 = 1.222...
        self.assertAlmostEqual(score, 1.2222, places=4)
    
    async def test_get_error_time_buckets(self):
        """Test error time bucket calculation."""
        # Create test error times
        error_times = [
            datetime.utcnow() - timedelta(minutes=i*10) for i in range(6)  # 6 errors over 50 minutes
        ]
        
        buckets = await self.api_error_tracker._get_error_time_buckets(error_times, 60)  # 1-hour buckets
        
        # Should have 1 bucket with 6 errors
        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0], 6)
    
    async def test_get_error_time_buckets_empty(self):
        """Test error time bucket calculation with no errors."""
        buckets = await self.api_error_tracker._get_error_time_buckets([], 60)
        
        # Should have empty buckets
        self.assertEqual(len(buckets), 0)
    
    async def test_analyze_error_patterns(self):
        """Test error pattern analysis."""
        # Create test error history with pattern
        error_history = [
            Mock(
                id=i,
                endpoint='get_ticker_price',
                error_type=ApiErrorType.RATE_LIMIT.value,
                datetime=datetime.utcnow() - timedelta(minutes=i*5),
                resolved=i % 2 == 0  # Alternating resolved/unresolved
            ) for i in range(10)
        ]
        
        patterns = await self.api_error_tracker._analyze_error_patterns(error_history)
        
        # Should detect patterns
        self.assertIn('rate_limit_burst', patterns)
        self.assertIn('persistent_errors', patterns)
        self.assertIn('error_clusters', patterns)
    
    async def test_analyze_error_patterns_empty(self):
        """Test error pattern analysis with no errors."""
        patterns = await self.api_error_tracker._analyze_error_patterns([])
        
        # Should return empty patterns
        self.assertEqual(len(patterns), 0)
    
    async def test_check_error_thresholds(self):
        """Test error threshold checking."""
        # Test various threshold scenarios
        test_cases = [
            (0.05, 0.10, False),  # Below threshold
            (0.15, 0.10, True),   # Above threshold
            (0.10, 0.10, False),  # Equal to threshold (not above)
        ]
        
        for error_rate, threshold, expected_result in test_cases:
            result = self.api_error_tracker._check_error_thresholds(error_rate, threshold)
            self.assertEqual(result, expected_result)
    
    async def test_get_endpoint_error_stats(self):
        """Test endpoint error statistics calculation."""
        # Create test error history
        error_history = [
            Mock(
                id=1,
                endpoint='get_ticker_price',
                error_type=ApiErrorType.RATE_LIMIT.value,
                datetime=datetime.utcnow() - timedelta(minutes=10),
                resolved=True
            ),
            Mock(
                id=2,
                endpoint='get_ticker_price',
                error_type=ApiErrorType.CONNECTION_ERROR.value,
                datetime=datetime.utcnow() - timedelta(minutes=20),
                resolved=False
            ),
            Mock(
                id=3,
                endpoint='get_klines',
                error_type=ApiErrorType.RATE_LIMIT.value,
                datetime=datetime.utcnow() - timedelta(minutes=30),
                resolved=True
            )
        ]
        
        stats = await self.api_error_tracker._get_endpoint_error_stats(error_history)
        
        # Should calculate statistics for each endpoint
        self.assertIn('get_ticker_price', stats)
        self.assertIn('get_klines', stats)
        
        # Verify get_ticker_price stats
        ticker_stats = stats['get_ticker_price']
        self.assertEqual(ticker_stats['total_errors'], 2)
        self.assertEqual(ticker_stats['resolved_errors'], 1)
        self.assertEqual(ticker_stats['unresolved_errors'], 1)
        self.assertEqual(ticker_stats['error_types'], ['RATE_LIMIT', 'CONNECTION_ERROR'])
        
        # Verify get_klines stats
        klines_stats = stats['get_klines']
        self.assertEqual(klines_stats['total_errors'], 1)
        self.assertEqual(klines_stats['resolved_errors'], 1)
        self.assertEqual(klines_stats['unresolved_errors'], 0)
        self.assertEqual(klines_stats['error_types'], ['RATE_LIMIT'])


if __name__ == '__main__':
    unittest.main()