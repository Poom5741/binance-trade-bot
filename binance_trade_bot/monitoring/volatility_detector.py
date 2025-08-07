"""
Market volatility detection and alerts module.

This module provides functionality to detect market volatility spikes and
generate alerts when volatility exceeds predefined thresholds.

Created: 2025-08-05
"""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from statistics import stdev, mean

from .base import MonitoringService, MonitoringAlert, AlertSeverity, AlertType, AlertStatus
from .models import VolatilityData, VolatilityMetric
from ..database import Database
from ..logger import Logger
from ..notifications import NotificationHandler
from ..models import Coin, Pair
from ..binance_api_manager import BinanceAPIManager


class VolatilityDetector(MonitoringService):
    """
    Service for detecting market volatility and generating alerts.
    
    This service monitors market volatility using multiple metrics and
    generates alerts when volatility exceeds predefined thresholds.
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
        Initialize the volatility detector.
        
        @description Create a new volatility detector instance
        @param {Database} database - Database connection for data storage
        @param {Logger} logger - Logger instance for logging
        @param {NotificationHandler} notifications - Notification handler for alerts
        @param {Dict} config - Configuration dictionary for volatility detection settings
        @param {BinanceAPIManager} binance_manager - Binance API manager for data retrieval
        @returns {VolatilityDetector} New volatility detector instance
        """
        super().__init__(database, logger, notifications, config)
        
        self.binance_manager = binance_manager
        
        # Configuration settings
        self.volatility_thresholds = config.get('volatility_thresholds', {
            'low': 0.02,      # 2%
            'medium': 0.05,   # 5%
            'high': 0.10,     # 10%
            'critical': 0.20  # 20%
        })
        
        self.volatility_periods = config.get('volatility_periods', [1, 6, 24, 168])  # 1h, 6h, 24h, 1w
        self.volatility_metrics = config.get('volatility_metrics', [
            VolatilityMetric.STANDARD_DEVIATION.value,
            VolatilityMetric.ATR.value,
            VolatilityMetric.HISTORICAL_VOLATILITY.value
        ])
        
        self.price_history_periods = config.get('price_history_periods', {
            1: 60,      # 1 hour: 60 minutes of data
            6: 360,     # 6 hours: 360 minutes of data
            24: 1440,   # 24 hours: 1440 minutes of data
            168: 10080  # 1 week: 10080 minutes of data
        })
        
        self.coins_to_monitor = config.get('coins_to_monitor', [])
        self.pairs_to_monitor = config.get('pairs_to_monitor', [])
        
        # Alert cooldown settings
        self.alert_cooldown_period = config.get('alert_cooldown_period', 60)  # 60 minutes
        self.last_alerts: Dict[str, datetime] = {}  # coin/pair -> last alert time
        
    async def collect_data(self) -> Dict[str, Any]:
        """
        Collect price data for volatility analysis.
        
        @description Collect historical price data for all monitored coins and pairs
        @returns {Dict} Dictionary containing collected price data
        """
        self.logger.info("Starting volatility data collection")
        
        data = {
            'coins': {},
            'pairs': {},
            'timestamp': datetime.utcnow()
        }
        
        try:
            # Collect data for coins
            coins_to_monitor = self.coins_to_monitor or [coin.symbol for coin in self.database.get_coins()]
            
            for coin_symbol in coins_to_monitor:
                try:
                    coin_data = await self._collect_coin_data(coin_symbol)
                    if coin_data:
                        data['coins'][coin_symbol] = coin_data
                except Exception as e:
                    self.logger.error(f"Error collecting data for coin {coin_symbol}: {e}")
                    continue
            
            # Collect data for pairs
            pairs_to_monitor = self.pairs_to_monitor or self.database.get_pairs()
            
            for pair in pairs_to_monitor:
                try:
                    pair_data = await self._collect_pair_data(pair)
                    if pair_data:
                        data['pairs'][pair.id] = pair_data
                except Exception as e:
                    self.logger.error(f"Error collecting data for pair {pair}: {e}")
                    continue
            
            self.logger.info(f"Collected data for {len(data['coins'])} coins and {len(data['pairs'])} pairs")
            return data
            
        except Exception as e:
            self.logger.error(f"Error collecting volatility data: {e}")
            raise
            
    async def _collect_coin_data(self, coin_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Collect price data for a specific coin.
        
        @description Collect historical price data for a single coin
        @param {str} coin_symbol - Symbol of the coin to collect data for
        @returns {Dict|null} Dictionary containing price data or None if failed
        """
        try:
            # Get USDT price data for the coin
            symbol = f"{coin_symbol}USDT"
            price_data = {}
            
            for period_minutes in self.price_history_periods.values():
                try:
                    klines = self.binance_manager.get_klines(symbol, limit=period_minutes)
                    
                    if klines and len(klines) >= period_minutes:
                        prices = [float(k[4]) for k in klines]  # Close prices
                        timestamps = [datetime.fromtimestamp(float(k[0])/1000) for k in klines]
                        
                        price_data[period_minutes] = {
                            'prices': prices,
                            'timestamps': timestamps,
                            'current_price': prices[-1],
                            'price_change_24h': ((prices[-1] - prices[0]) / prices[0]) * 100 if len(prices) > 1 else 0
                        }
                        
                except Exception as e:
                    self.logger.warning(f"Failed to get {period_minutes}m data for {symbol}: {e}")
                    continue
            
            return price_data if price_data else None
            
        except Exception as e:
            self.logger.error(f"Error collecting coin data for {coin_symbol}: {e}")
            return None
            
    async def _collect_pair_data(self, pair: Pair) -> Optional[Dict[str, Any]]:
        """
        Collect price data for a specific trading pair.
        
        @description Collect historical price data for a single trading pair
        @param {Pair} pair - Trading pair to collect data for
        @returns {Dict|null} Dictionary containing price data or None if failed
        """
        try:
            # Get bridge price data for the pair
            symbol = f"{pair.from_coin.symbol}{self.config.get('bridge_symbol', 'USDT')}"
            price_data = {}
            
            for period_minutes in self.price_history_periods.values():
                try:
                    klines = self.binance_manager.get_klines(symbol, limit=period_minutes)
                    
                    if klines and len(klines) >= period_minutes:
                        prices = [float(k[4]) for k in klines]  # Close prices
                        timestamps = [datetime.fromtimestamp(float(k[0])/1000) for k in klines]
                        
                        price_data[period_minutes] = {
                            'prices': prices,
                            'timestamps': timestamps,
                            'current_price': prices[-1],
                            'price_change_24h': ((prices[-1] - prices[0]) / prices[0]) * 100 if len(prices) > 1 else 0
                        }
                        
                except Exception as e:
                    self.logger.warning(f"Failed to get {period_minutes}m data for {symbol}: {e}")
                    continue
            
            return price_data if price_data else None
            
        except Exception as e:
            self.logger.error(f"Error collecting pair data for {pair}: {e}")
            return None
            
    async def analyze_data(self, data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze collected price data and detect volatility spikes.
        
        @description Analyze price data to identify abnormal volatility patterns
        @param {Dict} data - Collected price data
        @returns {List} List of volatility alerts
        """
        self.logger.info("Starting volatility analysis")
        
        alerts = []
        
        try:
            # Analyze coin data
            for coin_symbol, coin_data in data.get('coins', {}).items():
                coin_alerts = await self._analyze_coin_volatility(coin_symbol, coin_data)
                alerts.extend(coin_alerts)
            
            # Analyze pair data
            for pair_id, pair_data in data.get('pairs', {}).items():
                pair_alerts = await self._analyze_pair_volatility(pair_id, pair_data)
                alerts.extend(pair_alerts)
            
            self.logger.info(f"Generated {len(alerts)} volatility alerts")
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing volatility data: {e}")
            return []
            
    async def _analyze_coin_volatility(self, coin_symbol: str, coin_data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze volatility for a specific coin.
        
        @description Analyze volatility patterns for a single coin
        @param {str} coin_symbol - Symbol of the coin to analyze
        @param {Dict} coin_data - Price data for the coin
        @returns {List} List of volatility alerts for the coin
        """
        alerts = []
        
        try:
            # Get coin object from database
            coin = self.database.get_coin(coin_symbol)
            
            for period_minutes, period_data in coin_data.items():
                if period_minutes not in self.volatility_periods:
                    continue
                
                prices = period_data['prices']
                current_price = period_data['current_price']
                
                # Calculate different volatility metrics
                volatility_metrics = await self._calculate_volatility_metrics(prices, period_minutes)
                
                # Check each metric against thresholds
                for metric_type, volatility_value in volatility_metrics.items():
                    alert = await self._check_volatility_threshold(
                        coin=coin,
                        metric_type=metric_type,
                        volatility_value=volatility_value,
                        period_minutes=period_minutes,
                        current_price=current_price,
                        price_change_24h=period_data.get('price_change_24h', 0)
                    )
                    
                    if alert:
                        alerts.append(alert)
                        
                        # Store volatility data in database
                        await self._store_volatility_data(
                            coin=coin,
                            metric_type=metric_type,
                            period_minutes=period_minutes,
                            volatility_value=volatility_value,
                            current_price=current_price,
                            price_change_24h=period_data.get('price_change_24h', 0)
                        )
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing volatility for coin {coin_symbol}: {e}")
            return []
            
    async def _analyze_pair_volatility(self, pair_id: int, pair_data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze volatility for a specific trading pair.
        
        @description Analyze volatility patterns for a single trading pair
        @param {int} pair_id - ID of the trading pair to analyze
        @param {Dict} pair_data - Price data for the pair
        @returns {List} List of volatility alerts for the pair
        """
        alerts = []
        
        try:
            # Get pair object from database
            pair = self.database.get_pair_by_id(pair_id)
            
            for period_minutes, period_data in pair_data.items():
                if period_minutes not in self.volatility_periods:
                    continue
                
                prices = period_data['prices']
                current_price = period_data['current_price']
                
                # Calculate different volatility metrics
                volatility_metrics = await self._calculate_volatility_metrics(prices, period_minutes)
                
                # Check each metric against thresholds
                for metric_type, volatility_value in volatility_metrics.items():
                    alert = await self._check_volatility_threshold(
                        pair=pair,
                        metric_type=metric_type,
                        volatility_value=volatility_value,
                        period_minutes=period_minutes,
                        current_price=current_price,
                        price_change_24h=period_data.get('price_change_24h', 0)
                    )
                    
                    if alert:
                        alerts.append(alert)
                        
                        # Store volatility data in database
                        await self._store_volatility_data(
                            pair=pair,
                            metric_type=metric_type,
                            period_minutes=period_minutes,
                            volatility_value=volatility_value,
                            current_price=current_price,
                            price_change_24h=period_data.get('price_change_24h', 0)
                        )
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing volatility for pair {pair_id}: {e}")
            return []
            
    async def _calculate_volatility_metrics(self, prices: List[float], period_minutes: int) -> Dict[str, float]:
        """
        Calculate various volatility metrics for price data.
        
        @description Calculate different volatility metrics for a list of prices
        @param {List} prices - List of prices to analyze
        @param {int} period_minutes - Time period in minutes
        @returns {Dict} Dictionary of volatility metrics
        """
        metrics = {}
        
        if len(prices) < 2:
            return metrics
        
        try:
            # Standard deviation (percentage volatility)
            returns = [(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
            if returns:
                std_dev = stdev(returns) if len(returns) > 1 else 0
                annualized_std = std_dev * np.sqrt(1440 / period_minutes)  # Annualized
                metrics[VolatilityMetric.STANDARD_DEVIATION.value] = annualized_std
            
            # Historical volatility (simplified)
            price_change_pct = ((prices[-1] - prices[0]) / prices[0]) * 100
            metrics[VolatilityMetric.HISTORICAL_VOLATILITY.value] = abs(price_change_pct) / (period_minutes / 60)
            
            # Average True Range approximation
            high_prices = [float(k[2]) for k in self.binance_manager.get_klines(f"{prices[-1]}USDT", limit=period_minutes)]
            low_prices = [float(k[3]) for k in self.binance_manager.get_klines(f"{prices[-1]}USDT", limit=period_minutes)]
            
            if high_prices and low_prices and len(high_prices) == len(low_prices):
                tr = [high_prices[i] - low_prices[i] for i in range(len(high_prices))]
                atr = mean(tr) if tr else 0
                metrics[VolatilityMetric.ATR.value] = (atr / prices[-1]) * 100 if prices[-1] > 0 else 0
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility metrics: {e}")
            return {}
            
    async def _check_volatility_threshold(
        self,
        coin: Optional[Coin] = None,
        pair: Optional[Pair] = None,
        metric_type: str = None,
        volatility_value: float = None,
        period_minutes: int = None,
        current_price: float = None,
        price_change_24h: float = None
    ) -> Optional[MonitoringAlert]:
        """
        Check if volatility exceeds thresholds and generate alert if needed.
        
        @description Check volatility against thresholds and create alert if exceeded
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {str} metric_type - Type of volatility metric
        @param {float} volatility_value - Calculated volatility value
        @param {int} period_minutes - Time period in minutes
        @param {float} current_price - Current price
        @param {float} price_change_24h - 24-hour price change percentage
        @returns {MonitoringAlert|null} Alert object or None if no threshold exceeded
        """
        try:
            # Determine identifier for cooldown tracking
            identifier = f"{coin.symbol}_{metric_type}_{period_minutes}" if coin else f"pair_{pair.id}_{metric_type}_{period_minutes}"
            
            # Check cooldown period
            if identifier in self.last_alerts:
                time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
                if time_since_last < self.alert_cooldown_period:
                    return None
            
            # Determine severity based on volatility value
            severity = None
            threshold_value = None
            
            if volatility_value >= self.volatility_thresholds['critical']:
                severity = AlertSeverity.CRITICAL
                threshold_value = self.volatility_thresholds['critical']
            elif volatility_value >= self.volatility_thresholds['high']:
                severity = AlertSeverity.HIGH
                threshold_value = self.volatility_thresholds['high']
            elif volatility_value >= self.volatility_thresholds['medium']:
                severity = AlertSeverity.MEDIUM
                threshold_value = self.volatility_thresholds['medium']
            elif volatility_value >= self.volatility_thresholds['low']:
                severity = AlertSeverity.LOW
                threshold_value = self.volatility_thresholds['low']
            else:
                return None
            
            # Generate alert title and description
            asset_name = coin.symbol if coin else f"{pair.from_coin_id}->{pair.to_coin_id}"
            period_hours = period_minutes / 60
            
            title = f"High Volatility Alert: {asset_name}"
            description = (
                f"Volatility spike detected for {asset_name} over the last {period_hours:.1f} hours.\n\n"
                f"Metric: {metric_type}\n"
                f"Current Volatility: {volatility_value:.2%}\n"
                f"Threshold: {threshold_value:.2%}\n"
                f"Current Price: ${current_price:.2f}\n"
                f"24h Change: {price_change_24h:+.2f}%"
            )
            
            # Create alert
            alert = MonitoringAlert(
                alert_type=AlertType.VOLATILITY_SPIKE,
                severity=severity,
                title=title,
                description=description,
                coin=coin,
                pair=pair,
                threshold_value=threshold_value,
                current_value=volatility_value,
                metadata={
                    'metric_type': metric_type,
                    'period_minutes': period_minutes,
                    'period_hours': period_hours,
                    'price_change_24h': price_change_24h
                },
                context={
                    'current_price': current_price,
                    'volatility_metrics': {
                        metric_type: volatility_value
                    }
                }
            )
            
            # Update last alert time
            self.last_alerts[identifier] = datetime.utcnow()
            
            return alert
            
        except Exception as e:
            self.logger.error(f"Error checking volatility threshold: {e}")
            return None
            
    async def _store_volatility_data(
        self,
        coin: Optional[Coin] = None,
        pair: Optional[Pair] = None,
        metric_type: str = None,
        period_minutes: int = None,
        volatility_value: float = None,
        current_price: float = None,
        price_change_24h: float = None
    ):
        """
        Store volatility data in the database.
        
        @description Store volatility measurement in database for historical tracking
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {str} metric_type - Type of volatility metric
        @param {int} period_minutes - Time period in minutes
        @param {float} volatility_value - Calculated volatility value
        @param {float} current_price - Current price
        @param {float} price_change_24h - 24-hour price change percentage
        @returns {void}
        """
        try:
            # Convert string metric type to enum
            metric_enum = VolatilityMetric(metric_type)
            
            # Create volatility data record
            volatility_data = VolatilityData(
                coin=coin,
                pair=pair,
                metric_type=metric_enum,
                period=period_minutes,
                volatility_value=volatility_value,
                current_price=current_price,
                price_change_percentage=price_change_24h,
                metadata={
                    'calculated_at': datetime.utcnow().isoformat(),
                    'detector_version': '1.0.0'
                }
            )
            
            # Store in database
            session = self.database.db_session()
            session.add(volatility_data)
            session.commit()
            
        except Exception as e:
            self.logger.error(f"Error storing volatility data: {e}")
            
    async def generate_report(self, alerts: List[MonitoringAlert]) -> str:
        """
        Generate a volatility monitoring report.
        
        @description Generate a human-readable report of volatility monitoring findings
        @param {List} alerts - List of alerts to include in the report
        @returns {str} Generated report text
        """
        if not alerts:
            return "✅ No volatility alerts generated. Market conditions appear normal."
        
        report_lines = [
            "📊 Market Volatility Monitoring Report",
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
                    report_lines.append(f"  • {alert.title}")
                    report_lines.append(f"    Volatility: {alert.current_value:.2%}")
                    report_lines.append(f"    Asset: {asset_name}")
                
                if len(alerts_by_severity[severity]) > 3:
                    report_lines.append(f"  ... and {len(alerts_by_severity[severity]) - 3} more")
                
                report_lines.append("")
        
        # Summary statistics
        report_lines.append("📈 Summary Statistics:")
        report_lines.append(f"• Assets monitored: {len(self.last_alerts)}")
        report_lines.append(f"• Alert cooldown: {self.alert_cooldown_period} minutes")
        report_lines.append(f"• Volatility thresholds: {self.volatility_thresholds}")
        
        return "\n".join(report_lines)