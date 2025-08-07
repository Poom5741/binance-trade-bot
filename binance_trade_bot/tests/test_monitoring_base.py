"""
Unit tests for monitoring base classes.

This module contains comprehensive unit tests for the monitoring system
base classes and data models.

Created: 2025-08-05
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import uuid

from binance_trade_bot.monitoring.base import (
    MonitoringService,
    MonitoringAlert,
    AlertSeverity,
    AlertType,
    AlertStatus
)
from binance_trade_bot.monitoring.models import (
    VolatilityData,
    PerformanceData,
    TradingFrequencyData,
    ApiErrorData,
    VolatilityMetric,
    PerformanceMetric,
    TradingFrequencyMetric,
    ApiErrorType,
    ApiErrorSeverity
)


class TestMonitoringAlert(unittest.TestCase):
    """Test cases for MonitoringAlert class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.alert_uuid = str(uuid.uuid4())
        self.test_alert = MonitoringAlert(
            alert_uuid=self.alert_uuid,
            alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
            severity=AlertSeverity.HIGH,
            title="Test Alert",
            description="This is a test alert",
            coin=None,
            pair=None,
            threshold_value=0.05,
            current_value=0.08,
            metadata={'test': 'data'},
            context={'test': 'context'}
        )
    
    def test_alert_initialization(self):
        """Test alert initialization."""
        self.assertEqual(self.test_alert.alert_uuid, self.alert_uuid)
        self.assertEqual(self.test_alert.alert_type, AlertType.MARKET_VOLATILITY_DETECTED)
        self.assertEqual(self.test_alert.severity, AlertSeverity.HIGH)
        self.assertEqual(self.test_alert.title, "Test Alert")
        self.assertEqual(self.test_alert.description, "This is a test alert")
        self.assertIsNone(self.test_alert.coin)
        self.assertIsNone(self.test_alert.pair)
        self.assertEqual(self.test_alert.threshold_value, 0.05)
        self.assertEqual(self.test_alert.current_value, 0.08)
        self.assertEqual(self.test_alert.metadata, {'test': 'data'})
        self.assertEqual(self.test_alert.context, {'test': 'context'})
        self.assertEqual(self.test_alert.status, AlertStatus.OPEN)
        self.assertIsNotNone(self.test_alert.created_at)
    
    def test_alert_info(self):
        """Test alert info method."""
        info = self.test_alert.info()
        
        expected_keys = [
            'alert_uuid', 'alert_type', 'severity', 'title', 'description',
            'coin', 'pair', 'threshold_value', 'current_value', 'metadata',
            'context', 'status', 'created_at'
        ]
        
        for key in expected_keys:
            self.assertIn(key, info)
        
        self.assertEqual(info['alert_uuid'], self.alert_uuid)
        self.assertEqual(info['alert_type'], AlertType.MARKET_VOLATILITY_DETECTED.value)
        self.assertEqual(info['severity'], AlertSeverity.HIGH.value)
        self.assertEqual(info['title'], "Test Alert")
        self.assertEqual(info['description'], "This is a test alert")
        self.assertIsNone(info['coin'])
        self.assertIsNone(info['pair'])
        self.assertEqual(info['threshold_value'], 0.05)
        self.assertEqual(info['current_value'], 0.08)
        self.assertEqual(info['metadata'], {'test': 'data'})
        self.assertEqual(info['context'], {'test': 'context'})
        self.assertEqual(info['status'], AlertStatus.OPEN.value)
        self.assertIsNotNone(info['created_at'])
    
    def test_alert_status_update(self):
        """Test alert status update."""
        # Test status update
        self.test_alert.update_status(AlertStatus.RESOLVED)
        self.assertEqual(self.test_alert.status, AlertStatus.RESOLVED)
        
        # Test invalid status
        with self.assertRaises(ValueError):
            self.test_alert.update_status('invalid_status')
    
    def test_alert_equality(self):
        """Test alert equality."""
        # Create identical alert
        identical_alert = MonitoringAlert(
            alert_uuid=self.alert_uuid,
            alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
            severity=AlertSeverity.HIGH,
            title="Test Alert",
            description="This is a test alert"
        )
        
        # Create different alert
        different_alert = MonitoringAlert(
            alert_uuid=str(uuid.uuid4()),
            alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
            severity=AlertSeverity.MEDIUM,
            title="Different Alert",
            description="This is a different alert"
        )
        
        # Test equality
        self.assertEqual(self.test_alert, identical_alert)
        self.assertNotEqual(self.test_alert, different_alert)


class TestMonitoringService(unittest.TestCase):
    """Test cases for MonitoringService base class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock()
        self.mock_logger = Mock()
        self.mock_notifications = Mock()
        self.test_config = {'test': 'config'}
        
        # Create a concrete implementation for testing
        class TestMonitoringService(MonitoringService):
            def __init__(self, database, logger, notifications, config):
                super().__init__(database, logger, notifications, config)
                self.test_data = None
            
            async def collect_data(self):
                self.test_data = {'test': 'data'}
                return self.test_data
            
            async def analyze_data(self, data):
                if data.get('test') == 'trigger_alert':
                    return [MonitoringAlert(
                        alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                        severity=AlertSeverity.HIGH,
                        title="Test Alert",
                        description="Test alert triggered"
                    )]
                return []
        
        self.service = TestMonitoringService(
            self.mock_database,
            self.mock_logger,
            self.mock_notifications,
            self.test_config
        )
    
    def test_service_initialization(self):
        """Test service initialization."""
        self.assertEqual(self.service.database, self.mock_database)
        self.assertEqual(self.service.logger, self.mock_logger)
        self.assertEqual(self.service.notifications, self.mock_notifications)
        self.assertEqual(self.service.config, self.test_config)
        self.assertTrue(self.service.enabled)
    
    async def test_collect_data(self):
        """Test data collection."""
        data = await self.service.collect_data()
        
        self.assertEqual(data, {'test': 'data'})
        self.assertEqual(self.service.test_data, {'test': 'data'})
    
    async def test_analyze_data(self):
        """Test data analysis."""
        # Test normal case
        data = {'test': 'normal'}
        alerts = await self.service.analyze_data(data)
        self.assertEqual(len(alerts), 0)
        
        # Test alert case
        data = {'test': 'trigger_alert'}
        alerts = await self.service.analyze_data(data)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].alert_type, AlertType.MARKET_VOLATILITY_DETECTED)
        self.assertEqual(alerts[0].severity, AlertSeverity.HIGH)
    
    async def test_send_alert(self):
        """Test alert sending."""
        test_alert = MonitoringAlert(
            alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
            severity=AlertSeverity.HIGH,
            title="Test Alert",
            description="Test alert"
        )
        
        await self.service.send_alert(test_alert)
        
        # Verify notification was sent
        self.mock_notifications.send_notification.assert_called_once()
        
        # Verify alert was logged
        self.mock_logger.info.assert_called()
    
    async def test_send_alert_disabled(self):
        """Test alert sending when service is disabled."""
        self.service.enabled = False
        
        test_alert = MonitoringAlert(
            alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
            severity=AlertSeverity.HIGH,
            title="Test Alert",
            description="Test alert"
        )
        
        await self.service.send_alert(test_alert)
        
        # Verify notification was not sent
        self.mock_notifications.send_notification.assert_not_called()
    
    def test_service_configuration(self):
        """Test service configuration methods."""
        # Test default configuration
        self.assertEqual(self.service.get_config('test'), 'config')
        self.assertIsNone(self.service.get_config('nonexistent'))
        
        # Test configuration with default
        self.assertEqual(self.service.get_config('nonexistent', 'default'), 'default')
        
        # Test configuration update
        self.service.update_config({'new': 'value'})
        self.assertEqual(self.service.get_config('new'), 'value')
        self.assertEqual(self.service.get_config('test'), 'config')  # Existing value preserved


class TestVolatilityData(unittest.TestCase):
    """Test cases for VolatilityData model."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_coin = Mock()
        self.test_coin.symbol = 'BTC'
        
        self.test_pair = Mock()
        self.test_pair.id = '1'
        
        self.test_volatility_data = VolatilityData(
            coin=self.test_coin,
            pair=self.test_pair,
            metric_type=VolatilityMetric.STANDARD_DEVIATION,
            period=60,
            volatility_value=0.05,
            threshold_value=0.03,
            metadata={'test': 'data'}
        )
    
    def test_volatility_data_initialization(self):
        """Test volatility data initialization."""
        self.assertEqual(self.test_volatility_data.coin, self.test_coin)
        self.assertEqual(self.test_volatility_data.pair, self.test_pair)
        self.assertEqual(self.test_volatility_data.metric_type, VolatilityMetric.STANDARD_DEVIATION)
        self.assertEqual(self.test_volatility_data.period, 60)
        self.assertEqual(self.test_volatility_data.volatility_value, 0.05)
        self.assertEqual(self.test_volatility_data.threshold_value, 0.03)
        self.assertEqual(self.test_volatility_data.metadata, {'test': 'data'})
        self.assertIsNotNone(self.test_volatility_data.created_at)
    
    def test_volatility_data_info(self):
        """Test volatility data info method."""
        info = self.test_volatility_data.info()
        
        expected_keys = [
            'coin', 'pair', 'metric_type', 'period', 'volatility_value',
            'threshold_value', 'metadata', 'created_at'
        ]
        
        for key in expected_keys:
            self.assertIn(key, info)
        
        self.assertEqual(info['coin'], self.test_coin.symbol)
        self.assertEqual(info['pair'], self.test_pair.id)
        self.assertEqual(info['metric_type'], VolatilityMetric.STANDARD_DEVIATION.value)
        self.assertEqual(info['period'], 60)
        self.assertEqual(info['volatility_value'], 0.05)
        self.assertEqual(info['threshold_value'], 0.03)
        self.assertEqual(info['metadata'], {'test': 'data'})
        self.assertIsNotNone(info['created_at'])


class TestPerformanceData(unittest.TestCase):
    """Test cases for PerformanceData model."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_coin = Mock()
        self.test_coin.symbol = 'BTC'
        
        self.test_performance_data = PerformanceData(
            coin=self.test_coin,
            metric_type=PerformanceMetric.PRICE_CHANGE_24H,
            period=1440,
            performance_value=0.15,
            threshold_value=0.10,
            metadata={'test': 'data'}
        )
    
    def test_performance_data_initialization(self):
        """Test performance data initialization."""
        self.assertEqual(self.test_performance_data.coin, self.test_coin)
        self.assertEqual(self.test_performance_data.metric_type, PerformanceMetric.PRICE_CHANGE_24H)
        self.assertEqual(self.test_performance_data.period, 1440)
        self.assertEqual(self.test_performance_data.performance_value, 0.15)
        self.assertEqual(self.test_performance_data.threshold_value, 0.10)
        self.assertEqual(self.test_performance_data.metadata, {'test': 'data'})
        self.assertIsNotNone(self.test_performance_data.created_at)
    
    def test_performance_data_info(self):
        """Test performance data info method."""
        info = self.test_performance_data.info()
        
        expected_keys = [
            'coin', 'metric_type', 'period', 'performance_value',
            'threshold_value', 'metadata', 'created_at'
        ]
        
        for key in expected_keys:
            self.assertIn(key, info)
        
        self.assertEqual(info['coin'], self.test_coin.symbol)
        self.assertEqual(info['metric_type'], PerformanceMetric.PRICE_CHANGE_24H.value)
        self.assertEqual(info['period'], 1440)
        self.assertEqual(info['performance_value'], 0.15)
        self.assertEqual(info['threshold_value'], 0.10)
        self.assertEqual(info['metadata'], {'test': 'data'})
        self.assertIsNotNone(info['created_at'])


class TestTradingFrequencyData(unittest.TestCase):
    """Test cases for TradingFrequencyData model."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_coin = Mock()
        self.test_coin.symbol = 'BTC'
        
        self.test_pair = Mock()
        self.test_pair.id = '1'
        
        self.test_frequency_data = TradingFrequencyData(
            coin=self.test_coin,
            pair=self.test_pair,
            metric_type=TradingFrequencyMetric.TRADES_PER_HOUR,
            period=60,
            frequency_value=15,
            threshold_value=10,
            metadata={'test': 'data'}
        )
    
    def test_trading_frequency_data_initialization(self):
        """Test trading frequency data initialization."""
        self.assertEqual(self.test_frequency_data.coin, self.test_coin)
        self.assertEqual(self.test_frequency_data.pair, self.test_pair)
        self.assertEqual(self.test_frequency_data.metric_type, TradingFrequencyMetric.TRADES_PER_HOUR)
        self.assertEqual(self.test_frequency_data.period, 60)
        self.assertEqual(self.test_frequency_data.frequency_value, 15)
        self.assertEqual(self.test_frequency_data.threshold_value, 10)
        self.assertEqual(self.test_frequency_data.metadata, {'test': 'data'})
        self.assertIsNotNone(self.test_frequency_data.created_at)
    
    def test_trading_frequency_data_info(self):
        """Test trading frequency data info method."""
        info = self.test_frequency_data.info()
        
        expected_keys = [
            'coin', 'pair', 'metric_type', 'period', 'frequency_value',
            'threshold_value', 'metadata', 'created_at'
        ]
        
        for key in expected_keys:
            self.assertIn(key, info)
        
        self.assertEqual(info['coin'], self.test_coin.symbol)
        self.assertEqual(info['pair'], self.test_pair.id)
        self.assertEqual(info['metric_type'], TradingFrequencyMetric.TRADES_PER_HOUR.value)
        self.assertEqual(info['period'], 60)
        self.assertEqual(info['frequency_value'], 15)
        self.assertEqual(info['threshold_value'], 10)
        self.assertEqual(info['metadata'], {'test': 'data'})
        self.assertIsNotNone(info['created_at'])


class TestApiErrorData(unittest.TestCase):
    """Test cases for ApiErrorData model."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_api_error_data = ApiErrorData(
            endpoint='get_ticker_price',
            error_type=ApiErrorType.RATE_LIMIT,
            period=60,
            error_value=0.15,
            threshold_value=0.10,
            metadata={'test': 'data'}
        )
    
    def test_api_error_data_initialization(self):
        """Test API error data initialization."""
        self.assertEqual(self.test_api_error_data.endpoint, 'get_ticker_price')
        self.assertEqual(self.test_api_error_data.error_type, ApiErrorType.RATE_LIMIT)
        self.assertEqual(self.test_api_error_data.period, 60)
        self.assertEqual(self.test_api_error_data.error_value, 0.15)
        self.assertEqual(self.test_api_error_data.threshold_value, 0.10)
        self.assertEqual(self.test_api_error_data.metadata, {'test': 'data'})
        self.assertIsNotNone(self.test_api_error_data.created_at)
    
    def test_api_error_data_info(self):
        """Test API error data info method."""
        info = self.test_api_error_data.info()
        
        expected_keys = [
            'endpoint', 'error_type', 'period', 'error_value',
            'threshold_value', 'metadata', 'created_at'
        ]
        
        for key in expected_keys:
            self.assertIn(key, info)
        
        self.assertEqual(info['endpoint'], 'get_ticker_price')
        self.assertEqual(info['error_type'], ApiErrorType.RATE_LIMIT.value)
        self.assertEqual(info['period'], 60)
        self.assertEqual(info['error_value'], 0.15)
        self.assertEqual(info['threshold_value'], 0.10)
        self.assertEqual(info['metadata'], {'test': 'data'})
        self.assertIsNotNone(info['created_at'])


if __name__ == '__main__':
    unittest.main()