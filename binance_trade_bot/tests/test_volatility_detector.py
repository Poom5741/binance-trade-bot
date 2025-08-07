"""
Unit tests for volatility detector module.

This module contains comprehensive unit tests for the volatility detector
functionality.

Created: 2025-08-05
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import pandas as pd
import numpy as np

from binance_trade_bot.monitoring.volatility_detector import VolatilityDetector
from binance_trade_bot.monitoring.base import MonitoringAlert, AlertSeverity, AlertType
from binance_trade_bot.monitoring.models import VolatilityMetric
from binance_trade_bot.models import Coin, Pair


class TestVolatilityDetector(unittest.TestCase):
    """Test cases for VolatilityDetector class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock()
        self.mock_logger = Mock()
        self.mock_notifications = Mock()
        self.test_config = {
            'volatility_thresholds': {
                'standard_deviation': {
                    'low': 0.02,
                    'medium': 0.05,
                    'high': 0.10,
                    'critical': 0.20
                },
                'price_range': {
                    'low': 0.05,
                    'medium': 0.10,
                    'high': 0.20,
                    'critical': 0.40
                },
                'volatility_ratio': {
                    'low': 1.5,
                    'medium': 2.0,
                    'high': 3.0,
                    'critical': 5.0
                }
            },
            'monitoring_periods': {
                VolatilityMetric.STANDARD_DEVIATION.value: 60,
                VolatilityMetric.PRICE_RANGE.value: 60,
                VolatilityMetric.VOLATILITY_RATIO.value: 60
            },
            'alert_cooldown_period': 30,
            'enabled_coins': ['BTC', 'ETH', 'BNB'],
            'enabled_pairs': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
        }
        
        self.volatility_detector = VolatilityDetector(
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
        
    def test_volatility_detector_initialization(self):
        """Test volatility detector initialization."""
        self.assertEqual(self.volatility_detector.database, self.mock_database)
        self.assertEqual(self.volatility_detector.logger, self.mock_logger)
        self.assertEqual(self.volatility_detector.notifications, self.mock_notifications)
        self.assertEqual(self.volatility_detector.config, self.test_config)
        self.assertTrue(self.volatility_detector.enabled)
        
        # Check configuration
        self.assertEqual(
            self.volatility_detector.volatility_thresholds,
            self.test_config['volatility_thresholds']
        )
        self.assertEqual(
            self.volatility_detector.monitoring_periods,
            self.test_config['monitoring_periods']
        )
        self.assertEqual(
            self.volatility_detector.alert_cooldown_period,
            self.test_config['alert_cooldown_period']
        )
        self.assertEqual(
            self.volatility_detector.enabled_coins,
            self.test_config['enabled_coins']
        )
        self.assertEqual(
            self.volatility_detector.enabled_pairs,
            self.test_config['enabled_pairs']
        )
    
    async def test_collect_data(self):
        """Test data collection for volatility detection."""
        # Mock database session
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        # Mock coin data
        mock_coins = [self.test_coin_btc, self.test_coin_eth, self.test_coin_bnb]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_coins
        
        # Mock pair data
        mock_pairs = [self.test_pair_btc_eth, self.test_pair_eth_btc]
        mock_session.query.return_value.filter.return_value.all.return_value = mock_pairs
        
        # Mock price data
        mock_btc_price = 50000.0
        mock_eth_price = 3000.0
        mock_bnb_price = 400.0
        
        self.volatility_detector.binance_manager.get_ticker_price.side_effect = [
            mock_btc_price, mock_eth_price, mock_bnb_price,
            mock_btc_price, mock_eth_price, mock_bnb_price
        ]
        
        # Mock historical data
        mock_historical_data = pd.DataFrame({
            'close': [50000, 50100, 49900, 50200, 49800, 50300, 49700, 50400, 49900, 50500]
        })
        
        with patch.object(self.volatility_detector, '_get_historical_data', return_value=mock_historical_data):
            data = await self.volatility_detector.collect_data()
        
        # Verify data structure
        self.assertIn('coins', data)
        self.assertIn('pairs', data)
        self.assertIn('timestamp', data)
        
        # Verify coin data
        self.assertEqual(len(data['coins']), 3)
        for coin_data in data['coins']:
            self.assertIn('symbol', coin_data)
            self.assertIn('price', coin_data)
            self.assertIn('price_history', coin_data)
        
        # Verify pair data
        self.assertEqual(len(data['pairs']), 2)
        for pair_data in data['pairs']:
            self.assertIn('from_coin', pair_data)
            self.assertIn('to_coin', pair_data)
            self.assertIn('price_history', pair_data)
        
        # Verify timestamp
        self.assertIsInstance(data['timestamp'], datetime)
    
    async def test_collect_data_no_coins(self):
        """Test data collection when no coins are enabled."""
        # Mock empty coin data
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        data = await self.volatility_detector.collect_data()
        
        self.assertEqual(len(data['coins']), 0)
        self.assertEqual(len(data['pairs']), 0)
    
    async def test_analyze_data(self):
        """Test data analysis for volatility detection."""
        # Create test data
        test_data = {
            'coins': [
                {
                    'symbol': 'BTC',
                    'price': 50000.0,
                    'price_history': [50000, 50100, 49900, 50200, 49800, 50300, 49700, 50400, 49900, 50500]
                },
                {
                    'symbol': 'ETH',
                    'price': 3000.0,
                    'price_history': [3000, 3100, 2900, 3200, 2800, 3300, 2700, 3400, 2600, 3500]
                }
            ],
            'pairs': [
                {
                    'from_coin': 'BTC',
                    'to_coin': 'ETH',
                    'price_history': [16.67, 16.16, 17.21, 15.69, 17.79, 15.24, 18.41, 14.82, 19.19, 14.43]
                }
            ],
            'timestamp': datetime.utcnow()
        }
        
        alerts = await self.volatility_detector.analyze_data(test_data)
        
        # Verify alerts are generated
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertIn(alert.alert_type, [AlertType.MARKET_VOLATILITY_DETECTED, AlertType.EXCEPTIONAL_PERFORMANCE])
            self.assertIn(alert.severity, [AlertSeverity.LOW, AlertSeverity.MEDIUM, AlertSeverity.HIGH, AlertSeverity.CRITICAL])
    
    async def test_analyze_data_no_volatility(self):
        """Test data analysis when no volatility is detected."""
        # Create stable price data
        test_data = {
            'coins': [
                {
                    'symbol': 'BTC',
                    'price': 50000.0,
                    'price_history': [50000, 50010, 49990, 50005, 49995, 50002, 49998, 50001, 49999, 50000]
                }
            ],
            'pairs': [],
            'timestamp': datetime.utcnow()
        }
        
        alerts = await self.volatility_detector.analyze_data(test_data)
        
        # No alerts should be generated for stable prices
        self.assertEqual(len(alerts), 0)
    
    async def test_calculate_standard_deviation(self):
        """Test standard deviation calculation."""
        # Test data with known volatility
        prices = [100, 102, 98, 104, 96, 106, 94, 108, 92, 110]
        expected_std = np.std(prices)
        
        result = await self.volatility_detector._calculate_standard_deviation(prices)
        
        self.assertAlmostEqual(result, expected_std, places=6)
    
    async def test_calculate_price_range(self):
        """Test price range calculation."""
        # Test data with known range
        prices = [100, 110, 90, 105, 95, 108, 92, 107, 93, 109]
        expected_range = (max(prices) - min(prices)) / np.mean(prices)
        
        result = await self.volatility_detector._calculate_price_range(prices)
        
        self.assertAlmostEqual(result, expected_range, places=6)
    
    async def test_calculate_volatility_ratio(self):
        """Test volatility ratio calculation."""
        # Test data
        short_prices = [100, 102, 98, 104, 96, 106, 94, 108, 92, 110]
        long_prices = [100, 101, 99, 102, 98, 103, 97, 104, 96, 105]
        
        short_std = np.std(short_prices)
        long_std = np.std(long_prices)
        expected_ratio = short_std / long_std if long_std > 0 else 0
        
        result = await self.volatility_detector._calculate_volatility_ratio(short_prices, long_prices)
        
        self.assertAlmostEqual(result, expected_ratio, places=6)
    
    async def test_determine_volatility_severity(self):
        """Test volatility severity determination."""
        thresholds = {
            'low': 0.02,
            'medium': 0.05,
            'high': 0.10,
            'critical': 0.20
        }
        
        # Test various volatility values
        test_cases = [
            (0.01, None),  # Below low threshold
            (0.03, AlertSeverity.LOW),
            (0.07, AlertSeverity.MEDIUM),
            (0.15, AlertSeverity.HIGH),
            (0.25, AlertSeverity.CRITICAL)
        ]
        
        for volatility, expected_severity in test_cases:
            result = self.volatility_detector._determine_volatility_severity(volatility, thresholds)
            self.assertEqual(result, expected_severity)
    
    async def test_check_coin_volatility(self):
        """Test coin volatility checking."""
        # Create test coin data
        coin_data = {
            'symbol': 'BTC',
            'price': 50000.0,
            'price_history': [50000, 50100, 49900, 50200, 49800, 50300, 49700, 50400, 49900, 50500]
        }
        
        alerts = await self.volatility_detector._check_coin_volatility(coin_data)
        
        # Alerts should be generated for volatile prices
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertEqual(alert.coin.symbol, 'BTC')
    
    async def test_check_pair_volatility(self):
        """Test pair volatility checking."""
        # Create test pair data
        pair_data = {
            'from_coin': 'BTC',
            'to_coin': 'ETH',
            'price_history': [16.67, 16.16, 17.21, 15.69, 17.79, 15.24, 18.41, 14.82, 19.19, 14.43]
        }
        
        alerts = await self.volatility_detector._check_pair_volatility(pair_data)
        
        # Alerts should be generated for volatile pairs
        self.assertGreater(len(alerts), 0)
        
        # Verify alert structure
        for alert in alerts:
            self.assertIsInstance(alert, MonitoringAlert)
            self.assertEqual(alert.pair.from_coin_id, 'BTC')
            self.assertEqual(alert.pair.to_coin_id, 'ETH')
    
    async def test_store_volatility_data(self):
        """Test volatility data storage."""
        # Create test alert
        test_alert = MonitoringAlert(
            alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
            severity=AlertSeverity.HIGH,
            title="Test Volatility Alert",
            description="Test volatility alert"
        )
        
        # Create test volatility data
        volatility_data = {
            'metric_type': VolatilityMetric.STANDARD_DEVIATION.value,
            'volatility_value': 0.08,
            'threshold_value': 0.05,
            'coin': self.test_coin_btc,
            'pair': self.test_pair_btc_eth
        }
        
        # Mock database session
        mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = mock_session
        
        await self.volatility_detector._store_volatility_data(test_alert, volatility_data)
        
        # Verify database operation
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
    
    async def test_generate_report(self):
        """Test report generation."""
        # Create test alerts
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
                title="Exceptional Performance Alert",
                description="Exceptional performance detected"
            )
        ]
        
        report = await self.volatility_detector.generate_report(test_alerts)
        
        # Verify report structure
        self.assertIn("📈 Volatility Detection Report", report)
        self.assertIn("Total Alerts: 2", report)
        self.assertIn("HIGH Severity Alerts: 1", report)
        self.assertIn("MEDIUM Severity Alerts: 1", report)
        self.assertIn("Summary Statistics:", report)
    
    async def test_generate_report_no_alerts(self):
        """Test report generation when no alerts are present."""
        report = await self.volatility_detector.generate_report([])
        
        self.assertIn("No volatility alerts generated", report)
    
    async def test_get_historical_data(self):
        """Test historical data retrieval."""
        # Mock binance manager
        mock_klines = [
            ["1609459200000", "50000.0", "50100.0", "49900.0", "50050.0", "1000.0", "1609459259999"],
            ["1609459260000", "50050.0", "50150.0", "49950.0", "50100.0", "1100.0", "1609459319999"],
            ["1609459320000", "50100.0", "50200.0", "50000.0", "50150.0", "900.0", "1609459379999"]
        ]
        
        self.volatility_detector.binance_manager.get_klines.return_value = mock_klines
        
        result = await self.volatility_detector._get_historical_data("BTCUSDT", 3)
        
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
        
        self.volatility_detector.binance_manager.get_klines.return_value = mock_klines
        
        result = await self.volatility_detector._get_historical_data("BTCUSDT", 3)
        
        # Should return None for insufficient data
        self.assertIsNone(result)
    
    async def test_get_historical_data_error(self):
        """Test historical data retrieval with error."""
        # Mock error
        self.volatility_detector.binance_manager.get_klines.side_effect = Exception("API Error")
        
        result = await self.volatility_detector._get_historical_data("BTCUSDT", 3)
        
        # Should return None on error
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()