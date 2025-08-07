"""
Statistics Manager for performance tracking.
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

# Optional pandas dependency
try:  # pragma: no cover
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover - when pandas is unavailable
    from types import SimpleNamespace

    class _DummyDataFrame:
        pass

    pd = SimpleNamespace(DataFrame=_DummyDataFrame)  # type: ignore

from .base import StatisticsBase
try:  # pragma: no cover - allow import without SQLAlchemy
    from .models import (
        Statistics,
        DailyPerformance,
        WeeklyPerformance,
        TotalPerformance,
        TradeRecord,
    )
except Exception:  # pragma: no cover - fallback when models can't be imported
    Statistics = DailyPerformance = WeeklyPerformance = TotalPerformance = TradeRecord = None  # type: ignore
from .calculators import (
    DailyPerformanceCalculator,
    WeeklyPerformanceCalculator,
    TotalPerformanceCalculator,
    ProfitLossCalculator,
    WinLossCalculator,
    AdvancedMetricsCalculator,
)
from ..database import Database

# Import trading and coin models lazily to avoid hard dependency on SQLAlchemy
try:  # pragma: no cover
    from ..models.trade import Trade, TradeState  # type: ignore
except Exception:  # pragma: no cover
    class Trade:  # type: ignore
        pass

    class TradeState:  # type: ignore
        COMPLETE = "COMPLETE"

try:  # pragma: no cover
    from ..models.coin import Coin, CoinValue  # type: ignore
except Exception:  # pragma: no cover
    class Coin:  # type: ignore
        symbol = ""

    class CoinValue:  # type: ignore
        pass

try:  # pragma: no cover
    from ..logger import Logger  # type: ignore
except Exception:  # pragma: no cover
    class Logger:  # type: ignore
        def info(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass


class StatisticsManager:
    """
    Main statistics manager class that coordinates all statistics calculations.
    """
    
    def __init__(self, config, database: Database, logger: Logger):
        """
        Initialize the statistics manager.
        
        @param {dict} config - Configuration dictionary
        @param {Database} database - Database instance
        @param {Logger} logger - Logger instance
        """
        self.config = config
        self.database = database
        self.logger = logger
        
        # Initialize calculators
        self.daily_calculator = DailyPerformanceCalculator(config, database)
        self.weekly_calculator = WeeklyPerformanceCalculator(config, database)
        self.total_calculator = TotalPerformanceCalculator(config, database)
        
        # Initialize helper calculators
        self.profit_loss_calculator = ProfitLossCalculator()
        self.win_loss_calculator = WinLossCalculator()
        self.advanced_metrics_calculator = AdvancedMetricsCalculator()
    
    def get_daily_statistics(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Get daily statistics for a specific date.
        
        @param {datetime} date - Date for which to get statistics (defaults to today)
        @returns {dict} Dictionary containing daily statistics
        """
        if date is None:
            date = datetime.now().date()
        
        if isinstance(date, datetime):
            date = date.date()
        
        # Convert to datetime at start of day
        start_date = datetime.combine(date, datetime.min.time())
        end_date = datetime.combine(date, datetime.max.time())
        
        try:
            with self.database.db_session() as session:
                # Get trades for the day
                trades = session.query(Trade).filter(
                    Trade.state == TradeState.COMPLETE,
                    Trade.datetime >= start_date,
                    Trade.datetime <= end_date
                ).all()
                
                # Convert to DataFrame
                trade_data = self._trades_to_dataframe(trades)
                
                # Calculate statistics
                daily_stats = self.daily_calculator.calculate_statistics(trade_data, start_date)
                
                # Save to database
                self._save_daily_statistics(session, daily_stats, start_date)
                
                return daily_stats
                
        except Exception as e:
            self.logger.error(f"Error calculating daily statistics: {str(e)}")
            return self._get_empty_daily_stats(start_date)
    
    def get_weekly_statistics(self, week_start: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Get weekly statistics for a specific week.
        
        @param {datetime} week_start - Start of the week (defaults to current week)
        @returns {dict} Dictionary containing weekly statistics
        """
        if week_start is None:
            # Get current week start (Monday)
            today = datetime.now()
            week_start = today - timedelta(days=today.weekday())
        
        # Calculate week end (Sunday)
        week_end = week_start + timedelta(days=6)
        
        try:
            with self.database.db_session() as session:
                # Get trades for the week
                trades = session.query(Trade).filter(
                    Trade.state == TradeState.COMPLETE,
                    Trade.datetime >= week_start,
                    Trade.datetime <= week_end
                ).all()
                
                # Convert to DataFrame
                trade_data = self._trades_to_dataframe(trades)
                
                # Calculate statistics
                weekly_stats = self.weekly_calculator.calculate_statistics(trade_data, week_start, week_end)
                
                # Save to database
                self._save_weekly_statistics(session, weekly_stats, week_start, week_end)
                
                return weekly_stats
                
        except Exception as e:
            self.logger.error(f"Error calculating weekly statistics: {str(e)}")
            return self._get_empty_weekly_stats(week_start, week_end)
    
    def get_total_statistics(self, start_date: Optional[datetime] = None, 
                           end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Get total statistics for a specific period.
        
        @param {datetime} start_date - Start date for the period
        @param {datetime} end_date - End date for the period
        @returns {dict} Dictionary containing total statistics
        """
        if start_date is None:
            start_date = datetime.now() - timedelta(days=30)  # Default to last 30 days
        
        if end_date is None:
            end_date = datetime.now()
        
        try:
            with self.database.db_session() as session:
                # Get trades for the period
                trades = session.query(Trade).filter(
                    Trade.state == TradeState.COMPLETE,
                    Trade.datetime >= start_date,
                    Trade.datetime <= end_date
                ).all()
                
                # Convert to DataFrame
                trade_data = self._trades_to_dataframe(trades)
                
                # Calculate statistics
                total_stats = self.total_calculator.calculate_statistics(trade_data, start_date, end_date)
                
                # Save to database
                self._save_total_statistics(session, total_stats, start_date, end_date)
                
                return total_stats
                
        except Exception as e:
            self.logger.error(f"Error calculating total statistics: {str(e)}")
            return self._get_empty_total_stats(start_date, end_date)
    
    def get_portfolio_statistics(self, coin_symbols: List[str] = None) -> Dict[str, Any]:
        """
        Get portfolio statistics for specific coins.
        
        @param {List[str]} coin_symbols - List of coin symbols to include
        @returns {dict} Dictionary containing portfolio statistics
        """
        try:
            with self.database.db_session() as session:
                # Get current coin values
                query = session.query(Coin)
                if coin_symbols:
                    query = query.filter(Coin.symbol.in_(coin_symbols))
                
                coins = query.all()
                
                portfolio_data = []
                for coin in coins:
                    # Get latest coin value
                    latest_value = session.query(CoinValue).filter(
                        CoinValue.coin_id == coin.symbol
                    ).order_by(CoinValue.datetime.desc()).first()
                    
                    if latest_value:
                        portfolio_data.append({
                            'symbol': coin.symbol,
                            'balance': latest_value.balance,
                            'current_price': latest_value.usd_price,
                            'current_value': latest_value.usd_value,
                            'initial_value': latest_value.balance * latest_value.usd_price,  # Simplified
                        })
                
                # Calculate portfolio profit/loss
                portfolio_stats = self.profit_loss_calculator.calculate_portfolio_profit_loss(portfolio_data)
                
                return {
                    'portfolio_data': portfolio_data,
                    'portfolio_statistics': portfolio_stats,
                    'timestamp': datetime.now().isoformat(),
                }
                
        except Exception as e:
            self.logger.error(f"Error calculating portfolio statistics: {str(e)}")
            return {
                'portfolio_data': [],
                'portfolio_statistics': {
                    'total_profit_loss': 0.0,
                    'total_profit_loss_percentage': 0.0,
                    'total_investment': 0.0,
                    'current_value': 0.0,
                },
                'timestamp': datetime.now().isoformat(),
            }
    
    def get_portfolio_value(self, coin_symbols: List[str] = None) -> Dict[str, Any]:
        """
        Calculate current portfolio value with USD conversion.
        
        @param {List[str]} coin_symbols - List of coin symbols to include
        @returns {dict} Dictionary containing portfolio value information
        """
        try:
            # Validate input parameters
            if coin_symbols is not None:
                if not isinstance(coin_symbols, list):
                    return {
                        'total_portfolio_value': 0.0,
                        'total_holdings_count': 0,
                        'individual_holdings': [],
                        'timestamp': datetime.now().isoformat(),
                        'status': 'error',
                        'message': 'coin_symbols must be a list or None'
                    }
                
                # Validate coin symbols format
                for symbol in coin_symbols:
                    if not isinstance(symbol, str) or not symbol.strip():
                        return {
                            'total_portfolio_value': 0.0,
                            'total_holdings_count': 0,
                            'individual_holdings': [],
                            'timestamp': datetime.now().isoformat(),
                            'status': 'error',
                            'message': f'Invalid coin symbol format: {symbol}'
                        }
            
            with self.database.db_session() as session:
                # Get current coin values
                query = session.query(Coin)
                if coin_symbols:
                    query = query.filter(Coin.symbol.in_(coin_symbols))
                
                coins = query.all()
                
                if not coins:
                    return {
                        'total_portfolio_value': 0.0,
                        'total_holdings_count': 0,
                        'individual_holdings': [],
                        'timestamp': datetime.now().isoformat(),
                        'status': 'success',
                        'message': 'No coins found in portfolio'
                    }
                
                total_portfolio_value = 0.0
                individual_holdings = []
                
                for coin in coins:
                    # Validate coin data
                    if not hasattr(coin, 'symbol') or not coin.symbol:
                        self.logger.warning(f"Coin with invalid symbol encountered: {coin}")
                        continue
                    
                    # Get latest coin value
                    latest_value = session.query(CoinValue).filter(
                        CoinValue.coin_id == coin.symbol
                    ).order_by(CoinValue.datetime.desc()).first()
                    
                    if latest_value:
                        # Validate coin value data
                        if latest_value.balance is None or latest_value.usd_price is None:
                            self.logger.warning(f"Invalid coin value data for {coin.symbol}: balance={latest_value.balance}, price={latest_value.usd_price}")
                            continue
                        
                        # Calculate USD value
                        coin_value = latest_value.usd_value
                        if coin_value is None:
                            coin_value = latest_value.balance * latest_value.usd_price
                        
                        # Validate calculated value
                        if coin_value < 0:
                            self.logger.warning(f"Negative coin value detected for {coin.symbol}: {coin_value}")
                            continue
                        
                        total_portfolio_value += coin_value
                        
                        # Calculate percentage of portfolio
                        percentage_of_portfolio = (coin_value / total_portfolio_value * 100) if total_portfolio_value > 0 else 0.0
                        
                        individual_holdings.append({
                            'symbol': coin.symbol,
                            'balance': latest_value.balance,
                            'usd_price': latest_value.usd_price,
                            'usd_value': coin_value,
                            'percentage_of_portfolio': percentage_of_portfolio,
                            'daily_change_percentage': latest_value.daily_change_percentage,
                            'risk_score': latest_value.risk_score,
                        })
                    else:
                        self.logger.warning(f"No coin value data found for {coin.symbol}")
                
                # Validate total portfolio value
                if total_portfolio_value < 0:
                    self.logger.error(f"Negative total portfolio value detected: {total_portfolio_value}")
                    total_portfolio_value = 0.0
                
                # Sort by value descending
                individual_holdings.sort(key=lambda x: x['usd_value'], reverse=True)
                
                return {
                    'total_portfolio_value': round(total_portfolio_value, 8),
                    'total_holdings_count': len(individual_holdings),
                    'individual_holdings': individual_holdings,
                    'timestamp': datetime.now().isoformat(),
                    'status': 'success'
                }
                
        except Exception as e:
            self.logger.error(f"Error calculating portfolio value: {str(e)}")
            return {
                'total_portfolio_value': 0.0,
                'total_holdings_count': 0,
                'individual_holdings': [],
                'timestamp': datetime.now().isoformat(),
                'status': 'error',
                'message': str(e)
            }
    
    def get_portfolio_composition(self, coin_symbols: List[str] = None) -> Dict[str, Any]:
        """
        Analyze portfolio composition and distribution.
        
        @param {List[str]} coin_symbols - List of coin symbols to include
        @returns {dict} Dictionary containing portfolio composition analysis
        """
        try:
            # Get portfolio value data first
            portfolio_data = self.get_portfolio_value(coin_symbols)
            
            if portfolio_data['status'] == 'error':
                return portfolio_data
            
            individual_holdings = portfolio_data['individual_holdings']
            total_value = portfolio_data['total_portfolio_value']
            
            # Validate input data
            if not isinstance(individual_holdings, list):
                self.logger.error("Invalid individual_holdings data type")
                return {
                    'total_portfolio_value': total_value,
                    'total_holdings_count': 0,
                    'individual_holdings': [],
                    'composition_analysis': {},
                    'timestamp': datetime.now().isoformat(),
                    'status': 'error',
                    'message': 'Invalid portfolio data structure'
                }
            
            # Calculate composition metrics
            composition_analysis = {
                'by_value': [],
                'by_percentage': [],
                'concentration_metrics': {},
                'diversification_score': 0.0,
                'largest_holding': 0.0,
                'smallest_holding': 0.0,
                'average_holding': 0.0,
            }
            
            if individual_holdings:
                # Validate each holding
                valid_holdings = []
                for holding in individual_holdings:
                    if (isinstance(holding, dict) and
                        'symbol' in holding and
                        'usd_value' in holding and
                        'percentage_of_portfolio' in holding and
                        isinstance(holding['usd_value'], (int, float)) and
                        isinstance(holding['percentage_of_portfolio'], (int, float))):
                        
                        # Validate percentage is reasonable (0-100)
                        if 0 <= holding['percentage_of_portfolio'] <= 100:
                            valid_holdings.append(holding)
                        else:
                            self.logger.warning(f"Invalid percentage for {holding['symbol']}: {holding['percentage_of_portfolio']}")
                    else:
                        self.logger.warning(f"Invalid holding data: {holding}")
                
                if not valid_holdings:
                    self.logger.warning("No valid holdings found for composition analysis")
                    return {
                        **portfolio_data,
                        'composition_analysis': composition_analysis,
                        'status': 'success'
                    }
                
                # Sort by percentage for analysis
                sorted_by_percentage = sorted(valid_holdings, key=lambda x: x['percentage_of_portfolio'], reverse=True)
                
                # Value-based analysis
                composition_analysis['by_value'] = [
                    {
                        'symbol': holding['symbol'],
                        'value': round(holding['usd_value'], 8),
                        'percentage': round(holding['percentage_of_portfolio'], 4)
                    }
                    for holding in valid_holdings
                ]
                
                # Percentage-based analysis
                composition_analysis['by_percentage'] = [
                    {
                        'symbol': holding['symbol'],
                        'balance': holding.get('balance', 0),
                        'usd_price': holding.get('usd_price', 0),
                        'usd_value': round(holding['usd_value'], 8),
                        'percentage_of_portfolio': round(holding['percentage_of_portfolio'], 4),
                        'daily_change_percentage': holding.get('daily_change_percentage'),
                        'risk_score': holding.get('risk_score'),
                    }
                    for holding in sorted_by_percentage
                ]
                
                # Concentration metrics
                top_holding_percentage = sorted_by_percentage[0]['percentage_of_portfolio'] if sorted_by_percentage else 0.0
                top_3_holdings_percentage = sum(holding['percentage_of_portfolio'] for holding in sorted_by_percentage[:3])
                top_5_holdings_percentage = sum(holding['percentage_of_portfolio'] for holding in sorted_by_percentage[:5])
                
                # Calculate Herfindahl Index (sum of squared percentages)
                herfindahl_index = sum((holding['percentage_of_portfolio'] / 100) ** 2 for holding in valid_holdings)
                
                composition_analysis['concentration_metrics'] = {
                    'top_holding_percentage': round(top_holding_percentage, 4),
                    'top_3_holdings_percentage': round(top_3_holdings_percentage, 4),
                    'top_5_holdings_percentage': round(top_5_holdings_percentage, 4),
                    'herfindahl_index': round(herfindahl_index, 6),
                    'effective_number_of_holdings': round(1 / herfindahl_index, 2) if herfindahl_index > 0 else 0,
                }
                
                # Diversification score (0-100, higher is more diversified)
                # Score decreases as concentration increases
                max_concentration = max(holding['percentage_of_portfolio'] for holding in valid_holdings)
                composition_analysis['diversification_score'] = max(0, round(100 - (max_concentration * 2), 2))
                
                # Individual holding metrics
                composition_analysis['largest_holding'] = round(top_holding_percentage, 4)
                composition_analysis['smallest_holding'] = round(sorted_by_percentage[-1]['percentage_of_portfolio'], 4) if sorted_by_percentage else 0.0
                composition_analysis['average_holding'] = round(sum(holding['percentage_of_portfolio'] for holding in valid_holdings) / len(valid_holdings), 4)
            
            return {
                **portfolio_data,
                'composition_analysis': composition_analysis,
                'status': 'success'
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating portfolio composition: {str(e)}")
            return {
                'total_portfolio_value': 0.0,
                'total_holdings_count': 0,
                'individual_holdings': [],
                'composition_analysis': {},
                'timestamp': datetime.now().isoformat(),
                'status': 'error',
                'message': str(e)
            }
    
    def get_portfolio_performance_benchmarks(self, benchmark_symbol: str = 'BTC',
                                           coin_symbols: List[str] = None) -> Dict[str, Any]:
        """
        Compare portfolio performance against benchmarks.
        
        @param {str} benchmark_symbol - Symbol to use as benchmark (default: BTC)
        @param {List[str]} coin_symbols - List of coin symbols to include
        @returns {dict} Dictionary containing performance comparison
        """
        try:
            # Validate input parameters
            if not isinstance(benchmark_symbol, str) or not benchmark_symbol.strip():
                return {
                    'portfolio_statistics': {},
                    'benchmark_statistics': {},
                    'comparison': {},
                    'timestamp': datetime.now().isoformat(),
                    'status': 'error',
                    'message': 'benchmark_symbol must be a non-empty string'
                }
            
            if coin_symbols is not None:
                if not isinstance(coin_symbols, list):
                    return {
                        'portfolio_statistics': {},
                        'benchmark_statistics': {},
                        'comparison': {},
                        'timestamp': datetime.now().isoformat(),
                        'status': 'error',
                        'message': 'coin_symbols must be a list or None'
                    }
                
                # Validate coin symbols format
                for symbol in coin_symbols:
                    if not isinstance(symbol, str) or not symbol.strip():
                        return {
                            'portfolio_statistics': {},
                            'benchmark_statistics': {},
                            'comparison': {},
                            'timestamp': datetime.now().isoformat(),
                            'status': 'error',
                            'message': f'Invalid coin symbol format: {symbol}'
                        }
            
            with self.database.db_session() as session:
                # Get portfolio statistics
                portfolio_stats = self.get_portfolio_statistics(coin_symbols)
                
                # Get benchmark data
                benchmark_data = session.query(CoinValue).filter(
                    CoinValue.coin_id == benchmark_symbol
                ).order_by(CoinValue.datetime.desc()).limit(30).all()  # Last 30 data points
                
                if not benchmark_data:
                    return {
                        'portfolio_statistics': portfolio_stats,
                        'benchmark_statistics': {},
                        'comparison': {},
                        'status': 'error',
                        'message': f'No benchmark data found for {benchmark_symbol}'
                    }
                
                # Validate benchmark data
                valid_benchmark_data = []
                for data_point in benchmark_data:
                    if (hasattr(data_point, 'usd_price') and
                        data_point.usd_price is not None and
                        data_point.usd_price > 0 and
                        hasattr(data_point, 'datetime') and
                        data_point.datetime is not None):
                        valid_benchmark_data.append(data_point)
                
                if not valid_benchmark_data:
                    return {
                        'portfolio_statistics': portfolio_stats,
                        'benchmark_statistics': {},
                        'comparison': {},
                        'status': 'error',
                        'message': f'No valid benchmark data found for {benchmark_symbol}'
                    }
                
                # Calculate benchmark performance
                benchmark_performance = self._calculate_benchmark_performance(valid_benchmark_data)
                
                # Get portfolio performance data
                portfolio_performance = self._calculate_portfolio_performance(coin_symbols)
                
                # Compare performance
                comparison = self._compare_performance(portfolio_performance, benchmark_performance)
                
                return {
                    'portfolio_statistics': portfolio_stats,
                    'benchmark_statistics': benchmark_performance,
                    'comparison': comparison,
                    'status': 'success'
                }
                
        except Exception as e:
            self.logger.error(f"Error calculating portfolio benchmarks: {str(e)}")
            return {
                'portfolio_statistics': {},
                'benchmark_statistics': {},
                'comparison': {},
                'timestamp': datetime.now().isoformat(),
                'status': 'error',
                'message': str(e)
            }
    
    def _calculate_benchmark_performance(self, benchmark_data: List[CoinValue]) -> Dict[str, Any]:
        """
        Calculate benchmark performance metrics.
        
        @param {List[CoinValue]} benchmark_data - Benchmark coin value data
        @returns {dict} Dictionary containing benchmark performance metrics
        """
        if not benchmark_data:
            return {}
        
        # Sort by datetime (oldest first)
        benchmark_data.sort(key=lambda x: x.datetime)
        
        # Validate data integrity
        for i, data_point in enumerate(benchmark_data):
            if not hasattr(data_point, 'usd_price') or data_point.usd_price is None:
                self.logger.warning(f"Invalid price data at index {i}: {data_point}")
                return {}
            if not hasattr(data_point, 'datetime') or data_point.datetime is None:
                self.logger.warning(f"Invalid datetime data at index {i}: {data_point}")
                return {}
        
        # Calculate price changes
        price_changes = []
        for i in range(1, len(benchmark_data)):
            prev_price = benchmark_data[i-1].usd_price
            curr_price = benchmark_data[i].usd_price
            if prev_price > 0 and curr_price > 0:
                price_change = (curr_price - prev_price) / prev_price
                price_changes.append(price_change)
            else:
                self.logger.warning(f"Invalid price values at index {i}: prev={prev_price}, curr={curr_price}")
        
        # Calculate metrics
        if price_changes:
            try:
                total_return = (benchmark_data[-1].usd_price / benchmark_data[0].usd_price - 1) * 100
                avg_daily_return = sum(price_changes) / len(price_changes) * 100
                
                # Calculate volatility (standard deviation of returns)
                variance = sum((x - avg_daily_return/100) ** 2 for x in price_changes) / len(price_changes)
                volatility = variance ** 0.5 * 100
                
                # Calculate max drawdown
                cumulative_returns = [1 + change for change in price_changes]
                running_max = [cumulative_returns[0]]
                for i in range(1, len(cumulative_returns)):
                    running_max.append(max(running_max[-1], cumulative_returns[i]))
                drawdowns = [(cumulative_returns[i] - running_max[i]) / running_max[i] for i in range(len(cumulative_returns))]
                max_drawdown = abs(min(drawdowns)) * 100 if drawdowns else 0.0
                
                return {
                    'symbol': benchmark_data[0].coin_id,
                    'current_price': round(benchmark_data[-1].usd_price, 8),
                    'period_start_price': round(benchmark_data[0].usd_price, 8),
                    'total_return_percentage': round(total_return, 4),
                    'average_daily_return_percentage': round(avg_daily_return, 4),
                    'volatility_percentage': round(volatility, 4),
                    'max_drawdown_percentage': round(max_drawdown, 4),
                    'data_points': len(benchmark_data),
                    'period_start': benchmark_data[0].datetime.isoformat(),
                    'period_end': benchmark_data[-1].datetime.isoformat(),
                }
            except Exception as e:
                self.logger.error(f"Error calculating benchmark performance: {str(e)}")
                return {
                    'symbol': benchmark_data[0].coin_id,
                    'current_price': round(benchmark_data[-1].usd_price, 8),
                    'period_start_price': round(benchmark_data[0].usd_price, 8),
                    'total_return_percentage': 0.0,
                    'average_daily_return_percentage': 0.0,
                    'volatility_percentage': 0.0,
                    'max_drawdown_percentage': 0.0,
                    'data_points': len(benchmark_data),
                    'period_start': benchmark_data[0].datetime.isoformat(),
                    'period_end': benchmark_data[-1].datetime.isoformat(),
                }
        else:
            return {
                'symbol': benchmark_data[0].coin_id,
                'current_price': round(benchmark_data[-1].usd_price, 8),
                'period_start_price': round(benchmark_data[0].usd_price, 8),
                'total_return_percentage': 0.0,
                'average_daily_return_percentage': 0.0,
                'volatility_percentage': 0.0,
                'max_drawdown_percentage': 0.0,
                'data_points': len(benchmark_data),
                'period_start': benchmark_data[0].datetime.isoformat(),
                'period_end': benchmark_data[-1].datetime.isoformat(),
            }
    
    def _calculate_portfolio_performance(self, coin_symbols: List[str] = None) -> Dict[str, Any]:
        """
        Calculate portfolio performance metrics.
        
        @param {List[str]} coin_symbols - List of coin symbols to include
        @returns {dict} Dictionary containing portfolio performance metrics
        """
        try:
            # Get portfolio value data
            portfolio_data = self.get_portfolio_value(coin_symbols)
            
            if portfolio_data['status'] == 'error' or not portfolio_data['individual_holdings']:
                return {
                    'total_return_percentage': 0.0,
                    'average_daily_return_percentage': 0.0,
                    'volatility_percentage': 0.0,
                    'max_drawdown_percentage': 0.0,
                }
            
            # This is a simplified calculation - in practice, you'd want to
            # get historical portfolio values to calculate proper performance metrics
            total_investment = sum(holding.get('initial_value', 0) for holding in portfolio_data['individual_holdings'])
            current_value = portfolio_data['total_portfolio_value']
            
            if total_investment > 0:
                total_return = (current_value - total_investment) / total_investment * 100
            else:
                total_return = 0.0
            
            return {
                'total_return_percentage': total_return,
                'average_daily_return_percentage': total_return / 30,  # Simplified
                'volatility_percentage': 0.0,  # Would need historical data
                'max_drawdown_percentage': 0.0,  # Would need historical data
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating portfolio performance: {str(e)}")
            return {
                'total_return_percentage': 0.0,
                'average_daily_return_percentage': 0.0,
                'volatility_percentage': 0.0,
                'max_drawdown_percentage': 0.0,
            }
    
    def _compare_performance(self, portfolio_performance: Dict[str, Any],
                           benchmark_performance: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare portfolio performance against benchmark.
        
        @param {dict} portfolio_performance - Portfolio performance metrics
        @param {dict} benchmark_performance - Benchmark performance metrics
        @returns {dict} Dictionary containing performance comparison
        """
        comparison = {
            'outperformance': 0.0,
            'relative_strength': 0.0,
            'risk_adjusted_performance': 0.0,
            'performance_summary': '',
        }
        
        try:
            # Validate input dictionaries
            if not isinstance(portfolio_performance, dict):
                portfolio_performance = {}
            if not isinstance(benchmark_performance, dict):
                benchmark_performance = {}
            
            # Calculate outperformance
            portfolio_return = portfolio_performance.get('total_return_percentage', 0.0)
            benchmark_return = benchmark_performance.get('total_return_percentage', 0.0)
            
            # Validate return values are numeric
            try:
                portfolio_return = float(portfolio_return)
                benchmark_return = float(benchmark_return)
            except (ValueError, TypeError):
                self.logger.warning(f"Invalid return values: portfolio={portfolio_return}, benchmark={benchmark_return}")
                portfolio_return = 0.0
                benchmark_return = 0.0
            
            comparison['outperformance'] = round(portfolio_return - benchmark_return, 4)
            
            # Calculate relative strength
            if benchmark_return != 0:
                comparison['relative_strength'] = round(portfolio_return / benchmark_return, 4) if benchmark_return != 0 else 1.0
            else:
                comparison['relative_strength'] = 1.0 if portfolio_return >= 0 else -1.0
            
            # Calculate risk-adjusted performance (simplified Sharpe ratio comparison)
            portfolio_volatility = portfolio_performance.get('volatility_percentage', 0.0)
            benchmark_volatility = benchmark_performance.get('volatility_percentage', 0.0)
            
            # Validate volatility values are numeric
            try:
                portfolio_volatility = float(portfolio_volatility)
                benchmark_volatility = float(benchmark_volatility)
            except (ValueError, TypeError):
                self.logger.warning(f"Invalid volatility values: portfolio={portfolio_volatility}, benchmark={benchmark_volatility}")
                portfolio_volatility = 0.0
                benchmark_volatility = 0.0
            
            if portfolio_volatility > 0:
                portfolio_sharpe = portfolio_return / portfolio_volatility
            else:
                portfolio_sharpe = 0.0 if portfolio_return >= 0 else float('-inf')
            
            if benchmark_volatility > 0:
                benchmark_sharpe = benchmark_return / benchmark_volatility
            else:
                benchmark_sharpe = 0.0 if benchmark_return >= 0 else float('-inf')
            
            comparison['risk_adjusted_performance'] = round(portfolio_sharpe - benchmark_sharpe, 4)
            
            # Generate performance summary
            if comparison['outperformance'] > 0:
                comparison['performance_summary'] = f'Portfolio outperformed benchmark by {comparison["outperformance"]:.2f}%'
            elif comparison['outperformance'] < 0:
                comparison['performance_summary'] = f'Portfolio underperformed benchmark by {abs(comparison["outperformance"]):.2f}%'
            else:
                comparison['performance_summary'] = 'Portfolio performance matched benchmark'
            
        except Exception as e:
            self.logger.error(f"Error comparing performance: {str(e)}")
            comparison['performance_summary'] = 'Error comparing performance'
        
        return comparison
    
    def get_trade_statistics(self, trade_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics for a specific trade or all trades.
        
        @param {str} trade_id - Trade ID to get statistics for (optional)
        @returns {dict} Dictionary containing trade statistics
        """
        try:
            with self.database.db_session() as session:
                if trade_id:
                    # Get specific trade
                    trade = session.query(Trade).filter(Trade.id == trade_id).first()
                    if not trade:
                        return {'error': 'Trade not found'}
                    
                    return self._calculate_trade_statistics(trade)
                else:
                    # Get all trades
                    trades = session.query(Trade).filter(
                        Trade.state == TradeState.COMPLETE
                    ).all()
                    
                    # Calculate win/loss metrics
                    win_loss_stats = self.win_loss_calculator.calculate_win_loss_metrics(trades)
                    
                    return {
                        'trade_count': len(trades),
                        'win_loss_statistics': win_loss_stats,
                        'timestamp': datetime.now().isoformat(),
                    }
                    
        except Exception as e:
            self.logger.error(f"Error calculating trade statistics: {str(e)}")
            return {'error': str(e)}
    
    def get_advanced_statistics(self, period: str = 'total', start_date: Optional[datetime] = None,
                              end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Get advanced statistics including Sharpe ratio, maximum drawdown, etc.
        
        @param {str} period - Time period ('daily', 'weekly', 'total')
        @param {datetime} start_date - Start date for the period
        @param {datetime} end_date - End date for the period
        @returns {dict} Dictionary containing advanced statistics
        """
        try:
            # Get basic statistics first
            if period == 'daily':
                stats = self.get_daily_statistics(start_date)
            elif period == 'weekly':
                stats = self.get_weekly_statistics(start_date)
            else:  # total
                stats = self.get_total_statistics(start_date, end_date)
            
            # Extract returns for advanced calculations
            returns = self._extract_returns_from_stats(stats)
            
            # Calculate advanced metrics
            if returns:
                advanced_metrics = self.advanced_metrics_calculator.calculate_all_advanced_metrics(
                    returns, 
                    stats.get('total_volume', 0)
                )
                
                # Merge with basic statistics
                stats.update(advanced_metrics)
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error calculating advanced statistics: {str(e)}")
            return {'error': str(e)}
    
    def generate_statistics_report(self, period: str = 'daily', 
                                 start_date: Optional[datetime] = None,
                                 end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Generate a comprehensive statistics report.
        
        @param {str} period - Time period ('daily', 'weekly', 'total')
        @param {datetime} start_date - Start date for the period
        @param {datetime} end_date - End date for the period
        @returns {dict} Dictionary containing comprehensive statistics report
        """
        try:
            report = {
                'period': period,
                'generated_at': datetime.now().isoformat(),
                'basic_statistics': {},
                'profit_loss_statistics': {},
                'win_loss_statistics': {},
                'advanced_statistics': {},
                'portfolio_statistics': {},
            }
            
            # Get basic statistics
            if period == 'daily':
                report['basic_statistics'] = self.get_daily_statistics(start_date)
            elif period == 'weekly':
                report['basic_statistics'] = self.get_weekly_statistics(start_date)
            else:  # total
                report['basic_statistics'] = self.get_total_statistics(start_date, end_date)
            
            # Get profit/loss statistics
            report['profit_loss_statistics'] = self.get_trade_statistics()
            
            # Get win/loss statistics
            report['win_loss_statistics'] = self.win_loss_calculator.calculate_win_loss_metrics(
                self._get_completed_trades()
            )
            
            # Get advanced statistics
            report['advanced_statistics'] = self.get_advanced_statistics(period, start_date, end_date)
            
            # Get portfolio statistics
            report['portfolio_statistics'] = self.get_portfolio_statistics()
            
            return report
            
        except Exception as e:
            self.logger.error(f"Error generating statistics report: {str(e)}")
            return {'error': str(e)}
    
    def _trades_to_dataframe(self, trades: List[Trade]) -> pd.DataFrame:
        """
        Convert list of trades to DataFrame.
        
        @param {List[Trade]} trades - List of trade objects
        @returns {pd.DataFrame} DataFrame containing trade data
        """
        if not trades:
            return pd.DataFrame()
        
        trade_data = []
        for trade in trades:
            # Calculate profit/loss (simplified)
            profit_loss = 0.0
            if trade.selling and trade.alt_trade_amount and trade.crypto_trade_amount:
                profit_loss = trade.alt_trade_amount - trade.crypto_trade_amount
            elif not trade.selling and trade.crypto_trade_amount and trade.alt_trade_amount:
                profit_loss = trade.crypto_trade_amount - trade.alt_trade_amount
            
            trade_data.append({
                'id': trade.id,
                'datetime': trade.datetime,
                'selling': trade.selling,
                'alt_starting_balance': trade.alt_starting_balance,
                'alt_trade_amount': trade.alt_trade_amount,
                'crypto_starting_balance': trade.crypto_starting_balance,
                'crypto_trade_amount': trade.crypto_trade_amount,
                'profit_loss': profit_loss,
            })
        
        return pd.DataFrame(trade_data)
    
    def _extract_returns_from_stats(self, stats: Dict[str, Any]) -> List[float]:
        """
        Extract returns from statistics for advanced calculations.
        
        @param {dict} stats - Statistics dictionary
        @returns {List[float]} List of returns
        """
        # This is a simplified implementation - in practice, you'd want to
        # extract actual returns from trade data
        returns = []
        
        if 'total_profit_loss' in stats and 'total_volume' in stats:
            if stats['total_volume'] > 0:
                returns.append(stats['total_profit_loss'] / stats['total_volume'])
        
        return returns
    
    def _get_completed_trades(self) -> List[Trade]:
        """
        Get all completed trades from the database.
        
        @returns {List[Trade]} List of completed trades
        """
        try:
            with self.database.db_session() as session:
                return session.query(Trade).filter(
                    Trade.state == TradeState.COMPLETE
                ).all()
        except Exception as e:
            self.logger.error(f"Error getting completed trades: {str(e)}")
            return []
    
    def _calculate_trade_statistics(self, trade: Trade) -> Dict[str, Any]:
        """
        Calculate statistics for a single trade.
        
        @param {Trade} trade - Trade object
        @returns {dict} Dictionary containing trade statistics
        """
        # Calculate profit/loss
        profit_loss = 0.0
        if trade.selling and trade.alt_trade_amount and trade.crypto_trade_amount:
            profit_loss = trade.alt_trade_amount - trade.crypto_trade_amount
        elif not trade.selling and trade.crypto_trade_amount and trade.alt_trade_amount:
            profit_loss = trade.crypto_trade_amount - trade.alt_trade_amount
        
        # Calculate percentage
        percentage = 0.0
        if trade.selling and trade.crypto_trade_amount:
            percentage = (profit_loss / trade.crypto_trade_amount) * 100
        elif not trade.selling and trade.alt_trade_amount:
            percentage = (profit_loss / trade.alt_trade_amount) * 100
        
        return {
            'trade_id': trade.id,
            'datetime': trade.datetime.isoformat(),
            'selling': trade.selling,
            'alt_coin': trade.alt_coin.symbol if trade.alt_coin else None,
            'crypto_coin': trade.crypto_coin.symbol if trade.crypto_coin else None,
            'alt_trade_amount': trade.alt_trade_amount,
            'crypto_trade_amount': trade.crypto_trade_amount,
            'profit_loss': profit_loss,
            'profit_loss_percentage': percentage,
            'state': trade.state.value,
        }
    
    def _save_daily_statistics(self, session, stats: Dict[str, Any], date: datetime):
        """
        Save daily statistics to database.
        
        @param {Session} session - Database session
        @param {dict} stats - Statistics dictionary
        @param {datetime} date - Date for the statistics
        """
        try:
            # Check if statistics already exist
            existing_stats = session.query(DailyPerformance).filter(
                DailyPerformance.date == date
            ).first()
            
            if existing_stats:
                # Update existing statistics
                existing_stats.total_trades = stats.get('total_trades', 0)
                existing_stats.winning_trades = stats.get('winning_trades', 0)
                existing_stats.losing_trades = stats.get('losing_trades', 0)
                existing_stats.win_rate = stats.get('win_rate', 0.0)
                existing_stats.total_profit_loss = stats.get('total_profit_loss', 0.0)
                existing_stats.total_profit_loss_percentage = stats.get('total_profit_loss_percentage', 0.0)
                existing_stats.average_profit_loss = stats.get('average_profit_loss', 0.0)
                existing_stats.average_win = stats.get('average_win', 0.0)
                existing_stats.average_loss = stats.get('average_loss', 0.0)
                existing_stats.total_volume = stats.get('total_volume', 0.0)
                existing_stats.average_trade_size = stats.get('average_trade_size', 0.0)
                existing_stats.roi = stats.get('roi', 0.0)
                existing_stats.sharpe_ratio = stats.get('sharpe_ratio', 0.0)
                existing_stats.max_drawdown = stats.get('max_drawdown', 0.0)
                existing_stats.volatility = stats.get('volatility', 0.0)
                existing_stats.profit_factor = stats.get('profit_factor', 0.0)
                existing_stats.recovery_factor = stats.get('recovery_factor', 0.0)
                existing_stats.calmar_ratio = stats.get('calmar_ratio', 0.0)
                existing_stats.updated_at = datetime.utcnow()
            else:
                # Create new statistics
                daily_stats = DailyPerformance(date)
                daily_stats.total_trades = stats.get('total_trades', 0)
                daily_stats.winning_trades = stats.get('winning_trades', 0)
                daily_stats.losing_trades = stats.get('losing_trades', 0)
                daily_stats.win_rate = stats.get('win_rate', 0.0)
                daily_stats.total_profit_loss = stats.get('total_profit_loss', 0.0)
                daily_stats.total_profit_loss_percentage = stats.get('total_profit_loss_percentage', 0.0)
                daily_stats.average_profit_loss = stats.get('average_profit_loss', 0.0)
                daily_stats.average_win = stats.get('average_win', 0.0)
                daily_stats.average_loss = stats.get('average_loss', 0.0)
                daily_stats.total_volume = stats.get('total_volume', 0.0)
                daily_stats.average_trade_size = stats.get('average_trade_size', 0.0)
                daily_stats.roi = stats.get('roi', 0.0)
                daily_stats.sharpe_ratio = stats.get('sharpe_ratio', 0.0)
                daily_stats.max_drawdown = stats.get('max_drawdown', 0.0)
                daily_stats.volatility = stats.get('volatility', 0.0)
                daily_stats.profit_factor = stats.get('profit_factor', 0.0)
                daily_stats.recovery_factor = stats.get('recovery_factor', 0.0)
                daily_stats.calmar_ratio = stats.get('calmar_ratio', 0.0)
                
                session.add(daily_stats)
                
        except Exception as e:
            self.logger.error(f"Error saving daily statistics: {str(e)}")
    
    def _save_weekly_statistics(self, session, stats: Dict[str, Any], week_start: datetime, week_end: datetime):
        """
        Save weekly statistics to database.
        
        @param {Session} session - Database session
        @param {dict} stats - Statistics dictionary
        @param {datetime} week_start - Start of the week
        @param {datetime} week_end - End of the week
        """
        try:
            # Check if statistics already exist
            existing_stats = session.query(WeeklyPerformance).filter(
                WeeklyPerformance.week_start == week_start,
                WeeklyPerformance.week_end == week_end
            ).first()
            
            if existing_stats:
                # Update existing statistics
                existing_stats.total_trades = stats.get('total_trades', 0)
                existing_stats.winning_trades = stats.get('winning_trades', 0)
                existing_stats.losing_trades = stats.get('losing_trades', 0)
                existing_stats.win_rate = stats.get('win_rate', 0.0)
                existing_stats.total_profit_loss = stats.get('total_profit_loss', 0.0)
                existing_stats.total_profit_loss_percentage = stats.get('total_profit_loss_percentage', 0.0)
                existing_stats.average_profit_loss = stats.get('average_profit_loss', 0.0)
                existing_stats.average_win = stats.get('average_win', 0.0)
                existing_stats.average_loss = stats.get('average_loss', 0.0)
                existing_stats.total_volume = stats.get('total_volume', 0.0)
                existing_stats.average_trade_size = stats.get('average_trade_size', 0.0)
                existing_stats.roi = stats.get('roi', 0.0)
                existing_stats.sharpe_ratio = stats.get('sharpe_ratio', 0.0)
                existing_stats.max_drawdown = stats.get('max_drawdown', 0.0)
                existing_stats.volatility = stats.get('volatility', 0.0)
                existing_stats.profit_factor = stats.get('profit_factor', 0.0)
                existing_stats.recovery_factor = stats.get('recovery_factor', 0.0)
                existing_stats.calmar_ratio = stats.get('calmar_ratio', 0.0)
                existing_stats.updated_at = datetime.utcnow()
            else:
                # Create new statistics
                weekly_stats = WeeklyPerformance(week_start, week_end)
                weekly_stats.total_trades = stats.get('total_trades', 0)
                weekly_stats.winning_trades = stats.get('winning_trades', 0)
                weekly_stats.losing_trades = stats.get('losing_trades', 0)
                weekly_stats.win_rate = stats.get('win_rate', 0.0)
                weekly_stats.total_profit_loss = stats.get('total_profit_loss', 0.0)
                weekly_stats.total_profit_loss_percentage = stats.get('total_profit_loss_percentage', 0.0)
                weekly_stats.average_profit_loss = stats.get('average_profit_loss', 0.0)
                weekly_stats.average_win = stats.get('average_win', 0.0)
                weekly_stats.average_loss = stats.get('average_loss', 0.0)
                weekly_stats.total_volume = stats.get('total_volume', 0.0)
                weekly_stats.average_trade_size = stats.get('average_trade_size', 0.0)
                weekly_stats.roi = stats.get('roi', 0.0)
                weekly_stats.sharpe_ratio = stats.get('sharpe_ratio', 0.0)
                weekly_stats.max_drawdown = stats.get('max_drawdown', 0.0)
                weekly_stats.volatility = stats.get('volatility', 0.0)
                weekly_stats.profit_factor = stats.get('profit_factor', 0.0)
                weekly_stats.recovery_factor = stats.get('recovery_factor', 0.0)
                weekly_stats.calmar_ratio = stats.get('calmar_ratio', 0.0)
                
                session.add(weekly_stats)
                
        except Exception as e:
            self.logger.error(f"Error saving weekly statistics: {str(e)}")
    
    def _save_total_statistics(self, session, stats: Dict[str, Any], start_date: datetime, end_date: datetime):
        """
        Save total statistics to database.
        
        @param {Session} session - Database session
        @param {dict} stats - Statistics dictionary
        @param {datetime} start_date - Start date for the period
        @param {datetime} end_date - End date for the period
        """
        try:
            # Check if statistics already exist
            existing_stats = session.query(TotalPerformance).filter(
                TotalPerformance.start_date == start_date,
                TotalPerformance.end_date == end_date
            ).first()
            
            if existing_stats:
                # Update existing statistics
                existing_stats.total_trades = stats.get('total_trades', 0)
                existing_stats.winning_trades = stats.get('winning_trades', 0)
                existing_stats.losing_trades = stats.get('losing_trades', 0)
                existing_stats.win_rate = stats.get('win_rate', 0.0)
                existing_stats.total_profit_loss = stats.get('total_profit_loss', 0.0)
                existing_stats.total_profit_loss_percentage = stats.get('total_profit_loss_percentage', 0.0)
                existing_stats.average_profit_loss = stats.get('average_profit_loss', 0.0)
                existing_stats.average_win = stats.get('average_win', 0.0)
                existing_stats.average_loss = stats.get('average_loss', 0.0)
                existing_stats.total_volume = stats.get('total_volume', 0.0)
                existing_stats.average_trade_size = stats.get('average_trade_size', 0.0)
                existing_stats.roi = stats.get('roi', 0.0)
                existing_stats.sharpe_ratio = stats.get('sharpe_ratio', 0.0)
                existing_stats.max_drawdown = stats.get('max_drawdown', 0.0)
                existing_stats.volatility = stats.get('volatility', 0.0)
                existing_stats.profit_factor = stats.get('profit_factor', 0.0)
                existing_stats.recovery_factor = stats.get('recovery_factor', 0.0)
                existing_stats.calmar_ratio = stats.get('calmar_ratio', 0.0)
                existing_stats.updated_at = datetime.utcnow()
            else:
                # Create new statistics
                total_stats = TotalPerformance(start_date, end_date)
                total_stats.total_trades = stats.get('total_trades', 0)
                total_stats.winning_trades = stats.get('winning_trades', 0)
                total_stats.losing_trades = stats.get('losing_trades', 0)
                total_stats.win_rate = stats.get('win_rate', 0.0)
                total_stats.total_profit_loss = stats.get('total_profit_loss', 0.0)
                total_stats.total_profit_loss_percentage = stats.get('total_profit_loss_percentage', 0.0)
                total_stats.average_profit_loss = stats.get('average_profit_loss', 0.0)
                total_stats.average_win = stats.get('average_win', 0.0)
                total_stats.average_loss = stats.get('average_loss', 0.0)
                total_stats.total_volume = stats.get('total_volume', 0.0)
                total_stats.average_trade_size = stats.get('average_trade_size', 0.0)
                total_stats.roi = stats.get('roi', 0.0)
                total_stats.sharpe_ratio = stats.get('sharpe_ratio', 0.0)
                total_stats.max_drawdown = stats.get('max_drawdown', 0.0)
                total_stats.volatility = stats.get('volatility', 0.0)
                total_stats.profit_factor = stats.get('profit_factor', 0.0)
                total_stats.recovery_factor = stats.get('recovery_factor', 0.0)
                total_stats.calmar_ratio = stats.get('calmar_ratio', 0.0)
                
                session.add(total_stats)
                
        except Exception as e:
            self.logger.error(f"Error saving total statistics: {str(e)}")
    
    def _get_empty_daily_stats(self, date: datetime) -> Dict[str, Any]:
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
            'roi': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'volatility': 0.0,
            'profit_factor': 0.0,
            'recovery_factor': 0.0,
            'calmar_ratio': 0.0,
        }
    
    def _get_empty_weekly_stats(self, week_start: datetime, week_end: datetime) -> Dict[str, Any]:
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
            'roi': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'volatility': 0.0,
            'profit_factor': 0.0,
            'recovery_factor': 0.0,
            'calmar_ratio': 0.0,
        }
    
    def _get_empty_total_stats(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
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
            'roi': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'volatility': 0.0,
            'profit_factor': 0.0,
            'recovery_factor': 0.0,
            'calmar_ratio': 0.0,
            'trading_days': 0,
            'best_day': 0.0,
            'worst_day': 0.0,
        }