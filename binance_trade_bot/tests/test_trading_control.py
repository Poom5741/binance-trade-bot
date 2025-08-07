"""
Unit tests for trading control commands module.
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
import asyncio

# Import telegram library directly, not from local module
import telegram as telegram_lib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

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
        
        # Mock user
        self.mock_user = Mock()
        self.mock_user.id = '123456789'
        self.mock_user.first_name = 'Test'
        self.mock_user.username = 'testuser'
        
        # Mock update
        self.mock_update = Mock(spec=Update)
        self.mock_update.effective_user = self.mock_user
        self.mock_update.message.reply_text = AsyncMock()
        self.mock_update.callback_query.answer = AsyncMock()
        self.mock_update.callback_query.edit_message_text = AsyncMock()
        
        # Mock context
        self.mock_context = Mock(spec=CallbackContext)
        self.mock_context.args = []

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

    async def test_send_message_success(self):
        """Test successful message sending."""
        chat_id = '123456789'
        text = 'Test message'
        
        # Mock bot
        self.trading_control.bot = Mock()
        self.trading_control.bot.send_message = AsyncMock()
        
        result = await self.trading_control.send_message(chat_id, text)
        
        self.assertTrue(result)
        self.trading_control.bot.send_message.assert_called_once_with(
            chat_id=chat_id,
            text=text,
            parse_mode=None,
            disable_web_page_preview=True
        )

    async def test_send_message_no_bot(self):
        """Test message sending without bot."""
        chat_id = '123456789'
        text = 'Test message'
        
        # No bot
        self.trading_control.bot = None
        
        result = await self.trading_control.send_message(chat_id, text)
        
        self.assertFalse(result)
        self.logger.error.assert_called_with("Bot not initialized")

    async def test_send_trade_notification_success(self):
        """Test successful trade notification."""
        trade_data = {
            'action': 'BUY',
            'pair': 'BTCUSDT',
            'price': 50000.0,
            'amount': 0.001,
            'timestamp': datetime.utcnow().timestamp(),
            'status': 'COMPLETED'
        }
        
        # Mock users
        mock_users = [
            Mock(spec=TelegramUsers),
            Mock(spec=TelegramUsers)
        ]
        mock_users[0].telegram_id = 'user1'
        mock_users[1].telegram_id = 'user2'
        
        self.mock_session.query.return_value.filter.return_value.all.return_value = mock_users
        
        # Mock successful message sending
        self.trading_control.send_message = AsyncMock(return_value=True)
        
        result = await self.trading_control.send_trade_notification(trade_data)
        
        self.assertTrue(result)
        self.assertEqual(self.trading_control.send_message.call_count, 2)

    async def test_send_alert_success(self):
        """Test successful alert sending."""
        alert_type = 'error'
        message = 'Test alert'
        details = {'key': 'value'}
        
        # Mock admin ID
        self.config['telegram_admin_id'] = 'admin123'
        
        # Mock admin users
        mock_admin_users = [Mock(spec=TelegramUsers)]
        mock_admin_users[0].telegram_id = 'admin1'
        
        self.mock_session.query.return_value.filter.return_value.all.return_value = mock_admin_users
        
        # Mock successful message sending
        self.trading_control.send_message = AsyncMock(return_value=True)
        
        result = await self.trading_control.send_alert(alert_type, message, details)
        
        self.assertTrue(result)
        self.assertEqual(self.trading_control.send_message.call_count, 2)  # To admin + admin users

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

    async def test_status_command_success(self):
        """Test successful status command."""
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock status generation
        self.trading_control._generate_status_message = AsyncMock(return_value='Status message')
        
        await self.trading_control._status_command(self.mock_update, self.mock_context)
        
        self.mock_update.message.reply_text.assert_called_once_with('Status message', parse_mode='Markdown')

    async def test_status_command_no_permission(self):
        """Test status command without permission."""
        # Mock user without permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = False
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        await self.trading_control._status_command(self.mock_update, self.mock_context)
        
        self.mock_update.message.reply_text.assert_called_once_with('❌ You don\'t have permission to view status.')

    async def test_stop_command_success(self):
        """Test successful stop command."""
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock successful stop
        self.trading_control.trading_enabled = True
        self.trading_control.send_message = AsyncMock(return_value=True)
        
        await self.trading_control._stop_command(self.mock_update, self.mock_context)
        
        self.assertFalse(self.trading_control.trading_enabled)
        self.mock_update.message.reply_text.assert_called_once()

    async def test_resume_command_success(self):
        """Test successful resume command."""
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock successful resume
        self.trading_control.trading_enabled = False
        self.trading_control.send_message = AsyncMock(return_value=True)
        
        await self.trading_control._resume_command(self.mock_update, self.mock_context)
        
        self.assertTrue(self.trading_control.trading_enabled)
        self.mock_update.message.reply_text.assert_called_once()

    async def test_shutdown_command_success(self):
        """Test successful shutdown command."""
        # Mock user with admin permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock shutdown confirmation
        self.trading_control._send_shutdown_confirmation = AsyncMock()
        
        await self.trading_control._shutdown_command(self.mock_update, self.mock_context)
        
        self.trading_control._send_shutdown_confirmation.assert_called_once()

    async def test_shutdown_command_no_permission(self):
        """Test shutdown command without permission."""
        # Mock user without permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = False
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        await self.trading_control._shutdown_command(self.mock_update, self.mock_context)
        
        self.mock_update.message.reply_text.assert_called_once_with('❌ You don\'t have permission to initiate shutdown.')

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


class TestTradingControlIntegration(unittest.TestCase):
    """Integration tests for TradingControlCommands."""

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


if __name__ == '__main__':
    unittest.main()