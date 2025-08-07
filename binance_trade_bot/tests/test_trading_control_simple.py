"""
Simple unit tests for trading control commands module.
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
import asyncio

from binance_trade_bot.telegram.trading_control import TradingControlCommands
from binance_trade_bot.models.telegram_users import TelegramUsers, UserRole, UserStatus
from binance_trade_bot.risk_management.integrated_risk_manager import IntegratedRiskManager
from binance_trade_bot.risk_management.emergency_shutdown_manager import EmergencyShutdownManager
from binance_trade_bot.auto_trader import AutoTrader
from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger


class TestTradingControlCommands(unittest.TestCase):
    """Test cases for TradingControlCommands class."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'telegram_token': 'test_token',
            'telegram_admin_id': '123456789',
            'trading_enabled': True,
            'emergency_shutdown': {
                'enabled': True,
                'auto_shutdown_threshold': 0.1,
                'cooldown_period': 300
            }
        }
        
        self.database = Mock(spec=Database)
        self.logger = Mock(spec=Logger)
        self.risk_manager = Mock(spec=IntegratedRiskManager)
        self.auto_trader = Mock(spec=AutoTrader)
        
        # Mock database session
        self.mock_session = Mock()
        self.database.db_session.return_value.__enter__.return_value = self.mock_session
        
        # Create trading control instance
        self.trading_control = TradingControlCommands(
            config=self.config,
            database=self.database,
            logger=self.logger,
            risk_manager=self.risk_manager,
            auto_trader=self.auto_trader
        )

    def test_init(self):
        """Test initialization of TradingControlCommands."""
        self.assertEqual(self.trading_control.config, self.config)
        self.assertEqual(self.trading_control.database, self.database)
        self.assertEqual(self.trading_control.logger, self.logger)
        self.assertEqual(self.trading_control.risk_manager, self.risk_manager)
        self.assertEqual(self.trading_control.auto_trader, self.auto_trader)
        self.assertTrue(self.trading_control.trading_enabled)
        self.assertFalse(self.trading_control.shutdown_requested)
        self.assertIsNone(self.trading_control.shutdown_reason)

    def test_is_rate_limited(self):
        """Test rate limiting functionality."""
        user_id = '123456789'
        command = 'status'
        
        # Test not rate limited initially
        self.assertFalse(self.trading_control._is_rate_limited(user_id, command))
        
        # Test rate limit exceeded
        for i in range(15):  # Exceeds limit of 10
            self.trading_control._record_command_usage(user_id, command)
        
        self.assertTrue(self.trading_control._is_rate_limited(user_id, command))

    def test_record_command_usage(self):
        """Test command usage recording."""
        user_id = '123456789'
        command = 'status'
        
        # Record usage
        self.trading_control._record_command_usage(user_id, command)
        
        # Check recorded usage
        self.assertIn(user_id, self.trading_control.user_command_counts)
        self.assertIn(command, self.trading_control.user_command_counts[user_id])
        self.assertEqual(len(self.trading_control.user_command_counts[user_id][command]), 1)

    @patch('binance_trade_bot.telegram.trading_control.datetime')
    def test_is_rate_limited_time_window(self, mock_datetime):
        """Test rate limiting respects time window."""
        user_id = '123456789'
        command = 'status'
        
        # Mock current time
        now = datetime.utcnow()
        mock_datetime.utcnow.return_value = now
        
        # Record usage
        self.trading_control._record_command_usage(user_id, command)
        
        # Mock time going back 2 minutes
        minute_ago = now - timedelta(minutes=2)
        mock_datetime.utcnow.return_value = minute_ago
        
        # Should not be rate limited since usage is older than 1 minute
        self.assertFalse(self.trading_control._is_rate_limited(user_id, command))

    def test_format_trade_message(self):
        """Test trade message formatting."""
        trade_data = {
            'action': 'BUY',
            'pair': 'BTCUSDT',
            'price': 50000.0,
            'amount': 0.001,
            'timestamp': datetime.utcnow().timestamp(),
            'status': 'COMPLETED',
            'message': 'Test trade'
        }
        
        message = self.trading_control._format_trade_message(trade_data)
        
        self.assertIn('Trade Notification', message)
        self.assertIn('BUY', message)
        self.assertIn('BTCUSDT', message)
        self.assertIn('50000.0', message)
        self.assertIn('0.001', message)
        self.assertIn('COMPLETED', message)
        self.assertIn('Test trade', message)

    def test_get_menu_keyboard_trader(self):
        """Test menu keyboard for trader role."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.TRADER
        
        keyboard = self.trading_control._get_menu_keyboard(mock_user)
        
        self.assertIsInstance(keyboard, list)
        self.assertTrue(len(keyboard) > 0)
        
        # Check for trading control buttons
        button_texts = [button.text for row in keyboard for button in row]
        self.assertIn('🛑 Stop Trading', button_texts)
        self.assertIn('▶️ Resume Trading', button_texts)
        self.assertIn('🚨 Emergency Shutdown', button_texts)

    def test_get_menu_viewer(self):
        """Test menu keyboard for viewer role."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.VIEWER
        
        keyboard = self.trading_control._get_menu_keyboard(mock_user)
        
        self.assertIsInstance(keyboard, list)
        self.assertTrue(len(keyboard) > 0)
        
        # Check that trading control buttons are not present
        button_texts = [button.text for row in keyboard for button in row]
        self.assertNotIn('🛑 Stop Trading', button_texts)
        self.assertNotIn('▶️ Resume Trading', button_texts)
        self.assertNotIn('🚨 Emergency Shutdown', button_texts)

    def test_get_menu_admin(self):
        """Test menu keyboard for admin role."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.ADMIN
        
        keyboard = self.trading_control._get_menu_keyboard(mock_user)
        
        self.assertIsInstance(keyboard, list)
        self.assertTrue(len(keyboard) > 0)
        
        # Check for all trading control buttons
        button_texts = [button.text for row in keyboard for button in row]
        self.assertIn('🛑 Stop Trading', button_texts)
        self.assertIn('▶️ Resume Trading', button_texts)
        self.assertIn('🚨 Emergency Shutdown', button_texts)

    def test_trading_state_management(self):
        """Test trading state management."""
        # Initial state
        self.assertTrue(self.trading_control.trading_enabled)
        self.assertFalse(self.trading_control.shutdown_requested)
        
        # Stop trading
        self.trading_control.trading_enabled = False
        self.assertFalse(self.trading_control.trading_enabled)
        
        # Resume trading
        self.trading_control.trading_enabled = True
        self.assertTrue(self.trading_control.trading_enabled)

    def test_shutdown_request_flow(self):
        """Test shutdown request flow."""
        # Initial state
        self.assertFalse(self.trading_control.shutdown_requested)
        self.assertIsNone(self.trading_control.shutdown_reason)
        
        # Request shutdown
        self.trading_control.shutdown_requested = True
        self.trading_control.shutdown_reason = 'Test reason'
        
        # Verify state
        self.assertTrue(self.trading_control.shutdown_requested)
        self.assertEqual(self.trading_control.shutdown_reason, 'Test reason')

    def test_rate_limiting_integration(self):
        """Test rate limiting integration with multiple commands."""
        user_id = '123456789'
        
        # Test different commands
        commands = ['status', 'stop', 'resume', 'shutdown']
        
        for command in commands:
            # Should not be rate limited initially
            self.assertFalse(self.trading_control._is_rate_limited(user_id, command))
            
            # Record usage
            self.trading_control._record_command_usage(user_id, command)
            
            # Should still not be rate limited
            self.assertFalse(self.trading_control._is_rate_limited(user_id, command))

    def test_command_rate_limits_includes_trading_commands(self):
        """Test that trading control commands are included in rate limits."""
        expected_commands = ['stop', 'resume', 'shutdown']
        
        for command in expected_commands:
            self.assertIn(command, self.trading_control.COMMAND_RATE_LIMITS)

    def test_user_permission_checking(self):
        """Test user permission checking for different roles."""
        # Test viewer role
        viewer_user = Mock(spec=TelegramUsers)
        viewer_user.role = UserRole.VIEWER
        
        # Test trader role
        trader_user = Mock(spec=TelegramUsers)
        trader_user.role = UserRole.TRADER
        
        # Test admin role
        admin_user = Mock(spec=TelegramUsers)
        admin_user.role = UserRole.ADMIN
        
        # Mock permission checking
        viewer_user.has_permission.return_value = False
        trader_user.has_permission.return_value = True
        admin_user.has_permission.return_value = True
        
        # Test that different roles have different permissions
        self.assertFalse(viewer_user.has_permission(UserRole.TRADER))
        self.assertTrue(trader_user.has_permission(UserRole.TRADER))
        self.assertTrue(admin_user.has_permission(UserRole.ADMIN))


if __name__ == '__main__':
    unittest.main()