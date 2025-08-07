"""
Emergency shutdown manager with state preservation for risk management.

This module implements:
- Emergency shutdown mechanisms with configurable thresholds
- State preservation during shutdown
- Manual confirmation requirements for resuming
- Risk event logging and notification system
- Configurable loss threshold settings
"""

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database import Database
from ..logger import Logger
from ..models import RiskEvent, RiskEventType, RiskEventSeverity, RiskEventStatus, Pair, Coin
from ..notifications import NotificationHandler


class ShutdownReason(Enum):
    DAILY_LOSS_EXCEEDED = "daily_loss_exceeded"
    MAX_DRAWDOWN_EXCEEDED = "max_drawdown_exceeded"
    MANUAL_SHUTDOWN = "manual_shutdown"
    CRITICAL_RISK_EVENT = "critical_risk_event"
    CONFIGURATION_ERROR = "configuration_error"


class ShutdownStatus(Enum):
    ACTIVE = "active"
    RESUMED = "resumed"
    PENDING_REVIEW = "pending_review"
    PERMANENT_SHUTDOWN = "permanent_shutdown"


class EmergencyShutdownManager:
    """
    Manager class for handling emergency shutdown with state preservation.
    
    This class provides methods to:
    - Initiate emergency shutdown based on configurable thresholds
    - Preserve trading state during shutdown
    - Require manual confirmation for resuming
    - Log risk events and send notifications
    - Manage configurable loss threshold settings
    """
    
    def __init__(self, database: Database, logger: Logger, config: Dict[str, Any], notification_handler: NotificationHandler):
        """
        Initialize the emergency shutdown manager.
        
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
        self.enable_emergency_shutdown = config.get('enable_emergency_shutdown', True)
        self.max_daily_loss_percentage = config.get('max_daily_loss_percentage', 5.0)
        self.max_drawdown_percentage = config.get('max_drawdown_percentage', 10.0)
        self.require_manual_confirmation = config.get('require_manual_confirmation', True)
        self.shutdown_cooldown_period = config.get('shutdown_cooldown_period', 3600)  # 1 hour in seconds
        self.enable_notifications = config.get('enable_notifications', True)
        
        # Shutdown state
        self.shutdown_status = ShutdownStatus.ACTIVE
        self.shutdown_reason = None
        self.shutdown_triggered_at = None
        self.shutdown_triggered_by = None
        self.state_preserved_data = {}
        
        # Initialize logger
        self.log = logging.getLogger(__name__)
        
        # Load existing shutdown state if any
        self._load_shutdown_state()
    
    def _load_shutdown_state(self):
        """
        Load existing shutdown state from database.
        """
        try:
            with self.database.db_session() as session:
                # Get the most recent shutdown event
                recent_event = session.query(RiskEvent).filter(
                    RiskEvent.event_type == RiskEventType.PORTFOLIO_LIMIT,
                    RiskEvent.status.in_([RiskEventStatus.OPEN, RiskEventStatus.ESCALATED])
                ).order_by(RiskEvent.created_at.desc()).first()
                
                if recent_event:
                    self.shutdown_status = ShutdownStatus.ACTIVE
                    self.shutdown_reason = ShutdownReason.DAILY_LOSS_EXCEEDED
                    self.shutdown_triggered_at = recent_event.created_at
                    self.shutdown_triggered_by = recent_event.created_by
                    
                    # Load preserved state from metadata if available
                    if recent_event.metadata_json:
                        metadata = json.loads(recent_event.metadata_json)
                        self.state_preserved_data = metadata.get('preserved_state', {})
                    
                    self.log.info(f"Loaded existing shutdown state from {recent_event.created_at}")
                    
        except Exception as e:
            self.log.error(f"Error loading shutdown state: {e}")
    
    def check_shutdown_conditions(self, session: Session, account_performance: Dict[str, Any]) -> bool:
        """
        Check if emergency shutdown conditions are met.
        
        @param {Session} session - Database session
        @param {Dict} account_performance - Account performance metrics
        @returns {bool} True if shutdown should be triggered, False otherwise
        """
        if not self.enable_emergency_shutdown:
            return False
        
        try:
            # Check daily loss threshold
            daily_loss = account_performance.get('daily_loss_percentage', 0)
            if daily_loss >= self.max_daily_loss_percentage:
                self.initiate_shutdown(
                    session=session,
                    reason=ShutdownReason.DAILY_LOSS_EXCEEDED,
                    trigger_value=daily_loss,
                    description=f"Daily loss threshold exceeded: {daily_loss:.2f}% (threshold: {self.max_daily_loss_percentage}%)"
                )
                return True
            
            # Check max drawdown threshold
            max_drawdown = account_performance.get('max_drawdown_percentage', 0)
            if max_drawdown >= self.max_drawdown_percentage:
                self.initiate_shutdown(
                    session=session,
                    reason=ShutdownReason.MAX_DRAWDOWN_EXCEEDED,
                    trigger_value=max_drawdown,
                    description=f"Maximum drawdown threshold exceeded: {max_drawdown:.2f}% (threshold: {self.max_drawdown_percentage}%)"
                )
                return True
            
            return False
            
        except Exception as e:
            self.log.error(f"Error checking shutdown conditions: {e}")
            return False
    
    def initiate_shutdown(self, session: Session, reason: ShutdownReason, trigger_value: float, description: str, triggered_by: str = "system"):
        """
        Initiate emergency shutdown.
        
        @param {Session} session - Database session
        @param {ShutdownReason} reason - Reason for shutdown
        @param {float} trigger_value - Value that triggered the shutdown
        @param {str} description - Description of the shutdown
        @param {str} triggered_by - Who triggered the shutdown
        """
        try:
            self.shutdown_status = ShutdownStatus.ACTIVE
            self.shutdown_reason = reason
            self.shutdown_triggered_at = datetime.utcnow()
            self.shutdown_triggered_by = triggered_by
            
            # Preserve current trading state
            self._preserve_trading_state()
            
            # Create risk event
            self._create_shutdown_risk_event(session, reason, trigger_value, description, triggered_by)
            
            # Send notification
            if self.enable_notifications:
                self._send_shutdown_notification(reason, description, triggered_by)
            
            self.log.warning(f"Emergency shutdown initiated: {description}")
            
        except Exception as e:
            self.log.error(f"Error initiating shutdown: {e}")
    
    def _preserve_trading_state(self):
        """
        Preserve current trading state for potential resumption.
        """
        try:
            # Collect current trading state data
            state_data = {
                'shutdown_triggered_at': self.shutdown_triggered_at.isoformat() if self.shutdown_triggered_at else None,
                'shutdown_reason': self.shutdown_reason.value if self.shutdown_reason else None,
                'shutdown_triggered_by': self.shutdown_triggered_by,
                'config_snapshot': {
                    'max_daily_loss_percentage': self.max_daily_loss_percentage,
                    'max_drawdown_percentage': self.max_drawdown_percentage,
                    'require_manual_confirmation': self.require_manual_confirmation,
                    'shutdown_cooldown_period': self.shutdown_cooldown_period
                },
                'timestamp': datetime.utcnow().isoformat()
            }
            
            self.state_preserved_data = state_data
            self.log.info("Trading state preserved for potential resumption")
            
        except Exception as e:
            self.log.error(f"Error preserving trading state: {e}")
    
    def _create_shutdown_risk_event(self, session: Session, reason: ShutdownReason, trigger_value: float, description: str, triggered_by: str):
        """
        Create a risk event for the emergency shutdown.
        
        @param {Session} session - Database session
        @param {ShutdownReason} reason - Reason for shutdown
        @param {float} trigger_value - Value that triggered the shutdown
        @param {str} description - Description of the shutdown
        @param {str} triggered_by - Who triggered the shutdown
        """
        try:
            # Find a default pair for the event
            pair = session.query(Pair).first()
            if not pair:
                pair = Pair(Coin("USDT", True), Coin("BTC", True))  # Default pair
                session.add(pair)
            
            # Determine severity based on reason
            if reason == ShutdownReason.CRITICAL_RISK_EVENT:
                severity = RiskEventSeverity.CRITICAL
            elif reason in [ShutdownReason.DAILY_LOSS_EXCEEDED, ShutdownReason.MAX_DRAWDOWN_EXCEEDED]:
                severity = RiskEventSeverity.HIGH
            else:
                severity = RiskEventSeverity.MEDIUM
            
            # Create risk event
            risk_event = RiskEvent(
                pair=pair,
                coin=pair.from_coin,  # Use from_coin as the main coin
                event_type=RiskEventType.PORTFOLIO_LIMIT,
                severity=severity,
                trigger_value=trigger_value,
                threshold_value=self.max_daily_loss_percentage if reason == ShutdownReason.DAILY_LOSS_EXCEEDED else self.max_drawdown_percentage,
                current_value=trigger_value,
                description=description,
                metadata_json=json.dumps({
                    'shutdown_reason': reason.value,
                    'preserved_state': self.state_preserved_data,
                    'requires_manual_confirmation': self.require_manual_confirmation
                }),
                created_by=triggered_by
            )
            
            session.add(risk_event)
            self.log.info(f"Created shutdown risk event: {description}")
            
        except Exception as e:
            self.log.error(f"Error creating shutdown risk event: {e}")
    
    def _send_shutdown_notification(self, reason: ShutdownReason, description: str, triggered_by: str):
        """
        Send notification about emergency shutdown.
        
        @param {ShutdownReason} reason - Reason for shutdown
        @param {str} description - Description of the shutdown
        @param {str} triggered_by - Who triggered the shutdown
        """
        try:
            message = f"🚨 EMERGENCY SHUTDOWN TRIGGERED\n\n"
            message += f"Reason: {reason.value.replace('_', ' ').title()}\n"
            message += f"Description: {description}\n"
            message += f"Triggered by: {triggered_by}\n"
            message += f"Time: {datetime.utcnow().isoformat()}\n"
            
            if self.require_manual_confirmation:
                message += f"\n⚠️  Manual confirmation required before resuming trading"
            
            self.notification_handler.send_notification(message)
            
        except Exception as e:
            self.log.error(f"Error sending shutdown notification: {e}")
    
    def request_resume(self, session: Session, requested_by: str = "system") -> Dict[str, Any]:
        """
        Request to resume trading after emergency shutdown.
        
        @param {Session} session - Database session
        @param {str} requested_by - Who is requesting the resume
        @returns {Dict} Resume request result
        """
        try:
            if self.shutdown_status != ShutdownStatus.ACTIVE:
                return {
                    "status": "error",
                    "message": "No active shutdown to resume from"
                }
            
            if self.require_manual_confirmation:
                # Set status to pending review
                self.shutdown_status = ShutdownStatus.PENDING_REVIEW
                
                # Create resume request event
                self._create_resume_request_event(session, requested_by)
                
                # Send notification
                if self.enable_notifications:
                    self._send_resume_request_notification(requested_by)
                
                return {
                    "status": "success",
                    "message": "Resume request submitted and pending manual confirmation",
                    "status": "pending_review"
                }
            else:
                # Auto-resume if manual confirmation not required
                return self.resume_trading(session, requested_by)
                
        except Exception as e:
            self.log.error(f"Error requesting resume: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _create_resume_request_event(self, session: Session, requested_by: str):
        """
        Create a risk event for resume request.
        
        @param {Session} session - Database session
        @param {str} requested_by - Who requested the resume
        """
        try:
            # Find a default pair for the event
            pair = session.query(Pair).first()
            if not pair:
                pair = Pair(Coin("USDT", True), Coin("BTC", True))  # Default pair
                session.add(pair)
            
            # Create resume request event
            risk_event = RiskEvent(
                pair=pair,
                coin=pair.from_coin,
                event_type=RiskEventType.CUSTOM,  # Using custom for resume requests
                severity=RiskEventSeverity.MEDIUM,
                trigger_value=0,
                threshold_value=0,
                current_value=0,
                description=f"Resume request after emergency shutdown - requested by {requested_by}",
                metadata_json=json.dumps({
                    'request_type': 'resume_request',
                    'original_shutdown_reason': self.shutdown_reason.value if self.shutdown_reason else None,
                    'requested_by': requested_by,
                    'requested_at': datetime.utcnow().isoformat()
                }),
                created_by=requested_by
            )
            
            session.add(risk_event)
            self.log.info(f"Created resume request event by {requested_by}")
            
        except Exception as e:
            self.log.error(f"Error creating resume request event: {e}")
    
    def _send_resume_request_notification(self, requested_by: str):
        """
        Send notification about resume request.
        
        @param {str} requested_by - Who requested the resume
        """
        try:
            message = f"🔄 RESUME REQUEST SUBMITTED\n\n"
            message += f"Emergency shutdown resume requested by: {requested_by}\n"
            message += f"Original shutdown reason: {self.shutdown_reason.value.replace('_', ' ').title() if self.shutdown_reason else 'Unknown'}\n"
            message += f"Request time: {datetime.utcnow().isoformat()}\n"
            message += f"\n⚠️  Awaiting manual confirmation to resume trading"
            
            self.notification_handler.send_notification(message)
            
        except Exception as e:
            self.log.error(f"Error sending resume request notification: {e}")
    
    def confirm_resume(self, session: Session, confirmed_by: str) -> Dict[str, Any]:
        """
        Confirm resume request and reactivate trading.
        
        @param {Session} session - Database session
        @param {str} confirmed_by - Who confirmed the resume
        @returns {Dict} Resume confirmation result
        """
        try:
            if self.shutdown_status != ShutdownStatus.PENDING_REVIEW:
                return {
                    "status": "error",
                    "message": "No pending resume request to confirm"
                }
            
            # Check cooldown period
            if self.shutdown_triggered_at:
                cooldown_expiry = self.shutdown_triggered_at + timedelta(seconds=self.shutdown_cooldown_period)
                if datetime.utcnow() < cooldown_expiry:
                    remaining_time = cooldown_expiry - datetime.utcnow()
                    return {
                        "status": "error",
                        "message": f"Cooldown period still active. Resume available in {remaining_time.seconds // 60} minutes"
                    }
            
            return self.resume_trading(session, confirmed_by)
            
        except Exception as e:
            self.log.error(f"Error confirming resume: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def resume_trading(self, session: Session, resumed_by: str) -> Dict[str, Any]:
        """
        Resume trading after emergency shutdown.
        
        @param {Session} session - Database session
        @param {str} resumed_by - Who resumed trading
        @returns {Dict} Resume result
        """
        try:
            # Update shutdown status
            self.shutdown_status = ShutdownStatus.RESUMED
            
            # Resolve the shutdown risk event
            self._resolve_shutdown_risk_event(session, resumed_by)
            
            # Create resume confirmation event
            self._create_resume_confirmation_event(session, resumed_by)
            
            # Send notification
            if self.enable_notifications:
                self._send_resume_confirmation_notification(resumed_by)
            
            self.log.info(f"Trading resumed by {resumed_by}")
            
            return {
                "status": "success",
                "message": "Trading resumed successfully",
                "shutdown_status": self.shutdown_status.value
            }
            
        except Exception as e:
            self.log.error(f"Error resuming trading: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _resolve_shutdown_risk_event(self, session: Session, resolved_by: str):
        """
        Resolve the shutdown risk event.
        
        @param {Session} session - Database session
        @param {str} resolved_by - Who resolved the event
        """
        try:
            # Find and resolve the active shutdown event
            shutdown_event = session.query(RiskEvent).filter(
                RiskEvent.event_type == RiskEventType.PORTFOLIO_LIMIT,
                RiskEvent.status.in_([RiskEventStatus.OPEN, RiskEventStatus.ESCALATED])
            ).order_by(RiskEvent.created_at.desc()).first()
            
            if shutdown_event:
                shutdown_event.resolve(resolved_by)
                self.log.info(f"Resolved shutdown risk event ID {shutdown_event.id}")
                
        except Exception as e:
            self.log.error(f"Error resolving shutdown risk event: {e}")
    
    def _create_resume_confirmation_event(self, session: Session, resumed_by: str):
        """
        Create a risk event for resume confirmation.
        
        @param {Session} session - Database session
        @param {str} resumed_by - Who resumed trading
        """
        try:
            # Find a default pair for the event
            pair = session.query(Pair).first()
            if not pair:
                pair = Pair(Coin("USDT", True), Coin("BTC", True))  # Default pair
                session.add(pair)
            
            # Create resume confirmation event
            risk_event = RiskEvent(
                pair=pair,
                coin=pair.from_coin,
                event_type=RiskEventType.CUSTOM,  # Using custom for resume confirmations
                severity=RiskEventSeverity.LOW,
                trigger_value=0,
                threshold_value=0,
                current_value=0,
                description=f"Trading resumed after emergency shutdown - resumed by {resumed_by}",
                metadata_json=json.dumps({
                    'event_type': 'resume_confirmation',
                    'original_shutdown_reason': self.shutdown_reason.value if self.shutdown_reason else None,
                    'resumed_by': resumed_by,
                    'resumed_at': datetime.utcnow().isoformat(),
                    'downtime_seconds': (datetime.utcnow() - self.shutdown_triggered_at).total_seconds() if self.shutdown_triggered_at else 0
                }),
                created_by=resumed_by
            )
            
            session.add(risk_event)
            self.log.info(f"Created resume confirmation event by {resumed_by}")
            
        except Exception as e:
            self.log.error(f"Error creating resume confirmation event: {e}")
    
    def _send_resume_confirmation_notification(self, resumed_by: str):
        """
        Send notification about resume confirmation.
        
        @param {str} resumed_by - Who resumed trading
        """
        try:
            message = f"✅ TRADING RESUMED\n\n"
            message += f"Emergency shutdown ended - trading resumed by: {resumed_by}\n"
            message += f"Original shutdown reason: {self.shutdown_reason.value.replace('_', ' ').title() if self.shutdown_reason else 'Unknown'}\n"
            message += f"Resume time: {datetime.utcnow().isoformat()}\n"
            
            if self.shutdown_triggered_at:
                downtime = datetime.utcnow() - self.shutdown_triggered_at
                message += f"Downtime duration: {downtime.total_seconds():.0f} seconds\n"
            
            self.notification_handler.send_notification(message)
            
        except Exception as e:
            self.log.error(f"Error sending resume confirmation notification: {e}")
    
    def get_shutdown_status(self) -> Dict[str, Any]:
        """
        Get current shutdown status information.
        
        @returns {Dict} Shutdown status information
        """
        try:
            return {
                "status": "success",
                "data": {
                    "shutdown_status": self.shutdown_status.value,
                    "shutdown_reason": self.shutdown_reason.value if self.shutdown_reason else None,
                    "shutdown_triggered_at": self.shutdown_triggered_at.isoformat() if self.shutdown_triggered_at else None,
                    "shutdown_triggered_by": self.shutdown_triggered_by,
                    "require_manual_confirmation": self.require_manual_confirmation,
                    "shutdown_cooldown_period": self.shutdown_cooldown_period,
                    "enable_emergency_shutdown": self.enable_emergency_shutdown,
                    "max_daily_loss_percentage": self.max_daily_loss_percentage,
                    "max_drawdown_percentage": self.max_drawdown_percentage,
                    "state_preserved": bool(self.state_preserved_data),
                    "last_updated": datetime.utcnow().isoformat()
                }
            }
        except Exception as e:
            self.log.error(f"Error getting shutdown status: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def update_configuration(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update emergency shutdown configuration.
        
        @param {Dict} new_config - New configuration parameters
        @returns {Dict} Update result
        """
        try:
            # Update configuration parameters
            self.max_daily_loss_percentage = new_config.get('max_daily_loss_percentage', self.max_daily_loss_percentage)
            self.max_drawdown_percentage = new_config.get('max_drawdown_percentage', self.max_drawdown_percentage)
            self.require_manual_confirmation = new_config.get('require_manual_confirmation', self.require_manual_confirmation)
            self.shutdown_cooldown_period = new_config.get('shutdown_cooldown_period', self.shutdown_cooldown_period)
            self.enable_emergency_shutdown = new_config.get('enable_emergency_shutdown', self.enable_emergency_shutdown)
            self.enable_notifications = new_config.get('enable_notifications', self.enable_notifications)
            
            # Preserve updated configuration
            self._preserve_trading_state()
            
            self.log.info("Emergency shutdown configuration updated")
            
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
    
    def force_shutdown(self, session: Session, reason: ShutdownReason, description: str, triggered_by: str = "manual") -> Dict[str, Any]:
        """
        Force emergency shutdown (manual trigger).
        
        @param {Session} session - Database session
        @param {ShutdownReason} reason - Reason for shutdown
        @param {str} description - Description of the shutdown
        @param {str} triggered_by - Who triggered the shutdown
        @returns {Dict} Shutdown result
        """
        try:
            self.initiate_shutdown(session, reason, 0, description, triggered_by)
            
            return {
                "status": "success",
                "message": "Emergency shutdown forced successfully",
                "shutdown_status": self.shutdown_status.value
            }
            
        except Exception as e:
            self.log.error(f"Error forcing shutdown: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_shutdown_history(self, session: Session, days: int = 7) -> Dict[str, Any]:
        """
        Get shutdown history for the specified number of days.
        
        @param {Session} session - Database session
        @param {int} days - Number of days to look back
        @returns {Dict} Shutdown history
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Get shutdown-related risk events
            shutdown_events = session.query(RiskEvent).filter(
                RiskEvent.event_type == RiskEventType.PORTFOLIO_LIMIT,
                RiskEvent.created_at >= cutoff_date
            ).order_by(RiskEvent.created_at.desc()).all()
            
            history = []
            for event in shutdown_events:
                event_info = event.info()
                # Add metadata if available
                if event.metadata_json:
                    try:
                        metadata = json.loads(event.metadata_json)
                        event_info['metadata'] = metadata
                    except:
                        pass
                history.append(event_info)
            
            return {
                "status": "success",
                "data": history,
                "total_events": len(history)
            }
            
        except Exception as e:
            self.log.error(f"Error getting shutdown history: {e}")
            return {
                "status": "error",
                "message": str(e)
            }