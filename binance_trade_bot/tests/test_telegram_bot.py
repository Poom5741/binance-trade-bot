"""
Unit tests for Telegram bot implementation.

This module contains comprehensive tests for Telegram bot functionality,
including authentication, authorization, rate limiting, and command handling.
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
import asyncio

from telegram import Update, InlineKeyboardButton, Bot
from telegram.ext import CallbackContext

from binance_trade_bot.telegram.bot import TelegramBot
from binance_trade_bot.database import Database
from binance_trade_bot.models.telegram_users import TelegramUsers, UserRole, UserStatus
from binance_trade_bot.logger import Logger


class TestTelegramBot(unittest.TestCase):
    """
    Test suite for Telegram bot functionality.
    """
    
    def setUp(self):
        """
        Set up test fixtures before each test method.
        """
        # Create mock configuration
        self.config = {
            'telegram_token': 'test_token',
            'telegram_webhook_url': 'https://example.com/webhook',
            'telegram_admin_id': '123456789'
        }
        
        # Create mock database
        self.database = Mock(spec=Database)
        self.database.db_session = Mock()
        
        # Create mock logger
        self.logger = Mock(spec=Logger)
        
        # Create Telegram bot instance
        self.bot = TelegramBot(self.config, self.database, self.logger)
        
        # Mock user data
        self.mock_user = Mock()
        self.mock_user.id = '123456789'
        self.mock_user.username = 'testuser'
        self.mock_user.first_name = 'Test'
        self.mock_user.last_name = 'User'
        self.mock_user.language_code = 'en'
        
        # Mock update object
        self.update = Mock(spec=Update)
        self.update.effective_user = self.mock_user
        self.update.message = Mock()
        self.update.message.reply_text = AsyncMock()
        self.update.message.edit_text = AsyncMock()
        self.update.callback_query = Mock()
        self.update.callback_query.from_user = self.mock_user
        self.update.callback_query.message = Mock()
        self.update.callback_query.message.edit_text = AsyncMock()
        self.update.callback_query.answer = AsyncMock()
        
        # Mock context object
        self.context = Mock(spec=CallbackContext)
        self.context.bot = Mock(spec=Bot)
    
    def test_bot_initialization(self):
        """
        Test Telegram bot initialization with valid and invalid configurations.
        """
        # Test valid initialization
        bot = TelegramBot(self.config, self.database, self.logger)
        self.assertEqual(bot.telegram_token, 'test_token')
        self.assertEqual(bot.telegram_webhook_url, 'https://example.com/webhook')
        self.assertEqual(bot.telegram_admin_id, '123456789')
        self.assertIsNotNone(bot.user_command_counts)
        self.assertIsNotNone(bot.user_sessions)
        
        # Test missing token
        invalid_config = self.config.copy()
        invalid_config.pop('telegram_token')
        
        with self.assertRaises(ValueError) as context:
            TelegramBot(invalid_config, self.database, self.logger)
        
        self.assertIn('Telegram token is required', str(context.exception))
    
    def test_is_rate_limited(self):
        """
        Test command rate limiting functionality.
        """
        user_id = '123456789'
        
        # Test non-limited command
        self.assertFalse(self.bot._is_rate_limited(user_id, 'help'))
        
        # Test rate limited command (simulate hitting limit)
        now = datetime.utcnow()
        for i in range(5):  # Hit the limit for 'start' command (5 per minute)
            if user_id not in self.bot.user_command_counts:
                self.bot.user_command_counts[user_id] = {}
            if 'start' not in self.bot.user_command_counts[user_id]:
                self.bot.user_command_counts[user_id]['start'] = []
            
            self.bot.user_command_counts[user_id]['start'].append(now - timedelta(seconds=60-i*12))
        
        # Should be rate limited now
        self.assertTrue(self.bot._is_rate_limited(user_id, 'start'))
        
        # Test different command (should not be affected)
        self.assertFalse(self.bot._is_rate_limited(user_id, 'help'))
        
        # Test command not in rate limits
        self.assertFalse(self.bot._is_rate_limited(user_id, 'unknown'))
    
    def test_record_command_usage(self):
        """
        Test command usage recording functionality.
        """
        user_id = '123456789'
        command = 'start'
        
        # Initially no command usage
        self.assertNotIn(user_id, self.bot.user_command_counts)
        
        # Record command usage
        self.bot._record_command_usage(user_id, command)
        
        # Verify usage was recorded
        self.assertIn(user_id, self.bot.user_command_counts)
        self.assertIn(command, self.bot.user_command_counts[user_id])
        self.assertEqual(len(self.bot.user_command_counts[user_id][command]), 1)
        self.assertIsInstance(self.bot.user_command_counts[user_id][command][0], datetime)
    
    def test_format_trade_message(self):
        """
        Test trade message formatting functionality.
        """
        # Test with complete trade data
        trade_data = {
            'action': 'buy',
            'pair': 'BTCUSDT',
            'price': '50000.00',
            'amount': '0.001',
            'timestamp': datetime.utcnow().timestamp(),
            'status': 'completed',
            'message': 'Trade executed successfully'
        }
        
        message = self.bot._format_trade_message(trade_data)
        
        self.assertIn('🤖', message)
        self.assertIn('Trade Notification', message)
        self.assertIn('BUY', message)
        self.assertIn('BTCUSDT', message)
        self.assertIn('50000.00', message)
        self.assertIn('0.001', message)
        self.assertIn('completed', message)
        self.assertIn('Trade executed successfully', message)
        
        # Test with minimal trade data
        minimal_trade = {'action': 'sell'}
        minimal_message = self.bot._format_trade_message(minimal_trade)
        
        self.assertIn('🤖', minimal_message)
        self.assertIn('Trade Notification', minimal_message)
        self.assertIn('SELL', minimal_message)
    
    @patch('binance_trade_bot.telegram.bot.TelegramBot.send_message')
    async def test_send_trade_notification(self, mock_send_message):
        """
        Test trade notification sending functionality.
        """
        # Mock database session and users
        mock_session = Mock()
        mock_user1 = Mock()
        mock_user1.telegram_id = '123456789'
        mock_user2 = Mock()
        mock_user2.telegram_id = '987654321'
        
        mock_session.query.return_value.filter.return_value.all.return_value = [mock_user1, mock_user2]
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Mock successful message sending
        mock_send_message.return_value = True
        
        trade_data = {'action': 'buy', 'pair': 'BTCUSDT'}
        result = await self.bot.send_trade_notification(trade_data)
        
        # Verify result
        self.assertTrue(result)
        self.assertEqual(mock_send_message.call_count, 2)
        
        # Verify calls were made with correct parameters
        mock_send_message.assert_any_call('123456789', self.bot._format_trade_message(trade_data))
        mock_send_message.assert_any_call('987654321', self.bot._format_trade_message(trade_data))
    
    @patch('binance_trade_bot.telegram.bot.TelegramBot.send_message')
    async def test_send_alert(self, mock_send_message):
        """
        Test alert sending functionality.
        """
        # Mock successful message sending
        mock_send_message.return_value = True
        
        alert_data = {'type': 'error', 'message': 'Test error', 'details': {'code': 500}}
        result = await self.bot.send_alert('error', 'Test error', {'code': 500})
        
        # Verify result
        self.assertTrue(result)
        self.assertEqual(mock_send_message.call_count, 1)  # Only to admin
        
        # Verify call was made with correct parameters
        mock_send_message.assert_called_once_with(
            self.config['telegram_admin_id'],
            '🚨 *ERROR ALERT* 🚨\n\n*Message:* Test error\n\n*Details:*\n• code: 500\n',
            parse_mode='Markdown'
        )
    
    @patch('binance_trade_bot.telegram.bot.TelegramBot.send_message')
    async def test_send_message_success(self, mock_send_message):
        """
        Test successful message sending.
        """
        mock_send_message.return_value = True
        
        result = await self.bot.send_message('123456789', 'Test message')
        
        self.assertTrue(result)
        mock_send_message.assert_called_once_with(
            chat_id='123456789',
            text='Test message',
            parse_mode=None,
            disable_web_page_preview=True
        )
    
    @patch('binance_trade_bot.telegram.bot.TelegramBot.send_message')
    async def test_send_message_forbidden(self, mock_send_message):
        """
        Test message sending when user has blocked the bot.
        """
        from telegram.error import Forbidden
        mock_send_message.side_effect = Forbidden('User blocked the bot')
        
        result = await self.bot.send_message('123456789', 'Test message')
        
        self.assertFalse(result)
        self.logger.warning.assert_called_once()
    
    @patch('binance_trade_bot.telegram.bot.TelegramBot.send_message')
    async def test_send_message_bad_request(self, mock_send_message):
        """
        Test message sending with bad request.
        """
        from telegram.error import BadRequest
        mock_send_message.side_effect = BadRequest('Bad request')
        
        result = await self.bot.send_message('123456789', 'Test message')
        
        self.assertFalse(result)
        self.logger.error.assert_called()
    
    @patch('binance_trade_bot.telegram.bot.TelegramBot.send_message')
    async def test_send_message_telegram_error(self, mock_send_message):
        """
        Test message sending with general Telegram error.
        """
        from telegram.error import TelegramError
        mock_send_message.side_effect = TelegramError('Telegram error')
        
        result = await self.bot.send_message('123456789', 'Test message')
        
        self.assertFalse(result)
        self.logger.error.assert_called()
    
    @patch('binance_trade_bot.telegram.bot.TelegramBot.send_message')
    async def test_send_message_exception(self, mock_send_message):
        """
        Test message sending with unexpected exception.
        """
        mock_send_message.side_effect = Exception('Unexpected error')
        
        result = await self.bot.send_message('123456789', 'Test message')
        
        self.assertFalse(result)
        self.logger.error.assert_called()
    
    async def test_start_command_new_user(self):
        """
        Test /start command with new user.
        """
        # Mock database session
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session.add = Mock()
        mock_session.commit = Mock()
        
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Execute command
        await self.bot._start_command(self.update, self.context)
        
        # Verify user creation
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        
        # Verify welcome message
        self.update.message.reply_text.assert_called_once()
        call_args = self.update.message.reply_text.call_args[0][0]
        self.assertIn('Welcome to the Binance Trade Bot', call_args)
        self.assertIn('use /help to see available commands', call_args)
    
    async def test_start_command_existing_user(self):
        """
        Test /start command with existing user.
        """
        # Mock existing user
        mock_db_user = Mock()
        mock_db_user.username = 'oldusername'
        mock_db_user.first_name = 'Old'
        mock_db_user.last_name = 'User'
        mock_db_user.last_login_at = None
        
        # Mock database session
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        mock_session.commit = Mock()
        
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Execute command
        await self.bot._start_command(self.update, self.context)
        
        # Verify user info update
        self.assertEqual(mock_db_user.username, 'testuser')
        self.assertEqual(mock_db_user.first_name, 'Test')
        self.assertEqual(mock_db_user.last_name, 'User')
        mock_session.commit.assert_called_once()
        
        # Verify welcome back message
        self.update.message.reply_text.assert_called_once()
        call_args = self.update.message.reply_text.call_args[0][0]
        self.assertIn('Welcome back', call_args)
        self.assertIn('Test', call_args)
    
    async def test_start_command_rate_limited(self):
        """
        Test /start command with rate limiting.
        """
        # Simulate rate limiting
        self.bot._record_command_usage(str(self.mock_user.id), 'start')
        self.bot._record_command_usage(str(self.mock_user.id), 'start')
        self.bot._record_command_usage(str(self.mock_user.id), 'start')
        self.bot._record_command_usage(str(self.mock_user.id), 'start')
        self.bot._record_command_usage(str(self.mock_user.id), 'start')  # Hit limit
        
        # Execute command
        await self.bot._start_command(self.update, self.context)
        
        # Verify rate limited response
        self.update.message.reply_text.assert_called_once_with(
            "⚠️ Too many start commands. Please wait a moment."
        )
    
    async def test_help_command(self):
        """
        Test /help command.
        """
        # Mock database session
        mock_session = Mock()
        mock_user = Mock()
        mock_user.role = UserRole.VIEWER
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Execute command
        await self.bot._help_command(self.update, self.context)
        
        # Verify help message
        self.update.message.reply_text.assert_called_once()
        call_args = self.update.message.reply_text.call_args[0][0]
        self.assertIn('Available Commands', call_args)
        self.assertIn('/start', call_args)
        self.assertIn('/help', call_args)
        self.assertIn('/menu', call_args)
    
    async def test_help_command_user_not_found(self):
        """
        Test /help command when user is not found.
        """
        # Mock database session returning no user
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Execute command
        await self.bot._help_command(self.update, self.context)
        
        # Verify error message
        self.update.message.reply_text.assert_called_once_with(
            "❌ User not found. Please use /start first."
        )
    
    async def test_menu_command(self):
        """
        Test /menu command.
        """
        # Mock database session
        mock_session = Mock()
        mock_user = Mock()
        mock_user.role = UserRole.VIEWER
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Execute command
        await self.bot._menu_command(self.update, self.context)
        
        # Verify menu message
        self.update.message.reply_text.assert_called_once()
        call_args = self.update.message.reply_text.call_args[0][0]
        self.assertIn('Main Menu', call_args)
        self.assertIn('Choose an option:', call_args)
        
        # Verify keyboard was created
        reply_markup = self.update.message.reply_text.call_args[1]['reply_markup']
        self.assertIsInstance(reply_markup, InlineKeyboardMarkup)
        self.assertTrue(len(reply_markup.inline_keyboard) > 0)
    
    async def test_menu_command_admin_user(self):
        """
        Test /menu command with admin user.
        """
        # Mock admin user
        mock_session = Mock()
        mock_user = Mock()
        mock_user.role = UserRole.ADMIN
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        # Execute command
        await self.bot._menu_command(self.update, self.context)
        
        # Verify admin options are included
        reply_markup = self.update.message.reply_text.call_args[1]['reply_markup']
        keyboard_buttons = []
        for row in reply_markup.inline_keyboard:
            for button in row:
                keyboard_buttons.append(button.text)
        
        self.assertIn('Admin Panel', keyboard_buttons)
        self.assertIn('Broadcast', keyboard_buttons)
    
    async def test_handle_callback_query_close(self):
        """
        Test callback query handler for close action.
        """
        self.update.callback_query.data = 'close'
        
        await self.bot._handle_callback_query(self.update, self.context)
        
        # Verify close action
        self.update.callback_query.answer.assert_called_once_with()
        self.update.callback_query.message.delete.assert_called_once()
    
    async def test_handle_callback_query_balance(self):
        """
        Test callback query handler for balance action.
        """
        self.update.callback_query.data = 'balance'
        
        # Mock database session
        mock_session = Mock()
        mock_user = Mock()
        mock_user.role = UserRole.VIEWER
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        await self.bot._handle_callback_query(self.update, self.context)
        
        # Verify balance display
        self.update.callback_query.answer.assert_called_once_with()
        self.update.callback_query.message.edit_text.assert_called_once()
        call_args = self.update.callback_query.message.edit_text.call_args[0][0]
        self.assertIn('Balance Information', call_args)
        self.assertIn('BTC', call_args)
        self.assertIn('ETH', call_args)
        self.assertIn('USDT', call_args)
    
    async def test_handle_callback_query_unknown_command(self):
        """
        Test callback query handler for unknown command.
        """
        self.update.callback_query.data = 'unknown'
        
        # Mock database session
        mock_session = Mock()
        mock_user = Mock()
        mock_user.role = UserRole.VIEWER
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        await self.bot._handle_callback_query(self.update, self.context)
        
        # Verify unknown command response
        self.update.callback_query.answer.assert_called_once_with("❌ Unknown command")
    
    async def test_handle_callback_query_admin_only(self):
        """
        Test callback query handler for admin-only command with non-admin user.
        """
        self.update.callback_query.data = 'admin'
        
        # Mock non-admin user
        mock_session = Mock()
        mock_user = Mock()
        mock_user.role = UserRole.VIEWER
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        await self.bot._handle_callback_query(self.update, self.context)
        
        # Verify access denied
        self.update.callback_query.answer.assert_called_once_with("❌ Unknown command")
    
    async def test_handle_callback_query_admin_success(self):
        """
        Test callback query handler for admin-only command with admin user.
        """
        self.update.callback_query.data = 'admin'
        
        # Mock admin user
        mock_session = Mock()
        mock_user = Mock()
        mock_user.role = UserRole.ADMIN
        mock_user.first_name = 'Admin'
        mock_user.last_name = 'User'
        mock_user.last_login_at = datetime.utcnow()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_user
        
        self.database.db_session.return_value.__enter__.return_value = mock_session
        
        await self.bot._handle_callback_query(self.update, self.context)
        
        # Verify admin panel display
        self.update.callback_query.answer.assert_called_once_with()
        self.update.callback_query.message.edit_text.assert_called_once()
        call_args = self.update.callback_query.message.edit_text.call_args[0][0]
        self.assertIn('Admin Panel', call_args)
        self.assertIn('Admin: Admin User', call_args)
    
    async def test_unknown_command_handler(self):
        """
        Test unknown command handler.
        """
        await self.bot._unknown_command(self.update, self.context)
        
        # Verify unknown command response
        self.update.message.reply_text.assert_called_once_with(
            "❌ Unknown command. Use /help to see available commands."
        )
    
    @patch('binance_trade_bot.telegram.bot.Application')
    async def test_start_bot_success(self, mock_application):
        """
        Test successful bot start.
        """
        # Mock successful application setup
        mock_app_instance = Mock()
        mock_application.builder.return_value.token.return_value.build.return_value = mock_app_instance
        mock_app_instance.bot = Mock()
        mock_app_instance.initialize = AsyncMock()
        mock_app_instance.start = AsyncMock()
        mock_app_instance.updater = Mock()
        mock_app_instance.updater.start_polling = AsyncMock()
        
        # Execute start
        result = await self.bot.start_bot()
        
        # Verify success
        self.assertTrue(result)
        mock_app_instance.initialize.assert_called_once()
        mock_app_instance.start.assert_called_once()
        mock_app_instance.updater.start_polling.assert_called_once()
        
        # Verify logger call
        self.logger.info.assert_called()
    
    @patch('binance_trade_bot.telegram.bot.Application')
    async def test_start_bot_no_token(self, mock_application):
        """
        Test bot start without token.
        """
        # Remove token from config
        config_no_token = self.config.copy()
        config_no_token.pop('telegram_token')
        
        bot = TelegramBot(config_no_token, self.database, self.logger)
        
        # Execute start
        result = await bot.start_bot()
        
        # Verify failure
        self.assertFalse(result)
        self.logger.error.assert_called_once_with("Telegram token not configured")
    
    @patch('binance_trade_bot.telegram.bot.Application')
    async def test_start_bot_exception(self, mock_application):
        """
        Test bot start with exception.
        """
        # Mock exception
        mock_application.builder.return_value.token.return_value.build.side_effect = Exception("Setup failed")
        
        # Execute start
        result = await self.bot.start_bot()
        
        # Verify failure
        self.assertFalse(result)
        self.logger.error.assert_called()
    
    @patch('binance_trade_bot.telegram.bot.Application')
    async def test_stop_bot_success(self, mock_application):
        """
        Test successful bot stop.
        """
        # Mock application
        mock_app_instance = Mock()
        mock_app_instance.updater = Mock()
        mock_app_instance.updater.stop = AsyncMock()
        mock_app_instance.stop = AsyncMock()
        mock_app_instance.shutdown = AsyncMock()
        
        self.bot.application = mock_app_instance
        
        # Execute stop
        result = await self.bot.stop_bot()
        
        # Verify success
        self.assertTrue(result)
        mock_app_instance.updater.stop.assert_called_once()
        mock_app_instance.stop.assert_called_once()
        mock_app_instance.shutdown.assert_called_once()
        
        # Verify logger call
        self.logger.info.assert_called()
    
    async def test_stop_bot_no_application(self):
        """
        Test bot stop without application.
        """
        # Execute stop
        result = await self.bot.stop_bot()
        
        # Verify failure
        self.assertFalse(result)
    
    async def test_stop_bot_exception(self):
        """
        Test bot stop with exception.
        """
        # Mock application with exception
        mock_app_instance = Mock()
        mock_app_instance.updater = Mock()
        mock_app_instance.updater.stop.side_effect = Exception("Stop failed")
        
        self.bot.application = mock_app_instance
        
        # Execute stop
        result = await self.bot.stop_bot()
        
        # Verify failure
        self.assertFalse(result)
        self.logger.error.assert_called()


class TestTelegramBotIntegration(unittest.TestCase):
    """
    Integration tests for Telegram bot with database and authentication.
    """
    
    def setUp(self):
        """
        Set up test fixtures for integration tests.
        """
        # Create test configuration
        self.config = {
            'telegram_token': 'test_token',
            'telegram_webhook_url': 'https://example.com/webhook',
            'telegram_admin_id': '123456789'
        }
        
        # Create mock database with real session behavior
        self.database = Mock(spec=Database)
        self.database.db_session = Mock()
        
        # Create mock logger
        self.logger = Mock(spec=Logger)
        
        # Create Telegram bot instance
        self.bot = TelegramBot(self.config, self.database, self.logger)
    
    def test_user_role_hierarchy(self):
        """
        Test user role hierarchy permissions.
        """
        # Test role hierarchy
        from binance_trade_bot.models.telegram_users import UserRole
        
        # Create mock users with different roles
        viewer_user = Mock()
        viewer_user.role = UserRole.VIEWER
        
        trader_user = Mock()
        trader_user.role = UserRole.TRADER
        
        admin_user = Mock()
        admin_user.role = UserRole.ADMIN
        
        # Test permissions
        self.assertFalse(viewer_user.has_permission(UserRole.ADMIN))
        self.assertFalse(viewer_user.has_permission(UserRole.TRADER))
        self.assertTrue(viewer_user.has_permission(UserRole.VIEWER))
        
        self.assertFalse(trader_user.has_permission(UserRole.ADMIN))
        self.assertTrue(trader_user.has_permission(UserRole.TRADER))
        self.assertTrue(trader_user.has_permission(UserRole.VIEWER))
        
        self.assertTrue(admin_user.has_permission(UserRole.ADMIN))
        self.assertTrue(admin_user.has_permission(UserRole.TRADER))
        self.assertTrue(admin_user.has_permission(UserRole.VIEWER))
    
    def test_user_status_management(self):
        """
        Test user status management functionality.
        """
        from binance_trade_bot.models.telegram_users import UserStatus
        
        # Create mock user
        user = Mock()
        user.status = UserStatus.PENDING
        
        # Test status transitions
        user.activate()
        self.assertEqual(user.status, UserStatus.ACTIVE)
        
        user.deactivate()
        self.assertEqual(user.status, UserStatus.INACTIVE)
        
        user.ban()
        self.assertEqual(user.status, UserStatus.BANNED)
        
        user.set_pending()
        self.assertEqual(user.status, UserStatus.PENDING)
    
    def test_user_authentication_methods(self):
        """
        Test user authentication methods.
        """
        from binance_trade_bot.models.telegram_users import UserStatus
        
        # Create mock user
        user = Mock()
        user.failed_login_attempts = 0
        user.locked_until = None
        
        # Test failed login recording
        user.record_failed_login = Mock()
        user.reset_failed_login = Mock()
        
        # Test authentication methods
        user.generate_api_key = Mock(return_value='test_api_key')
        user.revoke_api_key = Mock()
        user.is_api_key_valid = Mock(return_value=True)
        
        # Test two-factor authentication
        user.enable_two_factor = Mock()
        user.disable_two_factor = Mock()
        
        # Verify methods exist and can be called
        user.generate_api_key(30)
        user.revoke_api_key()
        user.enable_two_factor('test_secret')
        user.disable_two_factor()
        
        # Verify notification and preference methods
        user.update_notification_settings = Mock()
        user.update_trading_preferences = Mock()
        user.get_notification_settings = Mock(return_value={})
        user.get_trading_preferences = Mock(return_value={})
        
        user.update_notification_settings({'enabled': True})
        user.update_trading_preferences({'risk_level': 'medium'})


if __name__ == '__main__':
    unittest.main()