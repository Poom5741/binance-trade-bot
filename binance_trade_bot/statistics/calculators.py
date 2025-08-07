"""
Statistics calculators for performance tracking.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from abc import ABC, abstractmethod

from .base import StatisticsBase
from ..database import Database
from ..models.trade import Trade, TradeState


class DailyPerformanceCalculator(StatisticsBase):
    """
    Calculator for daily performance statistics.
    """
    
    def __init__(self, config, database: Database):
        super().__init__(config)
        self.database = database
    
    def calculate_statistics(self, data: pd.DataFrame, date: datetime) -> Dict[str, Any]:
        """
        Calculate daily statistics.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @param {datetime} date - Date for the statistics
        @returns {dict} Dictionary containing daily statistics
        """
        if not self.validate_data(data):
            return self._get_empty_stats(date)
        
        # Calculate basic metrics
        basic_metrics = self.calculate_basic_metrics(data)
        
        # Calculate profit/loss metrics
        profit_loss_metrics = self.calculate_profit_loss_metrics(data)
        
        # Calculate win/loss metrics
        win_loss_metrics = self.calculate_win_loss_metrics(data)
        
        # Combine all metrics
        daily_stats = {
            'date': date.isoformat(),
            **basic_metrics,
            **profit_loss_metrics,
            **win_loss_metrics,
        }
        
        return self.format_statistics(daily_stats)
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        Validate daily trade data.
        
        @param {pd.DataFrame} data - DataFrame to validate
        @returns {bool} True if data is valid, False otherwise
        """
        return not data.empty and 'datetime' in data.columns
    
    def get_time_period(self) -> str:
        """Get the time period for this calculator."""
        return 'daily'
    
    def calculate_profit_loss_metrics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate profit/loss metrics for daily data.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @returns {dict} Dictionary containing profit/loss metrics
        """
        if 'profit_loss' not in data.columns or data.empty:
            return {
                'total_profit_loss': 0.0,
                'total_profit_loss_percentage': 0.0,
                'average_profit_loss': 0.0,
                'average_win': 0.0,
                'average_loss': 0.0,
            }
        
        profit_losses = data['profit_loss'].dropna()
        
        if profit_losses.empty:
            return {
                'total_profit_loss': 0.0,
                'total_profit_loss_percentage': 0.0,
                'average_profit_loss': 0.0,
                'average_win': 0.0,
                'average_loss': 0.0,
            }
        
        total_profit_loss = profit_losses.sum()
        average_profit_loss = profit_losses.mean()
        
        # Calculate average win and loss
        winning_trades = profit_losses[profit_losses > 0]
        losing_trades = profit_losses[profit_losses < 0]
        
        average_win = winning_trades.mean() if not winning_trades.empty else 0.0
        average_loss = losing_trades.mean() if not losing_trades.empty else 0.0
        
        # Calculate percentage (simplified)
        total_volume = data['crypto_trade_amount'].sum() if 'crypto_trade_amount' in data.columns else 1.0
        total_profit_loss_percentage = (total_profit_loss / total_volume) * 100 if total_volume > 0 else 0.0
        
        return {
            'total_profit_loss': total_profit_loss,
            'total_profit_loss_percentage': total_profit_loss_percentage,
            'average_profit_loss': average_profit_loss,
            'average_win': average_win,
            'average_loss': average_loss,
        }
    
    def calculate_win_loss_metrics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate win/loss metrics for daily data.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @returns {dict} Dictionary containing win/loss metrics
        """
        if 'profit_loss' not in data.columns or data.empty:
            return {
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
            }
        
        profit_losses = data['profit_loss'].dropna()
        
        if profit_losses.empty:
            return {
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
            }
        
        winning_trades = len(profit_losses[profit_losses > 0])
        losing_trades = len(profit_losses[profit_losses < 0])
        total_trades = len(profit_losses)
        
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
        
        return {
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
        }
    
    def _get_empty_stats(self, date: datetime) -> Dict[str, Any]:
        """Get empty daily statistics."""
        return {
            'date': date.isoformat(),
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_profit_loss': 0.0,
            'total_profit_loss_percentage': 0.0,
            'average_profit_loss': 0.0,
            'average_win': 0.0,
            'average_loss': 0.0,
            'total_volume': 0.0,
            'average_trade_size': 0.0,
        }


class WeeklyPerformanceCalculator(StatisticsBase):
    """
    Calculator for weekly performance statistics.
    """
    
    def __init__(self, config, database: Database):
        super().__init__(config)
        self.database = database
    
    def calculate_statistics(self, data: pd.DataFrame, week_start: datetime, week_end: datetime) -> Dict[str, Any]:
        """
        Calculate weekly statistics.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @param {datetime} week_start - Start of the week
        @param {datetime} week_end - End of the week
        @returns {dict} Dictionary containing weekly statistics
        """
        if not self.validate_data(data):
            return self._get_empty_stats(week_start, week_end)
        
        # Filter data by week
        weekly_data = self.filter_data_by_time_period(data, week_start, week_end)
        
        # Calculate basic metrics
        basic_metrics = self.calculate_basic_metrics(weekly_data)
        
        # Calculate profit/loss metrics
        profit_loss_metrics = self.calculate_profit_loss_metrics(weekly_data)
        
        # Calculate win/loss metrics
        win_loss_metrics = self.calculate_win_loss_metrics(weekly_data)
        
        # Combine all metrics
        weekly_stats = {
            'week_start': week_start.isoformat(),
            'week_end': week_end.isoformat(),
            **basic_metrics,
            **profit_loss_metrics,
            **win_loss_metrics,
        }
        
        return self.format_statistics(weekly_stats)
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        Validate weekly trade data.
        
        @param {pd.DataFrame} data - DataFrame to validate
        @returns {bool} True if data is valid, False otherwise
        """
        return not data.empty and 'datetime' in data.columns
    
    def get_time_period(self) -> str:
        """Get the time period for this calculator."""
        return 'weekly'
    
    def calculate_profit_loss_metrics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate profit/loss metrics for weekly data.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @returns {dict} Dictionary containing profit/loss metrics
        """
        if 'profit_loss' not in data.columns or data.empty:
            return {
                'total_profit_loss': 0.0,
                'total_profit_loss_percentage': 0.0,
                'average_profit_loss': 0.0,
                'average_win': 0.0,
                'average_loss': 0.0,
            }
        
        profit_losses = data['profit_loss'].dropna()
        
        if profit_losses.empty:
            return {
                'total_profit_loss': 0.0,
                'total_profit_loss_percentage': 0.0,
                'average_profit_loss': 0.0,
                'average_win': 0.0,
                'average_loss': 0.0,
            }
        
        total_profit_loss = profit_losses.sum()
        average_profit_loss = profit_losses.mean()
        
        # Calculate average win and loss
        winning_trades = profit_losses[profit_losses > 0]
        losing_trades = profit_losses[profit_losses < 0]
        
        average_win = winning_trades.mean() if not winning_trades.empty else 0.0
        average_loss = losing_trades.mean() if not losing_trades.empty else 0.0
        
        # Calculate percentage (simplified)
        total_volume = data['crypto_trade_amount'].sum() if 'crypto_trade_amount' in data.columns else 1.0
        total_profit_loss_percentage = (total_profit_loss / total_volume) * 100 if total_volume > 0 else 0.0
        
        return {
            'total_profit_loss': total_profit_loss,
            'total_profit_loss_percentage': total_profit_loss_percentage,
            'average_profit_loss': average_profit_loss,
            'average_win': average_win,
            'average_loss': average_loss,
        }
    
    def calculate_win_loss_metrics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate win/loss metrics for weekly data.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @returns {dict} Dictionary containing win/loss metrics
        """
        if 'profit_loss' not in data.columns or data.empty:
            return {
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
            }
        
        profit_losses = data['profit_loss'].dropna()
        
        if profit_losses.empty:
            return {
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
            }
        
        winning_trades = len(profit_losses[profit_losses > 0])
        losing_trades = len(profit_losses[profit_losses < 0])
        total_trades = len(profit_losses)
        
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
        
        return {
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
        }
    
    def _get_empty_stats(self, week_start: datetime, week_end: datetime) -> Dict[str, Any]:
        """Get empty weekly statistics."""
        return {
            'week_start': week_start.isoformat(),
            'week_end': week_end.isoformat(),
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_profit_loss': 0.0,
            'total_profit_loss_percentage': 0.0,
            'average_profit_loss': 0.0,
            'average_win': 0.0,
            'average_loss': 0.0,
            'total_volume': 0.0,
            'average_trade_size': 0.0,
        }


class TotalPerformanceCalculator(StatisticsBase):
    """
    Calculator for total performance statistics.
    """
    
    def __init__(self, config, database: Database):
        super().__init__(config)
        self.database = database
    
    def calculate_statistics(self, data: pd.DataFrame, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Calculate total statistics.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @param {datetime} start_date - Start date for the period
        @param {datetime} end_date - End date for the period
        @returns {dict} Dictionary containing total statistics
        """
        if not self.validate_data(data):
            return self._get_empty_stats(start_date, end_date)
        
        # Filter data by period
        period_data = self.filter_data_by_time_period(data, start_date, end_date)
        
        # Calculate basic metrics
        basic_metrics = self.calculate_basic_metrics(period_data)
        
        # Calculate profit/loss metrics
        profit_loss_metrics = self.calculate_profit_loss_metrics(period_data)
        
        # Calculate win/loss metrics
        win_loss_metrics = self.calculate_win_loss_metrics(period_data)
        
        # Calculate additional metrics
        additional_metrics = self.calculate_additional_metrics(period_data, start_date, end_date)
        
        # Combine all metrics
        total_stats = {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            **basic_metrics,
            **profit_loss_metrics,
            **win_loss_metrics,
            **additional_metrics,
        }
        
        return self.format_statistics(total_stats)
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        Validate total trade data.
        
        @param {pd.DataFrame} data - DataFrame to validate
        @returns {bool} True if data is valid, False otherwise
        """
        return not data.empty and 'datetime' in data.columns
    
    def get_time_period(self) -> str:
        """Get the time period for this calculator."""
        return 'total'
    
    def calculate_profit_loss_metrics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate profit/loss metrics for total data.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @returns {dict} Dictionary containing profit/loss metrics
        """
        if 'profit_loss' not in data.columns or data.empty:
            return {
                'total_profit_loss': 0.0,
                'total_profit_loss_percentage': 0.0,
                'average_profit_loss': 0.0,
                'average_win': 0.0,
                'average_loss': 0.0,
            }
        
        profit_losses = data['profit_loss'].dropna()
        
        if profit_losses.empty:
            return {
                'total_profit_loss': 0.0,
                'total_profit_loss_percentage': 0.0,
                'average_profit_loss': 0.0,
                'average_win': 0.0,
                'average_loss': 0.0,
            }
        
        total_profit_loss = profit_losses.sum()
        average_profit_loss = profit_losses.mean()
        
        # Calculate average win and loss
        winning_trades = profit_losses[profit_losses > 0]
        losing_trades = profit_losses[profit_losses < 0]
        
        average_win = winning_trades.mean() if not winning_trades.empty else 0.0
        average_loss = losing_trades.mean() if not losing_trades.empty else 0.0
        
        # Calculate percentage (simplified)
        total_volume = data['crypto_trade_amount'].sum() if 'crypto_trade_amount' in data.columns else 1.0
        total_profit_loss_percentage = (total_profit_loss / total_volume) * 100 if total_volume > 0 else 0.0
        
        return {
            'total_profit_loss': total_profit_loss,
            'total_profit_loss_percentage': total_profit_loss_percentage,
            'average_profit_loss': average_profit_loss,
            'average_win': average_win,
            'average_loss': average_loss,
        }
    
    def calculate_win_loss_metrics(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate win/loss metrics for total data.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @returns {dict} Dictionary containing win/loss metrics
        """
        if 'profit_loss' not in data.columns or data.empty:
            return {
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
            }
        
        profit_losses = data['profit_loss'].dropna()
        
        if profit_losses.empty:
            return {
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
            }
        
        winning_trades = len(profit_losses[profit_losses > 0])
        losing_trades = len(profit_losses[profit_losses < 0])
        total_trades = len(profit_losses)
        
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
        
        return {
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
        }
    
    def calculate_additional_metrics(self, data: pd.DataFrame, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Calculate additional metrics for total data.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @param {datetime} start_date - Start date for the period
        @param {datetime} end_date - End date for the period
        @returns {dict} Dictionary containing additional metrics
        """
        # Calculate trading days
        trading_days = self._calculate_trading_days(data, start_date, end_date)
        
        # Calculate best and worst days
        best_day, worst_day = self._calculate_best_worst_days(data)
        
        return {
            'trading_days': trading_days,
            'best_day': best_day,
            'worst_day': worst_day,
        }
    
    def _calculate_trading_days(self, data: pd.DataFrame, start_date: datetime, end_date: datetime) -> int:
        """
        Calculate number of trading days in the period.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @param {datetime} start_date - Start date for the period
        @param {datetime} end_date - End date for the period
        @returns {int} Number of trading days
        """
        if data.empty or 'datetime' not in data.columns:
            return 0
        
        # Extract unique dates
        unique_dates = data['datetime'].dt.date.unique()
        
        # Filter by date range
        filtered_dates = [
            date for date in unique_dates 
            if start_date.date() <= date <= end_date.date()
        ]
        
        return len(filtered_dates)
    
    def _calculate_best_worst_days(self, data: pd.DataFrame) -> tuple:
        """
        Calculate best and worst trading days.
        
        @param {pd.DataFrame} data - DataFrame containing trade data
        @returns {tuple} Best day and worst day profit/loss
        """
        if data.empty or 'datetime' not in data.columns or 'profit_loss' not in data.columns:
            return 0.0, 0.0
        
        # Group by date and sum profit/loss
        daily_pnl = data.groupby(data['datetime'].dt.date)['profit_loss'].sum()
        
        if daily_pnl.empty:
            return 0.0, 0.0
        
        best_day = daily_pnl.max()
        worst_day = daily_pnl.min()
        
        return best_day, worst_day
    
    def _get_empty_stats(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get empty total statistics."""
        return {
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_profit_loss': 0.0,
            'total_profit_loss_percentage': 0.0,
            'average_profit_loss': 0.0,
            'average_win': 0.0,
            'average_loss': 0.0,
            'total_volume': 0.0,
            'average_trade_size': 0.0,
            'trading_days': 0,
            'best_day': 0.0,
            'worst_day': 0.0,
        }


class ProfitLossCalculator:
    """
    Calculator for profit/loss metrics.
    """
    
    def calculate_portfolio_profit_loss(self, portfolio_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate portfolio profit/loss.
        
        @param {List[Dict[str, Any]]} portfolio_data - List of portfolio data dictionaries
        @returns {dict} Dictionary containing portfolio profit/loss metrics
        """
        if not portfolio_data:
            return {
                'total_profit_loss': 0.0,
                'total_profit_loss_percentage': 0.0,
                'total_investment': 0.0,
                'current_value': 0.0,
            }
        
        total_investment = sum(item.get('initial_value', 0) for item in portfolio_data)
        current_value = sum(item.get('current_value', 0) for item in portfolio_data)
        
        total_profit_loss = current_value - total_investment
        total_profit_loss_percentage = (total_profit_loss / total_investment) * 100 if total_investment > 0 else 0.0
        
        return {
            'total_profit_loss': total_profit_loss,
            'total_profit_loss_percentage': total_profit_loss_percentage,
            'total_investment': total_investment,
            'current_value': current_value,
        }


class WinLossCalculator:
    """
    Calculator for win/loss metrics.
    """
    
    def calculate_win_loss_metrics(self, trades: List[Trade]) -> Dict[str, Any]:
        """
        Calculate win/loss metrics for trades.
        
        @param {List[Trade]} trades - List of trade objects
        @returns {dict} Dictionary containing win/loss metrics
        """
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'average_holding_period': 0.0,
                'largest_win': 0.0,
                'largest_loss': 0.0,
            }
        
        # Calculate profit/loss for each trade
        trade_results = []
        for trade in trades:
            profit_loss = 0.0
            if trade.selling and trade.alt_trade_amount and trade.crypto_trade_amount:
                profit_loss = trade.alt_trade_amount - trade.crypto_trade_amount
            elif not trade.selling and trade.crypto_trade_amount and trade.alt_trade_amount:
                profit_loss = trade.crypto_trade_amount - trade.alt_trade_amount
            
            trade_results.append({
                'profit_loss': profit_loss,
                'holding_period': (trade.datetime - trade.datetime).total_seconds() / 3600 if trade.datetime else 0,
            })
        
        # Calculate metrics
        total_trades = len(trade_results)
        winning_trades = len([r for r in trade_results if r['profit_loss'] > 0])
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
        
        # Calculate average holding period
        average_holding_period = np.mean([r['holding_period'] for r in trade_results]) if trade_results else 0.0
        
        # Calculate largest win and loss
        profit_losses = [r['profit_loss'] for r in trade_results]
        largest_win = max(profit_losses) if profit_losses else 0.0
        largest_loss = min(profit_losses) if profit_losses else 0.0
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'average_holding_period': average_holding_period,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
        }


class AdvancedMetricsCalculator:
    """
    Calculator for advanced metrics like Sharpe ratio, maximum drawdown, etc.
    """
    
    def calculate_all_advanced_metrics(self, returns: List[float], total_volume: float) -> Dict[str, Any]:
        """
        Calculate all advanced metrics.
        
        @param {List[float]} returns - List of returns
        @param {float} total_volume - Total trading volume
        @returns {dict} Dictionary containing advanced metrics
        """
        if not returns:
            return {
                'roi': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'volatility': 0.0,
                'profit_factor': 0.0,
                'recovery_factor': 0.0,
                'calmar_ratio': 0.0,
            }
        
        returns_array = np.array(returns)
        
        # Calculate ROI
        roi = np.sum(returns_array) * 100 if total_volume > 0 else 0.0
        
        # Calculate Sharpe ratio
        sharpe_ratio = self._calculate_sharpe_ratio(returns_array)
        
        # Calculate maximum drawdown
        max_drawdown = self._calculate_max_drawdown(returns_array)
        
        # Calculate volatility
        volatility = np.std(returns_array) * np.sqrt(252) if len(returns_array) > 1 else 0.0
        
        # Calculate profit factor
        profit_factor = self._calculate_profit_factor(returns_array)
        
        # Calculate recovery factor
        recovery_factor = self._calculate_recovery_factor(roi, max_drawdown)
        
        # Calculate Calmar ratio
        calmar_ratio = self._calculate_calmar_ratio(roi, max_drawdown)
        
        return {
            'roi': roi,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'volatility': volatility,
            'profit_factor': profit_factor,
            'recovery_factor': recovery_factor,
            'calmar_ratio': calmar_ratio,
        }
    
    def _calculate_sharpe_ratio(self, returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """
        Calculate Sharpe ratio.
        
        @param {np.ndarray} returns - Array of returns
        @param {float} risk_free_rate - Risk-free rate
        @returns {float} Sharpe ratio
        """
        if len(returns) < 2:
            return 0.0
        
        excess_returns = returns - risk_free_rate / 252  # Daily risk-free rate
        sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
        
        return sharpe_ratio if not np.isnan(sharpe_ratio) else 0.0
    
    def _calculate_max_drawdown(self, returns: np.ndarray) -> float:
        """
        Calculate maximum drawdown.
        
        @param {np.ndarray} returns - Array of returns
        @returns {float} Maximum drawdown
        """
        if len(returns) == 0:
            return 0.0
        
        cumulative_returns = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdowns = (cumulative_returns - running_max) / running_max
        
        return abs(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0
    
    def _calculate_profit_factor(self, returns: np.ndarray) -> float:
        """
        Calculate profit factor.
        
        @param {np.ndarray} returns - Array of returns
        @returns {float} Profit factor
        """
        if len(returns) == 0:
            return 0.0
        
        gross_profit = np.sum(returns[returns > 0])
        gross_loss = abs(np.sum(returns[returns < 0]))
        
        return gross_profit / gross_loss if gross_loss > 0 else 0.0
    
    def _calculate_recovery_factor(self, roi: float, max_drawdown: float) -> float:
        """
        Calculate recovery factor.
        
        @param {float} roi - Return on investment
        @param {float} max_drawdown - Maximum drawdown
        @returns {float} Recovery factor
        """
        if max_drawdown == 0:
            return 0.0
        
        return roi / max_drawdown
    
    def _calculate_calmar_ratio(self, roi: float, max_drawdown: float) -> float:
        """
        Calculate Calmar ratio.
        
        @param {float} roi - Return on investment
        @param {float} max_drawdown - Maximum drawdown
        @returns {float} Calmar ratio
        """
        if max_drawdown == 0:
            return 0.0
        
        return roi / max_drawdown