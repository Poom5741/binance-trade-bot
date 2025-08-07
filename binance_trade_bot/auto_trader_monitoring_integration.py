"""
AutoTrader Monitoring Integration

This module provides integration between the AutoTrader and the monitoring system.
It enables real-time monitoring and alerting during trading operations.

Created: 2025-08-05
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

from .monitoring.monitoring_manager import MonitoringManager
from .monitoring.base import MonitoringAlert, AlertSeverity, AlertType
from .monitoring.models import VolatilityMetric, PerformanceMetric, TradingFrequencyMetric, ApiErrorType
from .models import Coin, Pair, Trade, TradeState
from .database import Database
from .logger import Logger
from .config import Config
from .binance_api_manager import BinanceAPIManager


class AutoTraderMonitoringIntegration:
    """
    Integration class that connects AutoTrader with the monitoring system.
    
    This class provides methods to integrate monitoring functionality
    directly into the AutoTrader's trading operations.
    """
    
    def __init__(
        self,
        database: Database,
        logger: Logger,
        config: Config,
        binance_manager: BinanceAPIManager,
        monitoring_manager: MonitoringManager
    ):
        """
        Initialize the AutoTrader monitoring integration.
        
        @description Create integration instance with required dependencies
        @param {Database} database - Database instance for data storage
        @param {Logger} logger - Logger instance for logging
        @param {Config} config - Configuration instance
        @param {BinanceAPIManager} binance_manager - Binance API manager
        @param {MonitoringManager} monitoring_manager - Monitoring manager instance
        @returns {void}
        """
        self.database = database
        self.logger = logger
        self.config = config
        self.binance_manager = binance_manager
        self.monitoring_manager = monitoring_manager
        
        # Track trading operations for monitoring
        self.tracking_data = {
            'last_trade_time': None,
            'trade_count': 0,
            'trade_history': [],
            'error_count': 0,
            'error_history': []
        }
        
        # Monitoring configuration
        self.monitoring_enabled = config.get('monitoring.enabled', True)
        self.monitoring_interval = config.get('monitoring.check_interval', 60)
        self.alert_cooldown = config.get('monitoring.alert_cooldown_period', 30)
        
        # Start monitoring task if enabled
        if self.monitoring_enabled:
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        else:
            self.monitoring_task = None
    
    async def _monitoring_loop(self):
        """
        Main monitoring loop that runs periodically.
        
        @description Continuous monitoring loop that checks market conditions
        and trading performance
        @returns {void}
        """
        self.logger.info("Starting AutoTrader monitoring loop")
        
        while self.monitoring_enabled:
            try:
                # Run monitoring cycle
                success = await self.monitoring_manager.run_monitoring_cycle()
                
                if not success:
                    self.logger.warning("Monitoring cycle failed")
                
                # Wait for next interval
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                self.logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def track_trade_start(self, trade: Trade):
        """
        Track the start of a trade operation.
        
        @description Record trade start time and update tracking data
        @param {Trade} trade - Trade being started
        @returns {void}
        """
        self.tracking_data['last_trade_time'] = datetime.utcnow()
        self.tracking_data['trade_count'] += 1
        self.tracking_data['trade_history'].append({
            'trade_id': trade.id,
            'start_time': datetime.utcnow(),
            'from_coin': trade.alt_coin.symbol,
            'to_coin': trade.crypto_coin.symbol,
            'selling': trade.selling,
            'state': trade.state.value
        })
        
        # Keep only recent trade history (last 100 trades)
        if len(self.tracking_data['trade_history']) > 100:
            self.tracking_data['trade_history'] = self.tracking_data['trade_history'][-100:]
        
        self.logger.info(f"Tracking trade start: {trade.alt_coin.symbol} -> {trade.crypto_coin.symbol}")
    
    async def track_trade_complete(self, trade: Trade):
        """
        Track the completion of a trade operation.
        
        @description Update trade tracking data with completion information
        @param {Trade} trade - Trade being completed
        @returns {void}
        """
        # Find trade in history
        trade_record = None
        for record in self.tracking_data['trade_history']:
            if record['trade_id'] == trade.id:
                trade_record = record
                break
        
        if trade_record:
            trade_record['end_time'] = datetime.utcnow()
            trade_record['state'] = trade.state.value
            trade_record['crypto_trade_amount'] = trade.crypto_trade_amount
            trade_record['alt_trade_amount'] = trade.alt_trade_amount
            
            self.logger.info(f"Tracking trade complete: {trade.alt_coin.symbol} -> {trade.crypto_coin.symbol}")
    
    async def track_api_error(self, error: Exception, endpoint: str, **kwargs):
        """
        Track API errors for monitoring purposes.
        
        @description Record API errors for error tracking and analysis
        @param {Exception} error - The error that occurred
        @param {str} endpoint - API endpoint that failed
        @param {Any} kwargs - Additional error context
        @returns {void}
        """
        self.tracking_data['error_count'] += 1
        self.tracking_data['error_history'].append({
            'timestamp': datetime.utcnow(),
            'error_type': type(error).__name__,
            'error_message': str(error),
            'endpoint': endpoint,
            'context': kwargs
        })
        
        # Keep only recent error history (last 50 errors)
        if len(self.tracking_data['error_history']) > 50:
            self.tracking_data['error_history'] = self.tracking_data['error_history'][-50:]
        
        self.logger.error(f"API error tracked: {endpoint} - {error}")
    
    async def get_trading_statistics(self) -> Dict[str, Any]:
        """
        Get current trading statistics for monitoring.
        
        @description Generate trading statistics for monitoring analysis
        @returns {Dict} Trading statistics dictionary
        """
        now = datetime.utcnow()
        
        # Calculate trades per hour
        recent_trades = [
            trade for trade in self.tracking_data['trade_history']
            if (now - trade['start_time']).total_seconds() < 3600
        ]
        trades_per_hour = len(recent_trades)
        
        # Calculate trades per day
        daily_trades = [
            trade for trade in self.tracking_data['trade_history']
            if (now - trade['start_time']).total_seconds() < 86400
        ]
        trades_per_day = len(daily_trades)
        
        # Calculate error rate
        total_api_calls = trades_per_hour * 10  # Estimate based on trade complexity
        error_rate = self.tracking_data['error_count'] / max(total_api_calls, 1)
        
        # Calculate consecutive trades
        consecutive_trades = 0
        if self.tracking_data['trade_history']:
            recent_trades = [
                trade for trade in self.tracking_data['trade_history']
                if (now - trade['start_time']).total_seconds() < 3600
            ]
            consecutive_trades = len(recent_trades)
        
        return {
            'total_trades': self.tracking_data['trade_count'],
            'trades_per_hour': trades_per_hour,
            'trades_per_day': trades_per_day,
            'consecutive_trades': consecutive_trades,
            'total_errors': self.tracking_data['error_count'],
            'error_rate': error_rate,
            'last_trade_time': self.tracking_data['last_trade_time'],
            'monitoring_enabled': self.monitoring_enabled
        }
    
    async def check_pre_trade_conditions(self, pair: Pair) -> List[MonitoringAlert]:
        """
        Check pre-trade conditions before executing a trade.
        
        @description Validate market conditions before allowing trades
        @param {Pair} pair - Trading pair to validate
        @returns {List} List of monitoring alerts if conditions are not met
        """
        alerts = []
        
        try:
            # Get current market data
            symbol = pair.from_coin + self.config.BRIDGE
            current_price = self.binance_manager.get_ticker_price(symbol)
            
            if current_price is None:
                alerts.append(MonitoringAlert(
                    alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                    severity=AlertSeverity.CRITICAL,
                    title="Price Data Unavailable",
                    description=f"Cannot get current price for {symbol}"
                ))
                return alerts
            
            # Check for high volatility (simplified check)
            price_history = await self._get_recent_price_history(symbol, 60)  # 1 hour
            if price_history and len(price_history) > 10:
                price_changes = [
                    (price_history[i] - price_history[i-1]) / price_history[i-1]
                    for i in range(1, len(price_history))
                ]
                avg_volatility = sum(abs(change) for change in price_changes) / len(price_changes)
                
                if avg_volatility > 0.05:  # 5% average volatility
                    alerts.append(MonitoringAlert(
                        alert_type=AlertType.MARKET_VOLATILITY_DETECTED,
                        severity=AlertSeverity.HIGH,
                        title="High Market Volatility",
                        description=f"High volatility detected for {symbol}: {avg_volatility:.2%}"
                    ))
            
            # Check trading frequency limits
            stats = await self.get_trading_statistics()
            if stats['trades_per_hour'] > 20:  # High frequency threshold
                alerts.append(MonitoringAlert(
                    alert_type=AlertType.HIGH_TRADING_FREQUENCY,
                    severity=AlertSeverity.MEDIUM,
                    title="High Trading Frequency",
                    description=f"High trading frequency detected: {stats['trades_per_hour']} trades/hour"
                ))
            
            # Check error rates
            if stats['error_rate'] > 0.1:  # 10% error rate threshold
                alerts.append(MonitoringAlert(
                    alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                    severity=AlertSeverity.HIGH,
                    title="High API Error Rate",
                    description=f"High API error rate detected: {stats['error_rate']:.2%}"
                ))
            
        except Exception as e:
            self.logger.error(f"Error checking pre-trade conditions: {e}")
            alerts.append(MonitoringAlert(
                alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                severity=AlertSeverity.CRITICAL,
                title="Monitoring System Error",
                description=f"Error checking pre-trade conditions: {e}"
            ))
        
        return alerts
    
    async def _get_recent_price_history(self, symbol: str, periods: int = 60) -> Optional[List[float]]:
        """
        Get recent price history for volatility analysis.
        
        @description Fetch recent price data for market analysis
        @param {str} symbol - Trading symbol
        @param {int} periods - Number of periods to fetch
        @returns {List|null} Price history list or None if fetch fails
        """
        try:
            klines = self.binance_manager.get_klines(symbol, limit=periods)
            
            if not klines or len(klines) < periods:
                return None
            
            return [float(k[4]) for k in klines]  # Close prices
            
        except Exception as e:
            self.logger.error(f"Failed to get price history for {symbol}: {e}")
            return None
    
    async def generate_trading_report(self) -> str:
        """
        Generate a comprehensive trading report.
        
        @description Create detailed report of trading performance and monitoring
        @returns {str} Formatted trading report
        """
        stats = await self.get_trading_statistics()
        
        report = f"""
📊 AutoTrader Trading Report
{'=' * 50}
Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

Trading Statistics:
- Total Trades: {stats['total_trades']}
- Trades per Hour: {stats['trades_per_hour']}
- Trades per Day: {stats['trades_per_day']}
- Consecutive Trades: {stats['consecutive_trades']}
- Total Errors: {stats['total_errors']}
- Error Rate: {stats['error_rate']:.2%}
- Last Trade: {stats['last_trade_time'].strftime('%Y-%m-%d %H:%M:%S') if stats['last_trade_time'] else 'Never'}
- Monitoring: {'Enabled' if stats['monitoring_enabled'] else 'Disabled'}

Recent Trade History:
"""
        
        # Add recent trades
        recent_trades = self.tracking_data['trade_history'][-10:]  # Last 10 trades
        for trade in recent_trades:
            report += f"- {trade['from_coin']} -> {trade['to_coin']} ({trade['state']})\n"
        
        # Add recent errors
        if self.tracking_data['error_history']:
            report += f"\nRecent Errors:\n"
            recent_errors = self.tracking_data['error_history'][-5:]  # Last 5 errors
            for error in recent_errors:
                report += f"- {error['timestamp'].strftime('%H:%M:%S')} - {error['endpoint']}: {error['error_message']}\n"
        
        return report
    
    async def cleanup(self):
        """
        Cleanup resources when stopping the integration.
        
        @description Clean up monitoring task and resources
        @returns {void}
        """
        if self.monitoring_task:
            self.monitoring_enabled = False
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("AutoTrader monitoring integration stopped")


# Decorator for monitoring trade operations
def monitor_trade_operation(func):
    """
    Decorator to monitor trade operations.
    
    @description Decorator that wraps trade methods with monitoring
    @param {Function} func - Function to decorate
    @returns {Function} Decorated function with monitoring
    """
    async def wrapper(self, *args, **kwargs):
        # Get trade information from arguments
        trade = None
        for arg in args:
            if hasattr(arg, 'id') and hasattr(arg, 'alt_coin') and hasattr(arg, 'crypto_coin'):
                trade = arg
                break
        
        if trade is None:
            # Try to find trade in kwargs
            trade = kwargs.get('trade')
        
        # Start tracking if we have a trade
        tracking_integration = getattr(self, 'monitoring_integration', None)
        if tracking_integration and trade:
            await tracking_integration.track_trade_start(trade)
        
        try:
            # Execute the original function
            result = await func(self, *args, **kwargs)
            
            # Track completion if we have a trade
            if tracking_integration and trade:
                await tracking_integration.track_trade_complete(trade)
            
            return result
            
        except Exception as e:
            # Track API errors
            if tracking_integration:
                await tracking_integration.track_api_error(e, func.__name__)
            raise
    
    return wrapper


# Context manager for monitoring operations
@asynccontextmanager
async def monitoring_context(trade: Trade, integration: AutoTraderMonitoringIntegration):
    """
    Context manager for monitoring trade operations.
    
    @description Context manager that handles trade tracking
    @param {Trade} trade - Trade to monitor
    @param {AutoTraderMonitoringIntegration} integration - Monitoring integration
    @returns {AsyncContextManager} Context manager for monitoring
    """
    await integration.track_trade_start(trade)
    try:
        yield
        await integration.track_trade_complete(trade)
    except Exception as e:
        await integration.track_api_error(e, "trade_operation")
        raise