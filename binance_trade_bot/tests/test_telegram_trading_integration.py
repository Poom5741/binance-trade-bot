"""
Integration tests for Telegram bot with trading control commands.
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
import asyncio

# Import telegram library directly, not from local module
import telegram as telegram_lib
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from binance_trade_bot.telegram.bot import TelegramBot
from binance_trade_bot.models.telegram_users import TelegramUsers, UserRole, UserStatus
from binance_trade_bot.risk_management.integrated_risk_manager import IntegratedRiskManager
from binance_trade_bot.auto_trader import AutoTrader
from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger


class TestTelegramBotTradingIntegration(unittest.TestCase):
    """Test cases for Telegram bot integration with trading control."""

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
        
        # Create telegram bot instance with trading control
        self.telegram_bot = TelegramBot(
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
        self.mock_user.language_code = 'en'
        
        # Mock update
        self.mock_update = Mock(spec=Update)
        self.mock_update.effective_user = self.mock_user
        self.mock_update.message.reply_text = AsyncMock()
        self.mock_update.callback_query.answer = AsyncMock()
        self.mock_update.callback_query.edit_message_text = AsyncMock()
        
        # Mock context
        self.mock_context = Mock(spec=CallbackContext)
        self.mock_context.args = []

    def test_init_with_trading_control(self):
        """Test initialization with trading control dependencies."""
        self.assertIsNotNone(self.telegram_bot.trading_control)
        self.assertEqual(self.telegram_bot.trading_control.config, self.config)
        self.assertEqual(self.telegram_bot.trading_control.database, self.database)
        self.assertEqual(self.telegram_bot.trading_control.logger, self.logger)
        self.assertEqual(self.telegram_bot.trading_control.risk_manager, self.risk_manager)
        self.assertEqual(self.telegram_bot.trading_control.auto_trader, self.auto_trader)

    def test_init_without_trading_control(self):
        """Test initialization without trading control dependencies."""
        bot = TelegramBot(
            config=self.config,
            database=self.database,
            logger=self.logger
        )
        
        self.assertIsNone(bot.trading_control)

    def test_command_rate_limits_includes_trading_commands(self):
        """Test that trading control commands are included in rate limits."""
        expected_commands = ['stop', 'resume', 'shutdown']
        
        for command in expected_commands:
            self.assertIn(command, self.telegram_bot.COMMAND_RATE_LIMITS)

    async def test_status_command_integration(self):
        """Test status command integration with trading control."""
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock trading control status generation
        self.telegram_bot.trading_control._generate_status_message = AsyncMock(
            return_value='*Trading Status*\\n\\nStatus: Active'
        )
        
        await self.telegram_bot._status_command(self.mock_update, self.mock_context)
        
        self.mock_update.message.reply_text.assert_called_once_with(
            '*Trading Status*\\n\\nStatus: Active',
            parse_mode='Markdown'
        )

    async def test_stop_command_integration(self):
        """Test stop command integration with trading control."""
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock trading control stop command
        self.telegram_bot.trading_control._stop_command = AsyncMock()
        
        await self.telegram_bot._stop_command(self.mock_update, self.mock_context)
        
        self.telegram_bot.trading_control._stop_command.assert_called_once_with(
            self.mock_update, self.mock_context
        )

    async def test_resume_command_integration(self):
        """Test resume command integration with trading control."""
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock trading control resume command
        self.telegram_bot.trading_control._resume_command = AsyncMock()
        
        await self.telegram_bot._resume_command(self.mock_update, self.mock_context)
        
        self.telegram_bot.trading_control._resume_command.assert_called_once_with(
            self.mock_update, self.mock_context
        )

    async def test_shutdown_command_integration(self):
        """Test shutdown command integration with trading control."""
        # Mock user with admin permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock trading control shutdown command
        self.telegram_bot.trading_control._shutdown_command = AsyncMock()
        
        await self.telegram_bot._shutdown_command(self.mock_update, self.mock_context)
        
        self.telegram_bot.trading_control._shutdown_command.assert_called_once_with(
            self.mock_update, self.mock_context
        )

    async def test_status_command_without_trading_control(self):
        """Test status command fallback when trading control is not available."""
        # Create bot without trading control
        bot = TelegramBot(
            config=self.config,
            database=self.database,
            logger=self.logger
        )
        
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        await bot._status_command(self.mock_update, self.mock_context)
        
        expected_message = bot._get_basic_status_text()
        self.mock_update.message.reply_text.assert_called_once_with(expected_message, parse_mode='Markdown')

    async def test_stop_command_without_trading_control(self):
        """Test stop command fallback when trading control is not available."""
        # Create bot without trading control
        bot = TelegramBot(
            config=self.config,
            database=self.database,
            logger=self.logger
        )
        
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        await bot._stop_command(self.mock_update, self.mock_context)
        
        self.mock_update.message.reply_text.assert_called_once_with(
            "⚠️ Trading control not available. Please check system configuration."
        )

    async def test_resume_command_without_trading_control(self):
        """Test resume command fallback when trading control is not available."""
        # Create bot without trading control
        bot = TelegramBot(
            config=self.config,
            database=self.database,
            logger=self.logger
        )
        
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        await bot._resume_command(self.mock_update, self.mock_context)
        
        self.mock_update.message.reply_text.assert_called_once_with(
            "⚠️ Trading control not available. Please check system configuration."
        )

    async def test_shutdown_command_without_trading_control(self):
        """Test shutdown command fallback when trading control is not available."""
        # Create bot without trading control
        bot = TelegramBot(
            config=self.config,
            database=self.database,
            logger=self.logger
        )
        
        # Mock user with admin permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        await bot._shutdown_command(self.mock_update, self.mock_context)
        
        self.mock_update.message.reply_text.assert_called_once_with(
            "⚠️ Trading control not available. Please check system configuration."
        )

    def test_help_text_includes_trading_commands(self):
        """Test that help text includes trading control commands."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.VIEWER
        
        help_text = self.telegram_bot._get_help_text(mock_user)
        
        # Check that trading control commands are mentioned
        self.assertIn('/status', help_text)
        self.assertIn('/stop', help_text)
        self.assertIn('/resume', help_text)
        self.assertIn('/shutdown', help_text)
        self.assertIn('Trading Control:', help_text)

    def test_help_text_admin_includes_admin_features(self):
        """Test that admin help text includes admin features."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.ADMIN
        
        help_text = self.telegram_bot._get_help_text(mock_user)
        
        # Check that admin features are mentioned
        self.assertIn('Admin Features:', help_text)
        self.assertIn('Emergency shutdown requires confirmation dialog', help_text)
        self.assertIn('Full system control and monitoring capabilities', help_text)

    def test_menu_keyboard_includes_trading_buttons_for_trader(self):
        """Test that menu keyboard includes trading control buttons for trader role."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.TRADER
        
        keyboard = self.telegram_bot._get_menu_keyboard(mock_user)
        
        # Flatten keyboard to get all button texts
        button_texts = [button.text for row in keyboard for button in row]
        
        # Check that trading control buttons are present
        self.assertIn('📊 Status', button_texts)
        self.assertIn('🛑 Stop Trading', button_texts)
        self.assertIn('▶️ Resume Trading', button_texts)
        self.assertIn('🚨 Emergency Shutdown', button_texts)

    def test_menu_keyboard_includes_trading_buttons_for_admin(self):
        """Test that menu keyboard includes trading control buttons for admin role."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.ADMIN
        
        keyboard = self.telegram_bot._get_menu_keyboard(mock_user)
        
        # Flatten keyboard to get all button texts
        button_texts = [button.text for row in keyboard for button in row]
        
        # Check that trading control buttons are present
        self.assertIn('📊 Status', button_texts)
        self.assertIn('🛑 Stop Trading', button_texts)
        self.assertIn('▶️ Resume Trading', button_texts)
        self.assertIn('🚨 Emergency Shutdown', button_texts)

    def test_menu_keyboard_excludes_trading_buttons_for_viewer(self):
        """Test that menu keyboard excludes trading control buttons for viewer role."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.VIEWER
        
        keyboard = self.telegram_bot._get_menu_keyboard(mock_user)
        
        # Flatten keyboard to get all button texts
        button_texts = [button.text for row in keyboard for button in row]
        
        # Check that trading control buttons are not present
        self.assertNotIn('🛑 Stop Trading', button_texts)
        self.assertNotIn('▶️ Resume Trading', button_texts)
        self.assertNotIn('🚨 Emergency Shutdown', button_texts)

    @patch('binance_trade_bot.telegram.bot.Application')
    async def test_start_bot_registers_trading_commands(self, mock_application):
        """Test that start bot registers trading control commands when available."""
        # Mock application and bot
        mock_app_instance = Mock()
        mock_bot_instance = Mock()
        mock_application.builder.return_value.token.return_value.build.return_value = mock_app_instance
        mock_app_instance.bot = mock_bot_instance
        
        # Mock successful start
        mock_app_instance.initialize = AsyncMock()
        mock_app_instance.start = AsyncMock()
        mock_app_instance.updater.start_polling = AsyncMock()
        
        # Start bot
        result = await self.telegram_bot.start_bot()
        
        # Verify that trading control commands are registered
        self.assertTrue(result)
        
        # Check that command handlers were added
        self.assertIn(CommandHandler, [type(handler) for handler in mock_app_instance.add_handler.call_args_list])

    @patch('binance_trade_bot.telegram.bot.Application')
    async def test_start_bot_without_trading_commands(self, mock_application):
        """Test that start bot doesn't register trading commands when not available."""
        # Create bot without trading control
        bot = TelegramBot(
            config=self.config,
            database=self.database,
            logger=self.logger
        )
        
        # Mock application and bot
        mock_app_instance = Mock()
        mock_bot_instance = Mock()
        mock_application.builder.return_value.token.return_value.build.return_value = mock_app_instance
        mock_app_instance.bot = mock_bot_instance
        
        # Mock successful start
        mock_app_instance.initialize = AsyncMock()
        mock_app_instance.start = AsyncMock()
        mock_app_instance.updater.start_polling = AsyncMock()
        
        # Start bot
        result = await bot.start_bot()
        
        # Verify that bot started successfully
        self.assertTrue(result)
        
        # Check that only basic commands are registered
        call_args_list = mock_app_instance.add_handler.call_args_list
        handler_types = [type(handler[0][0]) for handler in call_args_list]
        
        # Should not have trading control commands
        self.assertNotIn(CommandHandler('status', bot._status_command), handler_types)
        self.assertNotIn(CommandHandler('stop', bot._stop_command), handler_types)
        self.assertNotIn(CommandHandler('resume', bot._resume_command), handler_types)
        self.assertNotIn(CommandHandler('shutdown', bot._shutdown_command), handler_types)


class TestTelegramBotErrorHandling(unittest.TestCase):
    """Test error handling in Telegram bot with trading control integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'telegram_token': 'test_token',
            'telegram_admin_id': '123456789',
            'trading_enabled': True
        }
        
        self.database = Mock(spec=Database)
        self.logger = Mock(spec=Logger)
        self.risk_manager = Mock(spec=IntegratedRiskManager)
        self.auto_trader = Mock(spec=AutoTrader)
        
        # Mock database session
        self.mock_session = Mock()
        self.database.db_session.return_value.__enter__.return_value = self.mock_session
        
        # Create telegram bot instance
        self.telegram_bot = TelegramBot(
            config=self.config,
            database=self.database,
            logger=self.logger,
            risk_manager=self.risk_manager,
            auto_trader=self.auto_trader
        )

    async def test_status_command_error_handling(self):
        """Test error handling in status command."""
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock trading control to raise exception
        self.telegram_bot.trading_control._generate_status_message = AsyncMock(
            side_effect=Exception("Test error")
        )
        
        # Mock update
        mock_user = Mock()
        mock_user.id = '123456789'
        mock_update = Mock(spec=Update)
        mock_update.effective_user = mock_user
        mock_update.message.reply_text = AsyncMock()
        
        await self.telegram_bot._status_command(mock_update, Mock())
        
        # Check that error was logged
        self.logger.error.assert_called()
        
        # Check that user was notified
        mock_update.message.reply_text.assert_called_once_with("❌ An error occurred while fetching status.")

    async def test_stop_command_error_handling(self):
        """Test error handling in stop command."""
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock trading control to raise exception
        self.telegram_bot.trading_control._stop_command = AsyncMock(
            side_effect=Exception("Test error")
        )
        
        # Mock update
        mock_user = Mock()
        mock_user.id = '123456789'
        mock_update = Mock(spec=Update)
        mock_update.effective_user = mock_user
        mock_update.message.reply_text = AsyncMock()
        
        await self.telegram_bot._stop_command(mock_update, Mock())
        
        # Check that error was logged
        self.logger.error.assert_called()
        
        # Check that user was notified
        mock_update.message.reply_text.assert_called_once_with("❌ An error occurred while stopping trading.")

    async def test_resume_command_error_handling(self):
        """Test error handling in resume command."""
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock trading control to raise exception
        self.telegram_bot.trading_control._resume_command = AsyncMock(
            side_effect=Exception("Test error")
        )
        
        # Mock update
        mock_user = Mock()
        mock_user.id = '123456789'
        mock_update = Mock(spec=Update)
        mock_update.effective_user = mock_user
        mock_update.message.reply_text = AsyncMock()
        
        await self.telegram_bot._resume_command(mock_update, Mock())
        
        # Check that error was logged
        self.logger.error.assert_called()
        
        # Check that user was notified
        mock_update.message.reply_text.assert_called_once_with("❌ An error occurred while resuming trading.")

    async def test_shutdown_command_error_handling(self):
        """Test error handling in shutdown command."""
        # Mock user with permission
        mock_db_user = Mock(spec=TelegramUsers)
        mock_db_user.has_permission.return_value = True
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_db_user
        
        # Mock trading control to raise exception
        self.telegram_bot.trading_control._shutdown_command = AsyncMock(
            side_effect=Exception("Test error")
        )
        
        # Mock update
        mock_user = Mock()
        mock_user.id = '123456789'
        mock_update = Mock(spec=Update)
        mock_update.effective_user = mock_user
        mock_update.message.reply_text = AsyncMock()
        
        await self.telegram_bot._shutdown_command(mock_update, Mock())
        
        # Check that error was logged
        self.logger.error.assert_called()
        
        # Check that user was notified
        mock_update.message.reply_text.assert_called_once_with("❌ An error occurred while initiating shutdown.")


if __name__ == '__main__':
    unittest.main()