"""
Unit tests for trading frequency monitor module.

This module contains comprehensive unit tests for the trading frequency monitor
functionality.

Created: 2025-08-05
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import pandas as pd
import numpy as np

from binance_trade_bot.monitoring.trading_frequency_monitor import TradingFrequencyMonitor
from binance_trade_bot.monitoring.base import MonitoringAlert, AlertSeverity, AlertType
from binance_trade_bot.monitoring.models import TradingFrequencyMetric
from binance_trade_bot.models import Coin, Pair


class TestTradingFrequencyMonitor(unittest.TestCase):
    """Test cases for TradingFrequencyMonitor class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock()
        self.mock_logger = Mock()
        self.mock_notifications = Mock()
        self.test_config = {
            'frequency_thresholds': {
                'trades_per_hour': {
                    'low': 5,
                    'medium': 10,
                    'high': 20,
                    'critical': 50
                },
                'trades_per_day': {
                    'low': 50,
                    'medium': 100,
                    'high': 200,
                    'critical': 500
                },
                'consecutive_trades': {
                    'low': 3,
                    'medium': 5,
                    'high': 10,
                    'critical': 20
                },
                'trade_frequency_ratio': {
                    'low': 1.5,
                    'medium': 2.0,
                    'high': 3.0,
                    'critical': 5.0
                }
            },
            'monitoring_periods': {
                TradingFrequencyMetric.TRADES_PER_HOUR.value: 60,
                TradingFrequencyMetric.TRADES_PER_DAY.value: 1440,
                TradingFrequencyMetric.CONSECUTIVE_TRADES.value: 60,
                TradingFrequencyMetric.TRADE_FREQUENCY_RATIO.value: 60
            },
            'alert_cooldown_period': 30,
            'enabled_coins': ['BTC', 'ETH', 'BNB'],
            'enabled_pairs': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT'],
            'max_trades_per_hour': 30,
            'max_trades_per_day': 200,
            'max_consecutive_trades': 15,
            'trade_frequency_comparison_periods': [1, 24, 168]  # 1 hour, 24 hours, 1 week
        }
        
        self.frequency_monitor = TradingFrequencyMonitor(
            database=self.mock_database,
            logger=self.mock_logger,
            notifications=self.mock_notifications,
            config=self.test_config,
            binance_manager=Mock()
        )
        
        # Create test coins
        self.test_coin_btc = Coin('BTC')
        self.test_coin_eth = Coin('ETH')
        self.test_coin_bnb = Coin('BNB')
        
        # Create test pairs
        self.test_pair_btc_eth = Pair(self.test_coin_btc, self.test_coin_eth)
        self.test_pair_eth_btc = Pair(self.test_coin_eth, self.test_coin_btc)
        
    def test_trading_frequency_monitor_initialization(self):
        """Test trading frequency monitor initialization."""
        self.assertEqual(self.frequency_monitor.database, self.mock_database)
        self.assertEqual(self.frequency_monitor.logger, self.mock_logger)
        self.assertEqual(self.frequency_monitor.notifications, self.mock_notifications)
        self.assertEqual(self.frequency_monitor.config, self.test_config)
        self.assertTrue(self.frequency_monitor.enabled)
        
        # Check configuration
        self.assertEqual(
            self.frequency_monitor.frequency_thresholds,
            self.test_config['frequency_thresholds']
        )
        self.assertEqual(
            self.frequency_monitor.monitoring_periods,
            self.test_config['monitoring_periods']
        )
        self.assertEqual(
            self.frequency_monitor.alert_cooldown_period,
            self.test_config['alert_cooldown_period']
        )
        self.assertEqual(
            self.frequency_monitor.enabled_coins,
            self.test_config['enabled_coins']
        )
        self.assertEqual(
            self.frequency_monitor.enabled_pairs,
            self.test_config['enabled_pairs']
        )
        self.assertEqual(
            self.frequency_monitor.max_trades_per_hour,
            self.test_config['max_trades_per_hour']
        )
        self.assertEqual(
            self.frequency_monitor.max_trades_per_day,
            self.test_config['max_trades_per_day']
        )
        self.assertEqual(
            self.frequency_monitor.max_consecutive_trades,
            self.test_config['max_consecutive_trades']
        )
    
    async def test_collect_data(self):
        """Test data collection for trading frequency monitoring."""
        # Mock database session
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        # Mock coin data
        mock_coins = [self.test_coin_btc, self.test_coin_eth, self.test_coin_bnb]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_coins
        
        # Mock pair data
        mock_pairs = [self.test_pair_btc_eth, self.test_pair_eth_btc]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_pairs
        
        # Mock trade history data
        mock_trades = [
            Mock(
                id=1,
                from_coin_id='BTC',
                to_coin_id='ETH',
                selling=True,
                datetime=datetime.utcnow() - timedelta(minutes=10),
                state='COMPLETE'
            ),
            Mock(
                id=2,
                from_coin_id='ETH',
                to_coin_id='BTC',
                selling=False,
                datetime=datetime.utcnow() - timedelta(minutes=20),
                state='COMPLETE'
            ),
            Mock(
                id=3,
                from_coin_id='BTC',
                to_coin_id='ETH',
                selling=True,
                datetime=datetime.utcnow() - timedelta(minutes=30),
                state='COMPLETE'
            )
        ]
        
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_trades
        
        data = await self.frequency_monitor.collect_data()
        
        # Verify data structure
        self.assertIn('coins', data)
        self.assertIn('pairs', data)
        self.assertIn('trade_history', data)
        self.assertIn('timestamp', data)
        
        # Verify coin data
        self.assertEqual(len(data['coins']), 3)
        for coin_data in data['coins']:
            self.assertIn('symbol', coin_data)
            self.assertIn('trades_count', coin_data)
            self.assertIn('last_trade_time', coin_data)
        
        # Verify pair data
        self.assertEqual(len(data['pairs']), 2)
        for pair_data in data['pairs']:
            self.assertIn('from_coin', pair_data)
            self.assertIn('to_coin', pair_data)
            self.assertIn('trades_count', pair_data)
            self.assertIn('last_trade_time', pair_data)
        
        # Verify trade history
        self.assertEqual(len(data['trade_history']), 3)
        
        # Verify timestamp
        self.assertIsInstance(data['timestamp'], datetime)
    
    async def test_collect_data_no_trades(self):
        """Test data collection when no trades are present."""
        # Mock database session
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        # Mock empty trade history
        mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        
        data = await self.frequency_monitor.collect_data()
        
        self.assertEqual(len(data['trade_history']), 0)
        self.assertEqual(len(data['coins']), 0)
        self.assertEqual(len(data['pairs']), 0)
    
    async def test_analyze_data(self):
        """Test data analysis for trading frequency monitoring."""
        # Create test data with high trading frequency
        test_data = {
            'coins': [
                {
                    'symbol': 'BTC',
                    'trades_count': 25,
                    'last_trade_time': datetime.utcnow() - timedelta(minutes=10)
                },
                {
                    'symbol': 'ETH',
                    'trades_count': 15,
                    'last_trade_time': datetime.utcnow() - timedelta(minutes=20)
                }
            ],
            'pairs': [
                {
                    'from_coin': 'BTC',
                    'to_coin': 'ETH',
                    'trades_count': 20,
                    'last_trade_time': datetime.utcnow() - timedelta(minutes=15)
                }
            ],
            'trade_history': [
                Mock(
                    id=1,
                    from_coin_id='BTC',
                    to_coin_id='ETH',
                    selling=True,
                    datetime=datetime.utcnow() - timedelta(minutes=10),
                    state='COMPLETE'
                ),
                Mock(
                    id=2,
                    from_coin_id='ETH',
                    to_coin_id='BTC',
                    selling=False,
                    datetime=datetime.utcnow() - timedelta(minutes=20),
                    state='COMPLETE'
                ),
                Mock(
                    id=3,
                    from_coin_id='BTC',
                    to_coin_id='ETH',
                    selling=True,
                    datetime=datetime.utcnow() - timedelta(minutes=30),
                    state='COMPLETE'
                )
            ],
            'timestamp': datetime.utcnow()
        }
        
        alerts = await self.frequency_monitor.analyze_data(test_data)
        
        # Verify alerts are generated
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertIn(alert.alert_type, [AlertType.HIGH_TRADING_FREQUENCY, AlertType.EXCESSIVE_TRADING])
            self.assertIn(alert.severity, [AlertSeverity.LOW, AlertSeverity.MEDIUM, AlertSeverity.HIGH, AlertSeverity.CRITICAL])
    
    async def test_analyze_data_normal_frequency(self):
        """Test data analysis when trading frequency is normal."""
        # Create test data with normal trading frequency
        test_data = {
            'coins': [
                {
                    'symbol': 'BTC',
                    'trades_count': 5,
                    'last_trade_time': datetime.utcnow() - timedelta(hours=2)
                }
            ],
            'pairs': [
                {
                    'from_coin': 'BTC',
                    'to_coin': 'ETH',
                    'trades_count': 3,
                    'last_trade_time': datetime.utcnow() - timedelta(hours=3)
                }
            ],
            'trade_history': [
                Mock(
                    id=1,
                    from_coin_id='BTC',
                    to_coin_id='ETH',
                    selling=True,
                    datetime=datetime.utcnow() - timedelta(hours=2),
                    state='COMPLETE'
                )
            ],
            'timestamp': datetime.utcnow()
        }
        
        alerts = await self.frequency_monitor.analyze_data(test_data)
        
        # No alerts should be generated for normal frequency
        self.assertEqual(len(alerts), 0)
    
    async def test_calculate_trades_per_hour(self):
        """Test trades per hour calculation."""
        # Test trades per hour calculation
        trade_times = [
            datetime.utcnow() - timedelta(minutes=i*10) for i in range(6)  # 6 trades over 50 minutes
        ]
        
        trades_per_hour = await self.frequency_monitor._calculate_trades_per_hour(trade_times)
        
        # Should be approximately 7.2 trades per hour (6 trades / (50/60) hours)
        self.assertAlmostEqual(trades_per_hour, 7.2, places=1)
    
    async def test_calculate_trades_per_day(self):
        """Test trades per day calculation."""
        # Test trades per day calculation
        trade_times = [
            datetime.utcnow() - timedelta(hours=i) for i in range(25)  # 25 trades over 24 hours
        ]
        
        trades_per_day = await self.frequency_monitor._calculate_trades_per_day(trade_times)
        
        # Should be 25 trades per day
        self.assertEqual(trades_per_day, 25)
    
    async def test_calculate_consecutive_trades(self):
        """Test consecutive trades calculation."""
        # Test consecutive trades calculation
        trade_times = [
            datetime.utcnow() - timedelta(minutes=i*5) for i in range(8)  # 8 consecutive trades
        ]
        
        consecutive_trades = await self.frequency_monitor._calculate_consecutive_trades(trade_times)
        
        # Should be 8 consecutive trades
        self.assertEqual(consecutive_trades, 8)
    
    async def test_calculate_trade_frequency_ratio(self):
        """Test trade frequency ratio calculation."""
        # Test trade frequency ratio calculation
        recent_trades = 20
        historical_trades = 10
        
        ratio = await self.frequency_monitor._calculate_trade_frequency_ratio(recent_trades, historical_trades)
        
        # Should be 2.0 (20/10)
        self.assertEqual(ratio, 2.0)
    
    async def test_determine_frequency_severity(self):
        """Test frequency severity determination."""
        thresholds = {
            'low': 5,
            'medium': 10,
            'high': 20,
            'critical': 50
        }
        
        # Test various frequency values
        test_cases = [
            (3, None),  # Below low threshold
            (7, AlertSeverity.LOW),
            (15, AlertSeverity.MEDIUM),
            (25, AlertSeverity.HIGH),
            (55, AlertSeverity.CRITICAL)
        ]
        
        for frequency, expected_severity in test_cases:
            result = self.frequency_monitor._determine_frequency_severity(frequency, thresholds)
            self.assertEqual(result, expected_severity)
    
    async def test_check_coin_frequency(self):
        """Test coin frequency checking."""
        # Create test coin data with high frequency
        coin_data = {
            'symbol': 'BTC',
            'trades_count': 25,
            'last_trade_time': datetime.utcnow() - timedelta(minutes=10)
        }
        
        alerts = await self.frequency_monitor._check_coin_frequency(coin_data)
        
        # Alerts should be generated for high frequency
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertEqual(alert.coin.symbol, 'BTC')
    
    async def test_check_coin_frequency_normal(self):
        """Test coin frequency checking with normal frequency."""
        # Create test coin data with normal frequency
        coin_data = {
            'symbol': 'BTC',
            'trades_count': 5,
            'last_trade_time': datetime.utcnow() - timedelta(hours=2)
        }
        
        alerts = await self.frequency_monitor._check_coin_frequency(coin_data)
        
        # No alerts should be generated for normal frequency
        self.assertEqual(len(alerts), 0)
    
    async def test_check_pair_frequency(self):
        """Test pair frequency checking."""
        # Create test pair data with high frequency
        pair_data = {
            'from_coin': 'BTC',
            'to_coin': 'ETH',
            'trades_count': 20,
            'last_trade_time': datetime.utcnow() - timedelta(minutes=15)
        }
        
        alerts = await self.frequency_monitor._check_pair_frequency(pair_data)
        
        # Alerts should be generated for high frequency
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertEqual(alert.pair.from_coin_id, 'BTC')
            self.assertEqual(alert.pair.to_coin_id, 'ETH')
    
    async def test_check_pair_frequency_normal(self):
        """Test pair frequency checking with normal frequency."""
        # Create test pair data with normal frequency
        pair_data = {
            'from_coin': 'BTC',
            'to_coin': 'ETH',
            'trades_count': 3,
            'last_trade_time': datetime.utcnow() - timedelta(hours=3)
        }
        
        alerts = await self.frequency_monitor._check_pair_frequency(pair_data)
        
        # No alerts should be generated for normal frequency
        self.assertEqual(len(alerts), 0)
    
    async def test_check_trade_frequency(self):
        """Test overall trade frequency checking."""
        # Create test trade history with high frequency
        trade_history = [
            Mock(
                id=i,
                from_coin_id='BTC',
                to_coin_id='ETH',
                selling=True,
                datetime=datetime.utcnow() - timedelta(minutes=i*5),
                state='COMPLETE'
            ) for i in range(15)  # 15 trades over 70 minutes
        ]
        
        alerts = await self.frequency_monitor._check_trade_frequency(trade_history)
        
        # Alerts should be generated for high frequency
        self.assertGreater(len(alerts), 0)
    
    async def test_check_trade_frequency_normal(self):
        """Test overall trade frequency checking with normal frequency."""
        # Create test trade history with normal frequency
        trade_history = [
            Mock(
                id=1,
                from_coin_id='BTC',
                to_coin_id='ETH',
                selling=True,
                datetime=datetime.utcnow() - timedelta(hours=2),
                state='COMPLETE'
            )
        ]
        
        alerts = await self.frequency_monitor._check_trade_frequency(trade_history)
        
        # No alerts should be generated for normal frequency
        self.assertEqual(len(alerts), 0)
    
    async def test_store_frequency_data(self):
        """Test frequency data storage."""
        # Create test alert
        test_alert = MonitoringAlert(
            alert_type=AlertType.HIGH_TRADING_FREQUENCY,
            severity=AlertSeverity.HIGH,
            title="Test Frequency Alert",
            description="Test frequency alert"
        )
        
        # Create test frequency data
        frequency_data = {
            'metric_type': TradingFrequencyMetric.TRADES_PER_HOUR.value,
            'frequency_value': 25,
            'threshold_value': 20,
            'coin': self.test_coin_btc,
            'pair': self.test_pair_btc_eth
        }
        
        # Mock database session
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        await self.frequency_monitor._store_frequency_data(test_alert, frequency_data)
        
        # Verify database operation
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
    
    async def test_generate_report(self):
        """Test report generation."""
        # Create test alerts
        test_alerts = [
            MonitoringAlert(
                alert_type=AlertType.HIGH_TRADING_FREQUENCY,
                severity=AlertSeverity.HIGH,
                title="High Frequency Alert",
                description="High frequency detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.EXCESSIVE_TRADING,
                severity=AlertSeverity.MEDIUM,
                title="Excessive Trading Alert",
                description="Excessive trading detected"
            )
        ]
        
        report = await self.frequency_monitor.generate_report(test_alerts)
        
        # Verify report structure
        self.assertIn("📊 Trading Frequency Report", report)
        self.assertIn("Total Alerts: 2", report)
        self.assertIn("HIGH Severity Alerts: 1", report)
        self.assertIn("MEDIUM Severity Alerts: 1", report)
        self.assertIn("Summary Statistics:", report)
    
    async def test_generate_report_no_alerts(self):
        """Test report generation when no alerts are present."""
        report = await self.frequency_monitor.generate_report([])
        
        self.assertIn("No trading frequency alerts generated", report)
    
    async def test_check_thresholds(self):
        """Test threshold checking."""
        # Test various threshold scenarios
        test_cases = [
            (5, 10, False),  # Below threshold
            (15, 10, True),  # Above threshold
            (10, 10, False),  # Equal to threshold (not above)
        ]
        
        for value, threshold, expected_result in test_cases:
            result = self.frequency_monitor._check_thresholds(value, threshold)
            self.assertEqual(result, expected_result)
    
    async def test_get_trade_time_buckets(self):
        """Test trade time bucket calculation."""
        # Create test trade times
        trade_times = [
            datetime.utcnow() - timedelta(hours=i) for i in range(24)  # 24 trades over 24 hours
        ]
        
        buckets = await self.frequency_monitor._get_trade_time_buckets(trade_times, 60)  # 1-hour buckets
        
        # Should have 24 buckets with 1 trade each
        self.assertEqual(len(buckets), 24)
        for bucket_count in buckets:
            self.assertEqual(bucket_count, 1)
    
    async def test_get_trade_time_buckets_empty(self):
        """Test trade time bucket calculation with empty trades."""
        buckets = await self.frequency_monitor._get_trade_time_buckets([], 60)
        
        # Should have empty buckets
        self.assertEqual(len(buckets), 0)
    
    async def test_analyze_trade_patterns(self):
        """Test trade pattern analysis."""
        # Create test trade history with pattern
        trade_history = [
            Mock(
                id=i,
                from_coin_id='BTC',
                to_coin_id='ETH',
                selling=i % 2 == 0,  # Alternating sell/buy
                datetime=datetime.utcnow() - timedelta(minutes=i*10),
                state='COMPLETE'
            ) for i in range(10)
        ]
        
        patterns = await self.frequency_monitor._analyze_trade_patterns(trade_history)
        
        # Should detect patterns
        self.assertIn('alternating_trades', patterns)
        self.assertIn('rapid_trades', patterns)
        self.assertIn('consecutive_trades', patterns)
    
    async def test_analyze_trade_patterns_empty(self):
        """Test trade pattern analysis with empty trades."""
        patterns = await self.frequency_monitor._analyze_trade_patterns([])
        
        # Should return empty patterns
        self.assertEqual(len(patterns), 0)


if __name__ == '__main__':
    unittest.main()