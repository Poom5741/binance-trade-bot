"""
Telegram bot statistics and reporting commands implementation.

This module provides comprehensive statistics and reporting functionality
for the Telegram bot interface, including daily, weekly, total performance
display and current portfolio holdings.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal, ROUND_HALF_UP

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from .base import TelegramBase
from ..statistics.manager import StatisticsManager
from ..statistics.models import Statistics, DailyPerformance, WeeklyPerformance, TotalPerformance
from ..models.coin import Coin
from ..models.coin_value import CoinValue
from ..database import Database
from ..logger import Logger


class StatisticsCommands(TelegramBase):
    """
    Statistics and reporting commands for Telegram bot.
    
    This class provides comprehensive statistics and reporting functionality
    including daily, weekly, total performance display and current portfolio holdings.
    """
    
    # Command rate limiting (commands per minute)
    COMMAND_RATE_LIMITS = {
        'stats': 5,
        'weekly': 5,
        'total': 3,
        'portfolio': 10,
    }
    
    def __init__(self, config: Dict[str, Any], database: Database, logger: Logger,
                 statistics_manager: StatisticsManager = None):
        """
        Initialize the statistics commands with configuration, database, logger, and statistics manager.
        
        @param {dict} config - Configuration dictionary containing telegram settings
        @param {Database} database - Database instance for data access
        @param {Logger} logger - Logger instance for logging operations
        @param {StatisticsManager} statistics_manager - Statistics manager instance (optional)
        """
        super().__init__(config)
        self.database = database
        self.logger = logger
        self.statistics_manager = statistics_manager or StatisticsManager(config, database, logger)
        
        # Extract telegram configuration
        self.telegram_admin_id = config.get('telegram_admin_id')
        
        # Chart configuration
        self.chart_width = 20
        self.chart_height = 8
    
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
        if not hasattr(self, 'user_command_counts'):
            self.user_command_counts = {}
        
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
        
        if not hasattr(self, 'user_command_counts'):
            self.user_command_counts = {}
        
        if user_id not in self.user_command_counts:
            self.user_command_counts[user_id] = {}
        
        if command not in self.user_command_counts[user_id]:
            self.user_command_counts[user_id][command] = []
        
        self.user_command_counts[user_id][command].append(now)
    
    def _format_currency(self, amount: float, currency: str = 'USDT') -> str:
        """
        Format currency amount for display.
        
        @param {float} amount - Amount to format
        @param {str} currency - Currency code
        @returns {str} Formatted currency string
        """
        if abs(amount) >= 1000:
            return f"{amount:,.2f} {currency}"
        elif abs(amount) >= 1:
            return f"{amount:,.4f} {currency}"
        else:
            return f"{amount:,.6f} {currency}"
    
    def _format_percentage(self, percentage: float) -> str:
        """
        Format percentage for display.
        
        @param {float} percentage - Percentage value
        @returns {str} Formatted percentage string
        """
        return f"{percentage:+.2f}%"
    
    def _create_performance_bar(self, current_value: float, previous_value: float, max_bars: int = 10) -> str:
        """
        Create a visual performance bar chart.
        
        @param {float} current_value - Current value
        @param {float} previous_value - Previous value
        @param {int} max_bars - Maximum number of bars
        @returns {str} Visual bar chart
        """
        if previous_value == 0:
            change_percentage = 0 if current_value == 0 else 100
        else:
            change_percentage = ((current_value - previous_value) / previous_value) * 100
        
        # Calculate number of bars
        bars = int(abs(change_percentage) / 10)
        bars = min(bars, max_bars)
        
        if change_percentage > 0:
            bar = "🟢" + "🟢" * (bars - 1) + "⚪" * (max_bars - bars)
        elif change_percentage < 0:
            bar = "🔴" + "🔴" * (bars - 1) + "⚪" * (max_bars - bars)
        else:
            bar = "⚪" * max_bars
        
        return f"{bar} ({self._format_percentage(change_percentage)})"
    
    def _create_simple_chart(self, values: List[float], max_height: int = 5) -> str:
        """
        Create a simple ASCII chart from values.
        
        @param {List[float]} values - List of values
        @param {int} max_height - Maximum height of the chart
        @returns {str} ASCII chart
        """
        if not values or len(values) < 2:
            return "No data available"
        
        # Normalize values
        min_val = min(values)
        max_val = max(values)
        
        if max_val == min_val:
            # All values are the same
            return "─" * len(values)
        
        # Create chart
        chart = []
        for i in range(max_height):
            threshold = min_val + (max_val - min_val) * (max_height - i - 1) / (max_height - 1)
            line = []
            for value in values:
                if value >= threshold:
                    line.append("█")
                else:
                    line.append("─")
            chart.append("".join(line))
        
        return "\n".join(chart)
    
    def _format_daily_stats_message(self, stats: Dict[str, Any]) -> str:
        """
        Format daily statistics message for display.
        
        @param {dict} stats - Daily statistics dictionary
        @returns {str} Formatted message
        """
        message = "📊 *Daily Performance Report* 📊\n\n"
        
        # Date information
        if 'date' in stats:
            date_obj = datetime.fromisoformat(stats['date'])
            message += f"📅 *Date:* {date_obj.strftime('%Y-%m-%d')}\n"
        
        # Basic trading metrics
        message += f"\n🎯 *Trading Metrics:*\n"
        message += f"• *Total Trades:* {stats.get('total_trades', 0)}\n"
        message += f"• *Winning Trades:* {stats.get('winning_trades', 0)}\n"
        message += f"• *Losing Trades:* {stats.get('losing_trades', 0)}\n"
        message += f"• *Win Rate:* {self._format_percentage(stats.get('win_rate', 0) * 100)}\n"
        
        # Profit/Loss metrics
        message += f"\n💰 *Profit & Loss:*\n"
        message += f"• *Total P&L:* {self._format_currency(stats.get('total_profit_loss', 0))}\n"
        message += f"• *P&L %:* {self._format_percentage(stats.get('total_profit_loss_percentage', 0))}\n"
        message += f"• *Avg P&L:* {self._format_currency(stats.get('average_profit_loss', 0))}\n"
        
        # Win/Loss analysis
        if stats.get('average_win', 0) != 0 or stats.get('average_loss', 0) != 0:
            message += f"• *Avg Win:* {self._format_currency(stats.get('average_win', 0))}\n"
            message += f"• *Avg Loss:* {self._format_currency(stats.get('average_loss', 0))}\n"
        
        # Volume metrics
        message += f"\n📈 *Volume Metrics:*\n"
        message += f"• *Total Volume:* {self._format_currency(stats.get('total_volume', 0))}\n"
        message += f"• *Avg Trade Size:* {self._format_currency(stats.get('average_trade_size', 0))}\n"
        
        # Advanced metrics
        message += f"\n🔬 *Advanced Metrics:*\n"
        message += f"• *ROI:* {self._format_percentage(stats.get('roi', 0))}\n"
        message += f"• *Sharpe Ratio:* {stats.get('sharpe_ratio', 0):.2f}\n"
        message += f"• *Max Drawdown:* {self._format_percentage(stats.get('max_drawdown', 0))}\n"
        message += f"• *Volatility:* {self._format_percentage(stats.get('volatility', 0))}\n"
        
        # Additional metrics
        if stats.get('profit_factor', 0) != 0:
            message += f"• *Profit Factor:* {stats.get('profit_factor', 0):.2f}\n"
        
        # Performance chart
        if stats.get('daily_returns') and len(stats['daily_returns']) > 1:
            message += f"\n📊 *Performance Chart:*\n"
            chart = self._create_simple_chart(stats['daily_returns'])
            message += f"```\n{chart}\n```\n"
        
        return message
    
    def _format_weekly_stats_message(self, stats: Dict[str, Any]) -> str:
        """
        Format weekly statistics message for display.
        
        @param {dict} stats - Weekly statistics dictionary
        @returns {str} Formatted message
        """
        message = "📊 *Weekly Performance Report* 📊\n\n"
        
        # Date information
        if 'week_start' in stats and 'week_end' in stats:
            start_date = datetime.fromisoformat(stats['week_start'])
            end_date = datetime.fromisoformat(stats['week_end'])
            message += f"📅 *Period:* {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n"
        
        # Basic trading metrics
        message += f"\n🎯 *Trading Metrics:*\n"
        message += f"• *Total Trades:* {stats.get('total_trades', 0)}\n"
        message += f"• *Winning Trades:* {stats.get('winning_trades', 0)}\n"
        message += f"• *Losing Trades:* {stats.get('losing_trades', 0)}\n"
        message += f"• *Win Rate:* {self._format_percentage(stats.get('win_rate', 0) * 100)}\n"
        
        # Profit/Loss metrics
        message += f"\n💰 *Profit & Loss:*\n"
        message += f"• *Total P&L:* {self._format_currency(stats.get('total_profit_loss', 0))}\n"
        message += f"• *P&L %:* {self._format_percentage(stats.get('total_profit_loss_percentage', 0))}\n"
        message += f"• *Avg P&L:* {self._format_currency(stats.get('average_profit_loss', 0))}\n"
        
        # Volume metrics
        message += f"\n📈 *Volume Metrics:*\n"
        message += f"• *Total Volume:* {self._format_currency(stats.get('total_volume', 0))}\n"
        message += f"• *Avg Trade Size:* {self._format_currency(stats.get('average_trade_size', 0))}\n"
        
        # Advanced metrics
        message += f"\n🔬 *Advanced Metrics:*\n"
        message += f"• *ROI:* {self._format_percentage(stats.get('roi', 0))}\n"
        message += f"• *Sharpe Ratio:* {stats.get('sharpe_ratio', 0):.2f}\n"
        message += f"• *Max Drawdown:* {self._format_percentage(stats.get('max_drawdown', 0))}\n"
        message += f"• *Volatility:* {self._format_percentage(stats.get('volatility', 0))}\n"
        
        # Daily breakdown
        if stats.get('daily_breakdown'):
            message += f"\n📋 *Daily Breakdown:*\n"
            for daily_stats in stats['daily_breakdown']:
                date_str = daily_stats.get('date', 'N/A')
                daily_pnl = daily_stats.get('total_profit_loss', 0)
                message += f"• {date_str}: {self._format_currency(daily_pnl)}\n"
        
        return message
    
    def _format_total_stats_message(self, stats: Dict[str, Any]) -> str:
        """
        Format total statistics message for display.
        
        @param {dict} stats - Total statistics dictionary
        @returns {str} Formatted message
        """
        message = "📊 *Total Performance Report* 📊\n\n"
        
        # Date information
        if 'start_date' in stats and 'end_date' in stats:
            start_date = datetime.fromisoformat(stats['start_date'])
            end_date = datetime.fromisoformat(stats['end_date'])
            message += f"📅 *Period:* {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n"
        
        # Basic trading metrics
        message += f"\n🎯 *Trading Metrics:*\n"
        message += f"• *Total Trades:* {stats.get('total_trades', 0)}\n"
        message += f"• *Winning Trades:* {stats.get('winning_trades', 0)}\n"
        message += f"• *Losing Trades:* {stats.get('losing_trades', 0)}\n"
        message += f"• *Win Rate:* {self._format_percentage(stats.get('win_rate', 0) * 100)}\n"
        
        # Profit/Loss metrics
        message += f"\n💰 *Profit & Loss:*\n"
        message += f"• *Total P&L:* {self._format_currency(stats.get('total_profit_loss', 0))}\n"
        message += f"• *P&L %:* {self._format_percentage(stats.get('total_profit_loss_percentage', 0))}\n"
        message += f"• *Avg P&L:* {self._format_currency(stats.get('average_profit_loss', 0))}\n"
        
        # Volume metrics
        message += f"\n📈 *Volume Metrics:*\n"
        message += f"• *Total Volume:* {self._format_currency(stats.get('total_volume', 0))}\n"
        message += f"• *Avg Trade Size:* {self._format_currency(stats.get('average_trade_size', 0))}\n"
        
        # Advanced metrics
        message += f"\n🔬 *Advanced Metrics:*\n"
        message += f"• *ROI:* {self._format_percentage(stats.get('roi', 0))}\n"
        message += f"• *Sharpe Ratio:* {stats.get('sharpe_ratio', 0):.2f}\n"
        message += f"• *Max Drawdown:* {self._format_percentage(stats.get('max_drawdown', 0))}\n"
        message += f"• *Volatility:* {self._format_percentage(stats.get('volatility', 0))}\n"
        
        # Additional total metrics
        if stats.get('trading_days', 0) > 0:
            message += f"• *Trading Days:* {stats.get('trading_days', 0)}\n"
        
        if stats.get('best_day', 0) != 0:
            message += f"• *Best Day:* {self._format_currency(stats.get('best_day', 0))}\n"
        
        if stats.get('worst_day', 0) != 0:
            message += f"• *Worst Day:* {self._format_currency(stats.get('worst_day', 0))}\n"
        
        return message
    
    def _format_portfolio_message(self, portfolio_data: Dict[str, Any]) -> str:
        """
        Format portfolio message for display.
        
        @param {dict} portfolio_data - Portfolio data dictionary
        @returns {str} Formatted message
        """
        message = "💼 *Current Portfolio Holdings* 💼\n\n"
        
        # Portfolio summary
        total_value = portfolio_data.get('total_portfolio_value', 0)
        total_holdings = portfolio_data.get('total_holdings_count', 0)
        total_pnl = portfolio_data.get('total_profit_loss', 0)
        total_pnl_percentage = portfolio_data.get('total_profit_loss_percentage', 0)
        
        message += f"💰 *Portfolio Summary:*\n"
        message += f"• *Total Value:* {self._format_currency(total_value)}\n"
        message += f"• *Total Holdings:* {total_holdings}\n"
        message += f"• *Total P&L:* {self._format_currency(total_pnl)} ({self._format_percentage(total_pnl_percentage)})\n"
        
        # Individual holdings
        holdings = portfolio_data.get('individual_holdings', [])
        if holdings:
            message += f"\n📋 *Individual Holdings:*\n"
            
            # Sort holdings by value (descending)
            sorted_holdings = sorted(holdings, key=lambda x: x.get('usd_value', 0), reverse=True)
            
            for i, holding in enumerate(sorted_holdings[:10], 1):  # Show top 10 holdings
                symbol = holding.get('symbol', 'N/A')
                balance = holding.get('balance', 0)
                usd_value = holding.get('usd_value', 0)
                usd_price = holding.get('usd_price', 0)
                daily_change = holding.get('daily_change_percentage', 0)
                percentage = holding.get('percentage_of_portfolio', 0)
                
                message += f"\n{i}. *{symbol}*\n"
                message += f"   • *Balance:* {balance:,.8f}\n"
                message += f"   • *Value:* {self._format_currency(usd_value)} ({percentage:.1f}%)\n"
                message += f"   • *Price:* {self._format_currency(usd_price)}\n"
                message += f"   • *24h Change:* {self._format_percentage(daily_change)}\n"
                
                # Add performance indicator
                if daily_change > 0:
                    message += f"   • 🟢 Positive performance\n"
                elif daily_change < 0:
                    message += f"   • 🔴 Negative performance\n"
                else:
                    message += f"   • ⚪ No change\n"
        
        # Portfolio composition analysis
        if portfolio_data.get('composition_analysis'):
            composition = portfolio_data['composition_analysis']
            
            message += f"\n📊 *Portfolio Analysis:*\n"
            
            if composition.get('concentration_metrics'):
                metrics = composition['concentration_metrics']
                message += f"• *Top Holding:* {metrics.get('top_holding_percentage', 0):.1f}%\n"
                message += f"• *Top 3 Holdings:* {metrics.get('top_3_holdings_percentage', 0):.1f}%\n"
            
            if composition.get('diversification_score'):
                diversification_score = composition['diversification_score']
                message += f"• *Diversification Score:* {diversification_score:.1f}/10\n"
                
                # Add diversification indicator
                if diversification_score >= 8:
                    message += f"   • 🟢 Well diversified\n"
                elif diversification_score >= 5:
                    message += f"   • 🟡 Moderately diversified\n"
                else:
                    message += f"   • 🔴 Poorly diversified\n"
        
        return message
    
    async def _stats_command(self, update: Update, context: CallbackContext):
        """
        Handle /stats command - Display daily performance statistics.
        
        @param {Update} update - Telegram update object
        @param {CallbackContext} context - Telegram context object
        """
        user_id = str(update.effective_user.id)
        
        # Check rate limiting
        if self._is_rate_limited(user_id, 'stats'):
            await update.message.reply_text("⚠️ Too many stats commands. Please wait a moment.")
            return
        
        self._record_command_usage(user_id, 'stats')
        
        try:
            # Get today's date
            today = datetime.utcnow().date()
            
            # Get daily statistics
            stats = self.statistics_manager.get_daily_statistics(today)
            
            if not stats or stats.get('total_trades', 0) == 0:
                await update.message.reply_text(
                    "📊 *Daily Performance Report* 📊\n\n"
                    "📅 *Date:* " + today.strftime('%Y-%m-%d') + "\n\n"
                    "No trading activity recorded for today."
                )
                return
            
            # Format and send message
            message = self._format_daily_stats_message(stats)
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Error in /stats command: {str(e)}")
            await update.message.reply_text(
                "❌ Error retrieving daily statistics. Please try again later."
            )
    
    async def _weekly_command(self, update: Update, context: CallbackContext):
        """
        Handle /weekly command - Display weekly performance statistics.
        
        @param {Update} update - Telegram update object
        @param {CallbackContext} context - Telegram context object
        """
        user_id = str(update.effective_user.id)
        
        # Check rate limiting
        if self._is_rate_limited(user_id, 'weekly'):
            await update.message.reply_text("⚠️ Too many weekly commands. Please wait a moment.")
            return
        
        self._record_command_usage(user_id, 'weekly')
        
        try:
            # Get current week start (Monday)
            today = datetime.utcnow()
            week_start = today - timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Get weekly statistics
            stats = self.statistics_manager.get_weekly_statistics(week_start)
            
            if not stats or stats.get('total_trades', 0) == 0:
                week_end = week_start + timedelta(days=6)
                await update.message.reply_text(
                    "📊 *Weekly Performance Report* 📊\n\n"
                    f"📅 *Period:* {week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}\n\n"
                    "No trading activity recorded for this week."
                )
                return
            
            # Format and send message
            message = self._format_weekly_stats_message(stats)
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Error in /weekly command: {str(e)}")
            await update.message.reply_text(
                "❌ Error retrieving weekly statistics. Please try again later."
            )
    
    async def _total_command(self, update: Update, context: CallbackContext):
        """
        Handle /total command - Display total performance statistics.
        
        @param {Update} update - Telegram update object
        @param {CallbackContext} context - Telegram context object
        """
        user_id = str(update.effective_user.id)
        
        # Check rate limiting
        if self._is_rate_limited(user_id, 'total'):
            await update.message.reply_text("⚠️ Too many total commands. Please wait a moment.")
            return
        
        self._record_command_usage(user_id, 'total')
        
        try:
            # Get total statistics (last 30 days)
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=30)
            
            # Get total statistics
            stats = self.statistics_manager.get_total_statistics(start_date, end_date)
            
            if not stats or stats.get('total_trades', 0) == 0:
                await update.message.reply_text(
                    "📊 *Total Performance Report* 📊\n\n"
                    f"📅 *Period:* {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}\n\n"
                    "No trading activity recorded for this period."
                )
                return
            
            # Format and send message
            message = self._format_total_stats_message(stats)
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Error in /total command: {str(e)}")
            await update.message.reply_text(
                "❌ Error retrieving total statistics. Please try again later."
            )
    
    async def _portfolio_command(self, update: Update, context: CallbackContext):
        """
        Handle /portfolio command - Display current portfolio holdings.
        
        @param {Update} update - Telegram update object
        @param {CallbackContext} context - Telegram context object
        """
        user_id = str(update.effective_user.id)
        
        # Check rate limiting
        if self._is_rate_limited(user_id, 'portfolio'):
            await update.message.reply_text("⚠️ Too many portfolio commands. Please wait a moment.")
            return
        
        self._record_command_usage(user_id, 'portfolio')
        
        try:
            # Get portfolio data
            portfolio_data = self.statistics_manager.get_portfolio_value()
            
            if portfolio_data['status'] != 'success':
                await update.message.reply_text(
                    "❌ Error retrieving portfolio data. Please try again later."
                )
                return
            
            if portfolio_data.get('total_holdings_count', 0) == 0:
                await update.message.reply_text(
                    "💼 *Current Portfolio Holdings* 💼\n\n"
                    "No holdings found in your portfolio."
                )
                return
            
            # Format and send message
            message = self._format_portfolio_message(portfolio_data)
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            self.logger.error(f"Error in /portfolio command: {str(e)}")
            await update.message.reply_text(
                "❌ Error retrieving portfolio data. Please try again later."
            )
    
    def register_commands(self, application):
        """
        Register statistics commands with the Telegram application.
        
        @param {Application} application - Telegram application instance
        """
        # Register command handlers
        application.add_handler(
            CommandHandler('stats', self._stats_command)
        )
        application.add_handler(
            CommandHandler('weekly', self._weekly_command)
        )
        application.add_handler(
            CommandHandler('total', self._total_command)
        )
        application.add_handler(
            CommandHandler('portfolio', self._portfolio_command)
        )
        
        self.logger.info("Statistics commands registered successfully")