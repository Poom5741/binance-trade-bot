"""
Weighted Moving Average (WMA) calculation engine for technical analysis.

This module provides WMA calculation functions, trend detection logic,
and signal generation based on WMA crossovers.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from .base import TechnicalAnalysisBase
from ..models.wma_data import WmaData, SignalType
from ..models.pair import Pair
from ..models.coin import Coin


class WmaEngine(TechnicalAnalysisBase):
    """
    Weighted Moving Average (WMA) calculation engine.
    
    This class implements WMA-based technical analysis including:
    - WMA calculation for specified periods
    - Short-term and long-term WMA calculators
    - Trend detection using WMA crossovers
    - Signal generation based on WMA analysis
    """
    
    def __init__(self, config):
        """
        Initialize the WMA engine with configuration.
        
        @param {dict} config - Configuration dictionary containing WMA settings
        """
        super().__init__(config)
        self.short_period = config.get('wma_short_period', 7)
        self.long_period = config.get('wma_long_period', 21)
        self.price_column = config.get('price_column', 'close')
        
        # Validate periods
        if self.short_period <= 0:
            raise ValueError("Short-term WMA period must be positive")
        if self.long_period <= 0:
            raise ValueError("Long-term WMA period must be positive")
        if self.short_period >= self.long_period:
            raise ValueError("Short-term WMA period must be less than long-term WMA period")
    
    def calculate_wma(self, data: pd.Series, period: int) -> pd.Series:
        """
        Calculate Weighted Moving Average for the given data series.
        
        @description Weighted Moving Average gives more weight to recent prices
        @param {pd.Series} data - Price data series
        @param {int} period - Number of periods for WMA calculation
        @returns {pd.Series} WMA values
        """
        if len(data) < period:
            return pd.Series(dtype=float)
        
        # Calculate weights (linear weighting)
        weights = np.arange(1, period + 1)
        weights = weights / weights.sum()
        
        # Calculate WMA using rolling window
        wma_values = []
        for i in range(period - 1, len(data)):
            window = data.iloc[i - period + 1:i + 1]
            wma = (window * weights).sum()
            wma_values.append(wma)
        
        return pd.Series(wma_values, index=data.index[period - 1:])
    
    def calculate_short_term_wma(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate short-term WMA using configured short period.
        
        @param {pd.DataFrame} data - DataFrame containing price data
        @returns {pd.Series} Short-term WMA values
        """
        price_data = data[self.price_column]
        return self.calculate_wma(price_data, self.short_period)
    
    def calculate_long_term_wma(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate long-term WMA using configured long period.
        
        @param {pd.DataFrame} data - DataFrame containing price data
        @returns {pd.Series} Long-term WMA values
        """
        price_data = data[self.price_column]
        return self.calculate_wma(price_data, self.long_period)
    
    def detect_trend(self, data: pd.DataFrame) -> Dict:
        """
        Analyze market trend using WMA crossover analysis.
        
        @param {pd.DataFrame} data - DataFrame containing price data
        @returns {dict} Dictionary containing trend analysis results
        """
        if len(data) < self.long_period:
            return {
                'trend': 'insufficient_data',
                'trend_strength': 0.0,
                'crossover_signal': None
            }
        
        # Calculate WMAs
        short_wma = self.calculate_short_term_wma(data)
        long_wma = self.calculate_long_term_wma(data)
        
        # Get latest values
        latest_short_wma = short_wma.iloc[-1] if len(short_wma) > 0 else None
        latest_long_wma = long_wma.iloc[-1] if len(long_wma) > 0 else None
        latest_price = data[self.price_column].iloc[-1]
        
        if latest_short_wma is None or latest_long_wma is None:
            return {
                'trend': 'insufficient_data',
                'trend_strength': 0.0,
                'crossover_signal': None
            }
        
        # Determine trend direction
        if latest_short_wma > latest_long_wma:
            trend = 'bullish'
            trend_strength = (latest_short_wma - latest_long_wma) / latest_long_wma
        else:
            trend = 'bearish'
            trend_strength = (latest_long_wma - latest_short_wma) / latest_long_wma
        
        # Detect crossovers
        crossover_signal = self._detect_crossover(short_wma, long_wma)
        
        return {
            'trend': trend,
            'trend_strength': min(abs(trend_strength), 1.0),  # Cap at 1.0
            'crossover_signal': crossover_signal,
            'short_wma': latest_short_wma,
            'long_wma': latest_long_wma,
            'current_price': latest_price
        }
    
    def _detect_crossover(self, short_wma: pd.Series, long_wma: pd.Series) -> Optional[str]:
        """
        Detect WMA crossover signals.
        
        @param {pd.Series} short_wma - Short-term WMA values
        @param {pd.Series} long_wma - Long-term WMA values
        @returns {str|null} Crossover signal ('golden_cross', 'death_cross', or null)
        """
        if len(short_wma) < 2 or len(long_wma) < 2:
            return None
        
        # Check for crossovers
        prev_short = short_wma.iloc[-2]
        prev_long = long_wma.iloc[-2]
        curr_short = short_wma.iloc[-1]
        curr_long = long_wma.iloc[-1]
        
        # Golden cross (short crosses above long)
        if prev_short <= prev_long and curr_short > curr_long:
            return 'golden_cross'
        
        # Death cross (short crosses below long)
        if prev_short >= prev_long and curr_short < curr_long:
            return 'death_cross'
        
        return None
    
    def generate_signals(self, data_with_indicators: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on WMA analysis.
        
        @param {pd.DataFrame} data_with_indicators - DataFrame with WMA indicators
        @returns {pd.Series} Series of trading signals (1 for buy, -1 for sell, 0 for hold)
        """
        signals = pd.Series(0, index=data_with_indicators.index)
        
        if len(data_with_indicators) < self.long_period:
            return signals
        
        # Check for golden cross (buy signal)
        golden_cross_mask = (
            data_with_indicators[f'short_wma'] > data_with_indicators[f'long_wma']
        ) & (
            data_with_indicators[f'short_wma'].shift(1) <= data_with_indicators[f'long_wma'].shift(1)
        )
        signals[golden_cross_mask] = 1
        
        # Check for death cross (sell signal)
        death_cross_mask = (
            data_with_indicators[f'short_wma'] < data_with_indicators[f'long_wma']
        ) & (
            data_with_indicators[f'short_wma'].shift(1) >= data_with_indicators[f'long_wma'].shift(1)
        )
        signals[death_cross_mask] = -1
        
        return signals
    
    def calculate_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate WMA indicators for the given market data.
        
        @param {pd.DataFrame} data - DataFrame containing OHLCV market data
        @returns {pd.DataFrame} DataFrame with calculated WMA indicators added
        """
        # Validate data
        if not self.validate_data(data):
            raise ValueError("Invalid input data for WMA calculation")
        
        # Calculate WMAs
        data['short_wma'] = self.calculate_short_term_wma(data)
        data['long_wma'] = self.calculate_long_term_wma(data)
        
        # Calculate additional indicators
        data['wma_spread'] = data['short_wma'] - data['long_wma']
        data['wma_ratio'] = data['short_wma'] / data['long_wma']
        
        return data
    
    def analyze_trend(self, data: pd.DataFrame) -> Dict:
        """
        Analyze the current market trend using WMA analysis.
        
        @param {pd.DataFrame} data - DataFrame containing market data
        @returns {dict} Dictionary containing trend analysis results
        """
        return self.detect_trend(data)
    
    def calculate_support_resistance(self, data: pd.DataFrame) -> Dict:
        """
        Calculate support and resistance levels using WMA analysis.
        
        @param {pd.DataFrame} data - DataFrame containing market data
        @returns {dict} Dictionary with support and resistance levels
        """
        if len(data) < self.long_period:
            return {'support': None, 'resistance': None}
        
        # Use WMA as dynamic support/resistance
        long_wma = self.calculate_long_term_wma(data)
        current_long_wma = long_wma.iloc[-1] if len(long_wma) > 0 else None
        
        if current_long_wma is None:
            return {'support': None, 'resistance': None}
        
        # Determine if WMA acts as support or resistance
        current_price = data[self.price_column].iloc[-1]
        
        if current_price > current_long_wma:
            # Price above WMA, WMA acts as support
            return {
                'support': current_long_wma,
                'resistance': None,
                'dynamic_level': current_long_wma,
                'level_type': 'support'
            }
        else:
            # Price below WMA, WMA acts as resistance
            return {
                'support': None,
                'resistance': current_long_wma,
                'dynamic_level': current_long_wma,
                'level_type': 'resistance'
            }
    
    def get_market_sentiment(self, data: pd.DataFrame) -> float:
        """
        Calculate market sentiment based on WMA analysis.
        
        @param {pd.DataFrame} data - DataFrame containing market data
        @returns {float} Sentiment score between -1 (bearish) and 1 (bullish)
        """
        trend_analysis = self.detect_trend(data)
        
        if trend_analysis['trend'] == 'insufficient_data':
            return 0.0
        
        # Convert trend strength to sentiment score
        sentiment = 0.0
        if trend_analysis['trend'] == 'bullish':
            sentiment = trend_analysis['trend_strength']
        else:
            sentiment = -trend_analysis['trend_strength']
        
        return max(-1.0, min(1.0, sentiment))  # Ensure within [-1, 1] range
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        Validate that the input data meets requirements for WMA analysis.
        
        @param {pd.DataFrame} data - DataFrame to validate
        @returns {bool} True if data is valid, False otherwise
        """
        if data is None or data.empty:
            return False
        
        # Check required columns
        required_columns = [self.price_column]
        for col in required_columns:
            if col not in data.columns:
                return False
        
        # Check for sufficient data
        if len(data) < self.long_period:
            return False
        
        # Check for NaN values in price column
        if data[self.price_column].isna().any():
            return False
        
        return True
    
    def create_wma_data_record(self, data: pd.DataFrame, pair: Pair, coin: Coin) -> Optional[WmaData]:
        """
        Create a WmaData record from current analysis.
        
        @param {pd.DataFrame} data - DataFrame containing market data
        @param {Pair} pair - Trading pair
        @param {Coin} coin - Coin being analyzed
        @returns {WmaData|null} WmaData record or null if insufficient data
        """
        if not self.validate_data(data):
            return None
        
        trend_analysis = self.detect_trend(data)
        signals = self.generate_signals(self.calculate_indicators(data.copy()))
        
        if trend_analysis['trend'] == 'insufficient_data':
            return None
        
        # Determine signal type
        latest_signal = signals.iloc[-1] if len(signals) > 0 else 0
        if latest_signal == 1:
            signal_type = SignalType.BUY
        elif latest_signal == -1:
            signal_type = SignalType.SELL
        else:
            signal_type = SignalType.HOLD
        
        # Calculate confidence based on trend strength
        confidence = trend_analysis['trend_strength']
        
        # Create WmaData record
        wma_data = WmaData(
            pair=pair,
            coin=coin,
            period=self.short_period,  # Use short period as the primary period
            wma_value=trend_analysis['short_wma'],
            signal_type=signal_type,
            confidence=confidence,
            current_price=trend_analysis['current_price'],
            trend_strength=trend_analysis['trend_strength']
        )
        
        return wma_data