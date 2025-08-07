"""
Unit tests for Telegram bot statistics commands.

This module contains comprehensive unit tests for the statistics and reporting
commands functionality, including daily, weekly, total performance display
and current portfolio holdings.
"""

import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal

from telegram import Update, InlineKeyboardButton
from telegram.ext import CallbackContext

from binance_trade_bot.telegram.statistics_commands import StatisticsCommands
from binance_trade_bot.statistics.manager import StatisticsManager
from binance_trade_bot.statistics.models import Statistics, DailyPerformance, WeeklyPerformance, TotalPerformance
from binance_trade_bot.models.coin import Coin
from binance_trade_bot.models.coin_value import CoinValue
from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger


class TestStatisticsCommands(unittest.TestCase):
    """
    Test suite for StatisticsCommands class.
    """
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.config = {
            'telegram_token': 'test_token',
            'telegram_admin_id': '123456789'
        }
        
        # Mock database
        self.database = Mock(spec=Database)
        self.database.db_session.return_value.__enter__ = Mock()
        self.database.db_session.return_value.__exit__ = Mock()
        
        # Mock logger
        self.logger = Mock(spec=Logger)
        
        # Mock statistics manager
        self.statistics_manager = Mock(spec=StatisticsManager)
        
        # Create statistics commands instance
        self.statistics_commands = StatisticsCommands(
            config=self.config,
            database=self.database,
            logger=self.logger,
            statistics_manager=self.statistics_manager
        )
    
    def test_init(self):
        """Test StatisticsCommands initialization."""
        self.assertEqual(self.statistics_commands.config, self.config)
        self.assertEqual(self.statistics_commands.database, self.database)
        self.assertEqual(self.statistics_commands.logger, self.logger)
        self.assertEqual(self.statistics_commands.statistics_manager, self.statistics_manager)
        self.assertEqual(self.statistics_commands.telegram_admin_id, '123456789')
        self.assertEqual(self.statistics_commands.chart_width, 20)
        self.assertEqual(self.statistics_commands.chart_height, 8)
    
    def test_is_rate_limited_not_limited(self):
        """Test rate limiting when user is not rate limited."""
        user_id = '123456789'
        command = 'stats'
        
        result = self.statistics_commands._is_rate_limited(user_id, command)
        
        self.assertFalse(result)
    
    def test_is_rate_limited_limited(self):
        """Test rate limiting when user is rate limited."""
        user_id = '123456789'
        command = 'stats'
        
        # Simulate multiple calls in quick succession
        for _ in range(10):
            self.statistics_commands._record_command_usage(user_id, command)
        
        result = self.statistics_commands._is_rate_limited(user_id, command)
        
        self.assertTrue(result)
    
    def test_record_command_usage(self):
        """Test command usage recording."""
        user_id = '123456789'
        command = 'stats'
        
        self.statistics_commands._record_command_usage(user_id, command)
        
        # Verify usage was recorded
        self.assertIn(user_id, self.statistics_commands.user_command_counts)
        self.assertIn(command, self.statistics_commands.user_command_counts[user_id])
        self.assertEqual(len(self.statistics_commands.user_command_counts[user_id][command]), 1)
    
    def test_format_currency(self):
        """Test currency formatting."""
        result = self.statistics_commands._format_currency(1234.5678)
        self.assertEqual(result, '$1,234.57')
        
        result = self.statistics_commands._format_currency(1234.5678, 'BTC')
        self.assertEqual(result, '₿1,234.57')
    
    def test_format_percentage(self):
        """Test percentage formatting."""
        result = self.statistics_commands._format_percentage(0.1234)
        self.assertEqual(result, '+12.34%')
        
        result = self.statistics_commands._format_percentage(-0.1234)
        self.assertEqual(result, '-12.34%')
        
        result = self.statistics_commands._format_percentage(0)
        self.assertEqual(result, '0.00%')
    
    def test_format_number(self):
        """Test number formatting."""
        result = self.statistics_commands._format_number(1234567.89)
        self.assertEqual(result, '1,234,567.89')
        
        result = self.statistics_commands._format_number(0.00000123)
        self.assertEqual(result, '0.00000123')
    
    def test_create_simple_chart(self):
        """Test simple chart creation."""
        data = [100, 200, 150, 300, 250]
        result = self.statistics_commands._create_simple_chart(data)
        
        self.assertIsInstance(result, str)
        self.assertIn('█', result)  # Chart should contain block characters
        self.assertIn('\n', result)  # Chart should contain newlines
    
    def test_create_simple_chart_empty_data(self):
        """Test simple chart creation with empty data."""
        data = []
        result = self.statistics_commands._create_simple_chart(data)
        
        self.assertIsInstance(result, str)
        self.assertEqual(result, '')
    
    def test_format_daily_stats_message_no_data(self):
        """Test daily stats message formatting with no data."""
        stats = {
            'date': datetime.now().isoformat(),
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
        
        result = self.statistics_commands._format_daily_stats_message(stats)
        
        self.assertIsInstance(result, str)
        self.assertIn('Daily Performance', result)
        self.assertIn('No trading activity', result)
    
    def test_format_daily_stats_message_with_data(self):
        """Test daily stats message formatting with data."""
        stats = {
            'date': datetime.now().isoformat(),
            'total_trades': 10,
            'winning_trades': 6,
            'losing_trades': 4,
            'win_rate': 60.0,
            'total_profit_loss': 100.0,
            'total_profit_loss_percentage': 5.0,
            'average_profit_loss': 10.0,
            'average_win': 20.0,
            'average_loss': -15.0,
            'total_volume': 1000.0,
            'average_trade_size': 100.0,
            'roi': 10.0,
            'sharpe_ratio': 1.5,
            'max_drawdown': -5.0,
            'volatility': 10.0,
            'profit_factor': 2.0,
            'recovery_factor': 1.2,
            'calmar_ratio': 2.0,
        }
        
        result = self.statistics_commands._format_daily_stats_message(stats)
        
        self.assertIsInstance(result, str)
        self.assertIn('Daily Performance', result)
        self.assertIn('Total Trades: 10', result)
        self.assertIn('Win Rate: 60.00%', result)
        self.assertIn('Total P&L: +$100.00', result)
    
    def test_format_weekly_stats_message_no_data(self):
        """Test weekly stats message formatting with no data."""
        stats = {
            'week_start': datetime.now().isoformat(),
            'week_end': (datetime.now() + timedelta(days=6)).isoformat(),
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
        
        result = self.statistics_commands._format_weekly_stats_message(stats)
        
        self.assertIsInstance(result, str)
        self.assertIn('Weekly Performance', result)
        self.assertIn('No trading activity', result)
    
    def test_format_total_stats_message_no_data(self):
        """Test total stats message formatting with no data."""
        stats = {
            'start_date': datetime.now().isoformat(),
            'end_date': (datetime.now() + timedelta(days=30)).isoformat(),
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
        
        result = self.statistics_commands._format_total_stats_message(stats)
        
        self.assertIsInstance(result, str)
        self.assertIn('Total Performance', result)
        self.assertIn('No trading activity', result)
    
    def test_format_portfolio_message_no_holdings(self):
        """Test portfolio message formatting with no holdings."""
        portfolio_data = {
            'status': 'success',
            'total_value_usd': 0.0,
            'total_holdings_count': 0,
            'holdings': [],
            'last_updated': datetime.now().isoformat(),
        }
        
        result = self.statistics_commands._format_portfolio_message(portfolio_data)
        
        self.assertIsInstance(result, str)
        self.assertIn('Current Portfolio Holdings', result)
        self.assertIn('No holdings found', result)
    
    def test_format_portfolio_message_with_holdings(self):
        """Test portfolio message formatting with holdings."""
        portfolio_data = {
            'status': 'success',
            'total_value_usd': 1000.0,
            'total_holdings_count': 2,
            'holdings': [
                {
                    'symbol': 'BTC',
                    'quantity': 0.001,
                    'value_usd': 500.0,
                    'price_usd': 50000.0,
                    'percentage': 50.0,
                    'daily_change_percentage': 2.0,
                },
                {
                    'symbol': 'ETH',
                    'quantity': 0.1,
                    'value_usd': 500.0,
                    'price_usd': 5000.0,
                    'percentage': 50.0,
                    'daily_change_percentage': -1.0,
                }
            ],
            'last_updated': datetime.now().isoformat(),
        }
        
        result = self.statistics_commands._format_portfolio_message(portfolio_data)
        
        self.assertIsInstance(result, str)
        self.assertIn('Current Portfolio Holdings', result)
        self.assertIn('Total Value: $1,000.00', result)
        self.assertIn('BTC: 0.001', result)
        self.assertIn('ETH: 0.1', result)
    
    @patch('binance_trade_bot.telegram.statistics_commands.Update')
    @patch('binance_trade_bot.telegram.statistics_commands.CallbackContext')
    async def test_stats_command_no_data(self, mock_context, mock_update):
        """Test /stats command with no data."""
        # Mock update
        mock_update.effective_user.id = 123456789
        mock_update.message.reply_text = AsyncMock()
        
        # Mock statistics manager to return no data
        self.statistics_manager.get_daily_statistics.return_value = {
            'date': datetime.now().isoformat(),
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
        
        # Execute command
        await self.statistics_commands._stats_command(mock_update, mock_context)
        
        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0]
        self.assertIn('Daily Performance', call_args[0])
        self.assertIn('No trading activity', call_args[0])
    
    @patch('binance_trade_bot.telegram.statistics_commands.Update')
    @patch('binance_trade_bot.telegram.statistics_commands.CallbackContext')
    async def test_stats_command_with_data(self, mock_context, mock_update):
        """Test /stats command with data."""
        # Mock update
        mock_update.effective_user.id = 123456789
        mock_update.message.reply_text = AsyncMock()
        
        # Mock statistics manager to return data
        self.statistics_manager.get_daily_statistics.return_value = {
            'date': datetime.now().isoformat(),
            'total_trades': 10,
            'winning_trades': 6,
            'losing_trades': 4,
            'win_rate': 60.0,
            'total_profit_loss': 100.0,
            'total_profit_loss_percentage': 5.0,
            'average_profit_loss': 10.0,
            'average_win': 20.0,
            'average_loss': -15.0,
            'total_volume': 1000.0,
            'average_trade_size': 100.0,
            'roi': 10.0,
            'sharpe_ratio': 1.5,
            'max_drawdown': -5.0,
            'volatility': 10.0,
            'profit_factor': 2.0,
            'recovery_factor': 1.2,
            'calmar_ratio': 2.0,
        }
        
        # Execute command
        await self.statistics_commands._stats_command(mock_update, mock_context)
        
        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0]
        self.assertIn('Daily Performance', call_args[0])
        self.assertIn('Total Trades: 10', call_args[0])
        self.assertIn('Win Rate: 60.00%', call_args[0])
    
    @patch('binance_trade_bot.telegram.statistics_commands.Update')
    @patch('binance_trade_bot.telegram.statistics_commands.CallbackContext')
    async def test_weekly_command_no_data(self, mock_context, mock_update):
        """Test /weekly command with no data."""
        # Mock update
        mock_update.effective_user.id = 123456789
        mock_update.message.reply_text = AsyncMock()
        
        # Mock statistics manager to return no data
        self.statistics_manager.get_weekly_statistics.return_value = {
            'week_start': datetime.now().isoformat(),
            'week_end': (datetime.now() + timedelta(days=6)).isoformat(),
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
        
        # Execute command
        await self.statistics_commands._weekly_command(mock_update, mock_context)
        
        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0]
        self.assertIn('Weekly Performance', call_args[0])
        self.assertIn('No trading activity', call_args[0])
    
    @patch('binance_trade_bot.telegram.statistics_commands.Update')
    @patch('binance_trade_bot.telegram.statistics_commands.CallbackContext')
    async def test_total_command_no_data(self, mock_context, mock_update):
        """Test /total command with no data."""
        # Mock update
        mock_update.effective_user.id = 123456789
        mock_update.message.reply_text = AsyncMock()
        
        # Mock statistics manager to return no data
        self.statistics_manager.get_total_statistics.return_value = {
            'start_date': datetime.now().isoformat(),
            'end_date': (datetime.now() + timedelta(days=30)).isoformat(),
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
        
        # Execute command
        await self.statistics_commands._total_command(mock_update, mock_context)
        
        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0]
        self.assertIn('Total Performance', call_args[0])
        self.assertIn('No trading activity', call_args[0])
    
    @patch('binance_trade_bot.telegram.statistics_commands.Update')
    @patch('binance_trade_bot.telegram.statistics_commands.CallbackContext')
    async def test_portfolio_command_no_holdings(self, mock_context, mock_update):
        """Test /portfolio command with no holdings."""
        # Mock update
        mock_update.effective_user.id = 123456789
        mock_update.message.reply_text = AsyncMock()
        
        # Mock statistics manager to return no holdings
        self.statistics_manager.get_portfolio_value.return_value = {
            'status': 'success',
            'total_value_usd': 0.0,
            'total_holdings_count': 0,
            'holdings': [],
            'last_updated': datetime.now().isoformat(),
        }
        
        # Execute command
        await self.statistics_commands._portfolio_command(mock_update, mock_context)
        
        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0]
        self.assertIn('Current Portfolio Holdings', call_args[0])
        self.assertIn('No holdings found', call_args[0])
    
    @patch('binance_trade_bot.telegram.statistics_commands.Update')
    @patch('binance_trade_bot.telegram.statistics_commands.CallbackContext')
    async def test_portfolio_command_with_holdings(self, mock_context, mock_update):
        """Test /portfolio command with holdings."""
        # Mock update
        mock_update.effective_user.id = 123456789
        mock_update.message.reply_text = AsyncMock()
        
        # Mock statistics manager to return holdings
        self.statistics_manager.get_portfolio_value.return_value = {
            'status': 'success',
            'total_value_usd': 1000.0,
            'total_holdings_count': 2,
            'holdings': [
                {
                    'symbol': 'BTC',
                    'quantity': 0.001,
                    'value_usd': 500.0,
                    'price_usd': 50000.0,
                    'percentage': 50.0,
                    'daily_change_percentage': 2.0,
                },
                {
                    'symbol': 'ETH',
                    'quantity': 0.1,
                    'value_usd': 500.0,
                    'price_usd': 5000.0,
                    'percentage': 50.0,
                    'daily_change_percentage': -1.0,
                }
            ],
            'last_updated': datetime.now().isoformat(),
        }
        
        # Execute command
        await self.statistics_commands._portfolio_command(mock_update, mock_context)
        
        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0]
        self.assertIn('Current Portfolio Holdings', call_args[0])
        self.assertIn('Total Value: $1,000.00', call_args[0])
        self.assertIn('BTC: 0.001', call_args[0])
        self.assertIn('ETH: 0.1', call_args[0])
    
    @patch('binance_trade_bot.telegram.statistics_commands.Update')
    @patch('binance_trade_bot.telegram.statistics_commands.CallbackContext')
    async def test_stats_command_error(self, mock_context, mock_update):
        """Test /stats command with error."""
        # Mock update
        mock_update.effective_user.id = 123456789
        mock_update.message.reply_text = AsyncMock()
        
        # Mock statistics manager to raise exception
        self.statistics_manager.get_daily_statistics.side_effect = Exception("Database error")
        
        # Execute command
        await self.statistics_commands._stats_command(mock_update, mock_context)
        
        # Verify error message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0]
        self.assertIn('Error retrieving daily statistics', call_args[0])
    
    @patch('binance_trade_bot.telegram.statistics_commands.Update')
    @patch('binance_trade_bot.telegram.statistics_commands.CallbackContext')
    async def test_portfolio_command_error(self, mock_context, mock_update):
        """Test /portfolio command with error."""
        # Mock update
        mock_update.effective_user.id = 123456789
        mock_update.message.reply_text = AsyncMock()
        
        # Mock statistics manager to return error status
        self.statistics_manager.get_portfolio_value.return_value = {
            'status': 'error',
            'message': 'Failed to retrieve portfolio data'
        }
        
        # Execute command
        await self.statistics_commands._portfolio_command(mock_update, mock_context)
        
        # Verify error message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args[0]
        self.assertIn('Error retrieving portfolio data', call_args[0])
    
    def test_register_commands(self):
        """Test command registration."""
        # Mock application
        mock_application = Mock()
        mock_application.add_handler = Mock()
        
        # Register commands
        self.statistics_commands.register_commands(mock_application)
        
        # Verify handlers were added
        self.assertEqual(mock_application.add_handler.call_count, 4)
        
        # Verify correct handlers were added
        call_args_list = mock_application.add_handler.call_args_list
        handler_types = [call[0][0].__class__.__name__ for call in call_args_list]
        self.assertIn('CommandHandler', handler_types)
        
        # Verify correct commands were registered
        command_names = [call[0][0].command for call in call_args_list if hasattr(call[0][0], 'command')]
        expected_commands = ['stats', 'weekly', 'total', 'portfolio']
        for command in expected_commands:
            self.assertIn(command, command_names)


class TestStatisticsCommandsIntegration(unittest.TestCase):
    """
    Integration tests for StatisticsCommands with real dependencies.
    """
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.config = {
            'telegram_token': 'test_token',
            'telegram_admin_id': '123456789'
        }
        
        # Create real instances (mocked where necessary)
        self.database = Mock(spec=Database)
        self.database.db_session.return_value.__enter__ = Mock()
        self.database.db_session.return_value.__exit__ = Mock()
        
        self.logger = Mock(spec=Logger)
        
        # Create real statistics manager
        self.statistics_manager = StatisticsManager(
            config=self.config,
            database=self.database,
            logger=self.logger
        )
        
        # Create statistics commands instance
        self.statistics_commands = StatisticsCommands(
            config=self.config,
            database=self.database,
            logger=self.logger,
            statistics_manager=self.statistics_manager
        )
    
    def test_rate_limiting_integration(self):
        """Test rate limiting integration."""
        user_id = '123456789'
        command = 'stats'
        
        # Test initial state
        self.assertFalse(self.statistics_commands._is_rate_limited(user_id, command))
        
        # Record usage
        self.statistics_commands._record_command_usage(user_id, command)
        
        # Test after one usage
        self.assertFalse(self.statistics_commands._is_rate_limited(user_id, command))
        
        # Record multiple usages
        for _ in range(10):
            self.statistics_commands._record_command_usage(user_id, command)
        
        # Test after rate limiting threshold
        self.assertTrue(self.statistics_commands._is_rate_limited(user_id, command))
    
    def test_statistics_manager_integration(self):
        """Test integration with StatisticsManager."""
        # Mock the statistics manager methods
        self.statistics_manager.get_daily_statistics.return_value = {
            'date': datetime.now().isoformat(),
            'total_trades': 5,
            'winning_trades': 3,
            'losing_trades': 2,
            'win_rate': 60.0,
            'total_profit_loss': 50.0,
            'total_profit_loss_percentage': 2.5,
            'average_profit_loss': 10.0,
            'average_win': 20.0,
            'average_loss': -15.0,
            'total_volume': 500.0,
            'average_trade_size': 100.0,
            'roi': 5.0,
            'sharpe_ratio': 1.2,
            'max_drawdown': -3.0,
            'volatility': 8.0,
            'profit_factor': 1.8,
            'recovery_factor': 1.1,
            'calmar_ratio': 1.5,
        }
        
        # Test formatting
        stats = self.statistics_manager.get_daily_statistics()
        message = self.statistics_commands._format_daily_stats_message(stats)
        
        self.assertIn('Daily Performance', message)
        self.assertIn('Total Trades: 5', message)
        self.assertIn('Win Rate: 60.00%', message)
        self.assertIn('Total P&L: +$50.00', message)


if __name__ == '__main__':
    unittest.main()