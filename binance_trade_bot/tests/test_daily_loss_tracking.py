"""
Unit tests for the DailyLossTracking model.
"""

import unittest
from datetime import datetime, date, time, timedelta

from binance_trade_bot.models import DailyLossTracking, DailyLossStatus


class TestDailyLossTracking(unittest.TestCase):
    """Test cases for DailyLossTracking model."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_date = datetime(2025, 8, 5, 10, 0, 0)
        self.starting_value = 10000.0
        self.max_loss_percentage = 5.0
    
    def test_init(self):
        """Test DailyLossTracking initialization."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value,
            max_daily_loss_percentage=self.max_loss_percentage
        )
        
        self.assertEqual(tracking.tracking_date, self.test_date)
        self.assertEqual(tracking.starting_portfolio_value, self.starting_value)
        self.assertEqual(tracking.current_portfolio_value, self.starting_value)
        self.assertEqual(tracking.daily_loss_amount, 0.0)
        self.assertEqual(tracking.daily_loss_percentage, 0.0)
        self.assertEqual(trading.max_daily_loss_percentage, self.max_loss_percentage)
        self.assertFalse(tracking.trading_halted)
        self.assertIsNone(tracking.halt_reason)
        self.assertEqual(tracking.status, DailyLossStatus.ACTIVE)
        self.assertEqual(tracking.total_trades_today, 0)
        self.assertEqual(tracking.winning_trades, 0)
        self.assertEqual(tracking.losing_trades, 0)
        self.assertEqual(tracking.largest_win_amount, 0.0)
        self.assertEqual(tracking.largest_loss_amount, 0.0)
    
    def test_is_loss_threshold_exceeded_false(self):
        """Test is_loss_threshold_exceeded when threshold not exceeded."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value,
            max_daily_loss_percentage=self.max_loss_percentage
        )
        
        # Set a small loss
        tracking.current_portfolio_value = 9900.0  # 1% loss
        tracking.daily_loss_percentage = 1.0
        
        self.assertFalse(tracking.is_loss_threshold_exceeded)
    
    def test_is_loss_threshold_exceeded_true(self):
        """Test is_loss_threshold_exceeded when threshold exceeded."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value,
            max_daily_loss_percentage=self.max_loss_percentage
        )
        
        # Set a loss that exceeds threshold
        tracking.current_portfolio_value = 9400.0  # 6% loss
        tracking.daily_loss_percentage = 6.0
        
        self.assertTrue(tracking.is_loss_threshold_exceeded)
    
    def test_portfolio_value_change(self):
        """Test portfolio_value_change calculation."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value
        )
        
        # Set a profit
        tracking.current_portfolio_value = 11000.0
        
        change = tracking.portfolio_value_change
        self.assertEqual(change, 1000.0)
    
    def test_win_rate_no_trades(self):
        """Test win_rate calculation with no trades."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value
        )
        
        win_rate = tracking.win_rate
        self.assertEqual(win_rate, 0.0)
    
    def test_win_rate_with_trades(self):
        """Test win_rate calculation with trades."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value
        )
        
        tracking.total_trades_today = 10
        tracking.winning_trades = 7
        tracking.losing_trades = 3
        
        win_rate = tracking.win_rate
        self.assertEqual(win_rate, 70.0)
    
    def test_update_portfolio_value_no_halt(self):
        """Test update_portfolio_value without triggering halt."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value,
            max_daily_loss_percentage=self.max_loss_percentage
        )
        
        new_value = 9800.0  # 2% loss
        tracking.update_portfolio_value(new_value)
        
        self.assertEqual(tracking.current_portfolio_value, new_value)
        self.assertEqual(tracking.daily_loss_amount, 200.0)
        self.assertEqual(tracking.daily_loss_percentage, 2.0)
        self.assertFalse(tracking.trading_halted)
        self.assertIsNone(tracking.halt_reason)
        self.assertEqual(tracking.status, DailyLossStatus.ACTIVE)
    
    def test_update_portfolio_value_with_halt(self):
        """Test update_portfolio_value triggering trading halt."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value,
            max_daily_loss_percentage=self.max_loss_percentage
        )
        
        new_value = 9400.0  # 6% loss - exceeds 5% threshold
        tracking.update_portfolio_value(new_value)
        
        self.assertEqual(tracking.current_portfolio_value, new_value)
        self.assertEqual(tracking.daily_loss_amount, 600.0)
        self.assertEqual(tracking.daily_loss_percentage, 6.0)
        self.assertTrue(tracking.trading_halted)
        self.assertIsNotNone(tracking.halt_reason)
        self.assertEqual(tracking.status, DailyLossStatus.HALTED)
    
    def test_add_trade_result_win(self):
        """Test adding a winning trade result."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value
        )
        
        tracking.add_trade_result(is_win=True, amount=150.0)
        
        self.assertEqual(tracking.total_trades_today, 1)
        self.assertEqual(tracking.winning_trades, 1)
        self.assertEqual(tracking.losing_trades, 0)
        self.assertEqual(tracking.largest_win_amount, 150.0)
        self.assertEqual(tracking.largest_loss_amount, 0.0)
    
    def test_add_trade_result_loss(self):
        """Test adding a losing trade result."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value
        )
        
        tracking.add_trade_result(is_win=False, amount=100.0)
        
        self.assertEqual(tracking.total_trades_today, 1)
        self.assertEqual(tracking.winning_trades, 0)
        self.assertEqual(tracking.losing_trades, 1)
        self.assertEqual(tracking.largest_win_amount, 0.0)
        self.assertEqual(tracking.largest_loss_amount, 100.0)
    
    def test_add_trade_result_multiple_trades(self):
        """Test adding multiple trade results."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value
        )
        
        # Add several trades
        tracking.add_trade_result(is_win=True, amount=50.0)
        tracking.add_trade_result(is_win=False, amount=75.0)
        tracking.add_trade_result(is_win=True, amount=200.0)  # New largest win
        tracking.add_trade_result(is_win=False, amount=150.0)  # New largest loss
        
        self.assertEqual(tracking.total_trades_today, 4)
        self.assertEqual(tracking.winning_trades, 2)
        self.assertEqual(tracking.losing_trades, 2)
        self.assertEqual(tracking.largest_win_amount, 200.0)
        self.assertEqual(tracking.largest_loss_amount, 150.0)
    
    def test_reset_daily_tracking(self):
        """Test resetting daily tracking."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value
        )
        
        # Add some data
        tracking.current_portfolio_value = 9500.0
        tracking.daily_loss_amount = 500.0
        tracking.daily_loss_percentage = 5.0
        tracking.trading_halted = True
        tracking.halt_reason = "Test halt"
        tracking.total_trades_today = 5
        tracking.winning_trades = 3
        tracking.losing_trades = 2
        tracking.largest_win_amount = 100.0
        tracking.largest_loss_amount = 50.0
        
        # Reset
        tracking.reset_daily_tracking()
        
        self.assertEqual(tracking.status, DailyLossStatus.RESET)
        self.assertIsNotNone(tracking.reset_at)
        self.assertFalse(tracking.trading_halted)
        self.assertIsNone(tracking.halt_reason)
        self.assertEqual(tracking.total_trades_today, 0)
        self.assertEqual(tracking.winning_trades, 0)
        self.assertEqual(tracking.losing_trades, 0)
        self.assertEqual(tracking.largest_win_amount, 0.0)
        self.assertEqual(tracking.largest_loss_amount, 0.0)
    
    def test_reactivate_trading(self):
        """Test reactivating trading after halt."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value
        )
        
        # Set to halted state
        tracking.trading_halted = True
        tracking.halt_reason = "Test halt"
        tracking.status = DailyLossStatus.HALTED
        
        # Reactivate
        tracking.reactivate_trading()
        
        self.assertFalse(tracking.trading_halted)
        self.assertIsNone(tracking.halt_reason)
        self.assertEqual(tracking.status, DailyLossStatus.ACTIVE)
    
    def test_info(self):
        """Test info method returns correct data."""
        tracking = DailyLossTracking(
            tracking_date=self.test_date,
            starting_portfolio_value=self.starting_value,
            max_daily_loss_percentage=self.max_loss_percentage
        )
        
        # Add some data
        tracking.current_portfolio_value = 9500.0
        tracking.daily_loss_amount = 500.0
        tracking.daily_loss_percentage = 5.0
        tracking.total_trades_today = 3
        tracking.winning_trades = 2
        tracking.losing_trades = 1
        
        info = tracking.info()
        
        self.assertEqual(info["id"], tracking.id)
        self.assertEqual(info["tracking_date"], self.test_date.isoformat())
        self.assertEqual(info["starting_portfolio_value"], self.starting_value)
        self.assertEqual(info["current_portfolio_value"], 9500.0)
        self.assertEqual(info["daily_loss_amount"], 500.0)
        self.assertEqual(info["daily_loss_percentage"], 5.0)
        self.assertEqual(info["max_daily_loss_percentage"], self.max_loss_percentage)
        self.assertTrue(info["is_loss_threshold_exceeded"])
        self.assertFalse(info["trading_halted"])
        self.assertIsNone(info["halt_reason"])
        self.assertEqual(info["status"], DailyLossStatus.ACTIVE.value)
        self.assertEqual(info["total_trades_today"], 3)
        self.assertEqual(info["winning_trades"], 2)
        self.assertEqual(info["losing_trades"], 1)
        self.assertEqual(info["win_rate"], 66.66666666666667)
        self.assertEqual(info["largest_win_amount"], 0.0)
        self.assertEqual(info["largest_loss_amount"], 0.0)
        self.assertIsNotNone(info["created_at"])
        self.assertIsNotNone(info["updated_at"])
        self.assertIsNone(info["reset_at"])


if __name__ == '__main__':
    unittest.main()