"""
Portfolio change monitoring and alerts module.

This module provides functionality to detect significant portfolio value changes
and generate alerts with contextual information and suggested actions.

Created: 2025-08-05
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from .base import MonitoringService, MonitoringAlert, AlertSeverity, AlertType, AlertStatus
from .models import PortfolioData, PortfolioMetric
from ..database import Database
from ..logger import Logger
from ..notifications import NotificationHandler
from ..statistics.manager import StatisticsManager
from ..models import Coin


class PortfolioChangeDirection(Enum):
    """Direction of portfolio value change."""
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"


class PortfolioChangeMonitor(MonitoringService):
    """
    Service for monitoring portfolio value changes and generating alerts.
    
    This service tracks portfolio value changes and generates alerts when
    significant changes are detected, with contextual information and suggested actions.
    """
    
    def __init__(
        self,
        database: Database,
        logger: Logger,
        notifications: NotificationHandler,
        config: Dict[str, Any],
        statistics_manager: StatisticsManager
    ):
        """
        Initialize the portfolio change monitor.
        
        @description Create a new portfolio change monitor instance
        @param {Database} database - Database connection for data storage
        @param {Logger} logger - Logger instance for logging
        @param {NotificationHandler} notifications - Notification handler for alerts
        @param {Dict} config - Configuration dictionary for portfolio monitoring settings
        @param {StatisticsManager} statistics_manager - Statistics manager for portfolio calculations
        @returns {PortfolioChangeMonitor} New portfolio change monitor instance
        """
        super().__init__(database, logger, notifications, config)
        
        self.statistics_manager = statistics_manager
        
        # Configuration settings
        self.portfolio_change_thresholds = config.get('portfolio_change_thresholds', {
            'low': 0.05,      # 5%
            'medium': 0.10,   # 10%
            'high': 0.20,     # 20%
            'critical': 0.30  # 30%
        })
        
        self.portfolio_change_periods = config.get('portfolio_change_periods', [1, 6, 24, 168])  # 1h, 6h, 24h, 1w
        self.portfolio_metrics = config.get('portfolio_metrics', [
            PortfolioMetric.TOTAL_VALUE_CHANGE.value,
            PortfolioMetric.ALLOCATION_CHANGE.value,
            PortfolioMetric.ROI_CHANGE.value,
            PortfolioMetric.RISK_ADJUSTED_RETURN.value
        ])
        
        # Alert cooldown settings
        self.alert_cooldown_period = config.get('alert_cooldown_period', 120)  # 120 minutes
        self.last_alerts: Dict[str, datetime] = {}  # metric_period -> last alert time
        
        # Rate limiting settings
        self.max_alerts_per_period = config.get('max_alerts_per_period', 5)
        self.rate_limit_period = config.get('rate_limit_period', 60)  # 60 minutes
        self.alert_counts: Dict[str, List[datetime]] = {}  # identifier -> alert timestamps
        
        # Priority system settings
        self.priority_weights = config.get('priority_weights', {
            'severity': 0.5,
            'frequency': 0.3,
            'impact': 0.2
        })
        
    async def collect_data(self) -> Dict[str, Any]:
        """
        Collect portfolio data for change analysis.
        
        @description Collect current and historical portfolio data for analysis
        @returns {Dict} Dictionary containing collected portfolio data
        """
        self.logger.info("Starting portfolio data collection")
        
        data = {
            'current_portfolio': {},
            'historical_portfolio': {},
            'timestamp': datetime.utcnow()
        }
        
        try:
            # Get current portfolio data
            current_portfolio = await self._collect_current_portfolio_data()
            data['current_portfolio'] = current_portfolio
            
            # Get historical portfolio data
            historical_portfolio = await self._collect_historical_portfolio_data()
            data['historical_portfolio'] = historical_portfolio
            
            self.logger.info(f"Collected portfolio data for {len(current_portfolio)} coins")
            return data
            
        except Exception as e:
            self.logger.error(f"Error collecting portfolio data: {e}")
            raise
            
    async def _collect_current_portfolio_data(self) -> Dict[str, Any]:
        """
        Collect current portfolio data.
        
        @description Collect current portfolio composition and values
        @returns {Dict} Dictionary containing current portfolio data
        """
        try:
            # Get current portfolio from statistics manager
            portfolio_stats = await self.statistics_manager.get_portfolio_statistics()
            
            current_portfolio = {
                'total_value': portfolio_stats.get('total_value', 0.0),
                'total_profit_loss': portfolio_stats.get('total_profit_loss', 0.0),
                'total_profit_loss_percentage': portfolio_stats.get('total_profit_loss_percentage', 0.0),
                'roi': portfolio_stats.get('roi', 0.0),
                'coins': {}
            }
            
            # Get individual coin data
            coins = self.database.get_coins()
            for coin in coins:
                coin_value = await self.statistics_manager.get_coin_statistics(coin.symbol)
                if coin_value:
                    current_portfolio['coins'][coin.symbol] = {
                        'balance': coin_value.get('balance', 0.0),
                        'usd_value': coin_value.get('usd_value', 0.0),
                        'allocation': coin_value.get('allocation', 0.0),
                        'price': coin_value.get('current_price', 0.0),
                        'price_change_24h': coin_value.get('price_change_24h', 0.0)
                    }
            
            return current_portfolio
            
        except Exception as e:
            self.logger.error(f"Error collecting current portfolio data: {e}")
            return {}
            
    async def _collect_historical_portfolio_data(self) -> Dict[str, Any]:
        """
        Collect historical portfolio data for comparison.
        
        @description Collect historical portfolio data for change analysis
        @returns {Dict} Dictionary containing historical portfolio data
        """
        try:
            historical_data = {}
            
            for period_hours in self.portfolio_change_periods:
                period_minutes = period_hours * 60
                
                try:
                    # Get portfolio statistics for the historical period
                    end_time = datetime.utcnow()
                    start_time = end_time - timedelta(hours=period_hours)
                    
                    historical_stats = await self.statistics_manager.get_portfolio_statistics(
                        start_time=start_time,
                        end_time=end_time
                    )
                    
                    if historical_stats:
                        historical_data[period_hours] = {
                            'total_value': historical_stats.get('total_value', 0.0),
                            'total_profit_loss': historical_stats.get('total_profit_loss', 0.0),
                            'total_profit_loss_percentage': historical_stats.get('total_profit_loss_percentage', 0.0),
                            'roi': historical_stats.get('roi', 0.0),
                            'timestamp': start_time.isoformat()
                        }
                        
                except Exception as e:
                    self.logger.warning(f"Failed to get historical data for {period_hours}h: {e}")
                    continue
            
            return historical_data
            
        except Exception as e:
            self.logger.error(f"Error collecting historical portfolio data: {e}")
            return {}
            
    async def analyze_data(self, data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze portfolio data and detect significant changes.
        
        @description Analyze portfolio data to identify significant value changes
        @param {Dict} data - Collected portfolio data
        @returns {List} List of portfolio change alerts
        """
        self.logger.info("Starting portfolio change analysis")
        
        alerts = []
        
        try:
            current_portfolio = data.get('current_portfolio', {})
            historical_portfolio = data.get('historical_portfolio', {})
            
            # Analyze different portfolio metrics
            for period_hours in self.portfolio_change_periods:
                if period_hours not in historical_portfolio:
                    continue
                
                period_alerts = await self._analyze_portfolio_period(
                    current_portfolio=current_portfolio,
                    historical_portfolio=historical_portfolio,
                    period_hours=period_hours
                )
                alerts.extend(period_alerts)
            
            # Apply rate limiting
            alerts = await self._apply_rate_limiting(alerts)
            
            self.logger.info(f"Generated {len(alerts)} portfolio change alerts")
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing portfolio data: {e}")
            return []
            
    async def _analyze_portfolio_period(
        self,
        current_portfolio: Dict[str, Any],
        historical_portfolio: Dict[str, Any],
        period_hours: int
    ) -> List[MonitoringAlert]:
        """
        Analyze portfolio changes for a specific time period.
        
        @description Analyze portfolio changes for a specific time period
        @param {Dict} current_portfolio - Current portfolio data
        @param {Dict} historical_portfolio - Historical portfolio data
        @param {int} period_hours - Time period in hours
        @returns {List} List of portfolio change alerts
        """
        alerts = []
        
        try:
            historical_data = historical_portfolio.get(period_hours, {})
            if not historical_data:
                return alerts
            
            # Analyze total value change
            value_change_alert = await self._analyze_total_value_change(
                current_portfolio=current_portfolio,
                historical_data=historical_data,
                period_hours=period_hours
            )
            if value_change_alert:
                alerts.append(value_change_alert)
            
            # Analyze allocation changes
            allocation_change_alert = await self._analyze_allocation_change(
                current_portfolio=current_portfolio,
                historical_data=historical_data,
                period_hours=period_hours
            )
            if allocation_change_alert:
                alerts.append(allocation_change_alert)
            
            # Analyze ROI change
            roi_change_alert = await self._analyze_roi_change(
                current_portfolio=current_portfolio,
                historical_data=historical_data,
                period_hours=period_hours
            )
            if roi_change_alert:
                alerts.append(roi_change_alert)
            
            # Analyze risk-adjusted return change
            risk_adjusted_alert = await self._analyze_risk_adjusted_return_change(
                current_portfolio=current_portfolio,
                historical_data=historical_data,
                period_hours=period_hours
            )
            if risk_adjusted_alert:
                alerts.append(risk_adjusted_alert)
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing portfolio period {period_hours}h: {e}")
            return []
            
    async def _analyze_total_value_change(
        self,
        current_portfolio: Dict[str, Any],
        historical_data: Dict[str, Any],
        period_hours: int
    ) -> Optional[MonitoringAlert]:
        """
        Analyze total portfolio value change.
        
        @description Analyze change in total portfolio value
        @param {Dict} current_portfolio - Current portfolio data
        @param {Dict} historical_data - Historical portfolio data
        @param {int} period_hours - Time period in hours
        @returns {MonitoringAlert|null} Alert object or None if no significant change
        """
        try:
            current_value = current_portfolio.get('total_value', 0.0)
            historical_value = historical_data.get('total_value', 0.0)
            
            if historical_value <= 0:
                return None
            
            # Calculate percentage change
            percentage_change = ((current_value - historical_value) / historical_value) * 100
            
            # Check if change exceeds threshold
            if abs(percentage_change) < self.portfolio_change_thresholds['low']:
                return None
            
            # Determine direction and severity
            direction = PortfolioChangeDirection.INCREASE if percentage_change > 0 else PortfolioChangeDirection.DECREASE
            severity = self._determine_severity(percentage_change)
            
            # Generate alert
            return await self._create_portfolio_change_alert(
                alert_type=AlertType.MARKET_CONDITION_CHANGE,
                severity=severity,
                title=f"Portfolio Value {direction.value.title()} Alert",
                description=(
                    f"Portfolio value has {direction.value.lower()} by {abs(percentage_change):.2f}% "
                    f"over the last {period_hours} hours.\n\n"
                    f"Current Value: ${current_value:,.2f}\n"
                    f"Previous Value: ${historical_value:,.2f}\n"
                    f"Change Amount: ${current_value - historical_value:,.2f}\n"
                    f"Change Percentage: {percentage_change:+.2f}%"
                ),
                metric_type=PortfolioMetric.TOTAL_VALUE_CHANGE.value,
                current_value=current_value,
                historical_value=historical_value,
                percentage_change=percentage_change,
                period_hours=period_hours,
                direction=direction,
                suggested_actions=self._get_suggested_actions_for_value_change(percentage_change, direction)
            )
            
        except Exception as e:
            self.logger.error(f"Error analyzing total value change: {e}")
            return None
            
    async def _analyze_allocation_change(
        self,
        current_portfolio: Dict[str, Any],
        historical_data: Dict[str, Any],
        period_hours: int
    ) -> Optional[MonitoringAlert]:
        """
        Analyze portfolio allocation changes.
        
        @description Analyze changes in coin allocation within portfolio
        @param {Dict} current_portfolio - Current portfolio data
        @param {Dict} historical_data - Historical portfolio data
        @param {int} period_hours - Time period in hours
        @returns {MonitoringAlert|null} Alert object or None if no significant change
        """
        try:
            current_coins = current_portfolio.get('coins', {})
            # Note: Historical allocation data would need to be stored differently
            # For now, we'll analyze current allocation for extreme concentrations
            
            # Check for extreme allocations
            extreme_allocations = []
            for coin_symbol, coin_data in current_coins.items():
                allocation = coin_data.get('allocation', 0.0)
                if allocation > 50.0:  # More than 50% in one coin
                    extreme_allocations.append({
                        'coin': coin_symbol,
                        'allocation': allocation,
                        'usd_value': coin_data.get('usd_value', 0.0)
                    })
            
            if not extreme_allocations:
                return None
            
            # Determine severity based on maximum allocation
            max_allocation = max(alloc['allocation'] for alloc in extreme_allocations)
            severity = self._determine_severity_from_allocation(max_allocation)
            
            # Generate alert
            return await self._create_portfolio_change_alert(
                alert_type=AlertType.MARKET_CONDITION_CHANGE,
                severity=severity,
                title="Portfolio Allocation Imbalance Alert",
                description=(
                    f"Portfolio shows significant allocation imbalance with {len(extreme_allocations)} "
                    f"coin(s) representing more than 50% of total value.\n\n"
                    f"Most Concentrated: {extreme_allocations[0]['coin']} ({extreme_allocations[0]['allocation']:.1f}%)\n"
                    f"Total Concentrated: {sum(alloc['allocation'] for alloc in extreme_allocations):.1f}%\n"
                    f"Period: {period_hours} hours"
                ),
                metric_type=PortfolioMetric.ALLOCATION_CHANGE.value,
                current_value=max_allocation,
                percentage_change=max_allocation,
                period_hours=period_hours,
                direction=PortfolioChangeDirection.INCREASE,
                extreme_allocations=extreme_allocations,
                suggested_actions=self._get_suggested_actions_for_allocation_imbalance(extreme_allocations)
            )
            
        except Exception as e:
            self.logger.error(f"Error analyzing allocation change: {e}")
            return None
            
    async def _analyze_roi_change(
        self,
        current_portfolio: Dict[str, Any],
        historical_data: Dict[str, Any],
        period_hours: int
    ) -> Optional[MonitoringAlert]:
        """
        Analyze ROI (Return on Investment) change.
        
        @description Analyze change in portfolio ROI
        @param {Dict} current_portfolio - Current portfolio data
        @param {Dict} historical_data - Historical portfolio data
        @param {int} period_hours - Time period in hours
        @returns {MonitoringAlert|null} Alert object or None if no significant change
        """
        try:
            current_roi = current_portfolio.get('roi', 0.0)
            historical_roi = historical_data.get('roi', 0.0)
            
            # Calculate ROI change
            roi_change = current_roi - historical_roi
            
            # Check if ROI change exceeds threshold
            if abs(roi_change) < self.portfolio_change_thresholds['low']:
                return None
            
            # Determine direction and severity
            direction = PortfolioChangeDirection.INCREASE if roi_change > 0 else PortfolioChangeDirection.DECREASE
            severity = self._determine_severity_from_roi_change(roi_change)
            
            # Generate alert
            return await self._create_portfolio_change_alert(
                alert_type=AlertType.MARKET_CONDITION_CHANGE,
                severity=severity,
                title=f"Portfolio ROI {direction.value.title()} Alert",
                description=(
                    f"Portfolio ROI has {direction.value.lower()} by {abs(roi_change):.2%} "
                    f"over the last {period_hours} hours.\n\n"
                    f"Current ROI: {current_roi:.2%}\n"
                    f"Previous ROI: {historical_roi:.2%}\n"
                    f"ROI Change: {roi_change:+.2%}"
                ),
                metric_type=PortfolioMetric.ROI_CHANGE.value,
                current_value=current_roi,
                historical_value=historical_roi,
                percentage_change=roi_change,
                period_hours=period_hours,
                direction=direction,
                suggested_actions=self._get_suggested_actions_for_roi_change(roi_change, direction)
            )
            
        except Exception as e:
            self.logger.error(f"Error analyzing ROI change: {e}")
            return None
            
    async def _analyze_risk_adjusted_return_change(
        self,
        current_portfolio: Dict[str, Any],
        historical_data: Dict[str, Any],
        period_hours: int
    ) -> Optional[MonitoringAlert]:
        """
        Analyze risk-adjusted return change.
        
        @description Analyze change in risk-adjusted portfolio returns
        @param {Dict} current_portfolio - Current portfolio data
        @param {Dict} historical_data - Historical portfolio data
        @param {int} period_hours - Time period in hours
        @returns {MonitoringAlert|null} Alert object or None if no significant change
        """
        try:
            # This is a simplified risk-adjusted return calculation
            # In a real implementation, you'd use metrics like Sharpe ratio, Sortino ratio, etc.
            current_roi = current_portfolio.get('roi', 0.0)
            current_volatility = current_portfolio.get('volatility', 0.1)  # Default 10% if not available
            
            historical_roi = historical_data.get('roi', 0.0)
            historical_volatility = historical_data.get('volatility', 0.1)
            
            # Calculate risk-adjusted returns (simplified Sharpe ratio approximation)
            current_sharpe = current_roi / current_volatility if current_volatility > 0 else 0
            historical_sharpe = historical_roi / historical_volatility if historical_volatility > 0 else 0
            
            sharpe_change = current_sharpe - historical_sharpe
            
            # Check if risk-adjusted return change exceeds threshold
            if abs(sharpe_change) < 0.1:  # 0.1 threshold for Sharpe ratio change
                return None
            
            # Determine direction and severity
            direction = PortfolioChangeDirection.INCREASE if sharpe_change > 0 else PortfolioChangeDirection.DECREASE
            severity = self._determine_severity_from_risk_adjusted_change(sharpe_change)
            
            # Generate alert
            return await self._create_portfolio_change_alert(
                alert_type=AlertType.MARKET_CONDITION_CHANGE,
                severity=severity,
                title=f"Risk-Adjusted Return {direction.value.title()} Alert",
                description=(
                    f"Portfolio risk-adjusted return has {direction.value.lower()} "
                    f"by {abs(sharpe_change):.3f} over the last {period_hours} hours.\n\n"
                    f"Current Sharpe Ratio: {current_sharpe:.3f}\n"
                    f"Previous Sharpe Ratio: {historical_sharpe:.3f}\n"
                    f"ROI: {current_roi:.2%}\n"
                    f"Volatility: {current_volatility:.2%}"
                ),
                metric_type=PortfolioMetric.RISK_ADJUSTED_RETURN.value,
                current_value=current_sharpe,
                historical_value=historical_sharpe,
                percentage_change=sharpe_change,
                period_hours=period_hours,
                direction=direction,
                suggested_actions=self._get_suggested_actions_for_risk_adjusted_change(sharpe_change, direction)
            )
            
        except Exception as e:
            self.logger.error(f"Error analyzing risk-adjusted return change: {e}")
            return None
            
    def _determine_severity(self, percentage_change: float) -> AlertSeverity:
        """
        Determine alert severity based on percentage change.
        
        @description Calculate alert severity based on percentage change
        @param {float} percentage_change - Percentage change value
        @returns {AlertSeverity} Determined severity level
        """
        abs_change = abs(percentage_change)
        
        if abs_change >= self.portfolio_change_thresholds['critical']:
            return AlertSeverity.CRITICAL
        elif abs_change >= self.portfolio_change_thresholds['high']:
            return AlertSeverity.HIGH
        elif abs_change >= self.portfolio_change_thresholds['medium']:
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW
            
    def _determine_severity_from_allocation(self, allocation_percentage: float) -> AlertSeverity:
        """
        Determine alert severity based on allocation concentration.
        
        @description Calculate alert severity based on allocation concentration
        @param {float} allocation_percentage - Allocation percentage
        @returns {AlertSeverity} Determined severity level
        """
        if allocation_percentage >= 80.0:  # 80% or more
            return AlertSeverity.CRITICAL
        elif allocation_percentage >= 60.0:  # 60% or more
            return AlertSeverity.HIGH
        elif allocation_percentage >= 50.0:  # 50% or more
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW
            
    def _determine_severity_from_roi_change(self, roi_change: float) -> AlertSeverity:
        """
        Determine alert severity based on ROI change.
        
        @description Calculate alert severity based on ROI change
        @param {float} roi_change - ROI change value
        @returns {AlertSeverity} Determined severity level
        """
        abs_change = abs(roi_change)
        
        if abs_change >= 0.15:  # 15% or more
            return AlertSeverity.CRITICAL
        elif abs_change >= 0.10:  # 10% or more
            return AlertSeverity.HIGH
        elif abs_change >= 0.05:  # 5% or more
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW
            
    def _determine_severity_from_risk_adjusted_change(self, sharpe_change: float) -> AlertSeverity:
        """
        Determine alert severity based on risk-adjusted return change.
        
        @description Calculate alert severity based on risk-adjusted return change
        @param {float} sharpe_change - Sharpe ratio change value
        @returns {AlertSeverity} Determined severity level
        """
        abs_change = abs(sharpe_change)
        
        if abs_change >= 0.5:  # 0.5 or more
            return AlertSeverity.CRITICAL
        elif abs_change >= 0.3:  # 0.3 or more
            return AlertSeverity.HIGH
        elif abs_change >= 0.15:  # 0.15 or more
            return AlertSeverity.MEDIUM
        else:
            return AlertSeverity.LOW
            
    async def _create_portfolio_change_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        description: str,
        metric_type: str,
        current_value: float,
        historical_value: float,
        percentage_change: float,
        period_hours: int,
        direction: PortfolioChangeDirection,
        suggested_actions: List[str],
        **kwargs
    ) -> Optional[MonitoringAlert]:
        """
        Create a portfolio change monitoring alert.
        
        @description Create a new portfolio change monitoring alert
        @param {AlertType} alert_type - Type of alert
        @param {AlertSeverity} severity - Severity level
        @param {str} title - Alert title
        @param {str} description - Alert description
        @param {str} metric_type - Type of portfolio metric
        @param {float} current_value - Current metric value
        @param {float} historical_value - Historical metric value
        @param {float} percentage_change - Percentage change
        @param {int} period_hours - Time period in hours
        @param {PortfolioChangeDirection} direction - Direction of change
        @param {List} suggested_actions - List of suggested actions
        @returns {MonitoringAlert|null} New monitoring alert instance or None if rate limited
        """
        # Check cooldown period
        identifier = f"{metric_type}_{period_hours}"
        
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
            threshold_value=historical_value,
            current_value=current_value,
            metadata={
                'metric_type': metric_type,
                'current_value': current_value,
                'historical_value': historical_value,
                'percentage_change': percentage_change,
                'period_hours': period_hours,
                'direction': direction.value,
                'suggested_actions': suggested_actions,
                'generated_at': datetime.utcnow().isoformat()
            },
            context={
                'portfolio_summary': {
                    'total_change': percentage_change,
                    'period': f"{period_hours}h",
                    'metric': metric_type
                }
            }
        )
        
        # Update last alert time
        self.last_alerts[identifier] = datetime.utcnow()
        
        return alert
        
    def _get_suggested_actions_for_value_change(self, percentage_change: float, direction: PortfolioChangeDirection) -> List[str]:
        """
        Get suggested actions for portfolio value change.
        
        @description Generate suggested actions based on value change
        @param {float} percentage_change - Percentage change
        @param {PortfolioChangeDirection} direction - Direction of change
        @returns {List} List of suggested actions
        """
        actions = []
        
        if direction == PortfolioChangeDirection.INCREASE:
            if percentage_change > 20.0:
                actions.append("Consider taking profits to lock in gains")
                actions.append("Rebalance portfolio to maintain target allocations")
            elif percentage_change > 10.0:
                actions.append("Monitor for potential overvaluation")
                actions.append("Consider partial profit taking")
        else:  # DECREASE
            if percentage_change < -20.0:
                actions.append("Review portfolio risk management strategy")
                actions.append("Consider defensive positioning if market conditions have changed")
            elif percentage_change < -10.0:
                actions.append("Monitor for potential buying opportunities")
                actions.append("Review individual coin fundamentals")
        
        actions.append("Check market conditions and news")
        actions.append("Verify trading bot performance and settings")
        
        return actions
        
    def _get_suggested_actions_for_allocation_imbalance(self, extreme_allocations: List[Dict]) -> List[str]:
        """
        Get suggested actions for portfolio allocation imbalance.
        
        @description Generate suggested actions for allocation imbalance
        @param {List} extreme_allocations - List of extreme allocations
        @returns {List} List of suggested actions
        """
        actions = [
            "Consider rebalancing portfolio to reduce concentration risk",
            "Review risk tolerance for concentrated positions",
            "Dollar-cost averaging into underallocated coins",
            "Consider setting up stop-loss orders for concentrated positions"
        ]
        
        return actions
        
    def _get_suggested_actions_for_roi_change(self, roi_change: float, direction: PortfolioChangeDirection) -> List[str]:
        """
        Get suggested actions for ROI change.
        
        @description Generate suggested actions based on ROI change
        @param {float} roi_change - ROI change
        @param {PortfolioChangeDirection} direction - Direction of change
        @returns {List} List of suggested actions
        """
        actions = []
        
        if direction == PortfolioChangeDirection.INCREASE:
            actions.append("Review successful strategies and consider scaling")
            actions.append("Monitor for sustainability of high returns")
        else:  # DECREASE
            actions.append("Review underperforming positions")
            actions.append("Consider adjusting trading parameters")
            actions.append("Check for market regime changes")
        
        actions.append("Verify risk management settings are appropriate")
        actions.append("Consider diversification strategies")
        
        return actions
        
    def _get_suggested_actions_for_risk_adjusted_change(self, sharpe_change: float, direction: PortfolioChangeDirection) -> List[str]:
        """
        Get suggested actions for risk-adjusted return change.
        
        @description Generate suggested actions based on risk-adjusted return change
        @param {float} sharpe_change - Sharpe ratio change
        @param {PortfolioChangeDirection} direction - Direction of change
        @returns {List} List of suggested actions
        """
        actions = []
        
        if direction == PortfolioChangeDirection.INCREASE:
            actions.append("Consider maintaining current strategy if risk-adjusted returns improved")
            actions.append("Review what factors contributed to improved risk-adjusted returns")
        else:  # DECREASE
            actions.append("Review risk management and position sizing")
            actions.append("Consider adjusting strategy parameters")
            actions.append("Check for increased volatility or correlation")
        
        actions.append("Monitor portfolio correlation and diversification")
        actions.append("Consider alternative strategies if risk-adjusted returns remain poor")
        
        return actions
        
    async def _apply_rate_limiting(self, alerts: List[MonitoringAlert]) -> List[MonitoringAlert]:
        """
        Apply rate limiting to alerts to prevent spam.
        
        @description Apply rate limiting to reduce alert frequency
        @param {List} alerts - List of potential alerts
        @returns {List} Filtered list of alerts after rate limiting
        """
        if not alerts:
            return alerts
        
        filtered_alerts = []
        current_time = datetime.utcnow()
        
        for alert in alerts:
            # Create identifier for rate limiting
            identifier = f"{alert.alert_type.value}_{alert.severity.value}"
            
            # Initialize alert count list if not exists
            if identifier not in self.alert_counts:
                self.alert_counts[identifier] = []
            
            # Remove old alerts outside the rate limit period
            self.alert_counts[identifier] = [
                timestamp for timestamp in self.alert_counts[identifier]
                if (current_time - timestamp).total_seconds() / 60 < self.rate_limit_period
            ]
            
            # Check if we can send this alert
            if len(self.alert_counts[identifier]) < self.max_alerts_per_period:
                filtered_alerts.append(alert)
                self.alert_counts[identifier].append(current_time)
        
        return filtered_alerts
        
    async def _send_notifications(self, alerts: List[MonitoringAlert]):
        """
        Send notifications for portfolio change alerts.
        
        @description Send notifications for generated alerts
        @param {List} alerts - List of alerts to send notifications for
        @returns {void}
        """
        if not alerts:
            return
        
        # Group alerts by priority for notification batching
        priority_groups = {
            AlertSeverity.CRITICAL: [],
            AlertSeverity.HIGH: [],
            AlertSeverity.MEDIUM: [],
            AlertSeverity.LOW: []
        }
        
        for alert in alerts:
            priority_groups[alert.severity].append(alert)
        
        # Send notifications for each priority level
        for severity, severity_alerts in priority_groups.items():
            if severity_alerts:
                await self._send_priority_notifications(severity, severity_alerts)
                
    async def _send_priority_notifications(self, severity: AlertSeverity, alerts: List[MonitoringAlert]):
        """
        Send priority-based notifications.
        
        @description Send notifications based on alert priority
        @param {AlertSeverity} severity - Severity level
        @param {List} alerts - List of alerts for this severity
        @returns {void}
        """
        try:
            # Create summary message for all alerts of this severity
            summary_message = self._create_priority_summary_message(severity, alerts)
            
            # Send summary notification
            self.notifications.send_notification(summary_message)
            
            # Send individual notifications for critical alerts
            if severity == AlertSeverity.CRITICAL:
                for alert in alerts:
                    individual_message = self._create_individual_alert_message(alert)
                    self.notifications.send_notification(individual_message)
                    
        except Exception as e:
            self.logger.error(f"Error sending priority notifications: {e}")
            
    def _create_priority_summary_message(self, severity: AlertSeverity, alerts: List[MonitoringAlert]) -> str:
        """
        Create a summary message for priority-based notifications.
        
        @description Create summary message for priority notifications
        @param {AlertSeverity} severity - Severity level
        @param {List} alerts - List of alerts
        @returns {str} Summary message
        """
        emoji_map = {
            AlertSeverity.CRITICAL: "🚨",
            AlertSeverity.HIGH: "⚠️",
            AlertSeverity.MEDIUM: "⚡",
            AlertSeverity.LOW: "ℹ️"
        }
        
        emoji = emoji_map.get(severity, "📊")
        count = len(alerts)
        
        if severity == AlertSeverity.CRITICAL:
            return f"{emoji} CRITICAL: {count} critical portfolio change detected. Immediate attention required."
        elif severity == AlertSeverity.HIGH:
            return f"{emoji} HIGH: {count} high-priority portfolio changes detected. Review recommended."
        elif severity == AlertSeverity.MEDIUM:
            return f"{emoji} MEDIUM: {count} medium-priority portfolio changes detected."
        else:
            return f"{emoji} LOW: {count} low-priority portfolio changes detected."
            
    def _create_individual_alert_message(self, alert: MonitoringAlert) -> str:
        """
        Create an individual alert message.
        
        @description Create individual alert message
        @param {MonitoringAlert} alert - Alert to create message for
        @returns {str} Individual alert message
        """
        suggested_actions = alert.metadata.get('suggested_actions', [])
        actions_text = "\n".join(f"• {action}" for action in suggested_actions[:3])  # Top 3 actions
        
        return (
            f"📊 Portfolio Alert: {alert.title}\n\n"
            f"{alert.description}\n\n"
            f"Severity: {alert.severity.value}\n"
            f"Suggested Actions:\n{actions_text}"
        )
        
    async def _store_alerts(self, alerts: List[MonitoringAlert]):
        """
        Store portfolio change alerts in the database.
        
        @description Store portfolio change alerts in database
        @param {List} alerts - List of alerts to store
        @returns {void}
        """
        try:
            session = self.database.db_session()
            
            for alert in alerts:
                # Create portfolio data record
                portfolio_data = PortfolioData(
                    alert_uuid=alert.alert_uuid,
                    metric_type=PortfolioMetric(alert.metadata.get('metric_type')),
                    period_hours=alert.metadata.get('period_hours', 1),
                    current_value=alert.metadata.get('current_value'),
                    historical_value=alert.metadata.get('historical_value'),
                    percentage_change=alert.metadata.get('percentage_change'),
                    direction=alert.metadata.get('direction'),
                    severity=alert.severity,
                    metadata_json=str(alert.metadata),
                    context_json=str(alert.context),
                    calculated_at=datetime.utcnow()
                )
                
                session.add(portfolio_data)
            
            session.commit()
            
        except Exception as e:
            self.logger.error(f"Error storing portfolio change alerts: {e}")
            
    async def generate_report(self, alerts: List[MonitoringAlert]) -> str:
        """
        Generate a portfolio change monitoring report.
        
        @description Generate a human-readable report of portfolio change monitoring findings
        @param {List} alerts - List of alerts to include in the report
        @returns {str} Generated report text
        """
        if not alerts:
            return "✅ No portfolio change alerts generated. Portfolio value changes are within normal ranges."
        
        report_lines = [
            "💼 Portfolio Change Monitoring Report",
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
                    metric_type = alert.metadata.get('metric_type', 'Unknown')
                    percentage_change = alert.metadata.get('percentage_change', 0)
                    period_hours = alert.metadata.get('period_hours', 1)
                    
                    report_lines.append(f"  • {alert.title}")
                    report_lines.append(f"    Metric: {metric_type}")
                    report_lines.append(f"    Change: {percentage_change:+.2f}%")
                    report_lines.append(f"    Period: {period_hours}h")
                    
                    # Show suggested actions
                    suggested_actions = alert.metadata.get('suggested_actions', [])
                    if suggested_actions:
                        report_lines.append(f"    Actions: {', '.join(suggested_actions[:2])}")
                
                if len(alerts_by_severity[severity]) > 3:
                    report_lines.append(f"  ... and {len(alerts_by_severity[severity]) - 3} more")
                
                report_lines.append("")
        
        # Summary statistics
        report_lines.append("📊 Summary Statistics:")
        report_lines.append(f"• Total portfolio changes monitored: {len(self.last_alerts)}")
        report_lines.append(f"• Alert cooldown: {self.alert_cooldown_period} minutes")
        report_lines.append(f"• Rate limit: {self.max_alerts_per_period} alerts per {self.rate_limit_period} minutes")
        report_lines.append(f"• Change thresholds: {self.portfolio_change_thresholds}")
        
        return "\n".join(report_lines)