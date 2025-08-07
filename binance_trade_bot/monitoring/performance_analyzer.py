"""
Exceptional coin performance notifications module.

This module provides functionality to detect exceptional coin performance
and generate alerts when coins show unusual performance patterns.

Created: 2025-08-05
"""

import asyncio
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from statistics import mean, stdev

from .base import MonitoringService, MonitoringAlert, AlertSeverity, AlertType, AlertStatus
from .models import PerformanceData, PerformanceMetric
from ..database import Database
from ..logger import Logger
from ..notifications import NotificationHandler
from ..models import Coin, Pair
from ..binance_api_manager import BinanceAPIManager


class PerformanceAnalyzer(MonitoringService):
    """
    Service for detecting exceptional coin performance and generating alerts.
    
    This service monitors coin performance using multiple metrics and
    generates alerts when performance shows unusual patterns.
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
        Initialize the performance analyzer.
        
        @description Create a new performance analyzer instance
        @param {Database} database - Database connection for data storage
        @param {Logger} logger - Logger instance for logging
        @param {NotificationHandler} notifications - Notification handler for alerts
        @param {Dict} config - Configuration dictionary for performance analysis settings
        @param {BinanceAPIManager} binance_manager - Binance API manager for data retrieval
        @returns {PerformanceAnalyzer} New performance analyzer instance
        """
        super().__init__(database, logger, notifications, config)
        
        self.binance_manager = binance_manager
        
        # Configuration settings
        self.performance_thresholds = config.get('performance_thresholds', {
            'price_change_high': 0.15,    # 15% positive change
            'price_change_low': -0.15,    # 15% negative change
            'volume_spike_multiplier': 3.0,  # 3x average volume
            'performance_deviation': 2.0,    # 2 standard deviations
        })
        
        self.performance_periods = config.get('performance_periods', [1, 6, 24, 168])  # 1h, 6h, 24h, 1w
        self.performance_metrics = config.get('performance_metrics', [
            PerformanceMetric.PRICE_CHANGE.value,
            PerformanceMetric.VOLUME_SPIKE.value,
            PerformanceMetric.TREND_STRENGTH.value
        ])
        
        self.baseline_periods = config.get('baseline_periods', [24, 168])  # 24h, 1w for baselines
        
        self.coins_to_monitor = config.get('coins_to_monitor', [])
        self.min_liquidity = config.get('min_liquidity', 10000)  # Minimum market cap in USD
        
        # Alert cooldown settings
        self.alert_cooldown_period = config.get('alert_cooldown_period', 30)  # 30 minutes
        self.last_alerts: Dict[str, datetime] = {}  # coin -> last alert time
        
    async def collect_data(self) -> Dict[str, Any]:
        """
        Collect performance data for coins.
        
        @description Collect price, volume, and performance data for monitored coins
        @returns {Dict} Dictionary containing collected performance data
        """
        self.logger.info("Starting performance data collection")
        
        data = {
            'coins': {},
            'timestamp': datetime.utcnow()
        }
        
        try:
            # Collect data for coins
            coins_to_monitor = self.coins_to_monitor or [coin.symbol for coin in self.database.get_coins()]
            
            for coin_symbol in coins_to_monitor:
                try:
                    coin_data = await self._collect_coin_performance_data(coin_symbol)
                    if coin_data:
                        data['coins'][coin_symbol] = coin_data
                except Exception as e:
                    self.logger.error(f"Error collecting performance data for coin {coin_symbol}: {e}")
                    continue
            
            self.logger.info(f"Collected performance data for {len(data['coins'])} coins")
            return data
            
        except Exception as e:
            self.logger.error(f"Error collecting performance data: {e}")
            raise
            
    async def _collect_coin_performance_data(self, coin_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Collect performance data for a specific coin.
        
        @description Collect price, volume, and performance metrics for a single coin
        @param {str} coin_symbol - Symbol of the coin to collect data for
        @returns {Dict|null} Dictionary containing performance data or None if failed
        """
        try:
            # Get USDT price and volume data for the coin
            symbol = f"{coin_symbol}USDT"
            performance_data = {}
            
            for period_hours in self.performance_periods:
                period_minutes = period_hours * 60
                
                try:
                    klines = self.binance_manager.get_klines(symbol, limit=period_minutes)
                    
                    if klines and len(klines) >= period_minutes:
                        prices = [float(k[4]) for k in klines]  # Close prices
                        volumes = [float(k[5]) for k in klines]  # Volumes
                        timestamps = [datetime.fromtimestamp(float(k[0])/1000) for k in klines]
                        
                        # Calculate performance metrics
                        price_change = ((prices[-1] - prices[0]) / prices[0]) * 100 if len(prices) > 1 else 0
                        avg_volume = mean(volumes) if volumes else 0
                        current_volume = volumes[-1] if volumes else 0
                        
                        performance_data[period_hours] = {
                            'prices': prices,
                            'volumes': volumes,
                            'timestamps': timestamps,
                            'current_price': prices[-1],
                            'price_change': price_change,
                            'avg_volume': avg_volume,
                            'current_volume': current_volume,
                            'volume_ratio': current_volume / avg_volume if avg_volume > 0 else 1.0
                        }
                        
                except Exception as e:
                    self.logger.warning(f"Failed to get {period_hours}h data for {symbol}: {e}")
                    continue
            
            # Get baseline data for comparison
            baseline_data = await self._collect_baseline_data(symbol)
            performance_data['baseline'] = baseline_data
            
            return performance_data if performance_data else None
            
        except Exception as e:
            self.logger.error(f"Error collecting performance data for {coin_symbol}: {e}")
            return None
            
    async def _collect_baseline_data(self, symbol: str) -> Dict[str, Any]:
        """
        Collect baseline performance data for comparison.
        
        @description Collect historical baseline data for performance comparison
        @param {str} symbol - Trading symbol (e.g., 'BTCUSDT')
        @returns {Dict} Dictionary containing baseline data
        """
        baseline_data = {}
        
        try:
            for period_hours in self.baseline_periods:
                period_minutes = period_hours * 60
                
                try:
                    klines = self.binance_manager.get_klines(symbol, limit=period_minutes)
                    
                    if klines and len(klines) >= period_minutes:
                        prices = [float(k[4]) for k in klines]  # Close prices
                        volumes = [float(k[5]) for k in klines]  # Volumes
                        
                        # Calculate baseline metrics
                        price_change = ((prices[-1] - prices[0]) / prices[0]) * 100 if len(prices) > 1 else 0
                        avg_volume = mean(volumes) if volumes else 0
                        
                        baseline_data[period_hours] = {
                            'price_change': price_change,
                            'avg_volume': avg_volume,
                            'volatility': stdev([(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]) if len(prices) > 1 else 0
                        }
                        
                except Exception as e:
                    self.logger.warning(f"Failed to get baseline {period_hours}h data for {symbol}: {e}")
                    continue
            
            return baseline_data
            
        except Exception as e:
            self.logger.error(f"Error collecting baseline data for {symbol}: {e}")
            return {}
            
    async def analyze_data(self, data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze collected performance data and detect exceptional performance.
        
        @description Analyze performance data to identify unusual performance patterns
        @param {Dict} data - Collected performance data
        @returns {List} List of performance alerts
        """
        self.logger.info("Starting performance analysis")
        
        alerts = []
        
        try:
            # Analyze coin data
            for coin_symbol, coin_data in data.get('coins', {}).items():
                coin_alerts = await self._analyze_coin_performance(coin_symbol, coin_data)
                alerts.extend(coin_alerts)
            
            self.logger.info(f"Generated {len(alerts)} performance alerts")
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing performance data: {e}")
            return []
            
    async def _analyze_coin_performance(self, coin_symbol: str, coin_data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze performance for a specific coin.
        
        @description Analyze performance patterns for a single coin
        @param {str} coin_symbol - Symbol of the coin to analyze
        @param {Dict} coin_data - Performance data for the coin
        @returns {List} List of performance alerts for the coin
        """
        alerts = []
        
        try:
            # Get coin object from database
            coin = self.database.get_coin(coin_symbol)
            
            # Check if coin meets minimum liquidity requirement
            if not await self._check_liquidity_requirement(coin):
                return []
            
            for period_hours, period_data in coin_data.items():
                if period_hours not in self.performance_periods:
                    continue
                
                # Analyze different performance metrics
                price_change_alert = await self._analyze_price_change_performance(
                    coin=coin,
                    period_hours=period_hours,
                    period_data=period_data,
                    baseline_data=coin_data.get('baseline', {})
                )
                
                volume_spike_alert = await self._analyze_volume_spike_performance(
                    coin=coin,
                    period_hours=period_hours,
                    period_data=period_data,
                    baseline_data=coin_data.get('baseline', {})
                )
                
                trend_strength_alert = await self._analyze_trend_strength_performance(
                    coin=coin,
                    period_hours=period_hours,
                    period_data=period_data
                )
                
                # Add alerts if they exist
                for alert in [price_change_alert, volume_spike_alert, trend_strength_alert]:
                    if alert:
                        alerts.append(alert)
                        
                        # Store performance data in database
                        await self._store_performance_data(
                            coin=coin,
                            alert=alert,
                            period_hours=period_hours,
                            period_data=period_data
                        )
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing performance for coin {coin_symbol}: {e}")
            return []
            
    async def _check_liquidity_requirement(self, coin: Coin) -> bool:
        """
        Check if coin meets minimum liquidity requirement.
        
        @description Verify that coin has sufficient liquidity for analysis
        @param {Coin} coin - Coin to check liquidity for
        @returns {bool} True if coin meets liquidity requirement
        """
        try:
            # Get current price and market cap (simplified check)
            symbol = f"{coin.symbol}USDT"
            ticker = self.binance_manager.get_ticker_price(symbol)
            
            if ticker:
                # This is a simplified liquidity check
                # In a real implementation, you'd get actual market cap data
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking liquidity for {coin.symbol}: {e}")
            return False
            
    async def _analyze_price_change_performance(
        self,
        coin: Coin,
        period_hours: int,
        period_data: Dict[str, Any],
        baseline_data: Dict[str, Any]
    ) -> Optional[MonitoringAlert]:
        """
        Analyze price change performance for exceptional movements.
        
        @description Analyze price changes to identify significant movements
        @param {Coin} coin - Associated coin
        @param {int} period_hours - Time period in hours
        @param {Dict} period_data - Performance data for the period
        @param {Dict} baseline_data - Baseline data for comparison
        @returns {MonitoringAlert|null} Alert object or None if no exceptional performance
        """
        try:
            price_change = period_data.get('price_change', 0)
            current_price = period_data.get('current_price', 0)
            
            # Check for exceptional positive performance
            if price_change > self.performance_thresholds['price_change_high']:
                # Compare with baseline to see if this is truly exceptional
                baseline_change = self._get_baseline_price_change(baseline_data, period_hours)
                is_truly_exceptional = self._is_performance_exceptional(price_change, baseline_change)
                
                if is_truly_exceptional:
                    return await self._create_performance_alert(
                        coin=coin,
                        alert_type=AlertType.COIN_PERFORMANCE_EXCEPTIONAL,
                        severity=self._determine_severity(price_change, 'positive'),
                        title=f"Exceptional Performance Alert: {coin.symbol}",
                        description=(
                            f"{coin.symbol} shows exceptional positive performance over the last {period_hours} hours.\n\n"
                            f"Price Change: {price_change:+.2f}%\n"
                            f"Current Price: ${current_price:.2f}\n"
                            f"Performance Type: Price Surge\n"
                            f"Baseline Comparison: {baseline_change:+.2f}%"
                        ),
                        metric_type=PerformanceMetric.PRICE_CHANGE.value,
                        performance_value=price_change,
                        baseline_value=baseline_change,
                        deviation_percentage=((price_change - baseline_change) / abs(baseline_change)) * 100 if baseline_change else 0
                    )
            
            # Check for exceptional negative performance
            elif price_change < self.performance_thresholds['price_change_low']:
                # Compare with baseline to see if this is truly exceptional
                baseline_change = self._get_baseline_price_change(baseline_data, period_hours)
                is_truly_exceptional = self._is_performance_exceptional(price_change, baseline_change)
                
                if is_truly_exceptional:
                    return await self._create_performance_alert(
                        coin=coin,
                        alert_type=AlertType.PERFORMANCE_ANOMALY,
                        severity=self._determine_severity(price_change, 'negative'),
                        title=f"Performance Anomaly Alert: {coin.symbol}",
                        description=(
                            f"{coin.symbol} shows significant negative performance over the last {period_hours} hours.\n\n"
                            f"Price Change: {price_change:+.2f}%\n"
                            f"Current Price: ${current_price:.2f}\n"
                            f"Performance Type: Price Drop\n"
                            f"Baseline Comparison: {baseline_change:+.2f}%"
                        ),
                        metric_type=PerformanceMetric.PRICE_CHANGE.value,
                        performance_value=price_change,
                        baseline_value=baseline_change,
                        deviation_percentage=((price_change - baseline_change) / abs(baseline_change)) * 100 if baseline_change else 0
                    )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing price change performance: {e}")
            return None
            
    async def _analyze_volume_spike_performance(
        self,
        coin: Coin,
        period_hours: int,
        period_data: Dict[str, Any],
        baseline_data: Dict[str, Any]
    ) -> Optional[MonitoringAlert]:
        """
        Analyze volume spike performance for unusual trading activity.
        
        @description Analyze volume changes to identify unusual trading activity
        @param {Coin} coin - Associated coin
        @param {int} period_hours - Time period in hours
        @param {Dict} period_data - Performance data for the period
        @param {Dict} baseline_data - Baseline data for comparison
        @returns {MonitoringAlert|null} Alert object or None if no volume spike detected
        """
        try:
            volume_ratio = period_data.get('volume_ratio', 1.0)
            current_volume = period_data.get('current_volume', 0)
            current_price = period_data.get('current_price', 0)
            
            # Check for volume spike
            if volume_ratio > self.performance_thresholds['volume_spike_multiplier']:
                # Get baseline volume for comparison
                baseline_volume = self._get_baseline_volume(baseline_data, period_hours)
                
                return await self._create_performance_alert(
                    coin=coin,
                    alert_type=AlertType.PERFORMANCE_ANOMALY,
                    severity=self._determine_severity_from_multiplier(volume_ratio),
                    title=f"Volume Spike Alert: {coin.symbol}",
                    description=(
                        f"{coin.symbol} shows unusual trading volume over the last {period_hours} hours.\n\n"
                        f"Volume Ratio: {volume_ratio:.1f}x average\n"
                        f"Current Volume: {current_volume:,.0f}\n"
                        f"Current Price: ${current_price:.2f}\n"
                        f"Baseline Volume: {baseline_volume:,.0f}"
                    ),
                    metric_type=PerformanceMetric.VOLUME_SPIKE.value,
                    performance_value=volume_ratio,
                    baseline_value=1.0,  # Normal volume is 1.0x
                    deviation_percentage=(volume_ratio - 1.0) * 100
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing volume spike performance: {e}")
            return None
            
    async def _analyze_trend_strength_performance(
        self,
        coin: Coin,
        period_hours: int,
        period_data: Dict[str, Any]
    ) -> Optional[MonitoringAlert]:
        """
        Analyze trend strength performance for directional momentum.
        
        @description Analyze trend strength to identify strong directional momentum
        @param {Coin} coin - Associated coin
        @param {int} period_hours - Time period in hours
        @param {Dict} period_data - Performance data for the period
        @returns {MonitoringAlert|null} Alert object or None if no strong trend detected
        """
        try:
            prices = period_data.get('prices', [])
            if len(prices) < 10:  # Need sufficient data for trend analysis
                return None
            
            # Calculate trend strength using linear regression
            trend_strength = self._calculate_trend_strength(prices)
            
            # Check for strong trend
            if abs(trend_strength) > self.performance_thresholds['performance_deviation']:
                current_price = period_data.get('current_price', 0)
                price_change = period_data.get('price_change', 0)
                
                trend_direction = "BULLISH" if trend_strength > 0 else "BEARISH"
                
                return await self._create_performance_alert(
                    coin=coin,
                    alert_type=AlertType.MARKET_CONDITION_CHANGE,
                    severity=self._determine_severity_from_trend_strength(trend_strength),
                    title=f"Strong {trend_direction} Trend Alert: {coin.symbol}",
                    description=(
                        f"{coin.symbol} shows strong {trend_direction} momentum over the last {period_hours} hours.\n\n"
                        f"Trend Strength: {trend_strength:.3f}\n"
                        f"Price Change: {price_change:+.2f}%\n"
                        f"Current Price: ${current_price:.2f}\n"
                        f"Analysis: Linear regression trend strength"
                    ),
                    metric_type=PerformanceMetric.TREND_STRENGTH.value,
                    performance_value=trend_strength,
                    baseline_value=0.0,  # No trend is baseline
                    deviation_percentage=abs(trend_strength) * 100
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing trend strength performance: {e}")
            return None
            
    def _calculate_trend_strength(self, prices: List[float]) -> float:
        """
        Calculate trend strength using linear regression.
        
        @description Calculate the strength of price trend using linear regression
        @param {List} prices - List of prices
        @returns {float} Trend strength value (positive for bullish, negative for bearish)
        """
        if len(prices) < 2:
            return 0.0
        
        try:
            # Simple linear regression to calculate trend
            n = len(prices)
            x = list(range(n))
            
            # Calculate means
            mean_x = mean(x)
            mean_y = mean(prices)
            
            # Calculate slope (trend)
            numerator = sum((x[i] - mean_x) * (prices[i] - mean_y) for i in range(n))
            denominator = sum((x[i] - mean_x) ** 2 for i in range(n))
            
            if denominator == 0:
                return 0.0
            
            slope = numerator / denominator
            
            # Normalize slope by average price to get relative trend strength
            avg_price = mean_y
            return slope / avg_price if avg_price > 0 else 0.0
            
        except Exception as e:
            self.logger.error(f"Error calculating trend strength: {e}")
            return 0.0
            
    def _get_baseline_price_change(self, baseline_data: Dict[str, Any], period_hours: int) -> float:
        """
        Get baseline price change for comparison.
        
        @description Get baseline price change from available baseline data
        @param {Dict} baseline_data - Baseline data dictionary
        @param {int} period_hours - Time period in hours
        @returns {float} Baseline price change percentage
        """
        # Try to get exact period match first
        if period_hours in baseline_data:
            return baseline_data[period_hours].get('price_change', 0)
        
        # Otherwise, use the closest available period
        available_periods = [p for p in baseline_data.keys() if p <= period_hours]
        if available_periods:
            closest_period = max(available_periods)
            return baseline_data[closest_period].get('price_change', 0)
        
        return 0.0
        
    def _get_baseline_volume(self, baseline_data: Dict[str, Any], period_hours: int) -> float:
        """
        Get baseline volume for comparison.
        
        @description Get baseline volume from available baseline data
        @param {Dict} baseline_data - Baseline data dictionary
        @param {int} period_hours - Time period in hours
        @returns {float} Baseline volume
        """
        # Try to get exact period match first
        if period_hours in baseline_data:
            return baseline_data[period_hours].get('avg_volume', 0)
        
        # Otherwise, use the closest available period
        available_periods = [p for p in baseline_data.keys() if p <= period_hours]
        if available_periods:
            closest_period = max(available_periods)
            return baseline_data[closest_period].get('avg_volume', 0)
        
        return 0.0
        
    def _is_performance_exceptional(self, current_performance: float, baseline_performance: float) -> bool:
        """
        Check if performance is truly exceptional compared to baseline.
        
        @description Determine if performance deviation from baseline is significant
        @param {float} current_performance - Current performance value
        @param {float} baseline_performance - Baseline performance value
        @returns {bool} True if performance is truly exceptional
        """
        if baseline_performance == 0:
            return abs(current_performance) > self.performance_thresholds['performance_deviation'] * 10
        
        # Calculate performance deviation
        deviation = abs(current_performance - baseline_performance) / abs(baseline_performance)
        
        return deviation > self.performance_thresholds['performance_deviation']
        
    def _determine_severity(self, performance_value: float, direction: str) -> AlertSeverity:
        """
        Determine alert severity based on performance value.
        
        @description Calculate alert severity based on performance metrics
        @param {float} performance_value - Performance value
        @param {str} direction - Direction of performance ('positive' or 'negative')
        @returns {AlertSeverity} Determined severity level
        """
        abs_value = abs(performance_value)
        
        if abs_value >= 0.30:  # 30% or more
            return AlertSeverity.CRITICAL
        elif abs_value >= 0.20:  # 20% or more
            return AlertSeverity.HIGH
        elif abs_value >= 0.10:  # 10% or more
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW
            
    def _determine_severity_from_multiplier(self, multiplier: float) -> AlertSeverity:
        """
        Determine alert severity based on volume multiplier.
        
        @description Calculate alert severity based on volume spike multiplier
        @param {float} multiplier - Volume multiplier (e.g., 3.0 for 3x volume)
        @returns {AlertSeverity} Determined severity level
        """
        if multiplier >= 10.0:  # 10x or more
            return AlertSeverity.CRITICAL
        elif multiplier >= 5.0:  # 5x or more
            return AlertSeverity.HIGH
        elif multiplier >= 3.0:  # 3x or more
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW
            
    def _determine_severity_from_trend_strength(self, trend_strength: float) -> AlertSeverity:
        """
        Determine alert severity based on trend strength.
        
        @description Calculate alert severity based on trend strength
        @param {float} trend_strength - Trend strength value
        @returns {AlertSeverity} Determined severity level
        """
        abs_strength = abs(trend_strength)
        
        if abs_strength >= 0.005:  # Very strong trend
            return AlertSeverity.CRITICAL
        elif abs_strength >= 0.003:  # Strong trend
            return AlertSeverity.HIGH
        elif abs_strength >= 0.001:  # Moderate trend
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW
            
    async def _create_performance_alert(
        self,
        coin: Coin,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        description: str,
        metric_type: str,
        performance_value: float,
        baseline_value: float,
        deviation_percentage: float
    ) -> MonitoringAlert:
        """
        Create a performance monitoring alert.
        
        @description Create a new performance monitoring alert
        @param {Coin} coin - Associated coin
        @param {AlertType} alert_type - Type of alert
        @param {AlertSeverity} severity - Severity level
        @param {str} title - Alert title
        @param {str} description - Alert description
        @param {str} metric_type - Type of performance metric
        @param {float} performance_value - Performance value
        @param {float} baseline_value - Baseline value for comparison
        @param {float} deviation_percentage - Deviation from baseline percentage
        @returns {MonitoringAlert} New monitoring alert instance
        """
        # Check cooldown period
        identifier = f"{coin.symbol}_{metric_type}"
        
        if identifier in self.last_alerts:
            time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
            if time_since_last < self.alert_cooldown_period:
                return None
        
        # Create alert
        alert = MonitoringAlert(
            alert_type=alert_type,
            severity=severity,
            title=title,
            description=description,
            coin=coin,
            threshold_value=baseline_value,
            current_value=performance_value,
            metadata={
                'metric_type': metric_type,
                'performance_value': performance_value,
                'baseline_value': baseline_value,
                'deviation_percentage': deviation_percentage
            },
            context={
                'coin': coin.info(),
                'analysis_timestamp': datetime.utcnow().isoformat()
            }
        )
        
        # Update last alert time
        self.last_alerts[identifier] = datetime.utcnow()
        
        return alert
        
    async def _store_performance_data(
        self,
        coin: Coin,
        alert: MonitoringAlert,
        period_hours: int,
        period_data: Dict[str, Any]
    ):
        """
        Store performance data in the database.
        
        @description Store performance measurement in database for historical tracking
        @param {Coin} coin - Associated coin
        @param {MonitoringAlert} alert - Alert containing performance information
        @param {int} period_hours - Time period in hours
        @param {Dict} period_data - Performance data for the period
        @returns {void}
        """
        try:
            # Convert string metric type to enum
            metric_enum = PerformanceMetric(alert.metadata.get('metric_type'))
            
            # Create performance data record
            performance_data = PerformanceData(
                coin=coin,
                metric_type=metric_enum,
                period=period_hours,
                performance_value=alert.metadata.get('performance_value'),
                baseline_value=alert.metadata.get('baseline_value'),
                deviation_percentage=alert.metadata.get('deviation_percentage'),
                metadata={
                    'alert_id': alert.alert_uuid,
                    'current_price': period_data.get('current_price'),
                    'price_change': period_data.get('price_change'),
                    'current_volume': period_data.get('current_volume'),
                    'avg_volume': period_data.get('avg_volume'),
                    'calculated_at': datetime.utcnow().isoformat(),
                    'analyzer_version': '1.0.0'
                }
            )
            
            # Store in database
            session = self.database.db_session()
            session.add(performance_data)
            session.commit()
            
        except Exception as e:
            self.logger.error(f"Error storing performance data: {e}")
            
    async def generate_report(self, alerts: List[MonitoringAlert]) -> str:
        """
        Generate a performance monitoring report.
        
        @description Generate a human-readable report of performance monitoring findings
        @param {List} alerts - List of alerts to include in the report
        @returns {str} Generated report text
        """
        if not alerts:
            return "✅ No performance alerts generated. All coins showing normal performance patterns."
        
        report_lines = [
            "📈 Coin Performance Monitoring Report",
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
                    coin_symbol = alert.coin.symbol if alert.coin else "Unknown"
                    metric_type = alert.metadata.get('metric_type', 'Unknown')
                    performance_value = alert.metadata.get('performance_value', 0)
                    
                    report_lines.append(f"  • {alert.title}")
                    report_lines.append(f"    Coin: {coin_symbol}")
                    report_lines.append(f"    Metric: {metric_type}")
                    report_lines.append(f"    Performance: {performance_value:+.2f}%")
                
                if len(alerts_by_severity[severity]) > 3:
                    report_lines.append(f"  ... and {len(alerts_by_severity[severity]) - 3} more")
                
                report_lines.append("")
        
        # Summary statistics
        report_lines.append("📊 Summary Statistics:")
        report_lines.append(f"• Coins monitored: {len(self.last_alerts)}")
        report_lines.append(f"• Alert cooldown: {self.alert_cooldown_period} minutes")
        report_lines.append(f"• Performance thresholds: {self.performance_thresholds}")
        
        return "\n".join(report_lines)