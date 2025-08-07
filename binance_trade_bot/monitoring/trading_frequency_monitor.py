"""
Trading frequency monitoring with alerts module.

This module provides functionality to monitor trading frequency and
generate alerts when trading activity exceeds predefined thresholds.

Created: 2025-08-05
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict, Counter

from .base import MonitoringService, MonitoringAlert, AlertSeverity, AlertType, AlertStatus
from .models import TradingFrequencyData, TradingFrequencyMetric
from ..database import Database
from ..logger import Logger
from ..notifications import NotificationHandler
from ..models import Coin, Pair, Trade, TradeState
from ..binance_api_manager import BinanceAPIManager


class TradingFrequencyMonitor(MonitoringService):
    """
    Service for monitoring trading frequency and generating alerts.
    
    This service monitors trading activity across multiple time periods
    and generates alerts when trading frequency exceeds predefined thresholds.
    """
    
    def __init__(
        self,
        database: Database,
        logger: Logger,
        notifications: NotificationHandler,
        config: Dict[str, Any],
        binance_manager: BinanceAPIManager
    ):
        """
        Initialize the trading frequency monitor.
        
        @description Create a new trading frequency monitor instance
        @param {Database} database - Database connection for data storage
        @param {Logger} logger - Logger instance for logging
        @param {NotificationHandler} notifications - Notification handler for alerts
        @param {Dict} config - Configuration dictionary for trading frequency monitoring settings
        @param {BinanceAPIManager} binance_manager - Binance API manager for data retrieval
        @returns {TradingFrequencyMonitor} New trading frequency monitor instance
        """
        super().__init__(database, logger, notifications, config)
        
        self.binance_manager = binance_manager
        
        # Configuration settings
        self.frequency_thresholds = config.get('frequency_thresholds', {
            'trades_per_hour': {
                'low': 5,
                'medium': 10,
                'high': 20,
                'critical': 30
            },
            'trades_per_day': {
                'low': 50,
                'medium': 100,
                'high': 200,
                'critical': 300
            },
            'trades_per_week': {
                'low': 200,
                'medium': 400,
                'high': 800,
                'critical': 1200
            },
            'consecutive_trades': {
                'low': 3,
                'medium': 5,
                'high': 8,
                'critical': 12
            },
            'holding_period_minutes': {
                'low': 30,
                'medium': 15,
                'high': 5,
                'critical': 1
            }
        })
        
        self.monitoring_periods = config.get('monitoring_periods', {
            TradingFrequencyMetric.TRADES_PER_HOUR: 60,  # 60 minutes
            TradingFrequencyMetric.TRADES_PER_DAY: 1440,  # 24 hours
            TradingFrequencyMetric.TRADES_PER_WEEK: 10080,  # 7 days
            TradingFrequencyMetric.CONSECUTIVE_TRADES: 0,  # All time
            TradingFrequencyMetric.HOLDING_PERIOD: 0  # All time
        })
        
        self.coins_to_monitor = config.get('coins_to_monitor', [])
        self.pairs_to_monitor = config.get('pairs_to_monitor', [])
        
        # Alert cooldown settings
        self.alert_cooldown_period = config.get('alert_cooldown_period', 60)  # 60 minutes
        self.last_alerts: Dict[str, datetime] = {}  # coin/pair_metric -> last alert time
        
        # Cache for recent trades
        self.recent_trades: List[Trade] = []
        self.last_trade_sync = datetime.utcnow()
        
    async def collect_data(self) -> Dict[str, Any]:
        """
        Collect trading frequency data.
        
        @description Collect recent trading data for frequency analysis
        @returns {Dict} Dictionary containing collected trading data
        """
        self.logger.info("Starting trading frequency data collection")
        
        data = {
            'trades': [],
            'coins': {},
            'pairs': {},
            'timestamp': datetime.utcnow()
        }
        
        try:
            # Sync recent trades from database
            await self._sync_recent_trades()
            
            # Add trades to data
            data['trades'] = self.recent_trades
            
            # Collect coin and pair data
            coins_to_monitor = self.coins_to_monitor or [coin.symbol for coin in self.database.get_coins()]
            pairs_to_monitor = self.pairs_to_monitor or self.database.get_pairs()
            
            for coin_symbol in coins_to_monitor:
                coin_data = await self._collect_coin_trading_data(coin_symbol)
                if coin_data:
                    data['coins'][coin_symbol] = coin_data
            
            for pair in pairs_to_monitor:
                pair_data = await self._collect_pair_trading_data(pair)
                if pair_data:
                    data['pairs'][pair.id] = pair_data
            
            self.logger.info(f"Collected trading data for {len(data['trades'])} trades, {len(data['coins'])} coins, {len(data['pairs'])} pairs")
            return data
            
        except Exception as e:
            self.logger.error(f"Error collecting trading frequency data: {e}")
            raise
            
    async def _sync_recent_trades(self):
        """
        Sync recent trades from database.
        
        @description Fetch recent trades from database and update cache
        @returns {void}
        """
        try:
            # Only sync if last sync was more than 5 minutes ago
            if (datetime.utcnow() - self.last_trade_sync).total_seconds() < 300:
                return
            
            # Get trades from the last 7 days (for weekly analysis)
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            
            session = self.database.db_session()
            recent_trades = session.query(Trade).filter(Trade.datetime >= cutoff_date).all()
            
            self.recent_trades = recent_trades
            self.last_trade_sync = datetime.utcnow()
            
            self.logger.info(f"Synced {len(recent_trades)} recent trades")
            
        except Exception as e:
            self.logger.error(f"Error syncing recent trades: {e}")
            self.recent_trades = []
            
    async def _collect_coin_trading_data(self, coin_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Collect trading data for a specific coin.
        
        @description Collect trading frequency data for a single coin
        @param {str} coin_symbol - Symbol of the coin to collect data for
        @returns {Dict|null} Dictionary containing trading data or None if failed
        """
        try:
            coin = self.database.get_coin(coin_symbol)
            if not coin:
                return None
            
            # Filter trades involving this coin
            coin_trades = [
                trade for trade in self.recent_trades
                if trade.alt_coin_id == coin_symbol or trade.crypto_coin_id == coin_symbol
            ]
            
            # Calculate trading metrics
            trading_data = {
                'total_trades': len(coin_trades),
                'buy_trades': len([t for t in coin_trades if not t.selling]),
                'sell_trades': len([t for t in coin_trades if t.selling]),
                'first_trade': min([t.datetime for t in coin_trades]) if coin_trades else None,
                'last_trade': max([t.datetime for t in coin_trades]) if coin_trades else None,
                'trades_by_hour': self._group_trades_by_period(coin_trades, 'hour'),
                'trades_by_day': self._group_trades_by_period(coin_trades, 'day'),
                'consecutive_trades': self._calculate_consecutive_trades(coin_trades),
                'holding_periods': self._calculate_holding_periods(coin_trades)
            }
            
            return trading_data
            
        except Exception as e:
            self.logger.error(f"Error collecting trading data for coin {coin_symbol}: {e}")
            return None
            
    async def _collect_pair_trading_data(self, pair: Pair) -> Optional[Dict[str, Any]]:
        """
        Collect trading data for a specific trading pair.
        
        @description Collect trading frequency data for a single trading pair
        @param {Pair} pair - Trading pair to collect data for
        @returns {Dict|null} Dictionary containing trading data or None if failed
        """
        try:
            # Filter trades involving this pair
            pair_trades = [
                trade for trade in self.recent_trades
                if (trade.alt_coin_id == pair.from_coin_id and trade.crypto_coin_id == pair.to_coin_id) or
                   (trade.alt_coin_id == pair.to_coin_id and trade.crypto_coin_id == pair.from_coin_id)
            ]
            
            # Calculate trading metrics
            trading_data = {
                'total_trades': len(pair_trades),
                'first_trade': min([t.datetime for t in pair_trades]) if pair_trades else None,
                'last_trade': max([t.datetime for t in pair_trades]) if pair_trades else None,
                'trades_by_hour': self._group_trades_by_period(pair_trades, 'hour'),
                'trades_by_day': self._group_trades_by_period(pair_trades, 'day'),
                'consecutive_trades': self._calculate_consecutive_trades(pair_trades)
            }
            
            return trading_data
            
        except Exception as e:
            self.logger.error(f"Error collecting trading data for pair {pair}: {e}")
            return None
            
    def _group_trades_by_period(self, trades: List[Trade], period: str) -> Dict[str, int]:
        """
        Group trades by time period.
        
        @description Group trades by hour or day for frequency analysis
        @param {List} trades - List of trades to group
        @param {str} period - Time period ('hour' or 'day')
        @returns {Dict} Dictionary with period keys and trade counts
        """
        if not trades:
            return {}
        
        try:
            grouped = defaultdict(int)
            
            for trade in trades:
                if period == 'hour':
                    key = trade.datetime.strftime('%Y-%m-%d %H:00')
                elif period == 'day':
                    key = trade.datetime.strftime('%Y-%m-%d')
                else:
                    continue
                
                grouped[key] += 1
            
            return dict(grouped)
            
        except Exception as e:
            self.logger.error(f"Error grouping trades by period: {e}")
            return {}
            
    def _calculate_consecutive_trades(self, trades: List[Trade]) -> int:
        """
        Calculate maximum number of consecutive trades.
        
        @description Calculate the maximum number of consecutive trades for a coin/pair
        @param {List} trades - List of trades to analyze
        @returns {int} Maximum number of consecutive trades
        """
        if not trades:
            return 0
        
        try:
            # Sort trades by datetime
            sorted_trades = sorted(trades, key=lambda x: x.datetime)
            
            max_consecutive = 1
            current_consecutive = 1
            
            for i in range(1, len(sorted_trades)):
                time_diff = (sorted_trades[i].datetime - sorted_trades[i-1].datetime).total_seconds() / 60
                
                # Consider trades consecutive if less than 1 hour apart
                if time_diff <= 60:
                    current_consecutive += 1
                    max_consecutive = max(max_consecutive, current_consecutive)
                else:
                    current_consecutive = 1
            
            return max_consecutive
            
        except Exception as e:
            self.logger.error(f"Error calculating consecutive trades: {e}")
            return 0
            
    def _calculate_holding_periods(self, trades: List[Trade]) -> List[float]:
        """
        Calculate holding periods for trades.
        
        @description Calculate holding periods in minutes for buy/sell trade pairs
        @param {List} trades - List of trades to analyze
        @returns {List} List of holding periods in minutes
        """
        holding_periods = []
        
        try:
            # Separate buy and sell trades
            buy_trades = [t for t in trades if not t.selling and t.state == TradeState.COMPLETE]
            sell_trades = [t for t in trades if t.selling and t.state == TradeState.COMPLETE]
            
            # Match buy and sell trades by coin
            for buy_trade in buy_trades:
                matching_sells = [
                    s for s in sell_trades
                    if (s.alt_coin_id == buy_trade.alt_coin_id or s.crypto_coin_id == buy_trade.alt_coin_id) and
                       s.datetime > buy_trade.datetime
                ]
                
                if matching_sells:
                    earliest_sell = min(matching_sells, key=lambda x: x.datetime)
                    holding_period = (earliest_sell.datetime - buy_trade.datetime).total_seconds() / 60
                    holding_periods.append(holding_period)
            
            return holding_periods
            
        except Exception as e:
            self.logger.error(f"Error calculating holding periods: {e}")
            return []
            
    async def analyze_data(self, data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze collected trading data and detect unusual trading frequency.
        
        @description Analyze trading data to identify unusual frequency patterns
        @param {Dict} data - Collected trading data
        @returns {List} List of trading frequency alerts
        """
        self.logger.info("Starting trading frequency analysis")
        
        alerts = []
        
        try:
            # Analyze coin trading data
            for coin_symbol, coin_data in data.get('coins', {}).items():
                coin = self.database.get_coin(coin_symbol)
                coin_alerts = await self._analyze_coin_trading_frequency(coin, coin_data)
                alerts.extend(coin_alerts)
            
            # Analyze pair trading data
            for pair_id, pair_data in data.get('pairs', {}).items():
                pair = self.database.get_pair_by_id(pair_id)
                pair_alerts = await self._analyze_pair_trading_frequency(pair, pair_data)
                alerts.extend(pair_alerts)
            
            self.logger.info(f"Generated {len(alerts)} trading frequency alerts")
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing trading frequency data: {e}")
            return []
            
    async def _analyze_coin_trading_frequency(self, coin: Coin, coin_data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze trading frequency for a specific coin.
        
        @description Analyze trading frequency patterns for a single coin
        @param {Coin} coin - Associated coin
        @param {Dict} coin_data - Trading data for the coin
        @returns {List} List of trading frequency alerts for the coin
        """
        alerts = []
        
        try:
            # Analyze trades per hour
            trades_per_hour_alert = await self._analyze_trades_per_hour_frequency(
                coin=coin,
                coin_data=coin_data
            )
            
            # Analyze trades per day
            trades_per_day_alert = await self._analyze_trades_per_day_frequency(
                coin=coin,
                coin_data=coin_data
            )
            
            # Analyze trades per week
            trades_per_week_alert = await self._analyze_trades_per_week_frequency(
                coin=coin,
                coin_data=coin_data
            )
            
            # Analyze consecutive trades
            consecutive_trades_alert = await self._analyze_consecutive_trades_frequency(
                coin=coin,
                coin_data=coin_data
            )
            
            # Analyze holding periods
            holding_period_alert = await self._analyze_holding_period_frequency(
                coin=coin,
                coin_data=coin_data
            )
            
            # Add alerts if they exist
            for alert in [trades_per_hour_alert, trades_per_day_alert, trades_per_week_alert, 
                         consecutive_trades_alert, holding_period_alert]:
                if alert:
                    alerts.append(alert)
                    
                    # Store trading frequency data in database
                    await self._store_trading_frequency_data(
                        coin=coin,
                        alert=alert,
                        coin_data=coin_data
                    )
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing trading frequency for coin {coin.symbol}: {e}")
            return []
            
    async def _analyze_pair_trading_frequency(self, pair: Pair, pair_data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze trading frequency for a specific trading pair.
        
        @description Analyze trading frequency patterns for a single trading pair
        @param {Pair} pair - Associated trading pair
        @param {Dict} pair_data - Trading data for the pair
        @returns {List} List of trading frequency alerts for the pair
        """
        alerts = []
        
        try:
            # Analyze trades per hour for pairs
            trades_per_hour_alert = await self._analyze_trades_per_hour_frequency(
                pair=pair,
                pair_data=pair_data
            )
            
            # Analyze trades per day for pairs
            trades_per_day_alert = await self._analyze_trades_per_day_frequency(
                pair=pair,
                pair_data=pair_data
            )
            
            # Analyze consecutive trades for pairs
            consecutive_trades_alert = await self._analyze_consecutive_trades_frequency(
                pair=pair,
                pair_data=pair_data
            )
            
            # Add alerts if they exist
            for alert in [trades_per_hour_alert, trades_per_day_alert, consecutive_trades_alert]:
                if alert:
                    alerts.append(alert)
                    
                    # Store trading frequency data in database
                    await self._store_trading_frequency_data(
                        pair=pair,
                        alert=alert,
                        pair_data=pair_data
                    )
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing trading frequency for pair {pair}: {e}")
            return []
            
    async def _analyze_trades_per_hour_frequency(
        self,
        coin: Optional[Coin] = None,
        pair: Optional[Pair] = None,
        coin_data: Optional[Dict[str, Any]] = None,
        pair_data: Optional[Dict[str, Any]] = None
    ) -> Optional[MonitoringAlert]:
        """
        Analyze trades per hour frequency.
        
        @description Analyze trading frequency per hour to identify unusual activity
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {Dict} coin_data - Trading data for the coin
        @param {Dict} pair_data - Trading data for the pair
        @returns {MonitoringAlert|null} Alert object or None if no threshold exceeded
        """
        try:
            # Determine data source
            data = coin_data if coin_data else pair_data
            if not data:
                return None
            
            trades_by_hour = data.get('trades_by_hour', {})
            if not trades_by_hour:
                return None
            
            # Find maximum trades in any single hour
            max_trades_per_hour = max(trades_by_hour.values()) if trades_by_hour else 0
            
            # Check against thresholds
            severity = self._determine_frequency_severity(
                max_trades_per_hour,
                self.frequency_thresholds['trades_per_hour']
            )
            
            if severity:
                # Determine identifier for cooldown tracking
                identifier = f"{coin.symbol if coin else f'pair_{pair.id}'}_trades_per_hour"
                
                # Check cooldown period
                if identifier in self.last_alerts:
                    time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
                    if time_since_last < self.alert_cooldown_period:
                        return None
                
                # Create alert
                asset_name = coin.symbol if coin else f"{pair.from_coin_id}->{pair.to_coin_id}"
                
                alert = MonitoringAlert(
                    alert_type=AlertType.TRADING_FREQUENCY_EXCEEDED,
                    severity=severity,
                    title=f"High Trading Frequency Alert: {asset_name}",
                    description=(
                        f"Unusually high trading frequency detected for {asset_name}.\n\n"
                        f"Maximum trades in any single hour: {max_trades_per_hour}\n"
                        f"Analysis period: Last 7 days\n"
                        f"Threshold exceeded: {severity.value} severity"
                    ),
                    coin=coin,
                    pair=pair,
                    threshold_value=self.frequency_thresholds['trades_per_hour'][severity.value.lower()],
                    current_value=max_trades_per_hour,
                    metadata={
                        'metric_type': TradingFrequencyMetric.TRADES_PER_HOUR.value,
                        'max_trades_per_hour': max_trades_per_hour,
                        'total_trades': data.get('total_trades', 0)
                    },
                    context={
                        'trades_by_hour': trades_by_hour,
                        'analysis_timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                # Update last alert time
                self.last_alerts[identifier] = datetime.utcnow()
                
                return alert
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing trades per hour frequency: {e}")
            return None
            
    async def _analyze_trades_per_day_frequency(
        self,
        coin: Optional[Coin] = None,
        pair: Optional[Pair] = None,
        coin_data: Optional[Dict[str, Any]] = None,
        pair_data: Optional[Dict[str, Any]] = None
    ) -> Optional[MonitoringAlert]:
        """
        Analyze trades per day frequency.
        
        @description Analyze trading frequency per day to identify unusual activity
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {Dict} coin_data - Trading data for the coin
        @param {Dict} pair_data - Trading data for the pair
        @returns {MonitoringAlert|null} Alert object or None if no threshold exceeded
        """
        try:
            # Determine data source
            data = coin_data if coin_data else pair_data
            if not data:
                return None
            
            trades_by_day = data.get('trades_by_day', {})
            if not trades_by_day:
                return None
            
            # Find maximum trades in any single day
            max_trades_per_day = max(trades_by_day.values()) if trades_by_day else 0
            
            # Check against thresholds
            severity = self._determine_frequency_severity(
                max_trades_per_day,
                self.frequency_thresholds['trades_per_day']
            )
            
            if severity:
                # Determine identifier for cooldown tracking
                identifier = f"{coin.symbol if coin else f'pair_{pair.id}'}_trades_per_day"
                
                # Check cooldown period
                if identifier in self.last_alerts:
                    time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
                    if time_since_last < self.alert_cooldown_period:
                        return None
                
                # Create alert
                asset_name = coin.symbol if coin else f"{pair.from_coin_id}->{pair.to_coin_id}"
                
                alert = MonitoringAlert(
                    alert_type=AlertType.TRADING_FREQUENCY_EXCEEDED,
                    severity=severity,
                    title=f"High Daily Trading Frequency Alert: {asset_name}",
                    description=(
                        f"Unusually high daily trading frequency detected for {asset_name}.\n\n"
                        f"Maximum trades in any single day: {max_trades_per_day}\n"
                        f"Analysis period: Last 7 days\n"
                        f"Threshold exceeded: {severity.value} severity"
                    ),
                    coin=coin,
                    pair=pair,
                    threshold_value=self.frequency_thresholds['trades_per_day'][severity.value.lower()],
                    current_value=max_trades_per_day,
                    metadata={
                        'metric_type': TradingFrequencyMetric.TRADES_PER_DAY.value,
                        'max_trades_per_day': max_trades_per_day,
                        'total_trades': data.get('total_trades', 0)
                    },
                    context={
                        'trades_by_day': trades_by_day,
                        'analysis_timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                # Update last alert time
                self.last_alerts[identifier] = datetime.utcnow()
                
                return alert
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing trades per day frequency: {e}")
            return None
            
    async def _analyze_trades_per_week_frequency(
        self,
        coin: Optional[Coin] = None,
        pair: Optional[Pair] = None,
        coin_data: Optional[Dict[str, Any]] = None
    ) -> Optional[MonitoringAlert]:
        """
        Analyze trades per week frequency.
        
        @description Analyze trading frequency per week to identify unusual activity
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {Dict} coin_data - Trading data for the coin
        @returns {MonitoringAlert|null} Alert object or None if no threshold exceeded
        """
        try:
            # Only analyze for coins, not pairs
            if not coin or not coin_data:
                return None
            
            total_trades = coin_data.get('total_trades', 0)
            
            # Check against thresholds (using weekly thresholds)
            severity = self._determine_frequency_severity(
                total_trades,
                self.frequency_thresholds['trades_per_week']
            )
            
            if severity:
                # Determine identifier for cooldown tracking
                identifier = f"{coin.symbol}_trades_per_week"
                
                # Check cooldown period
                if identifier in self.last_alerts:
                    time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
                    if time_since_last < self.alert_cooldown_period:
                        return None
                
                # Create alert
                alert = MonitoringAlert(
                    alert_type=AlertType.TRADING_FREQUENCY_EXCEEDED,
                    severity=severity,
                    title=f"High Weekly Trading Frequency Alert: {coin.symbol}",
                    description=(
                        f"Unusually high weekly trading frequency detected for {coin.symbol}.\n\n"
                        f"Total trades in the last 7 days: {total_trades}\n"
                        f"Analysis period: Last 7 days\n"
                        f"Threshold exceeded: {severity.value} severity"
                    ),
                    coin=coin,
                    threshold_value=self.frequency_thresholds['trades_per_week'][severity.value.lower()],
                    current_value=total_trades,
                    metadata={
                        'metric_type': TradingFrequencyMetric.TRADES_PER_WEEK.value,
                        'total_trades': total_trades,
                        'buy_trades': coin_data.get('buy_trades', 0),
                        'sell_trades': coin_data.get('sell_trades', 0)
                    },
                    context={
                        'analysis_timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                # Update last alert time
                self.last_alerts[identifier] = datetime.utcnow()
                
                return alert
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing trades per week frequency: {e}")
            return None
            
    async def _analyze_consecutive_trades_frequency(
        self,
        coin: Optional[Coin] = None,
        pair: Optional[Pair] = None,
        coin_data: Optional[Dict[str, Any]] = None,
        pair_data: Optional[Dict[str, Any]] = None
    ) -> Optional[MonitoringAlert]:
        """
        Analyze consecutive trades frequency.
        
        @description Analyze consecutive trades to identify unusual trading patterns
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {Dict} coin_data - Trading data for the coin
        @param {Dict} pair_data - Trading data for the pair
        @returns {MonitoringAlert|null} Alert object or None if no threshold exceeded
        """
        try:
            # Determine data source
            data = coin_data if coin_data else pair_data
            if not data:
                return None
            
            consecutive_trades = data.get('consecutive_trades', 0)
            
            # Check against thresholds
            severity = self._determine_frequency_severity(
                consecutive_trades,
                self.frequency_thresholds['consecutive_trades']
            )
            
            if severity:
                # Determine identifier for cooldown tracking
                identifier = f"{coin.symbol if coin else f'pair_{pair.id}'}_consecutive_trades"
                
                # Check cooldown period
                if identifier in self.last_alerts:
                    time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
                    if time_since_last < self.alert_cooldown_period:
                        return None
                
                # Create alert
                asset_name = coin.symbol if coin else f"{pair.from_coin_id}->{pair.to_coin_id}"
                
                alert = MonitoringAlert(
                    alert_type=AlertType.TRADING_FREQUENCY_EXCEEDED,
                    severity=severity,
                    title=f"High Consecutive Trades Alert: {asset_name}",
                    description=(
                        f"Unusually high number of consecutive trades detected for {asset_name}.\n\n"
                        f"Maximum consecutive trades: {consecutive_trades}\n"
                        f"Analysis period: Last 7 days\n"
                        f"Threshold exceeded: {severity.value} severity"
                    ),
                    coin=coin,
                    pair=pair,
                    threshold_value=self.frequency_thresholds['consecutive_trades'][severity.value.lower()],
                    current_value=consecutive_trades,
                    metadata={
                        'metric_type': TradingFrequencyMetric.CONSECUTIVE_TRADES.value,
                        'consecutive_trades': consecutive_trades
                    },
                    context={
                        'analysis_timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                # Update last alert time
                self.last_alerts[identifier] = datetime.utcnow()
                
                return alert
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing consecutive trades frequency: {e}")
            return None
            
    async def _analyze_holding_period_frequency(
        self,
        coin: Coin,
        coin_data: Dict[str, Any]
    ) -> Optional[MonitoringAlert]:
        """
        Analyze holding period frequency.
        
        @description Analyze holding periods to identify unusual trading patterns
        @param {Coin} coin - Associated coin
        @param {Dict} coin_data - Trading data for the coin
        @returns {MonitoringAlert|null} Alert object or None if no threshold exceeded
        """
        try:
            holding_periods = coin_data.get('holding_periods', [])
            if not holding_periods:
                return None
            
            # Find minimum holding period
            min_holding_period = min(holding_periods)
            
            # Check against thresholds (lower holding period = higher frequency)
            # Convert minutes to threshold comparison
            severity = self._determine_holding_period_severity(min_holding_period)
            
            if severity:
                # Determine identifier for cooldown tracking
                identifier = f"{coin.symbol}_holding_period"
                
                # Check cooldown period
                if identifier in self.last_alerts:
                    time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
                    if time_since_last < self.alert_cooldown_period:
                        return None
                
                # Create alert
                alert = MonitoringAlert(
                    alert_type=AlertType.TRADING_FREQUENCY_EXCEEDED,
                    severity=severity,
                    title=f"Short Holding Period Alert: {coin.symbol}",
                    description=(
                        f"Unusually short holding periods detected for {coin.symbol}.\n\n"
                        f"Minimum holding period: {min_holding_period:.1f} minutes\n"
                        f"Total holding periods analyzed: {len(holding_periods)}\n"
                        f"Threshold exceeded: {severity.value} severity"
                    ),
                    coin=coin,
                    threshold_value=self.frequency_thresholds['holding_period_minutes'][severity.value.lower()],
                    current_value=min_holding_period,
                    metadata={
                        'metric_type': TradingFrequencyMetric.HOLDING_PERIOD.value,
                        'min_holding_period': min_holding_period,
                        'avg_holding_period': sum(holding_periods) / len(holding_periods),
                        'total_holding_periods': len(holding_periods)
                    },
                    context={
                        'analysis_timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                # Update last alert time
                self.last_alerts[identifier] = datetime.utcnow()
                
                return alert
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing holding period frequency: {e}")
            return None
            
    def _determine_frequency_severity(self, value: int, thresholds: Dict[str, int]) -> Optional[AlertSeverity]:
        """
        Determine alert severity based on frequency value.
        
        @description Calculate alert severity based on frequency thresholds
        @param {int} value - Frequency value to evaluate
        @param {Dict} thresholds - Threshold dictionary with severity levels
        @returns {AlertSeverity|null} Determined severity level or None if no threshold exceeded
        """
        if value >= thresholds['critical']:
            return AlertSeverity.CRITICAL
        elif value >= thresholds['high']:
            return AlertSeverity.HIGH
        elif value >= thresholds['medium']:
            return AlertSeverity.MEDIUM
        elif value >= thresholds['low']:
            return AlertSeverity.LOW
        else:
            return None
            
    def _determine_holding_period_severity(self, holding_period_minutes: float) -> Optional[AlertSeverity]:
        """
        Determine alert severity based on holding period.
        
        @description Calculate alert severity based on holding period thresholds
        @param {float} holding_period_minutes - Holding period in minutes
        @returns {AlertSeverity|null} Determined severity level or None if no threshold exceeded
        """
        if holding_period_minutes <= self.frequency_thresholds['holding_period_minutes']['critical']:
            return AlertSeverity.CRITICAL
        elif holding_period_minutes <= self.frequency_thresholds['holding_period_minutes']['high']:
            return AlertSeverity.HIGH
        elif holding_period_minutes <= self.frequency_thresholds['holding_period_minutes']['medium']:
            return AlertSeverity.MEDIUM
        elif holding_period_minutes <= self.frequency_thresholds['holding_period_minutes']['low']:
            return AlertSeverity.LOW
        else:
            return None
            
    async def _store_trading_frequency_data(
        self,
        coin: Optional[Coin] = None,
        pair: Optional[Pair] = None,
        alert: Optional[MonitoringAlert] = None,
        coin_data: Optional[Dict[str, Any]] = None,
        pair_data: Optional[Dict[str, Any]] = None
    ):
        """
        Store trading frequency data in the database.
        
        @description Store trading frequency measurement in database for historical tracking
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {MonitoringAlert} alert - Alert containing frequency information
        @param {Dict} coin_data - Trading data for the coin
        @param {Dict} pair_data - Trading data for the pair
        @returns {void}
        """
        try:
            if not alert:
                return
            
            # Convert string metric type to enum
            metric_enum = TradingFrequencyMetric(alert.metadata.get('metric_type'))
            
            # Create trading frequency data record
            frequency_data = TradingFrequencyData(
                coin=coin,
                pair=pair,
                metric_type=metric_enum,
                period=self.monitoring_periods.get(metric_enum, 0),
                frequency_value=alert.current_value,
                threshold_value=alert.threshold_value,
                metadata={
                    'alert_id': alert.alert_uuid,
                    'total_trades': coin_data.get('total_trades', 0) if coin_data else pair_data.get('total_trades', 0),
                    'monitoring_timestamp': datetime.utcnow().isoformat(),
                    'monitor_version': '1.0.0'
                }
            )
            
            # Store in database
            session = self.database.db_session()
            session.add(frequency_data)
            session.commit()
            
        except Exception as e:
            self.logger.error(f"Error storing trading frequency data: {e}")
            
    async def generate_report(self, alerts: List[MonitoringAlert]) -> str:
        """
        Generate a trading frequency monitoring report.
        
        @description Generate a human-readable report of trading frequency monitoring findings
        @param {List} alerts - List of alerts to include in the report
        @returns {str} Generated report text
        """
        if not alerts:
            return "✅ No trading frequency alerts generated. Trading activity appears normal."
        
        report_lines = [
            "🔄 Trading Frequency Monitoring Report",
            "=" * 50,
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Total Alerts: {len(alerts)}",
            ""
        ]
        
        # Group alerts by severity
        alerts_by_severity = {}
        for alert in alerts:
            severity = alert.severity.value
            if severity not in alerts_by_severity:
                alerts_by_severity[severity] = []
            alerts_by_severity[severity].append(alert)
        
        # Report by severity
        severity_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
        for severity in severity_order:
            if severity in alerts_by_severity:
                report_lines.append(f"🚨 {severity} Severity Alerts: {len(alerts_by_severity[severity])}")
                
                for alert in alerts_by_severity[severity][:3]:  # Show top 3 per severity
                    asset_name = alert.coin.symbol if alert.coin else f"{alert.pair.from_coin_id}->{alert.pair.to_coin_id}"
                    metric_type = alert.metadata.get('metric_type', 'Unknown')
                    current_value = alert.current_value
                    
                    report_lines.append(f"  • {alert.title}")
                    report_lines.append(f"    Asset: {asset_name}")
                    report_lines.append(f"    Metric: {metric_type}")
                    report_lines.append(f"    Current Value: {current_value}")
                
                if len(alerts_by_severity[severity]) > 3:
                    report_lines.append(f"  ... and {len(alerts_by_severity[severity]) - 3} more")
                
                report_lines.append("")
        
        # Summary statistics
        report_lines.append("📊 Summary Statistics:")
        report_lines.append(f"• Assets monitored: {len(self.last_alerts)}")
        report_lines.append(f"• Alert cooldown: {self.alert_cooldown_period} minutes")
        report_lines.append(f"• Recent trades analyzed: {len(self.recent_trades)}")
        
        return "\n".join(report_lines)