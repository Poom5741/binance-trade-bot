"""
Unit tests for the DailyLossManager class.
"""

import unittest
from datetime import datetime, date, time, timedelta
from unittest.mock import Mock, patch, MagicMock

from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger
from binance_trade_bot.models import DailyLossTracking, DailyLossStatus, CoinValue, Coin, Interval
from binance_trade_bot.risk_management.daily_loss_manager import DailyLossManager


class TestDailyLossManager(unittest.TestCase):
    """Test cases for DailyLossManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock(spec=Database)
        self.mock_logger = Mock(spec=Logger)
        self.mock_session = Mock()
        
        # Test configuration
        self.test_config = {
            'max_daily_loss_percentage': 5.0,
            'portfolio_update_interval': 300,
            'enable_daily_loss_protection': True
        }
        
        self.daily_loss_manager = DailyLossManager(
            self.mock_database,
            self.mock_logger,
            self.test_config
        )
    
    def test_init(self):
        """Test DailyLossManager initialization."""
        self.assertEqual(self.daily_loss_manager.max_daily_loss_percentage, 5.0)
        self.assertEqual(self.daily_loss_manager.portfolio_update_interval, 300)
        self.assertTrue(self.daily_loss_manager.enable_daily_loss_protection)
    
    def test_init_with_disabled_protection(self):
        """Test initialization with daily loss protection disabled."""
        config = {'enable_daily_loss_protection': False}
        manager = DailyLossManager(self.mock_database, self.mock_logger, config)
        self.assertFalse(manager.enable_daily_loss_protection)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_get_or_create_daily_tracking_new(self, mock_datetime):
        """Test creating a new daily tracking record."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock the portfolio value calculation
        self.daily_loss_manager._calculate_current_portfolio_value = Mock(return_value=10000.0)
        
        # Mock no existing record
        self.mock_session.query.return_value.filter.return_value.first.return_value = None
        
        result = self.daily_loss_manager.get_or_create_daily_tracking(self.mock_session, test_date)
        
        # Verify new record creation
        self.mock_session.add.assert_called_once()
        self.assertIsInstance(result, DailyLossTracking)
        self.assertEqual(result.starting_portfolio_value, 10000.0)
        self.assertEqual(result.max_daily_loss_percentage, 5.0)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_get_or_create_daily_tracking_existing(self, mock_datetime):
        """Test retrieving an existing daily tracking record."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock existing record
        existing_record = DailyLossTracking(test_date, 5000.0)
        self.mock_session.query.return_value.filter.return_value.first.return_value = existing_record
        
        result = self.daily_loss_manager.get_or_create_daily_tracking(self.mock_session, test_date)
        
        # Verify existing record is returned
        self.assertEqual(result, existing_record)
        self.mock_session.add.assert_not_called()
    
    def test_calculate_current_portfolio_value(self):
        """Test portfolio value calculation."""
        # Mock coin values
        mock_coin1 = Mock()
        mock_coin1.usd_value = 1000.0
        
        mock_coin2 = Mock()
        mock_coin2.usd_value = 2000.0
        
        mock_coin_values = [mock_coin1, mock_coin2]
        
        # Mock session query
        self.mock_session.query.return_value.filter.return_value.all.return_value = mock_coin_values
        
        result = self.daily_loss_manager._calculate_current_portfolio_value(self.mock_session)
        
        self.assertEqual(result, 3000.0)
    
    def test_calculate_current_portfolio_value_with_none_values(self):
        """Test portfolio value calculation with None values."""
        # Mock coin values with None USD values
        mock_coin1 = Mock()
        mock_coin1.usd_value = None
        
        mock_coin2 = Mock()
        mock_coin2.usd_value = 2000.0
        
        mock_coin_values = [mock_coin1, mock_coin2]
        
        # Mock session query
        self.mock_session.query.return_value.filter.return_value.all.return_value = mock_coin_values
        
        result = self.daily_loss_manager._calculate_current_portfolio_value(self.mock_session)
        
        self.assertEqual(result, 2000.0)
    
    def test_calculate_current_portfolio_value_error(self):
        """Test portfolio value calculation error handling."""
        # Mock session query to raise exception
        self.mock_session.query.side_effect = Exception("Database error")
        
        result = self.daily_loss_manager._calculate_current_portfolio_value(self.mock_session)
        
        self.assertEqual(result, 0.0)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_update_portfolio_value_success(self, mock_datetime):
        """Test successful portfolio value update."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock tracking record
        mock_tracking = Mock()
        mock_tracking.trading_halted = False
        mock_tracking.update_portfolio_value = Mock()
        mock_tracking.halt_reason = None
        
        # Mock no existing record, create new one
        self.mock_session.query.return_value.filter.return_value.first.return_value = None
        self.daily_loss_manager._calculate_current_portfolio_value = Mock(return_value=8000.0)
        
        # Mock successful update
        self.daily_loss_manager.get_or_create_daily_tracking = Mock(return_value=mock_tracking)
        self.daily_loss_manager._create_risk_event = Mock()
        
        result = self.daily_loss_manager.update_portfolio_value(self.mock_session)
        
        self.assertTrue(result)
        mock_tracking.update_portfolio_value.assert_called_once_with(8000.0)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_update_portfolio_value_halted(self, mock_datetime):
        """Test portfolio value update when trading is halted."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock tracking record with trading halted
        mock_tracking = Mock()
        mock_tracking.trading_halted = True
        mock_tracking.halt_reason = "Daily loss exceeded"
        
        # Mock existing record
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_tracking
        
        result = self.daily_loss_manager.update_portfolio_value(self.mock_session)
        
        self.assertFalse(result)
        self.daily_loss_manager._create_risk_event.assert_called_once_with(self.mock_session, mock_tracking)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_update_portfolio_value_disabled_protection(self, mock_datetime):
        """Test portfolio value update with protection disabled."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Create manager with disabled protection
        config = {'enable_daily_loss_protection': False}
        manager = DailyLossManager(self.mock_database, self.mock_logger, config)
        
        result = manager.update_portfolio_value(self.mock_session)
        
        self.assertTrue(result)
        # Verify no database operations were performed
        self.mock_session.query.assert_not_called()
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_check_daily_reset_needed(self, mock_datetime):
        """Test daily reset check when reset is needed."""
        # Mock current time
        now = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = now
        
        # Mock last update as previous day
        self.daily_loss_manager.last_portfolio_update = datetime(2025, 8, 4, 15, 0, 0)
        
        # Mock tracking record
        mock_tracking = Mock()
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_tracking
        
        result = self.daily_loss_manager.check_daily_reset(self.mock_session)
        
        self.assertTrue(result)
        mock_tracking.reset_daily_tracking.assert_called_once()
        self.assertEqual(self.daily_loss_manager.last_portfolio_update, now)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_check_daily_reset_not_needed(self, mock_datetime):
        """Test daily reset check when reset is not needed."""
        # Mock current time
        now = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = now
        
        # Mock last update as today
        self.daily_loss_manager.last_portfolio_update = datetime(2025, 8, 5, 9, 0, 0)
        
        result = self.daily_loss_manager.check_daily_reset(self.mock_session)
        
        self.assertFalse(result)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_add_trade_result(self, mock_datetime):
        """Test adding trade result to daily tracking."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock trade
        mock_trade = Mock()
        
        # Mock tracking record
        mock_tracking = Mock()
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_tracking
        
        # Mock portfolio value update
        self.daily_loss_manager.update_portfolio_value = Mock(return_value=True)
        
        self.daily_loss_manager.add_trade_result(
            self.mock_session,
            mock_trade,
            is_profit=True,
            profit_amount=100.0
        )
        
        mock_tracking.add_trade_result.assert_called_once_with(True, 100.0)
        self.daily_loss_manager.update_portfolio_value.assert_called_once_with(self.mock_session)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_add_trade_result_disabled_protection(self, mock_datetime):
        """Test adding trade result with protection disabled."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Create manager with disabled protection
        config = {'enable_daily_loss_protection': False}
        manager = DailyLossManager(self.mock_database, self.mock_logger, config)
        
        # Mock trade
        mock_trade = Mock()
        
        result = manager.add_trade_result(
            self.mock_session,
            mock_trade,
            is_profit=True,
            profit_amount=100.0
        )
        
        # Should return without doing anything
        self.assertIsNone(result)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_is_trading_allowed(self, mock_datetime):
        """Test trading permission check."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock tracking record with trading allowed
        mock_tracking = Mock()
        mock_tracking.trading_halted = False
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_tracking
        
        result = self.daily_loss_manager.is_trading_allowed(self.mock_session)
        
        self.assertTrue(result)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_is_trading_allowed_halted(self, mock_datetime):
        """Test trading permission check when trading is halted."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock tracking record with trading halted
        mock_tracking = Mock()
        mock_tracking.trading_halted = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_tracking
        
        result = self.daily_loss_manager.is_trading_allowed(self.mock_session)
        
        self.assertFalse(result)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_is_trading_allowed_disabled_protection(self, mock_datetime):
        """Test trading permission check with protection disabled."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Create manager with disabled protection
        config = {'enable_daily_loss_protection': False}
        manager = DailyLossManager(self.mock_database, self.mock_logger, config)
        
        result = manager.is_trading_allowed(self.mock_session)
        
        self.assertTrue(result)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_get_daily_loss_summary(self, mock_datetime):
        """Test getting daily loss summary."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock tracking record
        mock_tracking = Mock()
        mock_tracking.info.return_value = {
            "id": 1,
            "tracking_date": test_date.isoformat(),
            "daily_loss_percentage": 2.5
        }
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_tracking
        
        result = self.daily_loss_manager.get_daily_loss_summary(self.mock_session)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["daily_loss_percentage"], 2.5)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_get_daily_loss_summary_no_data(self, mock_datetime):
        """Test getting daily loss summary when no data exists."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock no tracking record
        self.mock_session.query.return_value.filter.return_value.first.return_value = None
        
        result = self.daily_loss_manager.get_daily_loss_summary(self.mock_session)
        
        self.assertEqual(result["status"], "no_data")
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_get_daily_loss_history(self, mock_datetime):
        """Test getting daily loss history."""
        # Mock current time
        now = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = now
        
        # Mock tracking records
        mock_tracking1 = Mock()
        mock_tracking1.info.return_value = {"id": 1, "tracking_date": now.isoformat()}
        
        mock_tracking2 = Mock()
        mock_tracking2.info.return_value = {"id": 2, "tracking_date": (now - timedelta(days=1)).isoformat()}
        
        self.mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            mock_tracking1, mock_tracking2
        ]
        
        result = self.daily_loss_manager.get_daily_loss_history(self.mock_session, days=7)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["total_days"], 2)
        self.assertEqual(len(result["data"]), 2)
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_force_daily_reset(self, mock_datetime):
        """Test forcing a daily reset."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock tracking record
        mock_tracking = Mock()
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_tracking
        
        result = self.daily_loss_manager.force_daily_reset(self.mock_session)
        
        self.assertTrue(result)
        mock_tracking.reset_daily_tracking.assert_called_once()
    
    @patch('binance_trade_bot.risk_management.daily_loss_manager.datetime')
    def test_force_daily_reset_no_tracking(self, mock_datetime):
        """Test forcing a daily reset when no tracking record exists."""
        test_date = datetime(2025, 8, 5, 10, 0, 0)
        mock_datetime.now.return_value = test_date
        
        # Mock no tracking record
        self.mock_session.query.return_value.filter.return_value.first.return_value = None
        
        result = self.daily_loss_manager.force_daily_reset(self.mock_session)
        
        self.assertFalse(result)
    
    def test_create_risk_event(self):
        """Test creating a risk event."""
        # Mock tracking record
        mock_tracking = Mock()
        mock_tracking.daily_loss_percentage = 6.0
        mock_tracking.max_daily_loss_percentage = 5.0
        mock_tracking.halt_reason = "Daily loss exceeded"
        
        # Mock pair
        mock_pair = Mock()
        mock_pair.from_coin = Coin("BTC", True)
        
        self.mock_session.query.return_value.first.return_value = mock_pair
        
        self.daily_loss_manager._create_risk_event(self.mock_session, mock_tracking)
        
        # Verify risk event creation
        self.mock_session.add.assert_called_once()
    
    def test_create_risk_event_no_pair(self):
        """Test creating a risk event when no pair exists."""
        # Mock tracking record
        mock_tracking = Mock()
        mock_tracking.daily_loss_percentage = 6.0
        mock_tracking.max_daily_loss_percentage = 5.0
        
        # Mock no pair
        self.mock_session.query.return_value.first.return_value = None
        
        self.daily_loss_manager._create_risk_event(self.mock_session, mock_tracking)
        
        # Verify risk event creation with default pair
        self.mock_session.add.assert_called()


if __name__ == '__main__':
    unittest.main()