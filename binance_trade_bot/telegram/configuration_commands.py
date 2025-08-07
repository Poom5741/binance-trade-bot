"""
Configuration management commands for Telegram bot.

This module provides commands for managing trading bot configuration
including risk parameters, technical analysis settings, and AI features.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from .base import TelegramBase
from ..database import Database
from ..logger import Logger
from ..models.telegram_users import TelegramUsers, UserRole, UserStatus
from ..risk_management.integrated_risk_manager import IntegratedRiskManager
from ..technical_analysis.wma_engine import WmaEngine
from ..ai_adapter.base import AIAdapterBase
from ..models.ai_parameters import AiParameters, ParameterType, ParameterStatus
from ..models.risk_events import RiskEvent, RiskEventType, RiskEventSeverity


class ConfigurationCommands(TelegramBase):
    """
    Configuration management commands for Telegram bot.
    
    This class provides commands for managing trading bot configuration
    including risk parameters, technical analysis settings, and AI features.
    """
    
    # Command rate limiting (commands per minute)
    COMMAND_RATE_LIMITS = {
        'config': 5,
        'set_loss_limit': 3,
        'set_wma_periods': 3,
        'toggle_ai': 2,
    }
    
    def __init__(self, config: Dict[str, Any], database: Database, logger: Logger,
                 risk_manager: IntegratedRiskManager = None, wma_engine: WmaEngine = None,
                 ai_adapter: AIAdapterBase = None):
        """
        Initialize configuration commands with dependencies.
        
        @param {dict} config - Configuration dictionary
        @param {Database} database - Database instance for configuration management
        @param {Logger} logger - Logger instance for logging operations
        @param {IntegratedRiskManager} risk_manager - Risk management instance (optional)
        @param {WmaEngine} wma_engine - WMA engine instance (optional)
        @param {AIAdapterBase} ai_adapter - AI adapter instance (optional)
        """
        super().__init__(config)
        self.database = database
        self.logger = logger
        self.risk_manager = risk_manager
        self.wma_engine = wma_engine
        self.ai_adapter = ai_adapter
        
        # Track command usage for rate limiting
        self.user_command_counts = {}
    
    def _is_rate_limited(self, user_id: str, command: str) -> bool:
        """
        Check if user is rate limited for a specific command.
        
        @param {str} user_id - Telegram user ID
        @param {str} command - Command name
        @returns {bool} True if user is rate limited, False otherwise
        """
        from datetime import timedelta
        
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
        from datetime import datetime
        
        now = datetime.utcnow()
        
        if user_id not in self.user_command_counts:
            self.user_command_counts[user_id] = {}
        
        if command not in self.user_command_counts[user_id]:
            self.user_command_counts[user_id][command] = []
        
        self.user_command_counts[user_id][command].append(now)
    
    async def _config_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /config command to display current settings.
        
        @param {Update} update - Telegram update object
        @param {ContextTypes.DEFAULT_TYPE} context - Telegram context object
        """
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
            
            # Generate configuration display
            config_text = await self._generate_config_display(db_user)
            await update.message.reply_text(config_text, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Error in /config command: {e}")
            await update.message.reply_text("❌ An error occurred while fetching configuration.")
    
    async def _set_loss_limit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /set_loss_limit command to update risk parameters.
        
        @param {Update} update - Telegram update object
        @param {ContextTypes.DEFAULT_TYPE} context - Telegram context object
        """
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
            
            # Validate command arguments
            if len(context.args) != 1:
                await update.message.reply_text(
                    "❌ Invalid usage. Please provide a loss limit percentage.\n\n"
                    "Example: `/set_loss_limit 2.5`",
                    parse_mode='Markdown'
                )
                return
            
            try:
                loss_limit = float(context.args[0])
            except ValueError:
                await update.message.reply_text("❌ Invalid loss limit. Please provide a valid number.")
                return
            
            # Validate loss limit range
            if loss_limit < 0.1 or loss_limit > 50.0:
                await update.message.reply_text("❌ Loss limit must be between 0.1% and 50.0%.")
                return
            
            # Update loss limit if risk manager is available
            if self.risk_manager:
                result = await self._update_loss_limit(loss_limit, db_user)
                if result.get("status") == "success":
                    await update.message.reply_text(
                        f"✅ Loss limit updated to **{loss_limit:.2f}%** successfully.",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(f"❌ Failed to update loss limit: {result.get('message', 'Unknown error')}")
            else:
                await update.message.reply_text("❌ Risk management system is not available.")
                
        except Exception as e:
            self.logger.error(f"Error in /set_loss_limit command: {e}")
            await update.message.reply_text("❌ An error occurred while updating loss limit.")
    
    async def _set_wma_periods_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /set_wma_periods command to update technical analysis configuration.
        
        @param {Update} update - Telegram update object
        @param {ContextTypes.DEFAULT_TYPE} context - Telegram context object
        """
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
            
            # Validate command arguments
            if len(context.args) != 2:
                await update.message.reply_text(
                    "❌ Invalid usage. Please provide short and long period values.\n\n"
                    "Example: `/set_wma_periods 7 21`",
                    parse_mode='Markdown'
                )
                return
            
            try:
                short_period = int(context.args[0])
                long_period = int(context.args[1])
            except ValueError:
                await update.message.reply_text("❌ Invalid period values. Please provide valid integers.")
                return
            
            # Validate period ranges
            if short_period < 1 or short_period > 200:
                await update.message.reply_text("❌ Short period must be between 1 and 200.")
                return
            
            if long_period < 1 or long_period > 500:
                await update.message.reply_text("❌ Long period must be between 1 and 500.")
                return
            
            if short_period >= long_period:
                await update.message.reply_text("❌ Short period must be less than long period.")
                return
            
            # Update WMA periods if WMA engine is available
            if self.wma_engine:
                result = await self._update_wma_periods(short_period, long_period, db_user)
                if result.get("status") == "success":
                    await update.message.reply_text(
                        f"✅ WMA periods updated to **{short_period}** (short) and **{long_period}** (long) successfully.",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(f"❌ Failed to update WMA periods: {result.get('message', 'Unknown error')}")
            else:
                await update.message.reply_text("❌ Technical analysis system is not available.")
                
        except Exception as e:
            self.logger.error(f"Error in /set_wma_periods command: {e}")
            await update.message.reply_text("❌ An error occurred while updating WMA periods.")
    
    async def _toggle_ai_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /toggle_ai command to control AI features.
        
        @param {Update} update - Telegram update object
        @param {ContextTypes.DEFAULT_TYPE} context - Telegram context object
        """
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
            
            # Toggle AI features if AI adapter is available
            if self.ai_adapter:
                result = await self._toggle_ai_features(db_user)
                if result.get("status") == "success":
                    ai_status = "ENABLED" if result.get("data", {}).get("ai_enabled") else "DISABLED"
                    await update.message.reply_text(
                        f"✅ AI features have been **{ai_status}** successfully.",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(f"❌ Failed to toggle AI features: {result.get('message', 'Unknown error')}")
            else:
                await update.message.reply_text("❌ AI system is not available.")
                
        except Exception as e:
            self.logger.error(f"Error in /toggle_ai command: {e}")
            await update.message.reply_text("❌ An error occurred while toggling AI features.")
    
    async def _generate_config_display(self, user: TelegramUsers) -> str:
        """
        Generate configuration display text.
        
        @param {TelegramUsers} user - User object
        @returns {str} Formatted configuration display
        """
        config_text = "⚙️ *Current Configuration* ⚙️\n\n"
        
        # Risk Management Configuration
        config_text += "🛡️ *Risk Management:*\n"
        if self.risk_manager:
            try:
                risk_config = self.risk_manager.get_risk_configuration()
                config_text += f"• Loss Limit: {risk_config.get('loss_limit', 'N/A')}%\n"
                config_text += f"• Max Position Size: {risk_config.get('max_position_size', 'N/A')}%\n"
                config_text += f"• Daily Loss Limit: {risk_config.get('daily_loss_limit', 'N/A')}%\n"
                config_text += f"• Emergency Stop: {'Active' if risk_config.get('emergency_stop_enabled', False) else 'Inactive'}\n"
            except Exception as e:
                self.logger.error(f"Error getting risk configuration: {e}")
                config_text += "• Risk Configuration: Error loading\n"
        else:
            config_text += "• Risk Management: Not available\n"
        
        # Technical Analysis Configuration
        config_text += "\n📊 *Technical Analysis:*\n"
        if self.wma_engine:
            config_text += f"• WMA Short Period: {self.wma_engine.short_period}\n"
            config_text += f"• WMA Long Period: {self.wma_engine.long_period}\n"
            config_text += f"• Price Column: {self.wma_engine.price_column}\n"
        else:
            config_text += "• Technical Analysis: Not available\n"
        
        # AI Configuration
        config_text += "\n🤖 *AI Features:*\n"
        if self.ai_adapter:
            try:
                ai_config = self.ai_adapter.get_model_info()
                config_text += f"• AI Model: {ai_config.get('model_name', 'N/A')}\n"
                config_text += f"• Model Version: {ai_config.get('model_version', 'N/A')}\n"
                config_text += f"• Training Status: {'Trained' if ai_config.get('is_trained', False) else 'Not Trained'}\n"
                config_text += f"• AI Enabled: {'Yes' if self.config.get('ai_enabled', False) else 'No'}\n"
            except Exception as e:
                self.logger.error(f"Error getting AI configuration: {e}")
                config_text += "• AI Configuration: Error loading\n"
        else:
            config_text += "• AI Features: Not available\n"
        
        # Trading Configuration
        config_text += "\n💰 *Trading Settings:*\n"
        config_text += f"• Bridge Currency: {self.config.get('bridge', 'USDT')}\n"
        config_text += f"• Scout Multiplier: {self.config.get('scout_multiplier', 'N/A')}\n"
        config_text += f"• Scout Margin: {self.config.get('scout_margin', 'N/A')}%\n"
        config_text += f"• Use Margin: {self.config.get('use_margin', 'no')}\n"
        
        # Last Update
        config_text += f"\n📅 *Last Update:* {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        
        return config_text
    
    async def _update_loss_limit(self, loss_limit: float, user: TelegramUsers) -> Dict[str, Any]:
        """
        Update loss limit in risk management system.
        
        @param {float} loss_limit - New loss limit percentage
        @param {TelegramUsers} user - User making the change
        @returns {dict} Result status and message
        """
        try:
            # Update risk manager configuration
            if hasattr(self.risk_manager, 'set_loss_limit'):
                result = self.risk_manager.set_loss_limit(loss_limit)
            else:
                # Fallback to updating configuration directly
                self.config['loss_limit'] = loss_limit
                result = {"status": "success", "message": "Loss limit updated"}
            
            # Log the change
            self.logger.info(f"Loss limit updated to {loss_limit}% by {user.first_name} ({user.username})")
            
            # Create risk event for audit trail
            with self.database.db_session() as session:
                from ..models.pair import Pair
                from ..models.coin import Coin
                
                # Get default pair and coin for risk event
                pair = session.query(Pair).first()
                coin = session.query(Coin).first()
                
                if pair and coin:
                    risk_event = RiskEvent(
                        pair=pair,
                        coin=coin,
                        event_type=RiskEventType.CUSTOM,
                        severity=RiskEventSeverity.LOW,
                        trigger_value=loss_limit,
                        threshold_value=loss_limit,
                        current_value=loss_limit,
                        description=f"Loss limit updated by {user.first_name} ({user.username})",
                        created_by=f"telegram:{user.telegram_id}"
                    )
                    session.add(risk_event)
                    session.commit()
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error updating loss limit: {e}")
            return {"status": "error", "message": str(e)}
    
    async def _update_wma_periods(self, short_period: int, long_period: int, user: TelegramUsers) -> Dict[str, Any]:
        """
        Update WMA periods in technical analysis system.
        
        @param {int} short_period - New short period
        @param {int} long_period - New long period
        @param {TelegramUsers} user - User making the change
        @returns {dict} Result status and message
        """
        try:
            # Update WMA engine configuration
            if self.wma_engine:
                self.wma_engine.short_period = short_period
                self.wma_engine.long_period = long_period
                
                # Update configuration in config
                self.config['wma_short_period'] = short_period
                self.config['wma_long_period'] = long_period
                
                self.logger.info(f"WMA periods updated to {short_period}/{long_period} by {user.first_name} ({user.username})")
                
                return {"status": "success", "message": "WMA periods updated"}
            else:
                return {"status": "error", "message": "WMA engine not available"}
                
        except Exception as e:
            self.logger.error(f"Error updating WMA periods: {e}")
            return {"status": "error", "message": str(e)}
    
    async def _toggle_ai_features(self, user: TelegramUsers) -> Dict[str, Any]:
        """
        Toggle AI features on/off.
        
        @param {TelegramUsers} user - User making the change
        @returns {dict} Result status and message
        """
        try:
            # Toggle AI enabled status
            current_status = self.config.get('ai_enabled', False)
            new_status = not current_status
            
            self.config['ai_enabled'] = new_status
            
            # Log the change
            self.logger.info(f"AI features {'enabled' if new_status else 'disabled'} by {user.first_name} ({user.username})")
            
            return {
                "status": "success",
                "message": "AI features toggled",
                "data": {"ai_enabled": new_status}
            }
            
        except Exception as e:
            self.logger.error(f"Error toggling AI features: {e}")
            return {"status": "error", "message": str(e)}