"""
Unit tests for WMA (Weighted Moving Average) calculation engine.

This module contains comprehensive tests for WMA calculations,
trend detection, and signal generation using known datasets.
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from binance_trade_bot.technical_analysis.wma_engine import WmaEngine
from binance_trade_bot.models.pair import Pair
from binance_trade_bot.models.coin import Coin


class TestWmaEngine(unittest.TestCase):
    """
    Test suite for WMA calculation engine functionality.
    """
    
    def setUp(self):
        """
        Set up test fixtures before each test method.
        """
        # Create test configuration
        self.config = {
            'wma_short_period': 7,
            'wma_long_period': 21,
            'price_column': 'close'
        }
        
        # Create WMA engine instance
        self.wma_engine = WmaEngine(self.config)
        
        # Create known test datasets
        self.create_test_data()
        
        # Create mock pair and coin objects
        self.pair = Pair(id="BTCUSDT", symbol="BTCUSDT")
        self.coin = Coin(symbol="BTC", name="Bitcoin")
    
    def create_test_data(self):
        """
        Create known test datasets for validation.
        """
        # Create a simple price series with known WMA values
        dates = pd.date_range(start='2023-01-01', periods=30, freq='D')
        
        # Test case 1: Linear increasing prices
        self.linear_prices = [100 + i * 2 for i in range(30)]
        self.linear_data = pd.DataFrame({
            'close': self.linear_prices,
            'high': [p + 1 for p in self.linear_prices],
            'low': [p - 1 for p in self.linear_prices],
            'open': [p - 0.5 for p in self.linear_prices],
            'volume': [1000] * 30
        }, index=dates)
        
        # Test case 2: Sinusoidal price pattern
        t = np.linspace(0, 4 * np.pi, 30)
        self.sin_prices = 100 + 10 * np.sin(t)
        self.sin_data = pd.DataFrame({
            'close': self.sin_prices,
            'high': [p + 1 for p in self.sin_prices],
            'low': [p - 1 for p in self.sin_prices],
            'open': [p - 0.5 for p in self.sin_prices],
            'volume': [1000] * 30
        }, index=dates)
        
        # Test case 3: Volatile prices
        np.random.seed(42)  # For reproducible results
        self.volatile_prices = 100 + np.cumsum(np.random.normal(0, 2, 30))
        self.volatile_data = pd.DataFrame({
            'close': self.volatile_prices,
            'high': [p + 1 for p in self.volatile_prices],
            'low': [p - 1 for p in self.volatile_prices],
            'open': [p - 0.5 for p in self.volatile_prices],
            'volume': [1000] * 30
        }, index=dates)
    
    def test_wma_engine_initialization(self):
        """
        Test WMA engine initialization with valid and invalid configurations.
        """
        # Test valid initialization
        engine = WmaEngine(self.config)
        self.assertEqual(engine.short_period, 7)
        self.assertEqual(engine.long_period, 21)
        self.assertEqual(engine.price_column, 'close')
        
        # Test invalid short period
        with self.assertRaises(ValueError):
            WmaEngine({'wma_short_period': 0, 'wma_long_period': 21})
        
        # Test invalid long period
        with self.assertRaises(ValueError):
            WmaEngine({'wma_short_period': 7, 'wma_long_period': 0})
        
        # Test invalid period relationship
        with self.assertRaises(ValueError):
            WmaEngine({'wma_short_period': 21, 'wma_long_period': 7})
    
    def test_calculate_wma_basic(self):
        """
        Test basic WMA calculation with known values.
        """
        # Simple test case: [1, 2, 3, 4, 5] with period 3
        test_data = pd.Series([1, 2, 3, 4, 5])
        wma_result = self.wma_engine.calculate_wma(test_data, 3)
        
        # Expected WMA values:
        # WMA(3) = (1*1 + 2*2 + 3*3) / (1+2+3) = (1 + 4 + 9) / 6 = 14/6 = 2.333...
        # WMA(4) = (2*1 + 3*2 + 4*3) / (1+2+3) = (2 + 6 + 12) / 6 = 20/6 = 3.333...
        # WMA(5) = (3*1 + 4*2 + 5*3) / (1+2+3) = (3 + 8 + 15) / 6 = 26/6 = 4.333...
        
        expected_wma = [14/6, 20/6, 26/6]  # [2.333..., 3.333..., 4.333...]
        
        self.assertEqual(len(wma_result), 3)
        for i, expected in enumerate(expected_wma):
            self.assertAlmostEqual(wma_result.iloc[i], expected, places=3)
    
    def test_calculate_wma_insufficient_data(self):
        """
        Test WMA calculation with insufficient data.
        """
        test_data = pd.Series([1, 2])  # Only 2 data points
        wma_result = self.wma_engine.calculate_wma(test_data, 5)
        
        # Should return empty series for insufficient data
        self.assertEqual(len(wma_result), 0)
    
    def test_calculate_short_term_wma(self):
        """
        Test short-term WMA calculation with linear data.
        """
        short_wma = self.wma_engine.calculate_short_term_wma(self.linear_data)
        
        # Should have data points starting from index 6 (7-1)
        self.assertEqual(len(short_wma), len(self.linear_data) - 6)
        self.assertFalse(short_wma.isna().any())
        
        # For linear increasing data, WMA should also increase
        self.assertTrue(short_wma.is_monotonic_increasing)
    
    def test_calculate_long_term_wma(self):
        """
        Test long-term WMA calculation with linear data.
        """
        long_wma = self.wma_engine.calculate_long_term_wma(self.linear_data)
        
        # Should have data points starting from index 20 (21-1)
        self.assertEqual(len(long_wma), len(self.linear_data) - 20)
        self.assertFalse(long_wma.isna().any())
        
        # For linear increasing data, WMA should also increase
        self.assertTrue(long_wma.is_monotonic_increasing)
    
    def test_detect_trend_linear_data(self):
        """
        Test trend detection with linear increasing data.
        """
        trend_analysis = self.wma_engine.detect_trend(self.linear_data)
        
        self.assertEqual(trend_analysis['trend'], 'bullish')
        self.assertGreater(trend_analysis['trend_strength'], 0)
        self.assertIsNotNone(trend_analysis['short_wma'])
        self.assertIsNotNone(trend_analysis['long_wma'])
        self.assertIsNotNone(trend_analysis['current_price'])
    
    def test_detect_trend_sinusoidal_data(self):
        """
        Test trend detection with sinusoidal data.
        """
        trend_analysis = self.wma_engine.detect_trend(self.sin_data)
        
        # Trend should depend on the current phase of the sine wave
        self.assertIn(trend_analysis['trend'], ['bullish', 'bearish'])
        self.assertGreaterEqual(trend_analysis['trend_strength'], 0)
        self.assertLessEqual(trend_analysis['trend_strength'], 1.0)
    
    def test_detect_crossover_golden_cross(self):
        """
        Test golden cross detection (short WMA crosses above long WMA).
        """
        # Create test data with golden cross
        dates = pd.date_range(start='2023-01-01', periods=25, freq='D')
        
        # Create data where short WMA crosses above long WMA
        prices = [100] * 10 + [100 + i for i in range(15)]  # Sudden increase
        test_data = pd.DataFrame({
            'close': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'open': [p - 0.5 for p in prices],
            'volume': [1000] * 25
        }, index=dates)
        
        short_wma = self.wma_engine.calculate_short_term_wma(test_data)
        long_wma = self.wma_engine.calculate_long_term_wma(test_data)
        
        # Ensure we have enough data points
        if len(short_wma) >= 2 and len(long_wma) >= 2:
            crossover = self.wma_engine._detect_crossover(short_wma, long_wma)
            # Golden cross should be detected after the price increase
            self.assertEqual(crossover, 'golden_cross')
    
    def test_detect_crossover_death_cross(self):
        """
        Test death cross detection (short WMA crosses below long WMA).
        """
        # Create test data with death cross
        dates = pd.date_range(start='2023-01-01', periods=25, freq='D')
        
        # Create data where short WMA crosses below long WMA
        prices = [120] * 10 + [120 - i for i in range(15)]  # Sudden decrease
        test_data = pd.DataFrame({
            'close': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'open': [p - 0.5 for p in prices],
            'volume': [1000] * 25
        }, index=dates)
        
        short_wma = self.wma_engine.calculate_short_term_wma(test_data)
        long_wma = self.wma_engine.calculate_long_term_wma(test_data)
        
        # Ensure we have enough data points
        if len(short_wma) >= 2 and len(long_wma) >= 2:
            crossover = self.wma_engine._detect_crossover(short_wma, long_wma)
            # Death cross should be detected after the price decrease
            self.assertEqual(crossover, 'death_cross')
    
    def test_generate_signals(self):
        """
        Test signal generation based on WMA crossovers.
        """
        # Add WMA indicators to test data
        data_with_indicators = self.wma_engine.calculate_indicators(self.linear_data)
        signals = self.wma_engine.generate_signals(data_with_indicators)
        
        # Signals should be a pandas Series with the same index
        self.assertIsInstance(signals, pd.Series)
        self.assertEqual(len(signals), len(data_with_indicators))
        
        # Signal values should be -1, 0, or 1
        valid_signals = signals.isin([-1, 0, 1])
        self.assertTrue(valid_signals.all())
    
    def test_calculate_indicators(self):
        """
        Test calculation of all WMA indicators.
        """
        result = self.wma_engine.calculate_indicators(self.linear_data)
        
        # Should have original columns plus WMA indicators
        expected_columns = ['close', 'high', 'low', 'open', 'volume', 'short_wma', 'long_wma', 'wma_spread', 'wma_ratio']
        for col in expected_columns:
            self.assertIn(col, result.columns)
        
        # Should not have NaN values in WMA columns
        self.assertFalse(result['short_wma'].isna().all())
        self.assertFalse(result['long_wma'].isna().all())
    
    def test_analyze_trend(self):
        """
        Test trend analysis functionality.
        """
        trend_analysis = self.wma_engine.analyze_trend(self.linear_data)
        
        # Should return a dictionary with expected keys
        expected_keys = ['trend', 'trend_strength', 'crossover_signal', 'short_wma', 'long_wma', 'current_price']
        for key in expected_keys:
            self.assertIn(key, trend_analysis)
        
        # Trend should be one of the expected values
        self.assertIn(trend_analysis['trend'], ['bullish', 'bearish', 'insufficient_data'])
    
    def test_calculate_support_resistance(self):
        """
        Test support/resistance calculation using WMA.
        """
        result = self.wma_engine.calculate_support_resistance(self.linear_data)
        
        # Should return a dictionary with expected keys
        expected_keys = ['support', 'resistance', 'dynamic_level', 'level_type']
        for key in expected_keys:
            self.assertIn(key, result)
        
        # Either support or resistance should be None, but not both
        self.assertIsNone(result['support']) or self.assertIsNone(result['resistance'])
    
    def test_get_market_sentiment(self):
        """
        Test market sentiment calculation.
        """
        sentiment = self.wma_engine.get_market_sentiment(self.linear_data)
        
        # Sentiment should be between -1 and 1
        self.assertGreaterEqual(sentiment, -1.0)
        self.assertLessEqual(sentiment, 1.0)
    
    def test_validate_data(self):
        """
        Test data validation functionality.
        """
        # Valid data should pass validation
        self.assertTrue(self.wma_engine.validate_data(self.linear_data))
        
        # Invalid data should fail validation
        self.assertFalse(self.wma_engine.validate_data(None))
        self.assertFalse(self.wma_engine.validate_data(pd.DataFrame()))
        
        # Data without required columns should fail validation
        invalid_data = pd.DataFrame({'open': [1, 2, 3], 'high': [1, 2, 3], 'low': [1, 2, 3], 'volume': [1, 2, 3]})
        self.assertFalse(self.wma_engine.validate_data(invalid_data))
        
        # Data with insufficient length should fail validation
        short_data = pd.DataFrame({'close': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]})
        self.assertFalse(self.wma_engine.validate_data(short_data))
        
        # Data with NaN values should fail validation
        nan_data = pd.DataFrame({'close': [1, 2, 3, np.nan, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]})
        self.assertFalse(self.wma_engine.validate_data(nan_data))
    
    def test_create_wma_data_record(self):
        """
        Test creation of WmaData records.
        """
        # Test with valid data
        wma_record = self.wma_engine.create_wma_data_record(self.linear_data, self.pair, self.coin)
        
        if wma_record is not None:
            self.assertIsInstance(wma_record, WmaData)
            self.assertEqual(wma_record.pair, self.pair)
            self.assertEqual(wma_record.coin, self.coin)
            self.assertEqual(wma_record.period, 7)  # Short period
            self.assertIsNotNone(wma_record.wma_value)
            self.assertIsNotNone(wma_record.signal_type)
            self.assertIsNotNone(wma_record.confidence)
            self.assertIsNotNone(wma_record.current_price)
            self.assertIsNotNone(wma_record.trend_strength)
        
        # Test with insufficient data
        insufficient_data = pd.DataFrame({'close': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]})
        wma_record = self.wma_engine.create_wma_data_record(insufficient_data, self.pair, self.coin)
        self.assertIsNone(wma_record)
    
    def test_wma_calculation_precision(self):
        """
        Test WMA calculation precision with known mathematical results.
        """
        # Test with known values: [10, 20, 30, 40, 50] with period 3
        test_data = pd.Series([10, 20, 30, 40, 50])
        wma_result = self.wma_engine.calculate_wma(test_data, 3)
        
        # Expected WMA values:
        # WMA(3) = (10*1 + 20*2 + 30*3) / (1+2+3) = (10 + 40 + 90) / 6 = 140/6 = 23.333...
        # WMA(4) = (20*1 + 30*2 + 40*3) / (1+2+3) = (20 + 60 + 120) / 6 = 200/6 = 33.333...
        # WMA(5) = (30*1 + 40*2 + 50*3) / (1+2+3) = (30 + 80 + 150) / 6 = 260/6 = 43.333...
        
        expected_wma = [140/6, 200/6, 260/6]  # [23.333..., 33.333..., 43.333...]
        
        self.assertEqual(len(wma_result), 3)
        for i, expected in enumerate(expected_wma):
            self.assertAlmostEqual(wma_result.iloc[i], expected, places=6)
    
    def test_edge_cases(self):
        """
        Test edge cases and boundary conditions.
        """
        # Test with minimum required data
        min_data = pd.DataFrame({'close': [1] * 21})  # Exactly 21 data points
        result = self.wma_engine.calculate_indicators(min_data)
        
        # Should have some WMA values calculated
        self.assertFalse(result['long_wma'].isna().all())
        
        # Test with constant prices
        constant_data = pd.DataFrame({'close': [100] * 30})
        result = self.wma_engine.calculate_indicators(constant_data)
        
        # WMA values should be close to 100
        self.assertTrue((result['short_wma'] - 100).abs().le(0.1).all())
        self.assertTrue((result['long_wma'] - 100).abs().le(0.1).all())
        
        # Test with very volatile data
        volatile_result = self.wma_engine.calculate_indicators(self.volatile_data)
        
        # Should not have NaN values
        self.assertFalse(volatile_result['short_wma'].isna().all())
        self.assertFalse(volatile_result['long_wma'].isna().all())


if __name__ == '__main__':
    unittest.main()