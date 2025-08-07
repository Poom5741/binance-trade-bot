"""
Monitoring orchestrator module.

This module provides the main orchestrator that coordinates all monitoring services
and provides a unified interface for the monitoring system.

Created: 2025-08-05
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import uuid

from .base import MonitoringService, MonitoringAlert, AlertSeverity, AlertType, AlertStatus
from .models import VolatilityData, PerformanceData, TradingFrequencyData, ApiErrorData
from .volatility_detector import VolatilityDetector
from .performance_analyzer import PerformanceAnalyzer
from .trading_frequency_monitor import TradingFrequencyMonitor
from .api_error_tracker import ApiErrorTracker
from ..database import Database
from ..logger import Logger
from ..notifications import NotificationHandler
from ..models import Coin, Pair
from ..binance_api_manager import BinanceAPIManager


class MonitoringOrchestrator:
    """
    Main orchestrator for coordinating all monitoring services.
    
    This class provides a unified interface for the monitoring system,
    coordinating between different monitoring services and handling
    alert aggregation and notification.
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
        Initialize the monitoring orchestrator.
        
        @description Create a new monitoring orchestrator instance
        @param {Database} database - Database connection for data storage
        @param {Logger} logger - Logger instance for logging
        @param {NotificationHandler} notifications - Notification handler for alerts
        @param {Dict} config - Configuration dictionary for monitoring system
        @param {BinanceAPIManager} binance_manager - Binance API manager for data retrieval
        @returns {MonitoringOrchestrator} New monitoring orchestrator instance
        """
        self.database = database
        self.logger = logger
        self.notifications = notifications
        self.config = config
        self.binance_manager = binance_manager
        
        # Initialize monitoring services
        self.services: Dict[str, MonitoringService] = {}
        self._initialize_services()
        
        # Alert management
        self.active_alerts: Dict[str, MonitoringAlert] = {}  # alert_id -> alert
        self.alert_history: List[MonitoringAlert] = []
        self.last_run = datetime.utcnow()
        
        # Configuration settings
        self.monitoring_interval = config.get('monitoring_interval', 300)  # 5 minutes
        self.max_active_alerts = config.get('max_active_alerts', 100)
        self.alert_retention_period = config.get('alert_retention_period', 24 * 60 * 60)  # 24 hours
        
        # Statistics
        self.total_alerts_generated = 0
        self.total_alerts_resolved = 0
        self.total_alerts_ignored = 0
        
    def _initialize_services(self):
        """
        Initialize all monitoring services.
        
        @description Create and configure all monitoring services
        @returns {void}
        """
        try:
            # Get service configurations
            service_configs = self.config.get('services', {})
            
            # Initialize volatility detector
            volatility_config = service_configs.get('volatility_detector', {})
            self.services['volatility_detector'] = VolatilityDetector(
                database=self.database,
                logger=self.logger,
                notifications=self.notifications,
                config=volatility_config,
                binance_manager=self.binance_manager
            )
            
            # Initialize performance analyzer
            performance_config = service_configs.get('performance_analyzer', {})
            self.services['performance_analyzer'] = PerformanceAnalyzer(
                database=self.database,
                logger=self.logger,
                notifications=self.notifications,
                config=performance_config,
                binance_manager=self.binance_manager
            )
            
            # Initialize trading frequency monitor
            frequency_config = service_configs.get('trading_frequency_monitor', {})
            self.services['trading_frequency_monitor'] = TradingFrequencyMonitor(
                database=self.database,
                logger=self.logger,
                notifications=self.notifications,
                config=frequency_config,
                binance_manager=self.binance_manager
            )
            
            # Initialize API error tracker
            api_error_config = service_configs.get('api_error_tracker', {})
            self.services['api_error_tracker'] = ApiErrorTracker(
                database=self.database,
                logger=self.logger,
                notifications=self.notifications,
                config=api_error_config,
                binance_manager=self.binance_manager
            )
            
            self.logger.info(f"Initialized {len(self.services)} monitoring services")
            
        except Exception as e:
            self.logger.error(f"Error initializing monitoring services: {e}")
            raise
            
    async def run_monitoring_cycle(self) -> Dict[str, Any]:
        """
        Run a complete monitoring cycle.
        
        @description Execute all monitoring services and generate alerts
        @returns {Dict} Results of the monitoring cycle
        """
        self.logger.info("Starting monitoring cycle")
        
        cycle_results = {
            'start_time': datetime.utcnow(),
            'services': {},
            'alerts': [],
            'summary': {}
        }
        
        try:
            # Run each monitoring service
            for service_name, service in self.services.items():
                self.logger.info(f"Running monitoring service: {service_name}")
                
                try:
                    # Collect data
                    data = await service.collect_data()
                    
                    # Analyze data
                    alerts = await service.analyze_data(data)
                    
                    # Store results
                    cycle_results['services'][service_name] = {
                        'status': 'completed',
                        'data_points': len(data) if isinstance(data, dict) else 0,
                        'alerts_generated': len(alerts)
                    }
                    
                    # Process alerts
                    for alert in alerts:
                        await self._process_alert(alert, service_name)
                    
                    cycle_results['alerts'].extend(alerts)
                    
                except Exception as e:
                    self.logger.error(f"Error in monitoring service {service_name}: {e}")
                    cycle_results['services'][service_name] = {
                        'status': 'error',
                        'error': str(e)
                    }
            
            # Update statistics
            self.total_alerts_generated += len(cycle_results['alerts'])
            
            # Generate summary
            cycle_results['summary'] = self._generate_cycle_summary(cycle_results)
            
            # Clean up old alerts
            await self._cleanup_old_alerts()
            
            # Update last run time
            self.last_run = datetime.utcnow()
            
            self.logger.info(f"Monitoring cycle completed. Generated {len(cycle_results['alerts'])} alerts")
            
            return cycle_results
            
        except Exception as e:
            self.logger.error(f"Error in monitoring cycle: {e}")
            raise
            
    async def _process_alert(self, alert: MonitoringAlert, service_name: str):
        """
        Process a monitoring alert.
        
        @description Handle alert processing, notification, and storage
        @param {MonitoringAlert} alert - Alert to process
        @param {str} service_name - Name of the service that generated the alert
        @returns {void}
        """
        try:
            # Add service name to alert metadata
            alert.metadata['service_name'] = service_name
            
            # Generate unique alert ID if not exists
            if not alert.alert_uuid:
                alert.alert_uuid = str(uuid.uuid4())
            
            # Check alert limits
            if len(self.active_alerts) >= self.max_active_alerts:
                # Remove oldest alert
                oldest_alert_id = min(self.active_alerts.keys())
                del self.active_alerts[oldest_alert_id]
                self.total_alerts_ignored += 1
            
            # Store alert
            self.active_alerts[alert.alert_uuid] = alert
            self.alert_history.append(alert)
            
            # Send notification
            await self._send_alert_notification(alert)
            
            # Log alert
            self.logger.info(f"Alert generated: {alert.title} (Severity: {alert.severity.value})")
            
        except Exception as e:
            self.logger.error(f"Error processing alert: {e}")
            
    async def _send_alert_notification(self, alert: MonitoringAlert):
        """
        Send alert notification.
        
        @description Send alert notification through configured channels
        @param {MonitoringAlert} alert - Alert to send notification for
        @returns {void}
        """
        try:
            # Generate notification message
            message = self._format_alert_message(alert)
            
            # Send notification
            self.notifications.send_notification(message)
            
        except Exception as e:
            self.logger.error(f"Error sending alert notification: {e}")
            
    def _format_alert_message(self, alert: MonitoringAlert) -> str:
        """
        Format alert message for notification.
        
        @description Create a human-readable alert message
        @param {MonitoringAlert} alert - Alert to format
        @returns {str} Formatted alert message
        """
        try:
            # Create emoji based on severity
            severity_emojis = {
                AlertSeverity.CRITICAL.value: '🚨',
                AlertSeverity.HIGH.value: '⚠️',
                AlertSeverity.MEDIUM.value: '🔶',
                AlertSeverity.LOW.value: '🔵'
            }
            
            emoji = severity_emojis.get(alert.severity.value, '📢')
            
            # Create message
            message_lines = [
                f"{emoji} {alert.title}",
                f"Severity: {alert.severity.value}",
                f"Type: {alert.alert_type.value.replace('_', ' ').title()}",
                f"Time: {alert.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                "",
                alert.description
            ]
            
            # Add coin/pair information if available
            if alert.coin:
                message_lines.append(f"Coin: {alert.coin.symbol}")
            
            if alert.pair:
                message_lines.append(f"Pair: {alert.pair.from_coin_id} -> {alert.pair.to_coin_id}")
            
            # Add current value and threshold
            if alert.current_value is not None and alert.threshold_value is not None:
                message_lines.append(f"Current: {alert.current_value:.4f}")
                message_lines.append(f"Threshold: {alert.threshold_value:.4f}")
            
            return "\n".join(message_lines)
            
        except Exception as e:
            self.logger.error(f"Error formatting alert message: {e}")
            return f"Alert: {alert.title} - {alert.description}"
            
    async def _cleanup_old_alerts(self):
        """
        Clean up old alerts based on retention policy.
        
        @description Remove old alerts from active and history
        @returns {void}
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(seconds=self.alert_retention_period)
            
            # Clean up active alerts
            alerts_to_remove = [
                alert_id for alert_id, alert in self.active_alerts.items()
                if alert.created_at < cutoff_time
            ]
            
            for alert_id in alerts_to_remove:
                del self.active_alerts[alert_id]
                self.total_alerts_resolved += 1
            
            # Clean up history (keep only recent alerts)
            self.alert_history = [
                alert for alert in self.alert_history
                if alert.created_at >= cutoff_time
            ]
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old alerts: {e}")
            
    def _generate_cycle_summary(self, cycle_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate summary of monitoring cycle results.
        
        @description Create summary statistics for the monitoring cycle
        @param {Dict} cycle_results - Results from the monitoring cycle
        @returns {Dict} Summary statistics
        """
        try:
            summary = {
                'total_services': len(self.services),
                'services_completed': len([s for s in cycle_results['services'].values() if s['status'] == 'completed']),
                'services_with_errors': len([s for s in cycle_results['services'].values() if s['status'] == 'error']),
                'total_alerts': len(cycle_results['alerts']),
                'alerts_by_severity': {},
                'alerts_by_type': {},
                'alerts_by_service': {}
            }
            
            # Count alerts by severity
            for alert in cycle_results['alerts']:
                severity = alert.severity.value
                summary['alerts_by_severity'][severity] = summary['alerts_by_severity'].get(severity, 0) + 1
            
            # Count alerts by type
            for alert in cycle_results['alerts']:
                alert_type = alert.alert_type.value
                summary['alerts_by_type'][alert_type] = summary['alerts_by_type'].get(alert_type, 0) + 1
            
            # Count alerts by service
            for alert in cycle_results['alerts']:
                service_name = alert.metadata.get('service_name', 'unknown')
                summary['alerts_by_service'][service_name] = summary['alerts_by_service'].get(service_name, 0) + 1
            
            # Add overall statistics
            summary['total_alerts_generated'] = self.total_alerts_generated
            summary['total_alerts_resolved'] = self.total_alerts_resolved
            summary['total_alerts_ignored'] = self.total_alerts_ignored
            summary['active_alerts_count'] = len(self.active_alerts)
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Error generating cycle summary: {e}")
            return {}
            
    async def get_active_alerts(self, severity: Optional[AlertSeverity] = None, alert_type: Optional[AlertType] = None) -> List[MonitoringAlert]:
        """
        Get active alerts with optional filtering.
        
        @description Retrieve active alerts with optional filtering
        @param {AlertSeverity} severity - Filter by severity level
        @param {AlertType} alert_type - Filter by alert type
        @returns {List} List of active alerts
        """
        try:
            alerts = list(self.active_alerts.values())
            
            # Filter by severity
            if severity:
                alerts = [alert for alert in alerts if alert.severity == severity]
            
            # Filter by type
            if alert_type:
                alerts = [alert for alert in alerts if alert.alert_type == alert_type]
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error getting active alerts: {e}")
            return []
            
    async def get_alert_history(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        severity: Optional[AlertSeverity] = None,
        alert_type: Optional[AlertType] = None
    ) -> List[MonitoringAlert]:
        """
        Get alert history with optional filtering.
        
        @description Retrieve alert history with optional filtering
        @param {datetime} start_time - Filter by start time
        @param {datetime} end_time - Filter by end time
        @param {AlertSeverity} severity - Filter by severity level
        @param {AlertType} alert_type - Filter by alert type
        @returns {List} List of historical alerts
        """
        try:
            alerts = self.alert_history.copy()
            
            # Filter by time range
            if start_time:
                alerts = [alert for alert in alerts if alert.created_at >= start_time]
            
            if end_time:
                alerts = [alert for alert in alerts if alert.created_at <= end_time]
            
            # Filter by severity
            if severity:
                alerts = [alert for alert in alerts if alert.severity == severity]
            
            # Filter by type
            if alert_type:
                alerts = [alert for alert in alerts if alert.alert_type == alert_type]
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error getting alert history: {e}")
            return []
            
    async def get_service_status(self) -> Dict[str, Any]:
        """
        Get status of all monitoring services.
        
        @description Retrieve status information for all monitoring services
        @returns {Dict} Service status information
        """
        try:
            status = {
                'orchestrator': {
                    'last_run': self.last_run.isoformat() if self.last_run else None,
                    'monitoring_interval': self.monitoring_interval,
                    'active_alerts_count': len(self.active_alerts),
                    'total_alerts_generated': self.total_alerts_generated,
                    'total_alerts_resolved': self.total_alerts_resolved,
                    'total_alerts_ignored': self.total_alerts_ignored
                },
                'services': {}
            }
            
            # Get status for each service
            for service_name, service in self.services.items():
                service_status = {
                    'class_name': service.__class__.__name__,
                    'enabled': getattr(service, 'enabled', True),
                    'last_alerts': getattr(service, 'last_alerts', {}),
                    'config': getattr(service, 'config', {})
                }
                
                status['services'][service_name] = service_status
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting service status: {e}")
            return {}
            
    async def generate_comprehensive_report(self) -> str:
        """
        Generate a comprehensive monitoring report.
        
        @description Generate a detailed report of all monitoring activities
        @returns {str} Comprehensive report text
        """
        try:
            report_lines = [
                "📊 Comprehensive Monitoring Report",
                "=" * 60,
                f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
                ""
            ]
            
            # Orchestrator summary
            report_lines.append("🎯 Orchestrator Summary:")
            report_lines.append(f"• Last Run: {self.last_run.strftime('%Y-%m-%d %H:%M:%S UTC') if self.last_run else 'Never'}")
            report_lines.append(f"• Monitoring Interval: {self.monitoring_interval} seconds")
            report_lines.append(f"• Active Alerts: {len(self.active_alerts)}")
            report_lines.append(f"• Total Alerts Generated: {self.total_alerts_generated}")
            report_lines.append(f"• Total Alerts Resolved: {self.total_alerts_resolved}")
            report_lines.append(f"• Total Alerts Ignored: {self.total_alerts_ignored}")
            report_lines.append("")
            
            # Service status
            report_lines.append("🔧 Service Status:")
            for service_name, service in self.services.items():
                service_class = service.__class__.__name__
                report_lines.append(f"• {service_name}: {service_class}")
            report_lines.append("")
            
            # Active alerts by severity
            active_alerts = await self.get_active_alerts()
            if active_alerts:
                report_lines.append("🚨 Active Alerts:")
                alerts_by_severity = {}
                for alert in active_alerts:
                    severity = alert.severity.value
                    if severity not in alerts_by_severity:
                        alerts_by_severity[severity] = []
                    alerts_by_severity[severity].append(alert)
                
                for severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
                    if severity in alerts_by_severity:
                        report_lines.append(f"  {severity}: {len(alerts_by_severity[severity])} alerts")
                
                report_lines.append("")
            
            # Recent alerts
            recent_alerts = await self.get_alert_history(
                start_time=datetime.utcnow() - timedelta(hours=24)
            )
            
            if recent_alerts:
                report_lines.append("📈 Recent Activity (Last 24 Hours):")
                report_lines.append(f"• Total Alerts: {len(recent_alerts)}")
                
                # Alerts by type
                alerts_by_type = {}
                for alert in recent_alerts:
                    alert_type = alert.alert_type.value
                    if alert_type not in alerts_by_type:
                        alerts_by_type[alert_type] = []
                    alerts_by_type[alert_type].append(alert)
                
                for alert_type, alerts in alerts_by_type.items():
                    report_lines.append(f"  {alert_type.replace('_', ' ').title()}: {len(alerts)}")
                
                report_lines.append("")
            
            # Service reports
            report_lines.append("📋 Service Reports:")
            for service_name, service in self.services.items():
                try:
                    if hasattr(service, 'generate_report'):
                        service_report = await service.generate_report([])
                        if service_report:
                            report_lines.append(f"  {service_name}:")
                            report_lines.append(f"    {service_report.replace(chr(10), chr(10) + '    ')}")
                            report_lines.append("")
                except Exception as e:
                    self.logger.error(f"Error generating report for service {service_name}: {e}")
                    report_lines.append(f"  {service_name}: Error generating report")
                    report_lines.append("")
            
            return "\n".join(report_lines)
            
        except Exception as e:
            self.logger.error(f"Error generating comprehensive report: {e}")
            return f"Error generating report: {e}"
            
    async def shutdown(self):
        """
        Shutdown the monitoring orchestrator.
        
        @description Cleanly shutdown all monitoring services
        @returns {void}
        """
        try:
            self.logger.info("Shutting down monitoring orchestrator")
            
            # Shutdown each service
            for service_name, service in self.services.items():
                try:
                    if hasattr(service, 'shutdown'):
                        await service.shutdown()
                except Exception as e:
                    self.logger.error(f"Error shutting down service {service_name}: {e}")
            
            self.logger.info("Monitoring orchestrator shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")