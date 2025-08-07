"""
Trading control commands for Telegram bot interface.

This module provides trading control commands including status display,
stop/resume functionality, and shutdown procedures with proper
integration with AutoTrader, RiskManager, and database models.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import CallbackContext, ContextTypes
except Exception:  # pragma: no cover
    InlineKeyboardButton = InlineKeyboardMarkup = Update = object  # type: ignore
    CallbackContext = ContextTypes = object  # type: ignore

from .base import TelegramBase
from ..database import Database
from ..models.telegram_users import TelegramUsers, UserRole, UserStatus
from ..risk_management.integrated_risk_manager import IntegratedRiskManager
from ..risk_management.emergency_shutdown_manager import EmergencyShutdownManager
from ..auto_trader import AutoTrader
from ..logger import Logger


class TradingControlCommands(TelegramBase):
    """
    Trading control commands implementation for Telegram bot.
    
    This class provides comprehensive trading control functionality including:
    - Current trading status display
    - Trading stop/resume operations
    - Emergency shutdown with confirmation dialogs
    - Trade execution notifications
    """
    
    # Conversation states for shutdown confirmation
    SHUTDOWN_CONFIRMATION, SHUTDOWN_REASON = range(2)
    
    def __init__(self, config: Dict[str, Any], database: Database, 
                 logger: Logger, risk_manager: IntegratedRiskManager,
                 auto_trader: AutoTrader):
        """
        Initialize trading control commands.
        
        @param {dict} config - Configuration dictionary
        @param {Database} database - Database instance
        @param {Logger} logger - Logger instance
        @param {IntegratedRiskManager} risk_manager - Risk management instance
        @param {AutoTrader} auto_trader - AutoTrader instance
        """
        super().__init__(config)
        self.database = database
        self.logger = logger
        self.risk_manager = risk_manager
        self.auto_trader = auto_trader
        
        # Track trading state
        self.trading_enabled = True
        self.shutdown_requested = False
        self.shutdown_reason = None
        
        # Command rate limiting
        self.command_rate_limits = {
            'status': 10,
            'stop': 5,
            'resume': 5,
            'shutdown': 2,
        }
        self.user_command_counts = {}
        
        # Initialize logger
        self.log = logging.getLogger(__name__)
        self.log.info("Trading control commands initialized")

        # Register for trade execution notifications if possible
        if hasattr(self.auto_trader, 'manager') and \
                hasattr(self.auto_trader.manager, 'register_trade_notifier'):
            self.auto_trader.manager.register_trade_notifier(self._notify_trade)
    
    async def send_message(self, chat_id: str, text: str, parse_mode: str = None) -> bool:
        """
        Send a message to a specified chat.
        
        @param {str} chat_id - Unique identifier for the target chat
        @param {str} text - Text of the message to be sent
        @param {str} parse_mode - Optional. Mode for parsing entities (HTML/Markdown)
        @returns {bool} True if message was sent successfully, False otherwise
        """
        # This would be implemented by the concrete TelegramBot class
        # For now, we'll log the message
        self.log.info(f"Message to {chat_id}: {text}")
        return True
    
    async def send_trade_notification(self, trade_data: Dict[str, Any]) -> bool:
        """
        Send a trade execution notification message.
        
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
            
            self.log.info(f"Sent trade notification to {success_count}/{len(users)} users")
            return success_count > 0
            
        except Exception as e:
            self.log.error(f"Error sending trade notification: {e}")
            return False

    def _notify_trade(self, trade_data: Dict[str, Any]):
        """Wrapper to send trade notification from synchronous code."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.send_trade_notification(trade_data))
        except RuntimeError:
            asyncio.run(self.send_trade_notification(trade_data))
    
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
            
            # Send to admin users
            with self.database.db_session() as session:
                admin_users = session.query(TelegramUsers).filter(
                    TelegramUsers.role == UserRole.ADMIN,
                    TelegramUsers.status == UserStatus.ACTIVE
                ).all()
            
            success_count = 0
            for user in admin_users:
                if await self.send_message(user.telegram_id, alert_message, parse_mode='Markdown'):
                    success_count += 1
            
            self.log.info(f"Sent alert to {success_count} admin users")
            return success_count > 0
            
        except Exception as e:
            self.log.error(f"Error sending alert: {e}")
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
        if command not in self.command_rate_limits:
            return False
        
        limit = self.command_rate_limits[command]
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
    
    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /status command to display current trading status.
        
        @param {Update} update - Telegram update object
        @param {ContextTypes.DEFAULT_TYPE} context - Telegram context object
        """
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
            
            # Get trading status
            status_text = await self._generate_status_message()
            
            await update.message.reply_text(status_text, parse_mode='Markdown')
            
        except Exception as e:
            self.log.error(f"Error in /status command: {e}")
            await update.message.reply_text("❌ An error occurred while fetching status.")
    
    async def _generate_status_message(self) -> str:
        """
        Generate comprehensive trading status message.
        
        @returns {str} Formatted status message
        """
        try:
            # Get risk status
            risk_status = self.risk_manager.get_risk_status()
            
            # Get current trading state
            trading_allowed = self.risk_manager.is_trading_allowed()
            
            # Generate status message
            status_message = "📊 *Trading Status* 📊\n\n"
            
            # Overall status
            if trading_allowed:
                status_message += "🟢 *Trading Status:* **ACTIVE**\n"
            else:
                status_message += "🔴 *Trading Status:* **HALTED**\n"
            
            # Risk management status
            status_message += "\n⚠️ *Risk Management Status:*\n"
            if risk_status.get("status") == "success":
                overall_status = risk_status.get("overall_status", "unknown")
                if overall_status == "active":
                    status_message += "🟢 Risk management: Active\n"
                else:
                    status_message += "🔴 Risk management: Halted\n"
                
                # Add alerts
                alerts = risk_status.get("alerts", [])
                if alerts:
                    status_message += "\n🚨 *Active Alerts:*\n"
                    for alert in alerts[:3]:  # Show first 3 alerts
                        status_message += f"• {alert}\n"
            else:
                status_message += "⚠️ Risk management: Unknown\n"
            
            # Daily loss status
            daily_loss_component = risk_status.get("components", {}).get("daily_loss", {})
            if daily_loss_component.get("status") == "success":
                daily_loss_data = daily_loss_component.get("data", {})
                daily_loss_pct = daily_loss_data.get("daily_loss_percentage", 0)
                status_message += f"\n💰 *Daily Loss:* {daily_loss_pct:.2f}%\n"
                
                if daily_loss_data.get("is_loss_threshold_exceeded", False):
                    status_message += "🔴 Daily loss threshold exceeded!\n"
            
            # Emergency shutdown status
            shutdown_component = risk_status.get("components", {}).get("emergency_shutdown", {})
            if shutdown_component.get("is_shutdown_active", False):
                status_message += "\n🚨 *Emergency Shutdown:* **ACTIVE**\n"
                status_message += f"Reason: {shutdown_component.get('shutdown_reason', 'Unknown')}\n"
            
            # Recent trades (if available)
            try:
                with self.database.db_session() as session:
                    from ..models import Trade, TradeState
                    recent_trades = session.query(Trade).filter(
                        Trade.state == TradeState.COMPLETE
                    ).order_by(Trade.datetime.desc()).limit(5).all()
                
                if recent_trades:
                    status_message += "\n💼 *Recent Trades:*\n"
                    for trade in recent_trades:
                        trade_status = "✅" if trade.pnl > 0 else "❌"
                        status_message += f"{trade_status} {trade.from_coin.symbol}→{trade.to_coin.symbol}: {trade.pnl:.2f}\n"
            except Exception as e:
                self.log.debug(f"Could not fetch recent trades: {e}")
            
            # System uptime (approximate)
            status_message += f"\n⏰ *Last Update:* Just now\n"
            
            return status_message
            
        except Exception as e:
            self.log.error(f"Error generating status message: {e}")
            return "❌ Error generating status message."
    
    async def _stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /stop command to halt trading.
        
        @param {Update} update - Telegram update object
        @param {ContextTypes.DEFAULT_TYPE} context - Telegram context object
        """
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
            
            # Check if trading is already stopped
            if not self.trading_enabled:
                await update.message.reply_text("⚠️ Trading is already stopped.")
                return
            
            # Stop trading
            self.trading_enabled = False
            
            # Trigger emergency shutdown
            result = self.risk_manager.emergency_shutdown(
                reason="manual_stop",
                priority="high",
                description=f"Trading stopped by {db_user.first_name} ({db_user.username})"
            )
            
            if result.get("status") == "success":
                await update.message.reply_text(
                    "🛑 Trading has been **STOPPED**.\n\n"
                    "All trading activities have been halted. "
                    "Use /resume to restart trading when ready.",
                    parse_mode='Markdown'
                )
                
                # Send notification to all admin users
                await self.send_alert(
                    "info",
                    "Trading stopped manually",
                    {
                        "stopped_by": f"{db_user.first_name} ({db_user.username})",
                        "timestamp": datetime.utcnow().isoformat(),
                        "reason": "manual_stop"
                    }
                )
            else:
                await update.message.reply_text(f"❌ Failed to stop trading: {result.get('message', 'Unknown error')}")
                
        except Exception as e:
            self.log.error(f"Error in /stop command: {e}")
            await update.message.reply_text("❌ An error occurred while stopping trading.")
    
    async def _resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /resume command to restart trading.
        
        @param {Update} update - Telegram update object
        @param {ContextTypes.DEFAULT_TYPE} context - Telegram context object
        """
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
            
            # Check if trading is already running
            if self.trading_enabled:
                await update.message.reply_text("⚠️ Trading is already running.")
                return
            
            # Attempt recovery from emergency shutdown
            result = self.risk_manager.emergency_shutdown_manager.request_resume(
                self.database.db_session(),
                requested_by=f"{db_user.first_name} ({db_user.username})"
            )
            
            if result.get("status") == "success":
                self.trading_enabled = True
                
                await update.message.reply_text(
                    "▶️ Trading has been **RESUMED**.\n\n"
                    "All trading activities have been restarted. "
                    "Use /status to monitor trading performance.",
                    parse_mode='Markdown'
                )
                
                # Send notification to all admin users
                await self.send_alert(
                    "info",
                    "Trading resumed manually",
                    {
                        "resumed_by": f"{db_user.first_name} ({db_user.username})",
                        "timestamp": datetime.utcnow().isoformat(),
                        "reason": "manual_resume"
                    }
                )
            else:
                await update.message.reply_text(f"❌ Failed to resume trading: {result.get('message', 'Unknown error')}")
                
        except Exception as e:
            self.log.error(f"Error in /resume command: {e}")
            await update.message.reply_text("❌ An error occurred while resuming trading.")
    
    async def _shutdown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /shutdown command to initiate emergency shutdown with confirmation.
        
        @param {Update} update - Telegram update object
        @param {ContextTypes.DEFAULT_TYPE} context - Telegram context object
        """
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
            
            # Check if shutdown is already active
            shutdown_status = self.risk_manager.emergency_shutdown_manager.get_shutdown_status()
            if shutdown_status.get("status") == "success" and shutdown_status.get("data", {}).get("shutdown_status") == "active":
                await update.message.reply_text("⚠️ Emergency shutdown is already active.")
                return
            
            # Show confirmation dialog
            keyboard = [
                [InlineKeyboardButton("✅ CONFIRM", callback_data='shutdown_confirm')],
                [InlineKeyboardButton("❌ CANCEL", callback_data='shutdown_cancel')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🚨 *EMERGENCY SHUTDOWN CONFIRMATION* 🚨\n\n"
                "This will immediately stop all trading activities and require "
                "manual intervention to restart.\n\n"
                "Are you sure you want to proceed?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            # Store shutdown request context
            context.user_data['shutdown_requested_by'] = f"{db_user.first_name} ({db_user.username})"
            
        except Exception as e:
            self.log.error(f"Error in /shutdown command: {e}")
            await update.message.reply_text("❌ An error occurred while initiating shutdown.")
    
    async def _handle_shutdown_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle shutdown confirmation callback.
        
        @param {Update} update - Telegram update object
        @param {ContextTypes.DEFAULT_TYPE} context - Telegram context object
        """
        query = update.callback_query
        user = query.from_user
        
        try:
            with self.database.db_session() as session:
                db_user = session.query(TelegramUsers).filter(
                    TelegramUsers.telegram_id == str(user.id)
                ).first()
            
            if not db_user:
                await query.answer("❌ User not found.", show_alert=True)
                return
            
            # Check user permissions
            if not db_user.has_permission(UserRole.ADMIN):
                await query.answer("❌ You don't have permission to initiate shutdown.", show_alert=True)
                return
            
            if query.data == 'shutdown_confirm':
                # Execute shutdown
                requested_by = context.user_data.get('shutdown_requested_by', 'Unknown')
                
                result = self.risk_manager.emergency_shutdown_manager.force_shutdown(
                    self.database.db_session(),
                    reason="manual_shutdown",
                    description=f"Emergency shutdown initiated by {requested_by}",
                    triggered_by=requested_by
                )
                
                if result.get("status") == "success":
                    await query.answer("✅ Emergency shutdown confirmed.")
                    await query.message.edit_text(
                        "🚨 *EMERGENCY SHUTDOWN CONFIRMED* 🚨\n\n"
                        "All trading activities have been stopped.\n\n"
                        "Please contact the system administrator to restart trading.",
                        parse_mode='Markdown'
                    )
                    
                    # Send notification to all users
                    await self.send_alert(
                        "critical",
                        "Emergency shutdown activated",
                        {
                            "initiated_by": requested_by,
                            "timestamp": datetime.utcnow().isoformat(),
                            "reason": "admin_shutdown"
                        }
                    )
                else:
                    await query.answer(f"❌ Shutdown failed: {result.get('message', 'Unknown error')}", show_alert=True)
            
            elif query.data == 'shutdown_cancel':
                await query.answer("❌ Shutdown cancelled.")
                await query.message.edit_text(
                    "✅ Shutdown cancelled. Trading continues normally.",
                    parse_mode='Markdown'
                )
            
        except Exception as e:
            self.log.error(f"Error handling shutdown callback: {e}")
            await query.answer("❌ An error occurred.", show_alert=True)
    
    async def _get_help_text(self, user: TelegramUsers) -> str:
        """
        Get help text for trading control commands.
        
        @param {TelegramUsers} user - User object
        @returns {str} Help text
        """
        base_help = """
*Trading Control Commands:*

• `/status` - Show current trading status and risk metrics
• `/stop` - Halt all trading activities
• `/resume` - Resume trading after stop
• `/shutdown` - Emergency shutdown with confirmation

*Usage:*
• `/status` - View comprehensive trading status
• `/stop` - Stop trading (Trader+ permission)
• `/resume` - Resume trading (Trader+ permission)
• `/shutdown` - Emergency shutdown (Admin only)

*Examples:*
• `/status` - Shows current trading status, risk metrics, and recent trades
• `/stop` - Immediately stops all trading activities
• `/resume` - Restarts trading after it was stopped
• `/shutdown` - Shows confirmation dialog for emergency shutdown
        """
        
        if user.role == UserRole.ADMIN:
            admin_help = base_help + """

*Admin Features:*
• Emergency shutdown requires confirmation dialog
• Shutdown notifications sent to all users
• Full system control and monitoring capabilities
            """
            return admin_help
        
        return base_help
    
    def is_trading_enabled(self) -> bool:
        """
        Check if trading is currently enabled.
        
        @returns {bool} True if trading is enabled, False otherwise
        """
        return self.trading_enabled and self.risk_manager.is_trading_allowed()
    
    def get_trading_state(self) -> Dict[str, Any]:
        """
        Get current trading state information.
        
        @returns {dict} Trading state information
        """
        return {
            "trading_enabled": self.trading_enabled,
            "risk_allowed": self.risk_manager.is_trading_allowed(),
            "overall_enabled": self.is_trading_enabled(),
            "shutdown_requested": self.shutdown_requested,
            "shutdown_reason": self.shutdown_reason,
            "timestamp": datetime.utcnow().isoformat()
        }