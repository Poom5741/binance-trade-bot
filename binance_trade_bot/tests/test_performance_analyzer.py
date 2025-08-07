"""
Unit tests for performance analyzer module.

This module contains comprehensive unit tests for the performance analyzer
functionality.

Created: 2025-08-05
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import pandas as pd
import numpy as np

from binance_trade_bot.monitoring.performance_analyzer import PerformanceAnalyzer
from binance_trade_bot.monitoring.base import MonitoringAlert, AlertSeverity, AlertType
from binance_trade_bot.monitoring.models import PerformanceMetric
from binance_trade_bot.models import Coin, Pair


class TestPerformanceAnalyzer(unittest.TestCase):
    """Test cases for PerformanceAnalyzer class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock()
        self.mock_logger = Mock()
        self.mock_notifications = Mock()
        self.test_config = {
            'performance_thresholds': {
                'price_change_24h': {
                    'low': 0.05,
                    'medium': 0.10,
                    'high': 0.20,
                    'critical': 0.40
                },
                'price_change_1h': {
                    'low': 0.02,
                    'medium': 0.05,
                    'high': 0.10,
                    'critical': 0.20
                },
                'price_change_15m': {
                    'low': 0.01,
                    'medium': 0.03,
                    'high': 0.05,
                    'critical': 0.10
                },
                'volume_spike': {
                    'low': 2.0,
                    'medium': 5.0,
                    'high': 10.0,
                    'critical': 20.0
                },
                'market_cap_change': {
                    'low': 0.05,
                    'medium': 0.10,
                    'high': 0.20,
                    'critical': 0.40
                }
            },
            'monitoring_periods': {
                PerformanceMetric.PRICE_CHANGE_24H.value: 1440,
                PerformanceMetric.PRICE_CHANGE_1H.value: 60,
                PerformanceMetric.PRICE_CHANGE_15M.value: 15,
                PerformanceMetric.VOLUME_SPIKE.value: 60,
                PerformanceMetric.MARKET_CAP_CHANGE.value: 1440
            },
            'alert_cooldown_period': 30,
            'enabled_coins': ['BTC', 'ETH', 'BNB'],
            'volume_comparison_periods': [1, 24, 168]  # 1 hour, 24 hours, 1 week
        }
        
        self.performance_analyzer = PerformanceAnalyzer(
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
        
    def test_performance_analyzer_initialization(self):
        """Test performance analyzer initialization."""
        self.assertEqual(self.performance_analyzer.database, self.mock_database)
        self.assertEqual(self.performance_analyzer.logger, self.mock_logger)
        self.assertEqual(self.performance_analyzer.notifications, self.mock_notifications)
        self.assertEqual(self.performance_analyzer.config, self.test_config)
        self.assertTrue(self.performance_analyzer.enabled)
        
        # Check configuration
        self.assertEqual(
            self.performance_analyzer.performance_thresholds,
            self.test_config['performance_thresholds']
        )
        self.assertEqual(
            self.performance_analyzer.monitoring_periods,
            self.test_config['monitoring_periods']
        )
        self.assertEqual(
            self.performance_analyzer.alert_cooldown_period,
            self.test_config['alert_cooldown_period']
        )
        self.assertEqual(
            self.performance_analyzer.enabled_coins,
            self.test_config['enabled_coins']
        )
        self.assertEqual(
            self.performance_analyzer.volume_comparison_periods,
            self.test_config['volume_comparison_periods']
        )
    
    async def test_collect_data(self):
        """Test data collection for performance analysis."""
        # Mock database session
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        # Mock coin data
        mock_coins = [self.test_coin_btc, self.test_coin_eth, self.test_coin_bnb]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_coins
        
        # Mock price data
        mock_btc_price = 50000.0
        mock_eth_price = 3000.0
        mock_bnb_price = 400.0
        
        self.performance_analyzer.binance_manager.get_ticker_price.side_effect = [
            mock_btc_price, mock_eth_price, mock_bnb_price
        ]
        
        # Mock balance data
        self.performance_analyzer.binance_manager.get_currency_balance.side_effect = [
            1.0, 2.0, 5.0  # BTC balance, ETH balance, BNB balance
        ]
        
        # Mock historical data
        mock_historical_data = pd.DataFrame({
            'close': [50000, 50100, 49900, 50200, 49800, 50300, 49700, 50400, 49900, 50500]
        })
        
        with patch.object(self.performance_analyzer, '_get_historical_data', return_value=mock_historical_data):
            data = await self.performance_analyzer.collect_data()
        
        # Verify data structure
        self.assertIn('coins', data)
        self.assertIn('timestamp', data)
        
        # Verify coin data
        self.assertEqual(len(data['coins']), 3)
        for coin_data in data['coins']:
            self.assertIn('symbol', coin_data)
            self.assertIn('price', coin_data)
            self.assertIn('balance', coin_data)
            self.assertIn('price_history', coin_data)
            self.assertIn('volume_history', coin_data)
        
        # Verify timestamp
        self.assertIsInstance(data['timestamp'], datetime)
    
    async def test_collect_data_no_coins(self):
        """Test data collection when no coins are enabled."""
        # Mock empty coin data
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        data = await self.performance_analyzer.collect_data()
        
        self.assertEqual(len(data['coins']), 0)
    
    async def test_analyze_data(self):
        """Test data analysis for performance detection."""
        # Create test data with exceptional performance
        test_data = {
            'coins': [
                {
                    'symbol': 'BTC',
                    'price': 55000.0,  # 10% increase
                    'balance': 1.0,
                    'price_history': [50000, 50100, 49900, 50200, 49800, 50300, 49700, 50400, 49900, 50500],
                    'volume_history': [1000, 1100, 900, 1200, 800, 1300, 700, 1400, 600, 1500]
                },
                {
                    'symbol': 'ETH',
                    'price': 3300.0,  # 10% increase
                    'balance': 2.0,
                    'price_history': [3000, 3010, 2990, 3020, 2980, 3030, 2970, 3040, 2960, 3050],
                    'volume_history': [2000, 2100, 1900, 2200, 1800, 2300, 1700, 2400, 1600, 2500]
                }
            ],
            'timestamp': datetime.utcnow()
        }
        
        alerts = await self.performance_analyzer.analyze_data(test_data)
        
        # Verify alerts are generated
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertIn(alert.alert_type, [AlertType.EXCEPTIONAL_PERFORMANCE, AlertType.MARKET_VOLATILITY_DETECTED])
            self.assertIn(alert.severity, [AlertSeverity.LOW, AlertSeverity.MEDIUM, AlertSeverity.HIGH, AlertSeverity.CRITICAL])
    
    async def test_analyze_data_normal_performance(self):
        """Test data analysis when performance is normal."""
        # Create test data with normal performance
        test_data = {
            'coins': [
                {
                    'symbol': 'BTC',
                    'price': 50000.0,
                    'balance': 1.0,
                    'price_history': [50000, 50010, 49990, 50005, 49995, 50002, 49998, 50001, 49999, 50000],
                    'volume_history': [1000, 1005, 995, 1002, 998, 1001, 999, 1003, 997, 1000]
                }
            ],
            'timestamp': datetime.utcnow()
        }
        
        alerts = await self.performance_analyzer.analyze_data(test_data)
        
        # No alerts should be generated for normal performance
        self.assertEqual(len(alerts), 0)
    
    async def test_calculate_price_change(self):
        """Test price change calculation."""
        # Test 24h price change
        current_price = 55000.0
        historical_prices = [50000.0] * 24  # 24 hours of same price
        historical_prices[0] = 50000.0  # 24h ago
        
        change_24h = await self.performance_analyzer._calculate_price_change(
            current_price, historical_prices, 24
        )
        self.assertAlmostEqual(change_24h, 0.10, places=6)  # 10% increase
        
        # Test 1h price change
        historical_prices_1h = [50000.0] * 4  # 1 hour of same price
        historical_prices_1h[0] = 50000.0  # 1h ago
        
        change_1h = await self.performance_analyzer._calculate_price_change(
            current_price, historical_prices_1h, 4
        )
        self.assertAlmostEqual(change_1h, 0.10, places=6)  # 10% increase
    
    async def test_calculate_volume_spike(self):
        """Test volume spike calculation."""
        # Test volume spike
        current_volume = 5000.0
        historical_volumes = [1000.0, 1100.0, 900.0, 1200.0, 800.0]  # Normal volumes
        
        spike_ratio = await self.performance_analyzer._calculate_volume_spike(
            current_volume, historical_volumes
        )
        self.assertAlmostEqual(spike_ratio, 4.1667, places=4)  # ~4.17x increase
    
    async def test_calculate_market_cap_change(self):
        """Test market cap change calculation."""
        # Test market cap change
        current_price = 55000.0
        current_balance = 1.0
        historical_prices = [50000.0] * 24
        historical_balances = [1.0] * 24
        
        change = await self.performance_analyzer._calculate_market_cap_change(
            current_price, current_balance, historical_prices, historical_balances, 24
        )
        self.assertAlmostEqual(change, 0.10, places=6)  # 10% increase
    
    async def test_determine_performance_severity(self):
        """Test performance severity determination."""
        thresholds = {
            'low': 0.05,
            'medium': 0.10,
            'high': 0.20,
            'critical': 0.40
        }
        
        # Test various performance values
        test_cases = [
            (0.03, None),  # Below low threshold
            (0.07, AlertSeverity.LOW),
            (0.15, AlertSeverity.MEDIUM),
            (0.25, AlertSeverity.HIGH),
            (0.45, AlertSeverity.CRITICAL)
        ]
        
        for performance, expected_severity in test_cases:
            result = self.performance_analyzer._determine_performance_severity(performance, thresholds)
            self.assertEqual(result, expected_severity)
    
    async def test_check_coin_performance(self):
        """Test coin performance checking."""
        # Create test coin data with exceptional performance
        coin_data = {
            'symbol': 'BTC',
            'price': 55000.0,
            'balance': 1.0,
            'price_history': [50000, 50100, 49900, 50200, 49800, 50300, 49700, 50400, 49900, 50500],
            'volume_history': [1000, 1100, 900, 1200, 800, 1300, 700, 1400, 600, 1500]
        }
        
        alerts = await self.performance_analyzer._check_coin_performance(coin_data)
        
        # Alerts should be generated for exceptional performance
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertEqual(alert.coin.symbol, 'BTC')
    
    async def test_check_coin_performance_normal(self):
        """Test coin performance checking with normal performance."""
        # Create test coin data with normal performance
        coin_data = {
            'symbol': 'BTC',
            'price': 50000.0,
            'balance': 1.0,
            'price_history': [50000, 50010, 49990, 50005, 49995, 50002, 49998, 50001, 49999, 50000],
            'volume_history': [1000, 1005, 995, 1002, 998, 1001, 999, 1003, 997, 1000]
        }
        
        alerts = await self.performance_analyzer._check_coin_performance(coin_data)
        
        # No alerts should be generated for normal performance
        self.assertEqual(len(alerts), 0)
    
    async def test_store_performance_data(self):
        """Test performance data storage."""
        # Create test alert
        test_alert = MonitoringAlert(
            alert_type=AlertType.EXCEPTIONAL_PERFORMANCE,
            severity=AlertSeverity.HIGH,
            title="Test Performance Alert",
            description="Test performance alert"
        )
        
        # Create test performance data
        performance_data = {
            'metric_type': PerformanceMetric.PRICE_CHANGE_24H.value,
            'performance_value': 0.15,
            'threshold_value': 0.10,
            'coin': self.test_coin_btc
        }
        
        # Mock database session
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        await self.performance_analyzer._store_performance_data(test_alert, performance_data)
        
        # Verify database operation
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
    
    async def test_generate_report(self):
        """Test report generation."""
        # Create test alerts
        test_alerts = [
            MonitoringAlert(
                alert_type=AlertType.EXCEPTIONAL_PERFORMANCE,
                severity=AlertSeverity.HIGH,
                title="High Performance Alert",
                description="High performance detected"
            ),
            MonitoringAlert(
                alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                severity=AlertSeverity.MEDIUM,
                title="Volatility Alert",
                description="Volatility detected"
            )
        ]
        
        report = await self.performance_analyzer.generate_report(test_alerts)
        
        # Verify report structure
        self.assertIn("📈 Performance Analysis Report", report)
        self.assertIn("Total Alerts: 2", report)
        self.assertIn("HIGH Severity Alerts: 1", report)
        self.assertIn("MEDIUM Severity Alerts: 1", report)
        self.assertIn("Summary Statistics:", report)
    
    async def test_generate_report_no_alerts(self):
        """Test report generation when no alerts are present."""
        report = await self.performance_analyzer.generate_report([])
        
        self.assertIn("No performance alerts generated", report)
    
    async def test_get_historical_data(self):
        """Test historical data retrieval."""
        # Mock binance manager
        mock_klines = [
            ["1609459200000", "50000.0", "50100.0", "49900.0", "50050.0", "1000.0", "1609459259999"],
            ["1609459260000", "50050.0", "50150.0", "49950.0", "50100.0", "1100.0", "1609459319999"],
            ["1609459320000", "50100.0", "50200.0", "50000.0", "50150.0", "900.0", "1609459379999"]
        ]
        
        self.performance_analyzer.binance_manager.get_klines.return_value = mock_klines
        
        result = await self.performance_analyzer._get_historical_data("BTCUSDT", 3)
        
        # Verify result structure
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 3)
        self.assertIn('close', result.columns)
        self.assertIn('high', result.columns)
        self.assertIn('low', result.columns)
        self.assertIn('open', result.columns)
        self.assertIn('volume', result.columns)
    
    async def test_get_historical_data_insufficient(self):
        """Test historical data retrieval with insufficient data."""
        # Mock insufficient klines
        mock_klines = [
            ["1609459200000", "50000.0", "50100.0", "49900.0", "50050.0", "1000.0", "1609459259999"]
        ]
        
        self.performance_analyzer.binance_manager.get_klines.return_value = mock_klines
        
        result = await self.performance_analyzer._get_historical_data("BTCUSDT", 3)
        
        # Should return None for insufficient data
        self.assertIsNone(result)
    
    async def test_get_historical_data_error(self):
        """Test historical data retrieval with error."""
        # Mock error
        self.performance_analyzer.binance_manager.get_klines.side_effect = Exception("API Error")
        
        result = await self.performance_analyzer._get_historical_data("BTCUSDT", 3)
        
        # Should return None on error
        self.assertIsNone(result)
    
    async def test_calculate_price_percentiles(self):
        """Test price percentile calculation."""
        # Test price percentiles
        prices = [100, 200, 300, 400, 500]
        
        percentiles = await self.performance_analyzer._calculate_price_percentiles(prices)
        
        # Verify percentiles
        self.assertEqual(percentiles['min'], 100)
        self.assertEqual(percentiles['max'], 500)
        self.assertEqual(percentiles['median'], 300)
        self.assertEqual(percentiles['p25'], 200)
        self.assertEqual(percentiles['p75'], 400)
    
    async def test_detect_price_anomalies(self):
        """Test price anomaly detection."""
        # Test price anomalies
        prices = [100, 200, 300, 400, 5000]  # 5000 is an anomaly
        
        anomalies = await self.performance_analyzer._detect_price_anomalies(prices)
        
        # Should detect the anomaly
        self.assertTrue(anomalies['has_anomalies'])
        self.assertEqual(len(anomalies['anomaly_indices']), 1)
        self.assertEqual(anomalies['anomaly_indices'][0], 4)
    
    async def test_detect_price_anomalies_no_anomalies(self):
        """Test price anomaly detection with no anomalies."""
        # Test normal prices
        prices = [100, 200, 300, 400, 500]
        
        anomalies = await self.performance_analyzer._detect_price_anomalies(prices)
        
        # Should not detect anomalies
        self.assertFalse(anomalies['has_anomalies'])
        self.assertEqual(len(anomalies['anomaly_indices']), 0)


if __name__ == '__main__':
    unittest.main()