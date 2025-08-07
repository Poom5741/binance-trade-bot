"""
Base monitoring service class for the intelligent alert system.

This module provides the foundation for all monitoring components including
common functionality for data collection, analysis, and alert generation.

Created: 2025-08-05
"""

import abc
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from ..database import Database
from ..logger import Logger
from ..notifications import NotificationHandler
from ..models import Coin, Pair


class AlertSeverity(Enum):
    """Alert severity levels for monitoring events."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertType(Enum):
    """Alert types for different monitoring scenarios."""
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    PERFORMANCE_ANOMALY = "PERFORMANCE_ANOMALY"
    TRADING_FREQUENCY_EXCEEDED = "TRADING_FREQUENCY_EXCEEDED"
    API_ERROR_THRESHOLD = "API_ERROR_THRESHOLD"
    MARKET_CONDITION_CHANGE = "MARKET_CONDITION_CHANGE"
    COIN_PERFORMANCE_EXCEPTIONAL = "COIN_PERFORMANCE_EXCEPTIONAL"
    PORTFOLIO_VALUE_CHANGE = "PORTFOLIO_VALUE_CHANGE"


class AlertStatus(Enum):
    """Alert status tracking."""
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"


class MonitoringAlert:
    """
    Represents a monitoring alert with severity, type, and status tracking.
    """
    
    def __init__(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        description: str,
        coin: Optional[Coin] = None,
        pair: Optional[Pair] = None,
        metadata: Optional[Dict[str, Any]] = None,
        threshold_value: Optional[float] = None,
        current_value: Optional[float] = None,
    ):
        """
        Initialize a monitoring alert.
        
        @description Create a new monitoring alert with specified parameters
        @param {AlertType} alert_type - Type of alert being triggered
        @param {AlertSeverity} severity - Severity level of the alert
        @param {str} title - Brief title describing the alert
        @param {str} description - Detailed description of the alert
        @param {Coin} coin - Optional coin associated with the alert
        @param {Pair} pair - Optional trading pair associated with the alert
        @param {Dict} metadata - Additional metadata for the alert
        @param {float} threshold_value - Threshold value that was exceeded
        @param {float} current_value - Current value that triggered the alert
        @returns {MonitoringAlert} New monitoring alert instance
        """
        self.alert_type = alert_type
        self.severity = severity
        self.title = title
        self.description = description
        self.coin = coin
        self.pair = pair
        self.metadata = metadata or {}
        self.threshold_value = threshold_value
        self.current_value = current_value
        self.status = AlertStatus.ACTIVE
        self.created_at = datetime.utcnow()
        self.acknowledged_at = None
        self.resolved_at = None
        
    def acknowledge(self):
        """
        Acknowledge the alert.
        
        @description Mark alert as acknowledged
        @returns {void}
        """
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.utcnow()
        
    def resolve(self):
        """
        Resolve the alert.
        
        @description Mark alert as resolved
        @returns {void}
        """
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.utcnow()
        
    def suppress(self):
        """
        Suppress the alert.
        
        @description Mark alert as suppressed (temporarily ignored)
        @returns {void}
        """
        self.status = AlertStatus.SUPPRESSED
        
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert alert to dictionary representation.
        
        @description Convert alert object to serializable dictionary
        @returns {Dict} Dictionary representation of the alert
        """
        return {
            'alert_type': self.alert_type.value,
            'severity': self.severity.value,
            'title': self.title,
            'description': self.description,
            'coin': self.coin.info() if self.coin else None,
            'pair': self.pair.info() if self.pair else None,
            'metadata': self.metadata,
            'threshold_value': self.threshold_value,
            'current_value': self.current_value,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
        }


class MonitoringService(abc.ABC):
    """
    Abstract base class for all monitoring services.
    
    Provides common functionality for data collection, analysis, and alert generation.
    """
    
    def __init__(
        self,
        database: Database,
        logger: Logger,
        notifications: NotificationHandler,
        config: Dict[str, Any]
    ):
        """
        Initialize the monitoring service.
        
        @description Create a new monitoring service instance
        @param {Database} database - Database connection for data storage
        @param {Logger} logger - Logger instance for logging
        @param {NotificationHandler} notifications - Notification handler for alerts
        @param {Dict} config - Configuration dictionary for monitoring settings
        @returns {MonitoringService} New monitoring service instance
        """
        self.database = database
        self.logger = logger
        self.notifications = notifications
        self.config = config
        self.alerts: List[MonitoringAlert] = []
        self.last_run_time = None
        self.is_running = False
        
    @abc.abstractmethod
    async def collect_data(self) -> Dict[str, Any]:
        """
        Collect data needed for monitoring analysis.
        
        @description Collect relevant data from various sources for analysis
        @returns {Dict} Collected data dictionary
        """
        pass
        
    @abc.abstractmethod
    async def analyze_data(self, data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze collected data and generate alerts.
        
        @description Analyze the collected data and identify any issues or anomalies
        @param {Dict} data - Collected data to analyze
        @returns {List} List of generated monitoring alerts
        """
        pass
        
    @abc.abstractmethod
    async def generate_report(self, alerts: List[MonitoringAlert]) -> str:
        """
        Generate a report based on analysis results.
        
        @description Generate a human-readable report of monitoring findings
        @param {List} alerts - List of alerts to include in the report
        @returns {str} Generated report text
        """
        pass
        
    async def run_monitoring_cycle(self) -> Dict[str, Any]:
        """
        Execute a complete monitoring cycle.
        
        @description Run the complete monitoring process: collect, analyze, and report
        @returns {Dict} Results of the monitoring cycle
        """
        if self.is_running:
            self.logger.warning(f"{self.__class__.__name__} is already running")
            return {'status': 'error', 'message': 'Monitoring already in progress'}
            
        self.is_running = True
        self.last_run_time = datetime.utcnow()
        
        try:
            # Step 1: Collect data
            self.logger.info(f"Starting data collection for {self.__class__.__name__}")
            data = await self.collect_data()
            
            # Step 2: Analyze data and generate alerts
            self.logger.info(f"Starting data analysis for {self.__class__.__name__}")
            new_alerts = await self.analyze_data(data)
            
            # Add new alerts to the list
            self.alerts.extend(new_alerts)
            
            # Step 3: Generate report
            self.logger.info(f"Generating report for {self.__class__.__name__}")
            report = await self.generate_report(new_alerts)
            
            # Step 4: Send notifications for critical alerts
            await self._send_notifications(new_alerts)
            
            # Step 5: Store alerts in database
            await self._store_alerts(new_alerts)
            
            return {
                'status': 'success',
                'alerts_generated': len(new_alerts),
                'total_alerts': len(self.alerts),
                'report': report,
                'timestamp': self.last_run_time.isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error in monitoring cycle for {self.__class__.__name__}: {e}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
        finally:
            self.is_running = False
            
    async def _send_notifications(self, alerts: List[MonitoringAlert]):
        """
        Send notifications for alerts that require attention.
        
        @description Send notifications through configured notification channels
        @param {List} alerts - List of alerts to send notifications for
        @returns {void}
        """
        if not self.notifications.enabled:
            return
            
        for alert in alerts:
            # Only send notifications for active, high-severity alerts
            if alert.status == AlertStatus.ACTIVE and alert.severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL]:
                message = f"🚨 {alert.severity.value} Alert: {alert.title}\n\n{alert.description}"
                
                if alert.coin:
                    message += f"\n\nCoin: {alert.coin.symbol}"
                if alert.pair:
                    message += f"\nPair: {alert.pair.from_coin_id}->{alert.pair.to_coin_id}"
                if alert.threshold_value is not None and alert.current_value is not None:
                    message += f"\n\nThreshold: {alert.threshold_value}, Current: {alert.current_value}"
                    
                self.notifications.send_notification(message)
                
    async def _store_alerts(self, alerts: List[MonitoringAlert]):
        """
        Store alerts in the database.
        
        @description Persist alerts to the database for historical tracking
        @param {List} alerts - List of alerts to store
        @returns {void}
        """
        # This will be implemented when we create the database models
        pass
        
    def get_active_alerts(self) -> List[MonitoringAlert]:
        """
        Get all currently active alerts.
        
        @description Retrieve alerts that are still active (not resolved)
        @returns {List} List of active alerts
        """
        return [alert for alert in self.alerts if alert.status == AlertStatus.ACTIVE]
        
    def get_alerts_by_severity(self, severity: AlertSeverity) -> List[MonitoringAlert]:
        """
        Get alerts filtered by severity level.
        
        @description Retrieve alerts of a specific severity level
        @param {AlertSeverity} severity - Severity level to filter by
        @returns {List} List of matching alerts
        """
        return [alert for alert in self.alerts if alert.severity == severity]
        
    def clear_resolved_alerts(self, older_than_hours: int = 24):
        """
        Clear resolved alerts older than specified hours.
        
        @description Remove old resolved alerts to prevent database bloat
        @param {int} older_than_hours - Age threshold in hours
        @returns {int} Number of alerts cleared
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=older_than_hours)
        initial_count = len(self.alerts)
        
        self.alerts = [
            alert for alert in self.alerts 
            if not (alert.status == AlertStatus.RESOLVED and alert.resolved_at and alert.resolved_at < cutoff_time)
        ]
        
        cleared_count = initial_count - len(self.alerts)
        if cleared_count > 0:
            self.logger.info(f"Cleared {cleared_count} resolved older than {older_than_hours} hours")
            
        return cleared_count