"""
Base abstract class for statistics implementations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any
import pandas as pd


class StatisticsBase(ABC):
    """
    Abstract base class for statistics implementations.
    
    This class defines the interface that all statistics implementations
    must follow, ensuring consistent functionality across different
    statistical calculations and metrics.
    """
    
    def __init__(self, config):
        """
        Initialize the statistics module with configuration.
        
        @param {dict} config - Configuration dictionary containing statistics settings
        """
        self.config = config
    
    @abstractmethod
    def calculate_statistics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate statistics for the given trading data.
        
        @param {pd.DataFrame} data - DataFrame containing trading data
        @returns {dict} Dictionary containing calculated statistics
        """
        pass
    
    @abstractmethod
    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        Validate that the input data meets requirements for statistics calculation.
        
        @param {pd.DataFrame} data - DataFrame to validate
        @returns {bool} True if data is valid, False otherwise
        """
        pass
    
    @abstractmethod
    def get_time_period(self) -> str:
        """
        Get the time period for this statistics calculator.
        
        @returns {str} Time period (daily, weekly, total, etc.)
        """
        pass
    
    def filter_data_by_time_period(self, data: pd.DataFrame, start_date: Optional[datetime] = None, 
                                 end_date: Optional[datetime] = None) -> pd.DataFrame:
        """
        Filter data by time period.
        
        @param {pd.DataFrame} data - DataFrame to filter
        @param {datetime} start_date - Start date for filtering (optional)
        @param {datetime} end_date - End date for filtering (optional)
        @returns {pd.DataFrame} Filtered DataFrame
        """
        if start_date and 'datetime' in data.columns:
            data = data[data['datetime'] >= start_date]
        if end_date and 'datetime' in data.columns:
            data = data[data['datetime'] <= end_date]
        return data
    
    def calculate_basic_metrics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate basic metrics for the given data.
        
        @param {pd.DataFrame} data - DataFrame containing trading data
        @returns {dict} Dictionary containing basic metrics
        """
        if data.empty:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_volume': 0.0,
                'average_trade_size': 0.0,
            }
        
        total_trades = len(data)
        winning_trades = len(data[data['profit_loss'] > 0]) if 'profit_loss' in data.columns else 0
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
        total_volume = data['crypto_trade_amount'].sum() if 'crypto_trade_amount' in data.columns else 0.0
        average_trade_size = total_volume / total_trades if total_trades > 0 else 0.0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_volume': total_volume,
            'average_trade_size': average_trade_size,
        }
    
    def format_statistics(self, statistics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format statistics for consistent output.
        
        @param {dict} statistics - Raw statistics dictionary
        @returns {dict} Formatted statistics dictionary
        """
        formatted = {}
        
        for key, value in statistics.items():
            if isinstance(value, float):
                formatted[key] = round(value, 6)
            elif isinstance(value, dict):
                formatted[key] = self.format_statistics(value)
            else:
                formatted[key] = value
        
        return formatted