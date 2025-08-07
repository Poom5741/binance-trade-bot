"""
Concrete implementation of Telegram bot for trading notifications and commands.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackContext,
)
from telegram.error import TelegramError, BadRequest, Forbidden

from .base import TelegramBase
from .trading_control import TradingControlCommands
from .statistics_commands import StatisticsCommands
from .configuration_commands import ConfigurationCommands
from ..database import Database
from ..models.telegram_users import TelegramUsers, UserRole, UserStatus
from ..logger import Logger
from ..risk_management.integrated_risk_manager import IntegratedRiskManager
from ..auto_trader import AutoTrader


class TelegramBot(TelegramBase):
    """
    Concrete implementation of Telegram bot for trading notifications and commands.
    
    This class provides a full-featured Telegram bot with authentication,
    authorization, rate limiting, and command handling capabilities.
    """
    
    # Conversation states
    AUTHENTICATING, AWAITING_CODE, AWAITING_PASSWORD = range(3)
    
    # Command rate limiting (commands per minute)
    COMMAND_RATE_LIMITS = {
        'start': 5,
        'help': 10,
        'balance': 10,
        'status': 10,
        'trades': 5,
        'settings': 5,
        'admin': 2,
        'stop': 5,
        'resume': 5,
        'shutdown': 2,
        'stats': 5,
        'weekly': 5,
        'total': 3,
        'portfolio': 10,
        'config': 5,
        'set_loss_limit': 3,
        'set_wma_periods': 3,
        'toggle_ai': 2,
    }
    
    def __init__(self, config: Dict[str, Any], database: Database, logger: Logger,
                 risk_manager: IntegratedRiskManager = None, auto_trader: AutoTrader = None):
        """
        Initialize the Telegram bot with configuration, database, logger, and trading components.
        
        @param {dict} config - Configuration dictionary containing telegram settings
        @param {Database} database - Database instance for user management
        @param {Logger} logger - Logger instance for logging operations
        @param {IntegratedRiskManager} risk_manager - Risk management instance (optional)
        @param {AutoTrader} auto_trader - AutoTrader instance (optional)
        """
        super().__init__(config)
        self.database = database
        self.logger = logger
        self.application = None
        self.bot = None
        self.user_command_counts = {}  # Track command usage for rate limiting
        self.user_sessions = {}  # Track user authentication sessions
        
        # Initialize trading control commands if dependencies are available
        self.trading_control = None
        if risk_manager and auto_trader:
            self.trading_control = TradingControlCommands(
                config=config,
                database=database,
                logger=logger,
                risk_manager=risk_manager,
                auto_trader=auto_trader
            )
            self.logger.info("Trading control commands initialized")
        
        # Initialize statistics commands
        self.statistics_commands = None
        try:
            from ..statistics.manager import StatisticsManager
            statistics_manager = StatisticsManager(config, database, logger)
            self.statistics_commands = StatisticsCommands(
                config=config,
                database=database,
                logger=logger,
                statistics_manager=statistics_manager
            )
            self.logger.info("Statistics commands initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize statistics commands: {e}")
        
        # Initialize configuration commands
        self.configuration_commands = None
        try:
            from ..technical_analysis.wma_engine import WmaEngine
            from ..ai_adapter.base import AIAdapterBase
            wma_engine = WmaEngine(config) if 'technical_analysis' in config.get('modules', []) else None
            ai_adapter = AIAdapterBase(config) if 'ai' in config.get('modules', []) else None
            
            self.configuration_commands = ConfigurationCommands(
                config=config,
                database=database,
                logger=logger,
                risk_manager=risk_manager,
                wma_engine=wma_engine,
                ai_adapter=ai_adapter
            )
            self.logger.info("Configuration commands initialized")
        except Exception as e:
            self.logger.warning(f"Failed to initialize configuration commands: {e}")
        
        # Extract telegram configuration
        self.telegram_token = config.get('telegram_token')
        self.telegram_webhook_url = config.get('telegram_webhook_url')
        self.telegram_admin_id = config.get('telegram_admin_id')
        
        if not self.telegram_token:
            raise ValueError("Telegram token is required in configuration")
    
    async def send_message(self, chat_id: str, text: str, parse_mode: str = None) -> bool:
        """
        Send a message to a specified chat.
        
        @param {str} chat_id - Unique identifier for the target chat
        @param {str} text - Text of the message to be sent
        @param {str} parse_mode - Optional. Mode for parsing entities (HTML/Markdown)
        @returns {bool} True if message was sent successfully, False otherwise
        """
        try:
            if not self.bot:
                self.logger.error("Bot not initialized")
                return False
            
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
            return True
            
        except Forbidden:
            self.logger.warning(f"User {chat_id} has blocked the bot")
            return False
        except BadRequest as e:
            self.logger.error(f"Bad request to send message to {chat_id}: {e}")
            return False
        except TelegramError as e:
            self.logger.error(f"Telegram error sending message to {chat_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error sending message to {chat_id}: {e}")
            return False
    
    async def send_trade_notification(self, trade_data: Dict[str, Any]) -> bool:
        """
        Send a trade notification message.
        
        @param {dict} trade_data - Dictionary containing trade information
        @returns {bool} True if notification was sent successfully, False otherwise
        """
        try:
            # Get all active users with notifications enabled
            with self.database.db_session() as session:
                users = session.query(TelegramUsers).filter(
                    TelegramUsers.status == UserStatus.ACTIVE
                ).all()
            
            message = self._format_trade_message(trade_data)
            success_count = 0
            
            for user in users:
                if await self.send_message(user.telegram_id, message):
                    success_count += 1
            
            self.logger.info(f"Sent trade notification to {success_count}/{len(users)} users")
            return success_count > 0
            
        except Exception as e:
            self.logger.error(f"Error sending trade notification: {e}")
            return False
    
    async def send_alert(self, alert_type: str, message: str, details: Dict[str, Any] = None) -> bool:
        """
        Send an alert message based on alert type.
        
        @param {str} alert_type - Type of alert (e.g., 'error', 'warning', 'info')
        @param {str} message - Alert message
        @param {dict} details - Optional additional details about the alert
        @returns {bool} True if alert was sent successfully, False otherwise
        """
        try:
            # Format alert message
            alert_message = f"🚨 *{alert_type.upper()} ALERT* 🚨\n\n"
            alert_message += f"*Message:* {message}\n"
            
            if details:
                alert_message += "\n*Details:*\n"
                for key, value in details.items():
                    alert_message += f"• {key}: {value}\n"
            
            # Send to admin if configured
            if self.telegram_admin_id:
                await self.send_message(self.telegram_admin_id, alert_message, parse_mode='Markdown')
            
            # Also send to all active admin users
            with self.database.db_session() as session:
                admin_users = session.query(TelegramUsers).filter(
                    TelegramUsers.role == UserRole.ADMIN,
                    TelegramUsers.status == UserStatus.ACTIVE
                ).all()
            
            for user in admin_users:
                await self.send_message(user.telegram_id, alert_message, parse_mode='Markdown')
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error sending alert: {e}")
            return False
    
    def _format_trade_message(self, trade_data: Dict[str, Any]) -> str:
        """
        Format trade data into a readable message.
        
        @param {dict} trade_data - Dictionary containing trade information
        @returns {str} Formatted trade message
        """
        message = "🤖 *Trade Notification* 🤖\n\n"
        
        if trade_data.get('action'):
            message += f"*Action:* {trade_data['action'].upper()}\n"
        
        if trade_data.get('pair'):
            message += f"*Pair:* {trade_data['pair']}\n"
        
        if trade_data.get('price'):
            message += f"*Price:* {trade_data['price']}\n"
        
        if trade_data.get('amount'):
            message += f"*Amount:* {trade_data['amount']}\n"
        
        if trade_data.get('timestamp'):
            message += f"*Time:* {datetime.fromtimestamp(trade_data['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if trade_data.get('status'):
            message += f"*Status:* {trade_data['status']}\n"
        
        if trade_data.get('message'):
            message += f"\n*Note:* {trade_data['message']}\n"
        
        return message
    
    def _is_rate_limited(self, user_id: str, command: str) -> bool:
        """
        Check if user is rate limited for a specific command.
        
        @param {str} user_id - Telegram user ID
        @param {str} command - Command name
        @returns {bool} True if user is rate limited, False otherwise
        """
        if command not in self.COMMAND_RATE_LIMITS:
            return False
        
        limit = self.COMMAND_RATE_LIMITS[command]
        now = datetime.utcnow()
        
        # Initialize user command tracking if not exists
        if user_id not in self.user_command_counts:
            self.user_command_counts[user_id] = {}
        
        # Initialize command tracking if not exists
        if command not in self.user_command_counts[user_id]:
            self.user_command_counts[user_id][command] = []
        
        # Remove old command calls (older than 1 minute)
        minute_ago = now - timedelta(minutes=1)
        self.user_command_counts[user_id][command] = [
            timestamp for timestamp in self.user_command_counts[user_id][command]
            if timestamp > minute_ago
        ]
        
        # Check if limit exceeded
        return len(self.user_command_counts[user_id][command]) >= limit
    
    def _record_command_usage(self, user_id: str, command: str):
        """
        Record command usage for rate limiting.
        
        @param {str} user_id - Telegram user ID
        @param {str} command - Command name
        """
        now = datetime.utcnow()
        
        if user_id not in self.user_command_counts:
            self.user_command_counts[user_id] = {}
        
        if command not in self.user_command_counts[user_id]:
            self.user_command_counts[user_id][command] = []
        
        self.user_command_counts[user_id][command].append(now)
    
    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'start'):
            await update.message.reply_text("⚠️ Too many start commands. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'start')
        
        try:
            # Check if user exists in database
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                # Create new user
                db_user = TelegramUsers(
                    telegram_id=str(user.id),
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    language_code=user.language_code
                )
                session.add(db_user)
                session.commit()
                
                await update.message.reply_text(
                    "👋 Welcome to the Binance Trade Bot!\n\n"
                    "Please use /help to see available commands.\n\n"
                    "Your account has been created with default Viewer role."
                )
            else:
                # Update user info
                db_user.username = user.username
                db_user.first_name = user.first_name
                db_user.last_name = user.last_name
                db_user.language_code = user.language_code
                db_user.update_last_login()
                session.commit()
                
                await update.message.reply_text(
                    f"👋 Welcome back, {user.first_name}!\n\n"
                    f"Your role: {db_user.role.value}\n"
                    f"Status: {db_user.status.value}\n\n"
                    "Use /help to see available commands."
                )
                
        except Exception as e:
            self.logger.error(f"Error in /start command: {e}")
            await update.message.reply_text("❌ An error occurred. Please try again later.")
    
    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'help'):
            await update.message.reply_text("⚠️ Too many help requests. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'help')
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start first.")
                return
            
            help_text = self._get_help_text(db_user)
            await update.message.reply_text(help_text, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Error in /help command: {e}")
            await update.message.reply_text("❌ An error occurred. Please try again later.")
    
    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command for trading control."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'status'):
            await update.message.reply_text("⚠️ Too many status requests. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'status')
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start first.")
                return
            
            # Check user permissions
            if not db_user.has_permission(UserRole.VIEWER):
                await update.message.reply_text("❌ You don't have permission to view status.")
                return
            
            # Use trading control if available, otherwise show basic status
            if self.trading_control:
                status_text = await self.trading_control._generate_status_message()
            else:
                status_text = self._get_basic_status_text()
            
            await update.message.reply_text(status_text, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Error in /status command: {e}")
            await update.message.reply_text("❌ An error occurred while fetching status.")
    
    async def _stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command for trading control."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'stop'):
            await update.message.reply_text("⚠️ Too many stop requests. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'stop')
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start first.")
                return
            
            # Check user permissions
            if not db_user.has_permission(UserRole.TRADER):
                await update.message.reply_text("❌ You don't have permission to stop trading.")
                return
            
            # Use trading control if available
            if self.trading_control:
                await self.trading_control._stop_command(update, context)
            else:
                await update.message.reply_text("⚠️ Trading control not available. Please check system configuration.")
            
        except Exception as e:
            self.logger.error(f"Error in /stop command: {e}")
            await update.message.reply_text("❌ An error occurred while stopping trading.")
    
    async def _resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command for trading control."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'resume'):
            await update.message.reply_text("⚠️ Too many resume requests. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'resume')
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start first.")
                return
            
            # Check user permissions
            if not db_user.has_permission(UserRole.TRADER):
                await update.message.reply_text("❌ You don't have permission to resume trading.")
                return
            
            # Use trading control if available
            if self.trading_control:
                await self.trading_control._resume_command(update, context)
            else:
                await update.message.reply_text("⚠️ Trading control not available. Please check system configuration.")
            
        except Exception as e:
            self.logger.error(f"Error in /resume command: {e}")
            await update.message.reply_text("❌ An error occurred while resuming trading.")
    
    async def _shutdown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /shutdown command for trading control."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'shutdown'):
            await update.message.reply_text("⚠️ Too many shutdown requests. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'shutdown')
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start first.")
                return
            
            # Check user permissions
            if not db_user.has_permission(UserRole.ADMIN):
                await update.message.reply_text("❌ You don't have permission to initiate shutdown.")
                return
            
            # Use trading control if available
            if self.trading_control:
                await self.trading_control._shutdown_command(update, context)
            else:
                await update.message.reply_text("⚠️ Trading control not available. Please check system configuration.")
            
        except Exception as e:
            self.logger.error(f"Error in /shutdown command: {e}")
            await update.message.reply_text("❌ An error occurred while initiating shutdown.")
    
    async def _config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /config command for displaying current settings."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'config'):
            await update.message.reply_text("⚠️ Too many config requests. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'config')
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start first.")
                return
            
            # Check user permissions
            if not db_user.has_permission(UserRole.VIEWER):
                await update.message.reply_text("❌ You don't have permission to view configuration.")
                return
            
            # Use configuration commands if available
            if self.configuration_commands:
                await self.configuration_commands._config_command(update, context)
            else:
                await update.message.reply_text("⚠️ Configuration commands not available. Please check system configuration.")
            
        except Exception as e:
            self.logger.error(f"Error in /config command: {e}")
            await update.message.reply_text("❌ An error occurred while fetching configuration.")
    
    async def _set_loss_limit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /set_loss_limit command for updating risk parameters."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'set_loss_limit'):
            await update.message.reply_text("⚠️ Too many loss limit updates. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'set_loss_limit')
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start first.")
                return
            
            # Check user permissions
            if not db_user.has_permission(UserRole.TRADER):
                await update.message.reply_text("❌ You don't have permission to modify risk parameters.")
                return
            
            # Use configuration commands if available
            if self.configuration_commands:
                await self.configuration_commands._set_loss_limit_command(update, context)
            else:
                await update.message.reply_text("⚠️ Configuration commands not available. Please check system configuration.")
            
        except Exception as e:
            self.logger.error(f"Error in /set_loss_limit command: {e}")
            await update.message.reply_text("❌ An error occurred while updating loss limit.")
    
    async def _set_wma_periods_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /set_wma_periods command for updating technical analysis configuration."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'set_wma_periods'):
            await update.message.reply_text("⚠️ Too many WMA period updates. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'set_wma_periods')
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start first.")
                return
            
            # Check user permissions
            if not db_user.has_permission(UserRole.TRADER):
                await update.message.reply_text("❌ You don't have permission to modify technical analysis settings.")
                return
            
            # Use configuration commands if available
            if self.configuration_commands:
                await self.configuration_commands._set_wma_periods_command(update, context)
            else:
                await update.message.reply_text("⚠️ Configuration commands not available. Please check system configuration.")
            
        except Exception as e:
            self.logger.error(f"Error in /set_wma_periods command: {e}")
            await update.message.reply_text("❌ An error occurred while updating WMA periods.")
    
    async def _toggle_ai_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /toggle_ai command for controlling AI features."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'toggle_ai'):
            await update.message.reply_text("⚠️ Too many AI feature toggles. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'toggle_ai')
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start first.")
                return
            
            # Check user permissions
            if not db_user.has_permission(UserRole.TRADER):
                await update.message.reply_text("❌ You don't have permission to control AI features.")
                return
            
            # Use configuration commands if available
            if self.configuration_commands:
                await self.configuration_commands._toggle_ai_command(update, context)
            else:
                await update.message.reply_text("⚠️ Configuration commands not available. Please check system configuration.")
            
        except Exception as e:
            self.logger.error(f"Error in /toggle_ai command: {e}")
            await update.message.reply_text("❌ An error occurred while toggling AI features.")
    
    def _get_help_text(self, user: TelegramUsers) -> str:
        """Get help text based on user role."""
        base_help = """
*Available Commands:*

• `/start` - Start the bot and create your account
• `/help` - Show this help message
• `/balance` - Show current trading balance
• `/status` - Show bot status
• `/trades` - Show recent trades
• `/settings` - Configure notification preferences
• `/menu` - Show interactive menu

*Trading Control:*
• `/status` - Show current trading status and risk metrics
• `/stop` - Halt all trading activities
• `/resume` - Resume trading after stop
• `/shutdown` - Emergency shutdown with confirmation (Admin only)

*Configuration Management:*
• `/config` - Display current bot settings and configuration
• `/set_loss_limit <percentage>` - Update loss limit percentage (Trader+)
• `/set_wma_periods <short> <long>` - Update WMA periods for technical analysis (Trader+)
• `/toggle_ai` - Enable/disable AI features (Trader+)

*Statistics & Reporting:*
• `/stats` - Show daily performance statistics
• `/weekly` - Show weekly performance statistics
• `/total` - Show total performance statistics
• `/portfolio` - Show current portfolio holdings

*General:*
• Use `/menu` for interactive commands
• All commands are case-insensitive
• Contact admin for account upgrades
        """
        
        if user.role == UserRole.ADMIN:
            admin_help = base_help + """

*Admin Commands:*
• `/admin` - Admin panel
• `/users` - Manage users
• `/broadcast` - Send message to all users
• `/logs` - View system logs
• `/restart` - Restart the bot

*Admin Features:*
• Emergency shutdown requires confirmation dialog
• Shutdown notifications sent to all users
• Full system control and monitoring capabilities
            """
            return admin_help
        
        return base_help
    
    async def _menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command to show interactive menu."""
        user = update.effective_user
        
        # Check rate limiting
        if self._is_rate_limited(str(user.id), 'menu'):
            await update.message.reply_text("⚠️ Too many menu requests. Please wait a moment.")
            return
        
        self._record_command_usage(str(user.id), 'menu')
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await update.message.reply_text("❌ User not found. Please use /start first.")
                return
            
            keyboard = self._get_menu_keyboard(db_user)
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🤖 *Main Menu* 🤖\n\nChoose an option:",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            self.logger.error(f"Error in /menu command: {e}")
            await update.message.reply_text("❌ An error occurred. Please try again later.")
    
    def _get_menu_keyboard(self, user: TelegramUsers) -> List[List[InlineKeyboardButton]]:
        """Get keyboard markup based on user role."""
        keyboard = [
            [InlineKeyboardButton("💰 Balance", callback_data='balance')],
            [InlineKeyboardButton("📈 Status", callback_data='status')],
            [InlineKeyboardButton("💼 Recent Trades", callback_data='trades')],
            [InlineKeyboardButton("📊 Daily Stats", callback_data='stats')],
            [InlineKeyboardButton("📊 Weekly Stats", callback_data='weekly')],
            [InlineKeyboardButton("📊 Total Stats", callback_data='total')],
            [InlineKeyboardButton("💼 Portfolio", callback_data='portfolio')],
            [InlineKeyboardButton("⚙️ Settings", callback_data='settings')],
        ]
        
        if user.role == UserRole.ADMIN:
            keyboard.extend([
                [InlineKeyboardButton("👥 Admin Panel", callback_data='admin')],
                [InlineKeyboardButton("📢 Broadcast", callback_data='broadcast')],
            ])
        
        keyboard.append([InlineKeyboardButton("❌ Close", callback_data='close')])
        return keyboard
    
    async def _handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks."""
        query = update.callback_query
        user = query.from_user
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await query.answer("❌ User not found. Please use /start first.")
                return
            
            # Handle different callback data
            if query.data == 'close':
                await query.answer()
                await query.message.delete()
                return
            
            if query.data == 'balance':
                await query.answer()
                await self._show_balance(query, db_user)
                return
            
            if query.data == 'status':
                await query.answer()
                await self._show_status(query, db_user)
                return
            
            if query.data == 'trades':
                await query.answer()
                await self._show_trades(query, db_user)
                return
            
            if query.data == 'stats':
                await query.answer()
                if self.statistics_commands:
                    await self.statistics_commands._stats_command(query, None)
                else:
                    await query.message.edit_text("❌ Statistics not available")
                return
            
            if query.data == 'weekly':
                await query.answer()
                if self.statistics_commands:
                    await self.statistics_commands._weekly_command(query, None)
                else:
                    await query.message.edit_text("❌ Statistics not available")
                return
            
            if query.data == 'total':
                await query.answer()
                if self.statistics_commands:
                    await self.statistics_commands._total_command(query, None)
                else:
                    await query.message.edit_text("❌ Statistics not available")
                return
            
            if query.data == 'portfolio':
                await query.answer()
                if self.statistics_commands:
                    await self.statistics_commands._portfolio_command(query, None)
                else:
                    await query.message.edit_text("❌ Statistics not available")
                return
            
            if query.data == 'settings':
                await query.answer()
                await self._show_settings(query, db_user)
                return
            
            if query.data == 'admin' and db_user.role == UserRole.ADMIN:
                await query.answer()
                await self._show_admin_panel(query, db_user)
                return
            
            if query.data == 'broadcast' and db_user.role == UserRole.ADMIN:
                await query.answer()
                await self._show_broadcast(query, db_user)
                return
            
            if query.data in ['shutdown_confirm', 'shutdown_cancel'] and self.trading_control:
                await query.answer()
                await self.trading_control._handle_shutdown_callback(update, context)
                return
            
            await query.answer("❌ Unknown command")
            
        except Exception as e:
            self.logger.error(f"Error handling callback query: {e}")
            await query.answer("❌ An error occurred")
    
    async def _show_balance(self, query, user: TelegramUsers):
        """Show user balance information."""
        try:
            # This would integrate with the actual trading system
            balance_text = """
💰 *Balance Information* 💰

*Current Balance:*
• BTC: 0.00000000
• ETH: 0.00000000
• USDT: 0.00

*Total Value:* $0.00

*Note:* Balance integration coming soon!
            """
            await query.message.edit_text(balance_text, parse_mode='Markdown')
        except Exception as e:
            self.logger.error(f"Error showing balance: {e}")
            await query.message.edit_text("❌ Error retrieving balance")
    
    async def _show_status(self, query, user: TelegramUsers):
        """Show bot status."""
        try:
            status_text = """
📊 *Bot Status* 📊

*System Status:* 🟢 Online
*Uptime:* 24h 30m
*Active Trades:* 0
*Total Trades:* 0

*Last Update:* Just now

*Note:* Detailed status integration coming soon!
            """
            await query.message.edit_text(status_text, parse_mode='Markdown')
        except Exception as e:
            self.logger.error(f"Error showing status: {e}")
            await query.message.edit_text("❌ Error retrieving status")
    
    async def _show_trades(self, query, user: TelegramUsers):
        """Show recent trades."""
        try:
            trades_text = """
💼 *Recent Trades* 💼

No recent trades found.

*Note:* Trade history integration coming soon!
            """
            await query.message.edit_text(trades_text, parse_mode='Markdown')
        except Exception as e:
            self.logger.error(f"Error showing trades: {e}")
            await query.message.edit_text("❌ Error retrieving trades")
    
    async def _show_settings(self, query, user: TelegramUsers):
        """Show user settings."""
        try:
            settings_keyboard = [
                [InlineKeyboardButton("🔔 Notifications", callback_data='notifications')],
                [InlineKeyboardButton("🌐 Language", callback_data='language')],
                [InlineKeyboardButton("🔄 Back to Menu", callback_data='menu')],
            ]
            settings_markup = InlineKeyboardMarkup(settings_keyboard)
            
            settings_text = f"""
⚙️ *Settings* ⚙️

*User:* {user.first_name} {user.last_name or ''}
*Role:* {user.role.value}
*Status:* {user.status.value}

*Notification Settings:* Enabled
*Language:* English

Choose an option to configure:
            """
            
            await query.message.edit_text(settings_text, reply_markup=settings_markup, parse_mode='Markdown')
        except Exception as e:
            self.logger.error(f"Error showing settings: {e}")
            await query.message.edit_text("❌ Error retrieving settings")
    
    async def _show_admin_panel(self, query, user: TelegramUsers):
        """Show admin panel."""
        try:
            admin_keyboard = [
                [InlineKeyboardButton("👥 Users", callback_data='users')],
                [InlineKeyboardButton("📊 Statistics", callback_data='statistics')],
                [InlineKeyboardButton("🔧 System", callback_data='system')],
                [InlineKeyboardButton("🔄 Back to Menu", callback_data='menu')],
            ]
            admin_markup = InlineKeyboardMarkup(admin_keyboard)
            
            admin_text = f"""
👑 *Admin Panel* 👑

*Admin:* {user.first_name} {user.last_name or ''}
*Last Login:* {user.last_login_at.strftime('%Y-%m-%d %H:%M:%S') if user.last_login_at else 'Never'}

Choose an admin option:
            """
            
            await query.message.edit_text(admin_text, reply_markup=admin_markup, parse_mode='Markdown')
        except Exception as e:
            self.logger.error(f"Error showing admin panel: {e}")
            await query.message.edit_text("❌ Error accessing admin panel")
    
    async def _show_broadcast(self, query, user: TelegramUsers):
        """Show broadcast interface."""
        try:
            broadcast_text = """
📢 *Broadcast Message* 📢

Send a message to all users:

Example:
/broadcast Hello everyone! System maintenance at 2 AM UTC.

*Note:* This feature is for admin users only.
            """
            await query.message.edit_text(broadcast_text, parse_mode='Markdown')
        except Exception as e:
            self.logger.error(f"Error showing broadcast: {e}")
            await query.message.edit_text("❌ Error accessing broadcast")
    
    def _get_basic_status_text(self) -> str:
        """Get basic status text when trading control is not available."""
        return """
📊 *Basic Bot Status* 📊

*System Status:* 🟢 Online
*Uptime:* 24h 30m
*Active Trades:* 0
*Total Trades:* 0

*Last Update:* Just now

*Note:* Enhanced trading control not available. Please check system configuration.
        """
    
    async def _unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle unknown commands."""
        await update.message.reply_text(
            "❌ Unknown command. Use /help to see available commands."
        )
    
    async def start_bot(self) -> bool:
        """
        Start the telegram bot and begin listening for messages.
        
        @returns {bool} True if bot started successfully, False otherwise
        """
        try:
            if not self.telegram_token:
                self.logger.error("Telegram token not configured")
                return False
            
            # Create application
            self.application = Application.builder().token(self.telegram_token).build()
            self.bot = self.application.bot
            
            # Add handlers
            self.application.add_handler(CommandHandler("start", self._start_command))
            self.application.add_handler(CommandHandler("help", self._help_command))
            self.application.add_handler(CommandHandler("menu", self._menu_command))
            
            # Add trading control commands if available
            if self.trading_control:
                self.application.add_handler(CommandHandler("status", self._status_command))
                self.application.add_handler(CommandHandler("stop", self._stop_command))
                self.application.add_handler(CommandHandler("resume", self._resume_command))
                self.application.add_handler(CommandHandler("shutdown", self._shutdown_command))
            
            # Add configuration commands if available
            if self.configuration_commands:
                self.application.add_handler(CommandHandler("config", self._config_command))
                self.application.add_handler(CommandHandler("set_loss_limit", self._set_loss_limit_command))
                self.application.add_handler(CommandHandler("set_wma_periods", self._set_wma_periods_command))
                self.application.add_handler(CommandHandler("toggle_ai", self._toggle_ai_command))
            
            # Add statistics commands if available
            if self.statistics_commands:
                self.statistics_commands.register_commands(self.application)
            
            self.application.add_handler(CallbackQueryHandler(self._handle_callback_query))
            self.application.add_handler(MessageHandler(filters.COMMAND & ~filters.PREFIXED, self._unknown_command))
            
            # Start polling
            self.logger.info("Starting Telegram bot...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            self.logger.info("Telegram bot started successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error starting Telegram bot: {e}")
            return False
    
    async def stop_bot(self) -> bool:
        """
        Stop the telegram bot and clean up resources.
        
        @returns {bool} True if bot stopped successfully, False otherwise
        """
        try:
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                self.logger.info("Telegram bot stopped successfully")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error stopping Telegram bot: {e}")
            return False