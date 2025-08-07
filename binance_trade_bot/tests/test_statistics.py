"""
Unit tests for statistics module.
"""

import unittest
from datetime import datetime, timedelta
import math
from unittest.mock import Mock, patch, MagicMock

# Pandas is an optional dependency in the execution environment. The tests that
# rely on it will be skipped if it's unavailable so that the remaining unit tests
# can still execute.
try:  # pragma: no cover - exercised only when pandas isn't installed
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None  # type: ignore

from binance_trade_bot.statistics.base import StatisticsBase
from binance_trade_bot.statistics.calculators import (
    DailyPerformanceCalculator,
    WeeklyPerformanceCalculator,
    TotalPerformanceCalculator,
    ProfitLossCalculator,
    WinLossCalculator,
    AdvancedMetricsCalculator,
)
from binance_trade_bot.statistics.manager import StatisticsManager
# Local fallbacks for model classes when SQLAlchemy models are unavailable.
try:  # pragma: no cover
    from binance_trade_bot.models.trade import Trade, TradeState  # type: ignore
    from binance_trade_bot.models.coin import Coin  # type: ignore
    from binance_trade_bot.models.coin_value import CoinValue  # type: ignore
except Exception:  # pragma: no cover
    class Trade:  # type: ignore
        pass

    class TradeState:  # type: ignore
        COMPLETE = "COMPLETE"

    class Coin:  # type: ignore
        pass

    class CoinValue:  # type: ignore
        pass

try:  # pragma: no cover
    from binance_trade_bot.database import Database  # type: ignore
except Exception:  # pragma: no cover
    class Database:  # type: ignore
        db_session = MagicMock()

try:  # pragma: no cover
    from binance_trade_bot.logger import Logger  # type: ignore
except Exception:  # pragma: no cover
    class Logger:  # type: ignore
        def info(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass


@unittest.skipUnless(pd, "pandas not installed")
class TestStatisticsBase(unittest.TestCase):
    """
    Test cases for StatisticsBase class.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {'test': 'value'}
        self.statistics_base = StatisticsBase(self.config)
    
    def test_initialization(self):
        """Test StatisticsBase initialization."""
        self.assertEqual(self.statistics_base.config, self.config)
    
    def test_filter_data_by_time_period(self):
        """Test filtering data by time period."""
        # Create test data
        dates = [
            datetime(2023, 1, 1, 10, 0, 0),
            datetime(2023, 1, 2, 10, 0, 0),
            datetime(2023, 1, 3, 10, 0, 0),
        ]
        data = pd.DataFrame({
            'datetime': dates,
            'value': [1, 2, 3]
        })
        
        # Test filtering
        start_date = datetime(2023, 1, 2)
        end_date = datetime(2023, 1, 3)
        filtered_data = self.statistics_base.filter_data_by_time_period(data, start_date, end_date)
        
        # Verify results
        self.assertEqual(len(filtered_data), 2)
        self.assertEqual(filtered_data['datetime'].iloc[0], datetime(2023, 1, 2, 10, 0, 0))
        self.assertEqual(filtered_data['datetime'].iloc[1], datetime(2023, 1, 3, 10, 0, 0))
    
    def test_calculate_basic_metrics_empty_data(self):
        """Test calculating basic metrics with empty data."""
        data = pd.DataFrame()
        metrics = self.statistics_base.calculate_basic_metrics(data)
        
        expected_metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'total_volume': 0.0,
            'average_trade_size': 0.0,
        }
        
        self.assertEqual(metrics, expected_metrics)
    
    def test_calculate_basic_metrics_with_data(self):
        """Test calculating basic metrics with data."""
        data = pd.DataFrame({
            'profit_loss': [10, -5, 15, -10, 20],
            'crypto_trade_amount': [100, 200, 150, 300, 250]
        })
        
        metrics = self.statistics_base.calculate_basic_metrics(data)
        
        expected_metrics = {
            'total_trades': 5,
            'winning_trades': 3,
            'losing_trades': 2,
            'win_rate': 0.6,
            'total_volume': 1000.0,
            'average_trade_size': 200.0,
        }
        
        self.assertEqual(metrics, expected_metrics)
    
    def test_format_statistics(self):
        """Test formatting statistics."""
        stats = {
            'float_value': 3.14159,
            'int_value': 42,
            'nested': {
                'nested_float': 2.71828,
                'nested_int': 10
            }
        }
        
        formatted = self.statistics_base.format_statistics(stats)
        
        self.assertEqual(formatted['float_value'], 3.14159)
        self.assertEqual(formatted['int_value'], 42)
        self.assertEqual(formatted['nested']['nested_float'], 2.71828)
        self.assertEqual(formatted['nested']['nested_int'], 10)


@unittest.skipUnless(pd, "pandas not installed")
class TestDailyPerformanceCalculator(unittest.TestCase):
    """
    Test cases for DailyPerformanceCalculator class.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {'test': 'value'}
        self.database = Mock(spec=Database)
        self.calculator = DailyPerformanceCalculator(self.config, self.database)
    
    def test_initialization(self):
        """Test DailyPerformanceCalculator initialization."""
        self.assertEqual(self.calculator.config, self.config)
        self.assertEqual(self.calculator.database, self.database)
    
    def test_validate_data_valid(self):
        """Test data validation with valid data."""
        data = pd.DataFrame({
            'datetime': [datetime.now()],
            'profit_loss': [10.0]
        })
        
        self.assertTrue(self.calculator.validate_data(data))
    
    def test_validate_data_invalid(self):
        """Test data validation with invalid data."""
        data = pd.DataFrame()
        self.assertFalse(self.calculator.validate_data(data))
    
    def test_get_time_period(self):
        """Test getting time period."""
        self.assertEqual(self.calculator.get_time_period(), 'daily')
    
    def test_calculate_statistics_empty_data(self):
        """Test calculating statistics with empty data."""
        data = pd.DataFrame()
        date = datetime.now()
        
        stats = self.calculator.calculate_statistics(data, date)

        self.assertEqual(stats['date'], date.isoformat())
        self.assertEqual(stats['total_trades'], 0)
        self.assertEqual(stats['winning_trades'], 0)
        self.assertEqual(stats['losing_trades'], 0)
        self.assertEqual(stats['win_rate'], 0.0)
        self.assertEqual(stats['trade_frequency'], 0.0)
    
    def test_calculate_statistics_with_data(self):
        """Test calculating statistics with data."""
        data = pd.DataFrame({
            'datetime': [datetime.now()],
            'profit_loss': [10.0],
            'crypto_trade_amount': [100.0]
        })
        
        date = datetime.now()
        stats = self.calculator.calculate_statistics(data, date)

        self.assertEqual(stats['date'], date.isoformat())
        self.assertEqual(stats['total_trades'], 1)
        self.assertEqual(stats['winning_trades'], 1)
        self.assertEqual(stats['losing_trades'], 0)
        self.assertEqual(stats['win_rate'], 1.0)
        self.assertEqual(stats['total_profit_loss'], 10.0)
        self.assertEqual(stats['average_profit_loss'], 10.0)
        self.assertAlmostEqual(stats['roi'], 10.0)
        self.assertEqual(stats['sharpe_ratio'], 0.0)
        self.assertEqual(stats['max_drawdown'], 0.0)

    def test_calculate_trade_frequency(self):
        """Test trade frequency metric calculation."""
        data = pd.DataFrame({
            'datetime': [datetime.now()] * 48,
            'profit_loss': [0.0] * 48,
            'crypto_trade_amount': [1.0] * 48,
        })

        date = datetime.now()
        stats = self.calculator.calculate_statistics(data, date)

        self.assertEqual(stats['trade_frequency'], 2.0)  # 48 trades / 24 hours


@unittest.skipUnless(pd, "pandas not installed")
class TestWeeklyPerformanceCalculator(unittest.TestCase):
    """
    Test cases for WeeklyPerformanceCalculator class.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {'test': 'value'}
        self.database = Mock(spec=Database)
        self.calculator = WeeklyPerformanceCalculator(self.config, self.database)
    
    def test_initialization(self):
        """Test WeeklyPerformanceCalculator initialization."""
        self.assertEqual(self.calculator.config, self.config)
        self.assertEqual(self.calculator.database, self.database)
    
    def test_validate_data_valid(self):
        """Test data validation with valid data."""
        data = pd.DataFrame({
            'datetime': [datetime.now()],
            'profit_loss': [10.0]
        })
        
        self.assertTrue(self.calculator.validate_data(data))
    
    def test_validate_data_invalid(self):
        """Test data validation with invalid data."""
        data = pd.DataFrame()
        self.assertFalse(self.calculator.validate_data(data))
    
    def test_get_time_period(self):
        """Test getting time period."""
        self.assertEqual(self.calculator.get_time_period(), 'weekly')
    
    def test_calculate_statistics_empty_data(self):
        """Test calculating statistics with empty data."""
        data = pd.DataFrame()
        week_start = datetime.now()
        week_end = week_start + timedelta(days=6)
        
        stats = self.calculator.calculate_statistics(data, week_start, week_end)

        self.assertEqual(stats['week_start'], week_start.isoformat())
        self.assertEqual(stats['week_end'], week_end.isoformat())
        self.assertEqual(stats['total_trades'], 0)
        self.assertEqual(stats['winning_trades'], 0)
        self.assertEqual(stats['losing_trades'], 0)
        self.assertEqual(stats['win_rate'], 0.0)
        self.assertEqual(stats['trade_frequency'], 0.0)

    def test_calculate_trade_frequency(self):
        """Test weekly trade frequency metric."""
        data = pd.DataFrame({
            'datetime': [datetime.now()] * 14,
            'profit_loss': [0.0] * 14,
            'crypto_trade_amount': [1.0] * 14,
        })

        week_end = datetime.now()
        week_start = week_end - timedelta(days=7)

        stats = self.calculator.calculate_statistics(data, week_start, week_end)

        expected_frequency = 14 / (24 * 7)
        self.assertAlmostEqual(stats['trade_frequency'], expected_frequency)

    def test_calculate_statistics_with_data(self):
        """Test calculating weekly statistics with data."""
        data = pd.DataFrame({
            'datetime': [datetime.now()],
            'profit_loss': [10.0],
            'crypto_trade_amount': [100.0]
        })

        week_end = datetime.now()
        week_start = week_end - timedelta(days=7)
        stats = self.calculator.calculate_statistics(data, week_start, week_end)

        self.assertEqual(stats['total_trades'], 1)
        self.assertAlmostEqual(stats['roi'], 10.0)
        self.assertIn('sharpe_ratio', stats)
        self.assertIn('max_drawdown', stats)


@unittest.skipUnless(pd, "pandas not installed")
class TestTotalPerformanceCalculator(unittest.TestCase):
    """
    Test cases for TotalPerformanceCalculator class.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {'test': 'value'}
        self.database = Mock(spec=Database)
        self.calculator = TotalPerformanceCalculator(self.config, self.database)
    
    def test_initialization(self):
        """Test TotalPerformanceCalculator initialization."""
        self.assertEqual(self.calculator.config, self.config)
        self.assertEqual(self.calculator.database, self.database)
    
    def test_validate_data_valid(self):
        """Test data validation with valid data."""
        data = pd.DataFrame({
            'datetime': [datetime.now()],
            'profit_loss': [10.0]
        })
        
        self.assertTrue(self.calculator.validate_data(data))
    
    def test_validate_data_invalid(self):
        """Test data validation with invalid data."""
        data = pd.DataFrame()
        self.assertFalse(self.calculator.validate_data(data))
    
    def test_get_time_period(self):
        """Test getting time period."""
        self.assertEqual(self.calculator.get_time_period(), 'total')

    def test_calculate_trade_frequency(self):
        """Test total trade frequency metric."""
        start_date = datetime(2023, 1, 1)
        end_date = start_date + timedelta(hours=10)
        data = pd.DataFrame({
            'datetime': [start_date + timedelta(hours=i) for i in range(10)],
            'profit_loss': [0.0] * 10,
            'crypto_trade_amount': [1.0] * 10,
        })

        stats = self.calculator.calculate_statistics(data, start_date, end_date)

        self.assertEqual(stats['trade_frequency'], 1.0)  # 10 trades / 10 hours

    def test_calculate_statistics_with_data(self):
        """Test calculating total statistics with data."""
        start_date = datetime(2023, 1, 1)
        end_date = start_date + timedelta(days=1)
        data = pd.DataFrame({
            'datetime': [start_date, start_date + timedelta(hours=1)],
            'profit_loss': [10.0, 5.0],
            'crypto_trade_amount': [100.0, 100.0],
        })

        stats = self.calculator.calculate_statistics(data, start_date, end_date)

        self.assertEqual(stats['total_trades'], 2)
        self.assertAlmostEqual(stats['roi'], 15.0)
        self.assertIn('sharpe_ratio', stats)
        self.assertIn('max_drawdown', stats)
    
    def test_calculate_additional_metrics(self):
        """Test calculating additional metrics."""
        data = pd.DataFrame({
            'datetime': [
                datetime(2023, 1, 1, 10, 0, 0),
                datetime(2023, 1, 2, 10, 0, 0),
                datetime(2023, 1, 3, 10, 0, 0),
            ],
            'profit_loss': [10.0, -5.0, 15.0]
        })
        
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 3)
        
        metrics = self.calculator.calculate_additional_metrics(data, start_date, end_date)
        
        self.assertEqual(metrics['trading_days'], 3)
        self.assertEqual(metrics['best_day'], 15.0)
        self.assertEqual(metrics['worst_day'], -5.0)


class TestProfitLossCalculator(unittest.TestCase):
    """
    Test cases for ProfitLossCalculator class.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        self.calculator = ProfitLossCalculator()
    
    def test_calculate_portfolio_profit_loss_empty_data(self):
        """Test calculating portfolio profit/loss with empty data."""
        portfolio_data = []
        
        stats = self.calculator.calculate_portfolio_profit_loss(portfolio_data)
        
        expected_stats = {
            'total_profit_loss': 0.0,
            'total_profit_loss_percentage': 0.0,
            'total_investment': 0.0,
            'current_value': 0.0,
        }
        
        self.assertEqual(stats, expected_stats)
    
    def test_calculate_portfolio_profit_loss_with_data(self):
        """Test calculating portfolio profit/loss with data."""
        portfolio_data = [
            {'initial_value': 1000.0, 'current_value': 1200.0},
            {'initial_value': 2000.0, 'current_value': 1800.0},
        ]
        
        stats = self.calculator.calculate_portfolio_profit_loss(portfolio_data)
        
        expected_stats = {
            'total_profit_loss': 0.0,  # (1200 + 1800) - (1000 + 2000) = 0
            'total_profit_loss_percentage': 0.0,
            'total_investment': 3000.0,
            'current_value': 3000.0,
        }
        
        self.assertEqual(stats, expected_stats)


class TestWinLossCalculator(unittest.TestCase):
    """
    Test cases for WinLossCalculator class.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        self.calculator = WinLossCalculator()
    
    def test_calculate_win_loss_metrics_empty_data(self):
        """Test calculating win/loss metrics with empty data."""
        trades = []
        
        stats = self.calculator.calculate_win_loss_metrics(trades)

        expected_stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
            'win_loss_ratio': 0.0,
            'average_holding_period': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
        }
        
        self.assertEqual(stats, expected_stats)
    
    def test_calculate_win_loss_metrics_with_data(self):
        """Test calculating win/loss metrics with data."""
        # Create mock trades
        trade1 = Mock(spec=Trade)
        trade1.selling = False
        trade1.alt_trade_amount = 100.0
        trade1.crypto_trade_amount = 110.0
        trade1.datetime = datetime.now()
        
        trade2 = Mock(spec=Trade)
        trade2.selling = True
        trade2.alt_trade_amount = 90.0
        trade2.crypto_trade_amount = 100.0
        trade2.datetime = datetime.now()
        
        trades = [trade1, trade2]
        
        stats = self.calculator.calculate_win_loss_metrics(trades)

        self.assertEqual(stats['total_trades'], 2)
        self.assertEqual(stats['winning_trades'], 1)
        self.assertEqual(stats['losing_trades'], 1)
        self.assertEqual(stats['win_rate'], 0.5)
        self.assertEqual(stats['win_loss_ratio'], 1.0)
        self.assertEqual(stats['largest_win'], 10.0)
        self.assertEqual(stats['largest_loss'], -10.0)


class TestAdvancedMetricsCalculator(unittest.TestCase):
    """
    Test cases for AdvancedMetricsCalculator class.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        self.calculator = AdvancedMetricsCalculator()
    
    def test_calculate_all_advanced_metrics_empty_data(self):
        """Test calculating all advanced metrics with empty data."""
        returns = []
        total_volume = 0.0
        
        stats = self.calculator.calculate_all_advanced_metrics(returns, total_volume)
        
        expected_stats = {
            'roi': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'volatility': 0.0,
            'profit_factor': 0.0,
            'recovery_factor': 0.0,
            'calmar_ratio': 0.0,
        }
        
        self.assertEqual(stats, expected_stats)
    
    def test_calculate_all_advanced_metrics_with_data(self):
        """Test calculating all advanced metrics with data."""
        returns = [0.01, -0.005, 0.02, -0.01, 0.015]
        total_volume = 1000.0
        
        stats = self.calculator.calculate_all_advanced_metrics(returns, total_volume)
        
        # Verify that all metrics are calculated (exact values may vary)
        self.assertIn('roi', stats)
        self.assertIn('sharpe_ratio', stats)
        self.assertIn('max_drawdown', stats)
        self.assertIn('volatility', stats)
        self.assertIn('profit_factor', stats)
        self.assertIn('recovery_factor', stats)
        self.assertIn('calmar_ratio', stats)
        
        # Verify ROI calculation
        expected_roi = sum(returns) * 100
        self.assertAlmostEqual(stats['roi'], expected_roi, places=2)
    
    def test_calculate_sharpe_ratio(self):
        """Test calculating Sharpe ratio."""
        returns = [0.01, -0.005, 0.02, -0.01, 0.015]

        sharpe_ratio = self.calculator._calculate_sharpe_ratio(returns)

        self.assertIsInstance(sharpe_ratio, float)
        self.assertFalse(math.isnan(sharpe_ratio))
    
    def test_calculate_max_drawdown(self):
        """Test calculating maximum drawdown."""
        returns = [0.01, -0.02, 0.03, -0.01, 0.015]

        max_drawdown = self.calculator._calculate_max_drawdown(returns)
        
        self.assertIsInstance(max_drawdown, float)
        self.assertGreaterEqual(max_drawdown, 0.0)
    
    def test_calculate_profit_factor(self):
        """Test calculating profit factor."""
        returns = [0.01, -0.005, 0.02, -0.01, 0.015]

        profit_factor = self.calculator._calculate_profit_factor(returns)
        
        self.assertIsInstance(profit_factor, float)
        self.assertGreaterEqual(profit_factor, 0.0)


@unittest.skip("StatisticsManager requires full environment")
class TestStatisticsManager(unittest.TestCase):
    """
    Test cases for StatisticsManager class.
    """
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {'test': 'value'}
        self.database = Mock(spec=Database)
        self.logger = Mock(spec=Logger)
        self.manager = StatisticsManager(self.config, self.database, self.logger)
        # Avoid heavy dependencies in tests by mocking methods that rely on
        # pandas DataFrames or database models.
        self.manager._trades_to_dataframe = Mock(return_value=[])  # type: ignore
        self.manager._save_daily_statistics = Mock()  # type: ignore
        self.manager._save_weekly_statistics = Mock()  # type: ignore
        self.manager._save_total_statistics = Mock()  # type: ignore
    
    def test_initialization(self):
        """Test StatisticsManager initialization."""
        self.assertEqual(self.manager.config, self.config)
        self.assertEqual(self.manager.database, self.database)
        self.assertEqual(self.manager.logger, self.logger)
        
        # Verify calculators are initialized
        self.assertIsInstance(self.manager.daily_calculator, DailyPerformanceCalculator)
        self.assertIsInstance(self.manager.weekly_calculator, WeeklyPerformanceCalculator)
        self.assertIsInstance(self.manager.total_calculator, TotalPerformanceCalculator)
        self.assertIsInstance(self.manager.profit_loss_calculator, ProfitLossCalculator)
        self.assertIsInstance(self.manager.win_loss_calculator, WinLossCalculator)
        self.assertIsInstance(self.manager.advanced_metrics_calculator, AdvancedMetricsCalculator)
    
    def test_get_daily_statistics(self):
        """Test getting daily statistics."""
        # Mock database session
        mock_session = Mock()
        mock_trades = []
        mock_session.query.return_value.filter.return_value.all.return_value = mock_trades
        
        # Mock calculator
        self.manager.daily_calculator.calculate_statistics.return_value = {
            'date': datetime.now().isoformat(),
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
        }
        
        # Mock database context manager
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test
        date = datetime.now().date()
        stats = self.manager.get_daily_statistics(date)
        
        # Verify
        self.assertIn('date', stats)
        self.assertIn('total_trades', stats)
        self.assertIn('winning_trades', stats)
        self.assertIn('losing_trades', stats)
        self.assertIn('win_rate', stats)
    
    def test_get_weekly_statistics(self):
        """Test getting weekly statistics."""
        # Mock database session
        mock_session = Mock()
        mock_trades = []
        mock_session.query.return_value.filter.return_value.all.return_value = mock_trades
        
        # Mock calculator
        self.manager.weekly_calculator.calculate_statistics.return_value = {
            'week_start': datetime.now().isoformat(),
            'week_end': (datetime.now() + timedelta(days=6)).isoformat(),
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
        }
        
        # Mock database context manager
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test
        week_start = datetime.now()
        stats = self.manager.get_weekly_statistics(week_start)
        
        # Verify
        self.assertIn('week_start', stats)
        self.assertIn('week_end', stats)
        self.assertIn('total_trades', stats)
        self.assertIn('winning_trades', stats)
        self.assertIn('losing_trades', stats)
        self.assertIn('win_rate', stats)
    
    def test_get_total_statistics(self):
        """Test getting total statistics."""
        # Mock database session
        mock_session = Mock()
        mock_trades = []
        mock_session.query.return_value.filter.return_value.all.return_value = mock_trades
        
        # Mock calculator
        self.manager.total_calculator.calculate_statistics.return_value = {
            'start_date': datetime.now().isoformat(),
            'end_date': datetime.now().isoformat(),
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
        }
        
        # Mock database context manager
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()
        stats = self.manager.get_total_statistics(start_date, end_date)
        
        # Verify
        self.assertIn('start_date', stats)
        self.assertIn('end_date', stats)
        self.assertIn('total_trades', stats)
        self.assertIn('winning_trades', stats)
        self.assertIn('losing_trades', stats)
        self.assertIn('win_rate', stats)
    
    def test_get_portfolio_statistics(self):
        """Test getting portfolio statistics."""
        # Mock database session
        mock_session = Mock()
        mock_coins = []
        mock_session.query.return_value.all.return_value = mock_coins
        
        # Mock calculator
        self.manager.profit_loss_calculator.calculate_portfolio_profit_loss.return_value = {
            'total_profit_loss': 0.0,
            'total_profit_loss_percentage': 0.0,
            'total_investment': 0.0,
            'current_value': 0.0,
        }
        
        # Mock database context manager
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test
        stats = self.manager.get_portfolio_statistics()
        
        # Verify
        self.assertIn('portfolio_data', stats)
        self.assertIn('portfolio_statistics', stats)
        self.assertIn('timestamp', stats)
    
    def test_get_trade_statistics(self):
        """Test getting trade statistics."""
        # Mock database session
        mock_session = Mock()
        mock_trades = []
        mock_session.query.return_value.filter.return_value.all.return_value = mock_trades
        
        # Mock calculator
        self.manager.win_loss_calculator.calculate_win_loss_metrics.return_value = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0.0,
        }
        
        # Mock database context manager
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test
        stats = self.manager.get_trade_statistics()
        
        # Verify
        self.assertIn('trade_count', stats)
        self.assertIn('win_loss_statistics', stats)
        self.assertIn('timestamp', stats)
    
    def test_get_advanced_statistics(self):
        """Test getting advanced statistics."""
        # Mock basic statistics
        self.manager.get_daily_statistics.return_value = {
            'total_trades': 10,
            'total_profit_loss': 100.0,
            'total_volume': 1000.0,
        }
        
        # Mock advanced calculator
        self.manager.advanced_metrics_calculator.calculate_all_advanced_metrics.return_value = {
            'roi': 10.0,
            'sharpe_ratio': 1.5,
            'max_drawdown': 5.0,
        }
        
        # Test
        stats = self.manager.get_advanced_statistics('daily')
        
        # Verify
        self.assertIn('total_trades', stats)
        self.assertIn('total_profit_loss', stats)
        self.assertIn('roi', stats)
        self.assertIn('sharpe_ratio', stats)
        self.assertIn('max_drawdown', stats)
    
    def test_generate_statistics_report(self):
        """Test generating statistics report."""
        # Mock basic statistics
        self.manager.get_daily_statistics.return_value = {
            'total_trades': 10,
            'total_profit_loss': 100.0,
            'total_volume': 1000.0,
        }
        
        # Mock other statistics methods
        self.manager.get_trade_statistics.return_value = {
            'trade_count': 10,
            'win_loss_statistics': {
                'total_trades': 10,
                'winning_trades': 6,
                'losing_trades': 4,
                'win_rate': 0.6,
            },
        }
        
        self.manager.win_loss_calculator.calculate_win_loss_metrics.return_value = {
            'total_trades': 10,
            'winning_trades': 6,
            'losing_trades': 4,
            'win_rate': 0.6,
        }
        
        self.manager.get_advanced_statistics.return_value = {
            'roi': 10.0,
            'sharpe_ratio': 1.5,
            'max_drawdown': 5.0,
        }
        
        self.manager.get_portfolio_statistics.return_value = {
            'portfolio_data': [],
            'portfolio_statistics': {
                'total_profit_loss': 0.0,
                'total_profit_loss_percentage': 0.0,
                'total_investment': 0.0,
                'current_value': 0.0,
            },
            'timestamp': datetime.now().isoformat(),
        }
        
        # Test
        report = self.manager.generate_statistics_report('daily')
        
        # Verify
        self.assertIn('period', report)
        self.assertIn('generated_at', report)
        self.assertIn('basic_statistics', report)
        self.assertIn('profit_loss_statistics', report)
        self.assertIn('win_loss_statistics', report)
        self.assertIn('advanced_statistics', report)
        self.assertIn('portfolio_statistics', report)
    
    def test_get_portfolio_value_empty(self):
        """Test getting portfolio value with no coins."""
        # Mock database session
        mock_session = Mock()
        mock_coins = []
        mock_session.query.return_value.all.return_value = mock_coins
        
        # Mock database context manager
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test
        result = self.manager.get_portfolio_value()
        
        # Verify
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['total_portfolio_value'], 0.0)
        self.assertEqual(result['total_holdings_count'], 0)
        self.assertEqual(result['individual_holdings'], [])
    
    def test_get_portfolio_value_with_data(self):
        """Test getting portfolio value with coin data."""
        # Mock coin and coin value data
        mock_coin = Mock(spec=Coin)
        mock_coin.symbol = 'BTC'
        
        mock_coin_value = Mock(spec=CoinValue)
        mock_coin_value.balance = 1.5
        mock_coin_value.usd_price = 50000.0
        mock_coin_value.usd_value = 75000.0
        mock_coin_value.daily_change_percentage = 2.5
        mock_coin_value.risk_score = 0.1
        
        # Mock database session
        mock_session = Mock()
        mock_session.query.return_value.all.return_value = [mock_coin]
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_coin_value
        
        # Mock database context manager
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test
        result = self.manager.get_portfolio_value()
        
        # Verify
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['total_portfolio_value'], 75000.0)
        self.assertEqual(result['total_holdings_count'], 1)
        self.assertEqual(len(result['individual_holdings']), 1)
        self.assertEqual(result['individual_holdings'][0]['symbol'], 'BTC')
        self.assertEqual(result['individual_holdings'][0]['usd_value'], 75000.0)
    
    def test_get_portfolio_value_with_invalid_symbols(self):
        """Test getting portfolio value with invalid coin symbols."""
        # Test with invalid coin_symbols parameter
        result = self.manager.get_portfolio_value("invalid")
        self.assertEqual(result['status'], 'error')
        self.assertIn('message', result)
    
    def test_get_portfolio_composition_empty(self):
        """Test getting portfolio composition with no coins."""
        # Mock get_portfolio_value to return empty data
        self.manager.get_portfolio_value = Mock(return_value={
            'status': 'success',
            'total_portfolio_value': 0.0,
            'total_holdings_count': 0,
            'individual_holdings': []
        })
        
        # Test
        result = self.manager.get_portfolio_composition()
        
        # Verify
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['total_portfolio_value'], 0.0)
        self.assertEqual(result['total_holdings_count'], 0)
        self.assertEqual(result['individual_holdings'], [])
        self.assertIn('composition_analysis', result)
    
    def test_get_portfolio_composition_with_data(self):
        """Test getting portfolio composition with coin data."""
        # Mock get_portfolio_value to return data
        mock_holdings = [
            {
                'symbol': 'BTC',
                'usd_value': 50000.0,
                'percentage_of_portfolio': 66.67,
                'balance': 1.0,
                'usd_price': 50000.0,
                'daily_change_percentage': 2.5,
                'risk_score': 0.1
            },
            {
                'symbol': 'ETH',
                'usd_value': 25000.0,
                'percentage_of_portfolio': 33.33,
                'balance': 10.0,
                'usd_price': 2500.0,
                'daily_change_percentage': -1.2,
                'risk_score': 0.2
            }
        ]
        
        self.manager.get_portfolio_value = Mock(return_value={
            'status': 'success',
            'total_portfolio_value': 75000.0,
            'total_holdings_count': 2,
            'individual_holdings': mock_holdings
        })
        
        # Test
        result = self.manager.get_portfolio_composition()
        
        # Verify
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['total_portfolio_value'], 75000.0)
        self.assertEqual(result['total_holdings_count'], 2)
        
        # Check composition analysis
        composition = result['composition_analysis']
        self.assertIn('by_value', composition)
        self.assertIn('by_percentage', composition)
        self.assertIn('concentration_metrics', composition)
        self.assertIn('diversification_score', composition)
        
        # Check concentration metrics
        self.assertEqual(composition['concentration_metrics']['top_holding_percentage'], 66.67)
        self.assertEqual(composition['concentration_metrics']['top_3_holdings_percentage'], 100.0)
        self.assertEqual(composition['concentration_metrics']['herfindahl_index'], 0.4445)
    
    def test_get_portfolio_performance_benchmarks_empty(self):
        """Test getting portfolio benchmarks with no benchmark data."""
        # Mock database session
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        
        # Mock database context manager
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test
        result = self.manager.get_portfolio_performance_benchmarks()
        
        # Verify
        self.assertEqual(result['status'], 'error')
        self.assertIn('message', result)
    
    def test_get_portfolio_performance_benchmarks_with_data(self):
        """Test getting portfolio benchmarks with data."""
        # Mock coin value data
        mock_benchmark_data = []
        for i in range(5):
            mock_data = Mock(spec=CoinValue)
            mock_data.usd_price = 50000.0 + i * 1000  # Increasing price
            mock_data.datetime = datetime.now() - timedelta(days=i)
            mock_benchmark_data.append(mock_data)
        
        # Mock database session
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_benchmark_data
        
        # Mock portfolio statistics
        self.manager.get_portfolio_statistics = Mock(return_value={
            'portfolio_data': [],
            'portfolio_statistics': {},
            'timestamp': datetime.now().isoformat(),
        })
        
        # Mock database context manager
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Test
        result = self.manager.get_portfolio_performance_benchmarks()
        
        # Verify
        self.assertEqual(result['status'], 'success')
        self.assertIn('portfolio_statistics', result)
        self.assertIn('benchmark_statistics', result)
        self.assertIn('comparison', result)
        
        # Check benchmark statistics
        benchmark_stats = result['benchmark_statistics']
        self.assertIn('symbol', benchmark_stats)
        self.assertIn('total_return_percentage', benchmark_stats)
        self.assertIn('volatility_percentage', benchmark_stats)
    
    def test_get_portfolio_performance_benchmarks_invalid_symbol(self):
        """Test getting portfolio benchmarks with invalid benchmark symbol."""
        # Test with invalid benchmark_symbol
        result = self.manager.get_portfolio_performance_benchmarks("")
        self.assertEqual(result['status'], 'error')
        self.assertIn('message', result)
    
    def test_calculate_benchmark_performance_empty(self):
        """Test calculating benchmark performance with empty data."""
        result = self.manager._calculate_benchmark_performance([])
        self.assertEqual(result, {})
    
    def test_calculate_benchmark_performance_with_data(self):
        """Test calculating benchmark performance with data."""
        # Mock coin value data
        mock_data = []
        for i in range(3):
            mock_point = Mock(spec=CoinValue)
            mock_point.coin_id = 'BTC'
            mock_point.usd_price = 50000.0 + i * 5000  # Increasing price
            mock_point.datetime = datetime.now() - timedelta(days=i)
            mock_data.append(mock_point)
        
        # Test
        result = self.manager._calculate_benchmark_performance(mock_data)
        
        # Verify
        self.assertIn('symbol', result)
        self.assertIn('current_price', result)
        self.assertIn('total_return_percentage', result)
        self.assertIn('volatility_percentage', result)
        self.assertIn('max_drawdown_percentage', result)
        
        # Check calculations
        self.assertEqual(result['symbol'], 'BTC')
        self.assertEqual(result['current_price'], 65000.0)  # Last price
        self.assertEqual(result['period_start_price'], 50000.0)  # First price
        self.assertEqual(result['total_return_percentage'], 30.0)  # 30% increase
    
    def test_compare_performance_empty(self):
        """Test comparing performance with empty data."""
        portfolio_performance = {}
        benchmark_performance = {}
        
        result = self.manager._compare_performance(portfolio_performance, benchmark_performance)
        
        # Verify
        self.assertIn('outperformance', result)
        self.assertIn('relative_strength', result)
        self.assertIn('risk_adjusted_performance', result)
        self.assertIn('performance_summary', result)
        
        # Should be zero when no data
        self.assertEqual(result['outperformance'], 0.0)
        self.assertEqual(result['relative_strength'], 1.0)
        self.assertEqual(result['risk_adjusted_performance'], 0.0)
    
    def test_compare_performance_with_data(self):
        """Test comparing performance with data."""
        portfolio_performance = {
            'total_return_percentage': 15.0,
            'volatility_percentage': 10.0
        }
        benchmark_performance = {
            'total_return_percentage': 10.0,
            'volatility_percentage': 8.0
        }
        
        result = self.manager._compare_performance(portfolio_performance, benchmark_performance)
        
        # Verify
        self.assertEqual(result['outperformance'], 5.0)  # 15% - 10%
        self.assertEqual(result['relative_strength'], 1.5)  # 15% / 10%
        self.assertEqual(result['performance_summary'], 'Portfolio outperformed benchmark by 5.00%')
    
    def test_compare_performance_negative_returns(self):
        """Test comparing performance with negative returns."""
        portfolio_performance = {
            'total_return_percentage': -5.0,
            'volatility_percentage': 15.0
        }
        benchmark_performance = {
            'total_return_percentage': -10.0,
            'volatility_percentage': 12.0
        }
        
        result = self.manager._compare_performance(portfolio_performance, benchmark_performance)
        
        # Verify
        self.assertEqual(result['outperformance'], 5.0)  # -5% - (-10%)
        self.assertEqual(result['relative_strength'], 0.5)  # -5% / -10%
        self.assertEqual(result['performance_summary'], 'Portfolio outperformed benchmark by 5.00%')


if __name__ == '__main__':
    unittest.main()