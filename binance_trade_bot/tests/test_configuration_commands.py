"""
Unit tests for configuration commands in Telegram bot.
"""

import unittest
from unittest.mock import Mock, patch

from telegram import Update, User, Chat
from telegram.ext import ContextTypes

from binance_trade_bot.telegram.configuration_commands import ConfigurationCommands
from binance_trade_bot.models.telegram_users import TelegramUsers, UserRole, UserStatus
from binance_trade_bot.risk_management.integrated_risk_manager import IntegratedRiskManager
from binance_trade_bot.technical_analysis.wma_engine import WmaEngine
from binance_trade_bot.ai_adapter.base import AIAdapterBase


class TestConfigurationCommands(unittest.TestCase):
    """
    Test cases for ConfigurationCommands class.
    """
    
    def setUp(self):
        """Set up test fixtures before each test method."""
        self.config = {
            'telegram_token': 'test_token',
            'modules': ['technical_analysis', 'ai'],
            'risk_management': {
                'daily_loss_limit': 5.0,
                'emergency_shutdown_threshold': 10.0,
                'max_daily_loss': 1000.0
            },
            'technical_analysis': {
                'wma_periods': {'short': 10, 'long': 30}
            },
            'ai': {
                'enabled': True,
                'parameters': {
                    'learning_rate': 0.01,
                    'batch_size': 32
                }
            }
        }
        
        self.database = Mock()
        self.db_session = Mock()
        self.db_session.__enter__.return_value = self.db_session
        self.db_session.__exit__.return_value = None
        self.database.db_session.return_value = self.db_session
        self.logger = Mock()
        self.risk_manager = Mock(spec=IntegratedRiskManager)
        self.wma_engine = Mock(spec=WmaEngine)
        self.ai_adapter = Mock(spec=AIAdapterBase)

        self.risk_manager.get_risk_configuration.return_value = {
            'loss_limit': 5.0,
            'max_position_size': 10.0,
            'daily_loss_limit': 5.0,
            'emergency_stop_enabled': False
        }
        self.wma_engine.short_period = 10
        self.wma_engine.long_period = 30
        self.wma_engine.price_column = 'close'
        self.ai_adapter.get_model_info.return_value = {
            'model_name': 'TestModel',
            'model_version': '1.0',
            'is_trained': True
        }

        self.config_commands = ConfigurationCommands(
            config=self.config,
            database=self.database,
            logger=self.logger,
            risk_manager=self.risk_manager,
            wma_engine=self.wma_engine,
            ai_adapter=self.ai_adapter
        )
        
        # Mock user
        self.mock_user = Mock(spec=User)
        self.mock_user.id = 12345
        self.mock_user.username = 'testuser'
        self.mock_user.first_name = 'Test'
        self.mock_user.last_name = 'User'
        self.mock_user.language_code = 'en'
        
        # Mock update
        self.mock_update = Mock(spec=Update)
        self.mock_update.effective_user = self.mock_user
        self.mock_update.message = Mock()
        self.mock_update.message.reply_text = Mock()
        
        # Mock context
        self.mock_context = Mock(spec=ContextTypes.DEFAULT_TYPE)
        self.mock_context.args = []
    
    def test_init(self):
        """Test ConfigurationCommands initialization."""
        self.assertEqual(self.config_commands.config, self.config)
        self.assertEqual(self.config_commands.database, self.database)
        self.assertEqual(self.config_commands.logger, self.logger)
        self.assertEqual(self.config_commands.risk_manager, self.risk_manager)
        self.assertEqual(self.config_commands.wma_engine, self.wma_engine)
        self.assertEqual(self.config_commands.ai_adapter, self.ai_adapter)
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_config_command_success(self, mock_get_user):
        """Test /config command successful execution."""
        # Mock user with VIEWER role
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.VIEWER
        mock_user.has_permission.return_value = True
        mock_get_user.return_value = mock_user

        # Execute command
        import asyncio
        asyncio.run(self.config_commands._config_command(self.mock_update, self.mock_context))
        
        # Verify response
        self.mock_update.message.reply_text.assert_called_once()
        call_args = self.mock_update.message.reply_text.call_args[0][0]
        self.assertIn('Current Configuration', call_args)
        self.assertIn('Risk Management', call_args)
        self.assertIn('Technical Analysis', call_args)
        self.assertIn('AI Features', call_args)
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_config_command_user_not_found(self, mock_get_user):
        """Test /config command when user is not found."""
        mock_get_user.return_value = None

        import asyncio
        asyncio.run(self.config_commands._config_command(self.mock_update, self.mock_context))
        
        self.mock_update.message.reply_text.assert_called_once_with("❌ User not found. Please use /start first.")
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_config_command_insufficient_permissions(self, mock_get_user):
        """Test /config command when user has insufficient permissions."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.VIEWER
        mock_user.has_permission.return_value = False
        mock_get_user.return_value = mock_user

        import asyncio
        asyncio.run(self.config_commands._config_command(self.mock_update, self.mock_context))
        
        self.mock_update.message.reply_text.assert_called_once_with("❌ You don't have permission to view configuration.")
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_set_loss_limit_command_success(self, mock_get_user):
        """Test /set_loss_limit command successful execution."""
        # Mock user with TRADER role
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.TRADER
        mock_user.has_permission.return_value = True
        mock_get_user.return_value = mock_user

        # Set context args
        self.mock_context.args = ['5.5']

        # Mock risk manager
        self.risk_manager.set_loss_limit.return_value = {
            "status": "success",
            "message": "Loss limit updated successfully"
        }

        import asyncio
        asyncio.run(self.config_commands._set_loss_limit_command(self.mock_update, self.mock_context))

        # Verify risk manager was called
        self.risk_manager.set_loss_limit.assert_called_once_with(5.5)

        # Verify response
        self.mock_update.message.reply_text.assert_called_once()
        call_args = self.mock_update.message.reply_text.call_args[0][0]
        self.assertIn('Loss limit updated', call_args)
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_set_loss_limit_command_invalid_percentage(self, mock_get_user):
        """Test /set_loss_limit command with invalid percentage."""
        # Mock user with TRADER role
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.TRADER
        mock_user.has_permission.return_value = True
        mock_get_user.return_value = mock_user

        # Set invalid context args
        self.mock_context.args = ['invalid']

        import asyncio
        asyncio.run(self.config_commands._set_loss_limit_command(self.mock_update, self.mock_context))

        self.mock_update.message.reply_text.assert_called_once_with("❌ Invalid loss limit. Please provide a valid number.")
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_set_loss_limit_command_insufficient_permissions(self, mock_get_user):
        """Test /set_loss_limit command when user has insufficient permissions."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.VIEWER
        mock_user.has_permission.return_value = False
        mock_get_user.return_value = mock_user

        import asyncio
        asyncio.run(self.config_commands._set_loss_limit_command(self.mock_update, self.mock_context))
        
        self.mock_update.message.reply_text.assert_called_once_with("❌ You don't have permission to modify risk parameters.")
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_set_wma_periods_command_success(self, mock_get_user):
        """Test /set_wma_periods command successful execution."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.TRADER
        mock_user.has_permission.return_value = True
        mock_get_user.return_value = mock_user

        self.mock_context.args = ['15', '45']

        import asyncio
        asyncio.run(self.config_commands._set_wma_periods_command(self.mock_update, self.mock_context))

        self.assertEqual(self.wma_engine.short_period, 15)
        self.assertEqual(self.wma_engine.long_period, 45)

        self.mock_update.message.reply_text.assert_called_once()
        call_args = self.mock_update.message.reply_text.call_args[0][0]
        self.assertIn('WMA periods updated to', call_args)
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_set_wma_periods_command_invalid_periods(self, mock_get_user):
        """Test /set_wma_periods command with invalid periods."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.TRADER
        mock_user.has_permission.return_value = True
        mock_get_user.return_value = mock_user

        self.mock_context.args = ['invalid', '45']

        import asyncio
        asyncio.run(self.config_commands._set_wma_periods_command(self.mock_update, self.mock_context))

        self.mock_update.message.reply_text.assert_called_once_with("❌ Invalid period values. Please provide valid integers.")
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_set_wma_periods_command_insufficient_permissions(self, mock_get_user):
        """Test /set_wma_periods command when user has insufficient permissions."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.VIEWER
        mock_user.has_permission.return_value = False
        mock_get_user.return_value = mock_user
        
        import asyncio
        asyncio.run(self.config_commands._set_wma_periods_command(self.mock_update, self.mock_context))
        
        self.mock_update.message.reply_text.assert_called_once_with("❌ You don't have permission to modify technical analysis settings.")
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_toggle_ai_command_success(self, mock_get_user):
        """Test /toggle_ai command successful execution."""
        # Mock user with TRADER role
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.TRADER
        mock_user.has_permission.return_value = True
        mock_get_user.return_value = mock_user
        
        import asyncio
        asyncio.run(self.config_commands._toggle_ai_command(self.mock_update, self.mock_context))

        # Verify AI was toggled
        self.assertEqual(self.config['ai_enabled'], False)

        # Verify response
        self.mock_update.message.reply_text.assert_called_once()
        call_args = self.mock_update.message.reply_text.call_args[0][0]
        self.assertIn('AI features have been', call_args)
        self.assertIn('DISABLED', call_args)
    
    @patch('binance_trade_bot.telegram.configuration_commands.ConfigurationCommands._get_user_from_db')
    def test_toggle_ai_command_insufficient_permissions(self, mock_get_user):
        """Test /toggle_ai command when user has insufficient permissions."""
        mock_user = Mock(spec=TelegramUsers)
        mock_user.role = UserRole.VIEWER
        mock_user.has_permission.return_value = False
        mock_get_user.return_value = mock_user
        
        import asyncio
        asyncio.run(self.config_commands._toggle_ai_command(self.mock_update, self.mock_context))
        
        self.mock_update.message.reply_text.assert_called_once_with("❌ You don't have permission to control AI features.")
    
    def test_get_user_from_db_success(self):
        """Test _get_user_from_db method successful execution."""
        # Mock user
        mock_user = Mock(spec=TelegramUsers)
        mock_user.telegram_id = '12345'
        
        # Mock database session
        with self.database.db_session() as session:
            session.query.return_value.filter.return_value.first.return_value = mock_user
        
        result = self.config_commands._get_user_from_db('12345')
        
        self.assertEqual(result, mock_user)
        session.query.assert_called_once()
        session.query.return_value.filter.assert_called_once()
    
    def test_get_user_from_db_not_found(self):
        """Test _get_user_from_db method when user is not found."""
        # Mock database session
        with self.database.db_session() as session:
            session.query.return_value.filter.return_value.first.return_value = None
        
        result = self.config_commands._get_user_from_db('12345')
        
        self.assertIsNone(result)
    
    def test_format_config_text(self):
        """Test _format_config_text method."""
        config_text = self.config_commands._format_config_text()
        
        self.assertIn('Current Configuration', config_text)
        self.assertIn('Risk Management', config_text)
        self.assertIn('Technical Analysis', config_text)
        self.assertIn('AI Features', config_text)
        self.assertIn('Daily Loss Limit: 5.0%', config_text)
        self.assertIn('WMA Short Period: 10', config_text)
        self.assertIn('WMA Long Period: 30', config_text)
        self.assertIn('AI Enabled: True', config_text)


if __name__ == '__main__':
    unittest.main()