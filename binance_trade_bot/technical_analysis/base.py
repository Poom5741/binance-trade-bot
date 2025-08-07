"""
Base abstract class for technical analysis implementations.
"""

from abc import ABC, abstractmethod
import pandas as pd


class TechnicalAnalysisBase(ABC):
    """
    Abstract base class for technical analysis implementations.
    
    This class defines the interface that all technical analysis implementations
    must follow, ensuring consistent functionality across different analysis
    methods and indicators.
    """
    
    def __init__(self, config):
        """
        Initialize the technical analysis module with configuration.
        
        @param {dict} config - Configuration dictionary containing TA settings
        """
        self.config = config
    
    @abstractmethod
    def calculate_indicators(self, data):
        """
        Calculate technical indicators for the given market data.
        
        @param {pd.DataFrame} data - DataFrame containing OHLCV market data
        @returns {pd.DataFrame} DataFrame with calculated indicators added
        """
        pass
    
    @abstractmethod
    def generate_signals(self, data_with_indicators):
        """
        Generate trading signals based on technical indicators.
        
        @param {pd.DataFrame} data_with_indicators - DataFrame with indicators
        @returns {pd.Series} Series of trading signals (1 for buy, -1 for sell, 0 for hold)
        """
        pass
    
    @abstractmethod
    def analyze_trend(self, data):
        """
        Analyze the current market trend.
        
        @param {pd.DataFrame} data - DataFrame containing market data
        @returns {dict} Dictionary containing trend analysis results
        """
        pass
    
    @abstractmethod
    def calculate_support_resistance(self, data):
        """
        Calculate key support and resistance levels.
        
        @param {pd.DataFrame} data - DataFrame containing market data
        @returns {dict} Dictionary with support and resistance levels
        """
        pass
    
    @abstractmethod
    def get_market_sentiment(self, data):
        """
        Calculate market sentiment based on technical indicators.
        
        @param {pd.DataFrame} data - DataFrame containing market data
        @returns {float} Sentiment score between -1 (bearish) and 1 (bullish)
        """
        pass
    
    @abstractmethod
    def validate_data(self, data):
        """
        Validate that the input data meets requirements for analysis.
        
        @param {pd.DataFrame} data - DataFrame to validate
        @returns {bool} True if data is valid, False otherwise
        """
        pass