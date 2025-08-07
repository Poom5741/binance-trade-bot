"""
Risk event logging and notification system for comprehensive risk management.

This module implements:
- Comprehensive risk event logging with detailed metadata
- Real-time notification system for risk events
- Event categorization and severity assessment
- Event lifecycle management (creation, acknowledgment, resolution)
- Integration with emergency shutdown mechanisms
- Configurable notification thresholds and channels
"""

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List, Callable

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..database import Database
from ..logger import Logger
from ..models import RiskEvent, RiskEventType, RiskEventSeverity, RiskEventStatus, Pair, Coin
from ..notifications import NotificationHandler


class RiskEventCategory(Enum):
    TRADING_RISK = "trading_risk"
    PORTFOLIO_RISK = "portfolio_risk"
    MARKET_RISK = "market_risk"
    SYSTEM_RISK = "system_risk"
    COMPLIANCE_RISK = "compliance_risk"
    CUSTOM = "custom"


class RiskEventLogger:
    """
    Comprehensive risk event logging and notification system.
    
    This class provides methods to:
    - Log risk events with detailed metadata and categorization
    - Send real-time notifications based on severity and type
    - Manage event lifecycle (creation, acknowledgment, resolution)
    - Integrate with emergency shutdown mechanisms
    - Configure notification thresholds and channels
    - Generate risk event reports and analytics
    """
    
    def __init__(self, database: Database, logger: Logger, config: Dict[str, Any], notification_handler: NotificationHandler):
        """
        Initialize the risk event logger.
        
        @param {Database} database - Database instance
        @param {Logger} logger - Logger instance
        @param {Dict} config - Configuration dictionary
        @param {NotificationHandler} notification_handler - Notification handler instance
        """
        self.database = database
        self.logger = logger
        self.config = config
        self.notification_handler = notification_handler
        
        # Configuration parameters
        self.enable_risk_logging = config.get('enable_risk_logging', True)
        self.enable_notifications = config.get('enable_risk_notifications', True)
        self.auto_resolve_low_severity = config.get('auto_resolve_low_severity', True)
        self.notification_cooldown_period = config.get('notification_cooldown_period', 300)  # 5 minutes
        self.severity_notification_thresholds = config.get('severity_notification_thresholds', {
            RiskEventSeverity.LOW: False,
            RiskEventSeverity.MEDIUM: True,
            RiskEventSeverity.HIGH: True,
            RiskEventSeverity.CRITICAL: True
        })
        self.event_type_notification_thresholds = config.get('event_type_notification_thresholds', {})
        
        # Event tracking
        self.event_callbacks: Dict[RiskEventType, List[Callable]] = {}
        self.notification_history: List[Dict] = []
        
        # Initialize logger
        self.log = logging.getLogger(__name__)
        
        # Load existing configuration
        self._load_configuration()
    
    def _load_configuration(self):
        """
        Load existing configuration from database if available.
        """
        try:
            # Configuration can be extended to load from database in the future
            self.log.info("Risk event logger configuration loaded")
        except Exception as e:
            self.log.error(f"Error loading configuration: {e}")
    
    def log_risk_event(
        self,
        session: Session,
        pair: Pair,
        coin: Coin,
        event_type: RiskEventType,
        severity: RiskEventSeverity,
        trigger_value: float,
        threshold_value: float,
        current_value: float,
        description: str,
        category: RiskEventCategory = RiskEventCategory.CUSTOM,
        created_by: str = "system",
        metadata_json: Optional[str] = None,
        auto_notify: bool = True
    ) -> Optional[RiskEvent]:
        """
        Log a new risk event with comprehensive details.
        
        @param {Session} session - Database session
        @param {Pair} pair - Trading pair associated with the event
        @param {Coin} coin - Coin associated with the event
        @param {RiskEventType} event_type - Type of risk event
        @param {RiskEventSeverity} severity - Severity level
        @param {float} trigger_value - Value that triggered the event
        @param {float} threshold_value - Threshold value
        @param {float} current_value - Current value
        @param {str} description - Event description
        @param {RiskEventCategory} category - Event category
        @param {str} created_by - Who created the event
        @param {str} metadata_json - Additional metadata as JSON
        @param {bool} auto_notify - Whether to send notifications automatically
        @returns {RiskEvent} Created risk event or None if logging disabled
        """
        if not self.enable_risk_logging:
            self.log.info("Risk logging is disabled, skipping event creation")
            return None
        
        try:
            # Create risk event
            risk_event = RiskEvent(
                pair=pair,
                coin=coin,
                event_type=event_type,
                severity=severity,
                trigger_value=trigger_value,
                threshold_value=threshold_value,
                current_value=current_value,
                description=description,
                metadata_json=metadata_json or json.dumps({
                    'category': category.value,
                    'auto_generated': True,
                    'log_timestamp': datetime.utcnow().isoformat()
                }),
                created_by=created_by
            )
            
            session.add(risk_event)
            session.flush()  # Get the ID
            
            # Log to internal tracking
            self._log_event_creation(risk_event)
            
            # Handle automatic notifications
            if auto_notify and self.should_notify(event_type, severity):
                self._send_risk_event_notification(risk_event)
            
            # Handle automatic resolution for low severity events
            if self.auto_resolve_low_severity and severity == RiskEventSeverity.LOW:
                risk_event.resolve(created_by)
                self._log_event_resolution(risk_event)
            
            # Execute registered callbacks
            self._execute_event_callbacks(event_type, risk_event)
            
            self.log.info(f"Risk event logged: {event_type.value} - {description} (ID: {risk_event.id})")
            
            return risk_event
            
        except Exception as e:
            self.log.error(f"Error logging risk event: {e}")
            return None
    
    def _log_event_creation(self, risk_event: RiskEvent):
        """
        Log event creation internally.
        
        @param {RiskEvent} risk_event - Risk event that was created
        """
        try:
            log_entry = {
                'event_id': risk_event.id,
                'event_type': risk_event.event_type.value,
                'severity': risk_event.severity.value,
                'created_at': risk_event.created_at.isoformat(),
                'description': risk_event.description,
                'created_by': risk_event.created_by
            }
            
            # Add to notification history if applicable
            if self.should_notify(risk_event.event_type, risk_event.severity):
                self.notification_history.append(log_entry)
                
                # Keep only recent notifications (last 1000)
                if len(self.notification_history) > 1000:
                    self.notification_history = self.notification_history[-1000:]
            
        except Exception as e:
            self.log.error(f"Error logging event creation: {e}")
    
    def _log_event_resolution(self, risk_event: RiskEvent):
        """
        Log event resolution internally.
        
        @param {RiskEvent} risk_event - Risk event that was resolved
        """
        try:
            log_entry = {
                'event_id': risk_event.id,
                'event_type': risk_event.event_type.value,
                'severity': risk_event.severity.value,
                'resolved_at': risk_event.resolved_at.isoformat() if risk_event.resolved_at else None,
                'resolved_by': risk_event.acknowledged_by,
                'action': 'resolved'
            }
            
            self.log.info(f"Risk event automatically resolved: {risk_event.id}")
            
        except Exception as e:
            self.log.error(f"Error logging event resolution: {e}")
    
    def should_notify(self, event_type: RiskEventType, severity: RiskEventSeverity) -> bool:
        """
        Determine if a notification should be sent for a risk event.
        
        @param {RiskEventType} event_type - Type of risk event
        @param {RiskEventSeverity} severity - Severity level
        @returns {bool} True if notification should be sent
        """
        try:
            # Check severity threshold
            severity_threshold = self.severity_notification_thresholds.get(severity, False)
            if not severity_threshold:
                return False
            
            # Check event type threshold
            event_type_threshold = self.event_type_notification_thresholds.get(event_type.value, True)
            if not event_type_threshold:
                return False
            
            # Check cooldown period for similar events
            if self._is_in_cooldown_period(event_type, severity):
                return False
            
            return True
            
        except Exception as e:
            self.log.error(f"Error determining notification requirement: {e}")
            return False
    
    def _is_in_cooldown_period(self, event_type: RiskEventType, severity: RiskEventSeverity) -> bool:
        """
        Check if similar events are within the notification cooldown period.
        
        @param {RiskEventType} event_type - Type of risk event
        @param {RiskEventSeverity} severity - Severity level
        @returns {bool} True if within cooldown period
        """
        try:
            cutoff_time = datetime.utcnow() - timedelta(seconds=self.notification_cooldown_period)
            
            # Check recent notifications of the same type and severity
            recent_notifications = [
                n for n in self.notification_history
                if (n.get('event_type') == event_type.value and
                    n.get('severity') == severity.value and
                    datetime.fromisoformat(n.get('created_at')) > cutoff_time)
            ]
            
            return len(recent_notifications) > 0
            
        except Exception as e:
            self.log.error(f"Error checking cooldown period: {e}")
            return False
    
    def _send_risk_event_notification(self, risk_event: RiskEvent):
        """
        Send notification for a risk event.
        
        @param {RiskEvent} risk_event - Risk event to notify about
        """
        try:
            if not self.enable_notifications:
                return
            
            # Format notification message based on severity
            message = self._format_notification_message(risk_event)
            
            # Send notification
            self.notification_handler.send_notification(message)
            
            self.log.info(f"Risk event notification sent for event ID {risk_event.id}")
            
        except Exception as e:
            self.log.error(f"Error sending risk event notification: {e}")
    
    def _format_notification_message(self, risk_event: RiskEvent) -> str:
        """
        Format notification message for a risk event.
        
        @param {RiskEvent} risk_event - Risk event to format
        @returns {str} Formatted notification message
        """
        try:
            # Determine emoji based on severity
            emoji_map = {
                RiskEventSeverity.LOW: "ℹ️",
                RiskEventSeverity.MEDIUM: "⚠️",
                RiskEventSeverity.HIGH: "🚨",
                RiskEventSeverity.CRITICAL: "🔥"
            }
            
            emoji = emoji_map.get(risk_event.severity, "📋")
            
            # Format message
            message = f"{emoji} RISK EVENT ALERT\n\n"
            message += f"Type: {risk_event.event_type.value.replace('_', ' ').title()}\n"
            message += f"Severity: {risk_event.severity.value}\n"
            message += f"Pair: {risk_event.pair.info()['from_coin']['symbol']}/{risk_event.pair.info()['to_coin']['symbol']}\n"
            message += f"Description: {risk_event.description}\n"
            message += f"Trigger Value: {risk_event.trigger_value}\n"
            message += f"Threshold: {risk_event.threshold_value}\n"
            message += f"Current Value: {risk_event.current_value}\n"
            message += f"Event ID: {risk_event.id}\n"
            message += f"Time: {risk_event.created_at.isoformat()}\n"
            message += f"Created by: {risk_event.created_by}\n"
            
            # Add metadata if available
            if risk_event.metadata_json:
                try:
                    metadata = json.loads(risk_event.metadata_json)
                    if 'category' in metadata:
                        message += f"Category: {metadata['category']}\n"
                except:
                    pass
            
            return message
            
        except Exception as e:
            self.log.error(f"Error formatting notification message: {e}")
            return f"Risk Event Alert: {risk_event.description}"
    
    def _execute_event_callbacks(self, event_type: RiskEventType, risk_event: RiskEvent):
        """
        Execute registered callbacks for a risk event type.
        
        @param {RiskEventType} event_type - Type of risk event
        @param {RiskEvent} risk_event - Risk event instance
        """
        try:
            callbacks = self.event_callbacks.get(event_type, [])
            for callback in callbacks:
                try:
                    callback(risk_event)
                except Exception as e:
                    self.log.error(f"Error executing callback for {event_type.value}: {e}")
                    
        except Exception as e:
            self.log.error(f"Error executing event callbacks: {e}")
    
    def register_event_callback(self, event_type: RiskEventType, callback: Callable):
        """
        Register a callback function for a specific risk event type.
        
        @param {RiskEventType} event_type - Type of risk event
        @param {Callable} callback - Callback function to execute
        """
        try:
            if event_type not in self.event_callbacks:
                self.event_callbacks[event_type] = []
            
            self.event_callbacks[event_type].append(callback)
            self.log.info(f"Registered callback for {event_type.value}")
            
        except Exception as e:
            self.log.error(f"Error registering event callback: {e}")
    
    def acknowledge_event(self, session: Session, event_id: int, acknowledged_by: str = "system") -> Dict[str, Any]:
        """
        Acknowledge a risk event.
        
        @param {Session} session - Database session
        @param {int} event_id - ID of the risk event
        @param {str} acknowledged_by - Who acknowledged the event
        @returns {Dict} Acknowledgment result
        """
        try:
            risk_event = session.query(RiskEvent).get(event_id)
            if not risk_event:
                return {
                    "status": "error",
                    "message": "Risk event not found"
                }
            
            risk_event.acknowledge(acknowledged_by)
            
            self.log.info(f"Risk event acknowledged: {event_id} by {acknowledged_by}")
            
            return {
                "status": "success",
                "message": "Risk event acknowledged successfully",
                "event": risk_event.info()
            }
            
        except Exception as e:
            self.log.error(f"Error acknowledging risk event: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def resolve_event(self, session: Session, event_id: int, resolved_by: str = "system") -> Dict[str, Any]:
        """
        Resolve a risk event.
        
        @param {Session} session - Database session
        @param {int} event_id - ID of the risk event
        @param {str} resolved_by - Who resolved the event
        @returns {Dict} Resolution result
        """
        try:
            risk_event = session.query(RiskEvent).get(event_id)
            if not risk_event:
                return {
                    "status": "error",
                    "message": "Risk event not found"
                }
            
            risk_event.resolve(resolved_by)
            
            self.log.info(f"Risk event resolved: {event_id} by {resolved_by}")
            
            return {
                "status": "success",
                "message": "Risk event resolved successfully",
                "event": risk_event.info()
            }
            
        except Exception as e:
            self.log.error(f"Error resolving risk event: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def escalate_event(self, session: Session, event_id: int, escalated_by: str = "system") -> Dict[str, Any]:
        """
        Escalate a risk event.
        
        @param {Session} session - Database session
        @param {int} event_id - ID of the risk event
        @param {str} escalated_by - Who escalated the event
        @returns {Dict} Escalation result
        """
        try:
            risk_event = session.query(RiskEvent).get(event_id)
            if not risk_event:
                return {
                    "status": "error",
                    "message": "Risk event not found"
                }
            
            risk_event.escalate(escalated_by)
            
            # Send escalation notification
            if self.enable_notifications:
                self._send_escalation_notification(risk_event, escalated_by)
            
            self.log.info(f"Risk event escalated: {event_id} by {escalated_by}")
            
            return {
                "status": "success",
                "message": "Risk event escalated successfully",
                "event": risk_event.info()
            }
            
        except Exception as e:
            self.log.error(f"Error escalating risk event: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def ignore_event(self, session: Session, event_id: int, ignored_by: str = "system") -> Dict[str, Any]:
        """
        Ignore a risk event.
        
        @param {Session} session - Database session
        @param {int} event_id - ID of the risk event
        @param {str} ignored_by - Who ignored the event
        @returns {Dict} Ignore result
        """
        try:
            risk_event = session.query(RiskEvent).get(event_id)
            if not risk_event:
                return {
                    "status": "error",
                    "message": "Risk event not found"
                }
            
            risk_event.ignore(ignored_by)
            
            self.log.info(f"Risk event ignored: {event_id} by {ignored_by}")
            
            return {
                "status": "success",
                "message": "Risk event ignored successfully",
                "event": risk_event.info()
            }
            
        except Exception as e:
            self.log.error(f"Error ignoring risk event: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _send_escalation_notification(self, risk_event: RiskEvent, escalated_by: str):
        """
        Send escalation notification for a risk event.
        
        @param {RiskEvent} risk_event - Risk event that was escalated
        @param {str} escalated_by - Who escalated the event
        """
        try:
            message = f"🚨 RISK EVENT ESCALATED\n\n"
            message += f"Event ID: {risk_event.id}\n"
            message += f"Type: {risk_event.event_type.value.replace('_', ' ').title()}\n"
            message += f"Severity: {risk_event.severity.value}\n"
            message += f"Description: {risk_event.description}\n"
            message += f"Escalated by: {escalated_by}\n"
            message += f"Time: {datetime.utcnow().isoformat()}\n"
            message += f"\n⚠️  Immediate attention required"
            
            self.notification_handler.send_notification(message)
            
        except Exception as e:
            self.log.error(f"Error sending escalation notification: {e}")
    
    def get_risk_events(
        self,
        session: Session,
        event_type: Optional[RiskEventType] = None,
        severity: Optional[RiskEventSeverity] = None,
        status: Optional[RiskEventStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get risk events with optional filtering.
        
        @param {Session} session - Database session
        @param {RiskEventType} event_type - Filter by event type
        @param {RiskEventSeverity} severity - Filter by severity
        @param {RiskEventStatus} status - Filter by status
        @param {datetime} start_date - Filter by start date
        @param {datetime} end_date - Filter by end date
        @param {int} limit - Maximum number of results
        @param {int} offset - Offset for pagination
        @returns {Dict} Risk events query result
        """
        try:
            query = session.query(RiskEvent)
            
            # Apply filters
            if event_type:
                query = query.filter(RiskEvent.event_type == event_type)
            
            if severity:
                query = query.filter(RiskEvent.severity == severity)
            
            if status:
                query = query.filter(RiskEvent.status == status)
            
            if start_date:
                query = query.filter(RiskEvent.created_at >= start_date)
            
            if end_date:
                query = query.filter(RiskEvent.created_at <= end_date)
            
            # Get total count
            total_count = query.count()
            
            # Apply pagination
            events = query.order_by(RiskEvent.created_at.desc()).offset(offset).limit(limit).all()
            
            # Format results
            events_data = [event.info() for event in events]
            
            return {
                "status": "success",
                "data": events_data,
                "total_count": total_count,
                "limit": limit,
                "offset": offset
            }
            
        except Exception as e:
            self.log.error(f"Error getting risk events: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_risk_event_statistics(self, session: Session, days: int = 7) -> Dict[str, Any]:
        """
        Get risk event statistics for the specified number of days.
        
        @param {Session} session - Database session
        @param {int} days - Number of days to analyze
        @returns {Dict} Risk event statistics
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Get all events in the period
            events = session.query(RiskEvent).filter(
                RiskEvent.created_at >= cutoff_date
            ).all()
            
            # Calculate statistics
            stats = {
                "total_events": len(events),
                "by_type": {},
                "by_severity": {},
                "by_status": {},
                "by_day": {},
                "resolution_rate": 0,
                "escalation_rate": 0,
                "acknowledgment_rate": 0
            }
            
            # Count by type
            for event in events:
                event_type = event.event_type.value
                stats["by_type"][event_type] = stats["by_type"].get(event_type, 0) + 1
            
            # Count by severity
            for event in events:
                severity = event.severity.value
                stats["by_severity"][severity] = stats["by_severity"].get(severity, 0) + 1
            
            # Count by status
            for event in events:
                status = event.status.value
                stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            
            # Count by day
            for event in events:
                day = event.created_at.strftime('%Y-%m-%d')
                stats["by_day"][day] = stats["by_day"].get(day, 0) + 1
            
            # Calculate rates
            resolved_events = [e for e in events if e.status == RiskEventStatus.RESOLVED]
            escalated_events = [e for e in events if e.status == RiskEventStatus.ESCALATED]
            acknowledged_events = [e for e in events if e.acknowledged_at is not None]
            
            if events:
                stats["resolution_rate"] = len(resolved_events) / len(events) * 100
                stats["escalation_rate"] = len(escalated_events) / len(events) * 100
                stats["acknowledgment_rate"] = len(acknowledged_events) / len(events) * 100
            
            return {
                "status": "success",
                "data": stats,
                "period_days": days
            }
            
        except Exception as e:
            self.log.error(f"Error getting risk event statistics: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def update_configuration(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update risk event logger configuration.
        
        @param {Dict} new_config - New configuration parameters
        @returns {Dict} Update result
        """
        try:
            # Update configuration parameters
            self.enable_risk_logging = new_config.get('enable_risk_logging', self.enable_risk_logging)
            self.enable_notifications = new_config.get('enable_risk_notifications', self.enable_notifications)
            self.auto_resolve_low_severity = new_config.get('auto_resolve_low_severity', self.auto_resolve_low_severity)
            self.notification_cooldown_period = new_config.get('notification_cooldown_period', self.notification_cooldown_period)
            
            # Update severity notification thresholds
            severity_thresholds = new_config.get('severity_notification_thresholds', {})
            for severity, enabled in severity_thresholds.items():
                try:
                    enum_severity = RiskEventSeverity(severity.upper())
                    self.severity_notification_thresholds[enum_severity] = enabled
                except ValueError:
                    self.log.warning(f"Invalid severity value in configuration: {severity}")
            
            # Update event type notification thresholds
            event_type_thresholds = new_config.get('event_type_notification_thresholds', {})
            for event_type, enabled in event_type_thresholds.items():
                try:
                    enum_event_type = RiskEventType(event_type.upper())
                    self.event_type_notification_thresholds[enum_event_type.value] = enabled
                except ValueError:
                    self.log.warning(f"Invalid event type value in configuration: {event_type}")
            
            self.log.info("Risk event logger configuration updated")
            
            return {
                "status": "success",
                "message": "Configuration updated successfully"
            }
            
        except Exception as e:
            self.log.error(f"Error updating configuration: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_notification_history(self, limit: int = 100) -> Dict[str, Any]:
        """
        Get notification history.
        
        @param {int} limit - Maximum number of notifications to return
        @returns {Dict} Notification history
        """
        try:
            return {
                "status": "success",
                "data": self.notification_history[-limit:],
                "total_count": len(self.notification_history)
            }
        except Exception as e:
            self.log.error(f"Error getting notification history: {e}")
            return {
                "status": "error",
                "message": str(e)
            }