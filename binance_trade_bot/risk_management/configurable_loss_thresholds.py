"""
Configurable loss threshold settings for risk management.

This module implements:
- Dynamic loss threshold configuration
- Environment-specific threshold management
- Threshold validation and enforcement
- Historical threshold tracking
- Threshold change approval workflow
- Integration with emergency shutdown systems
- Real-time threshold monitoring
"""

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List, Union

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..database import Database
from ..logger import Logger
from ..models import RiskEvent, RiskEventType, RiskEventSeverity, RiskEventStatus, Pair, Coin
from ..notifications import NotificationHandler


class ThresholdType(Enum):
    DAILY_LOSS = "daily_loss"
    MAX_DRAWDOWN = "max_drawdown"
    POSITION_SIZE = "position_size"
    LEVERAGE = "leverage"
    VOLATILITY = "volatility"
    LIQUIDITY = "liquidity"
    CUSTOM = "custom"


class ThresholdStatus(Enum):
    ACTIVE = "active"
    PENDING = "pending"
    EXPIRED = "expired"
    DISABLED = "disabled"


class EnvironmentType(Enum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TESTING = "testing"


class ConfigurableLossThresholds:
    """
    Manager class for handling configurable loss threshold settings.
    
    This class provides methods to:
    - Configure and manage loss thresholds dynamically
    - Support environment-specific threshold settings
    - Validate threshold changes before implementation
    - Track threshold history and changes
    - Integrate with emergency shutdown systems
    - Monitor threshold compliance in real-time
    - Handle threshold approval workflows
    """
    
    def __init__(self, database: Database, logger: Logger, config: Dict[str, Any], notification_handler: NotificationHandler):
        """
        Initialize the configurable loss thresholds manager.
        
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
        self.enable_threshold_management = config.get('enable_threshold_management', True)
        self.require_approval_for_changes = config.get('require_approval_for_changes', True)
        self.auto_approve_dev_changes = config.get('auto_approve_dev_changes', True)
        self.threshold_change_cooldown_hours = config.get('threshold_change_cooldown_hours', 24)
        self.enable_threshold_notifications = config.get('enable_threshold_notifications', True)
        self.default_environment = EnvironmentType.PRODUCTION.value
        
        # Current thresholds
        self.current_thresholds: Dict[ThresholdType, Dict] = {}
        self.threshold_history: List[Dict] = []
        
        # Initialize logger
        self.log = logging.getLogger(__name__)
        
        # Load existing configuration
        self._load_current_thresholds()
    
    def _load_current_thresholds(self):
        """
        Load current threshold values from database or configuration.
        """
        try:
            # Load from configuration first
            config_thresholds = self.config.get('loss_thresholds', {})
            
            # Set default thresholds
            default_thresholds = {
                ThresholdType.DAILY_LOSS: {
                    'value': 5.0,
                    'unit': 'percentage',
                    'min_value': 0.1,
                    'max_value': 20.0,
                    'description': 'Maximum allowed daily loss percentage'
                },
                ThresholdType.MAX_DRAWDOWN: {
                    'value': 10.0,
                    'unit': 'percentage',
                    'min_value': 1.0,
                    'max_value': 50.0,
                    'description': 'Maximum allowed portfolio drawdown percentage'
                },
                ThresholdType.POSITION_SIZE: {
                    'value': 2.0,
                    'unit': 'percentage',
                    'min_value': 0.1,
                    'max_value': 10.0,
                    'description': 'Maximum position size as percentage of portfolio'
                },
                ThresholdType.LEVERAGE: {
                    'value': 3.0,
                    'unit': 'x',
                    'min_value': 1.0,
                    'max_value': 10.0,
                    'description': 'Maximum leverage allowed'
                },
                ThresholdType.VOLATILITY: {
                    'value': 5.0,
                    'unit': 'percentage',
                    'min_value': 1.0,
                    'max_value': 20.0,
                    'description': 'Maximum allowed volatility percentage'
                },
                ThresholdType.LIQUIDITY: {
                    'value': 10000.0,
                    'unit': 'usd',
                    'min_value': 1000.0,
                    'max_value': 1000000.0,
                    'description': 'Minimum liquidity requirement in USD'
                }
            }
            
            # Override with configuration values
            for threshold_type, config_value in config_thresholds.items():
                try:
                    enum_type = ThresholdType(threshold_type.lower())
                    if enum_type in default_thresholds:
                        default_thresholds[enum_type]['value'] = config_value
                except ValueError:
                    self.log.warning(f"Invalid threshold type in configuration: {threshold_type}")
            
            self.current_thresholds = default_thresholds
            self.log.info("Current loss thresholds loaded")
            
        except Exception as e:
            self.log.error(f"Error loading current thresholds: {e}")
    
    def get_threshold(
        self,
        threshold_type: ThresholdType,
        environment: Optional[EnvironmentType] = None,
        use_default: bool = True
    ) -> Dict[str, Any]:
        """
        Get current threshold value for a specific threshold type.
        
        @param {ThresholdType} threshold_type - Type of threshold
        @param {EnvironmentType} environment - Environment to get threshold for
        @param {bool} use_default - Whether to use default if not found
        @returns {Dict} Threshold information
        """
        try:
            # Get environment-specific threshold if provided
            if environment:
                env_threshold = self._get_environment_threshold(threshold_type, environment)
                if env_threshold:
                    return env_threshold
            
            # Get current threshold
            if threshold_type in self.current_thresholds:
                threshold_info = self.current_thresholds[threshold_type].copy()
                threshold_info['type'] = threshold_type.value
                threshold_info['status'] = ThresholdStatus.ACTIVE.value
                threshold_info['last_updated'] = datetime.utcnow().isoformat()
                return threshold_info
            
            # Return default if requested and not found
            if use_default:
                return self._get_default_threshold(threshold_type)
            
            return {
                "status": "error",
                "message": f"Threshold not found for type: {threshold_type.value}"
            }
            
        except Exception as e:
            self.log.error(f"Error getting threshold: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _get_environment_threshold(self, threshold_type: ThresholdType, environment: EnvironmentType) -> Optional[Dict]:
        """
        Get environment-specific threshold value.
        
        @param {ThresholdType} threshold_type - Type of threshold
        @param {EnvironmentType} environment - Environment type
        @returns {Dict} Environment-specific threshold or None
        """
        try:
            # This would typically query a database for environment-specific values
            # For now, we'll simulate with environment-based overrides
            env_overrides = {
                EnvironmentType.DEVELOPMENT: {
                    ThresholdType.DAILY_LOSS: 10.0,
                    ThresholdType.MAX_DRAWDOWN: 20.0,
                    ThresholdType.POSITION_SIZE: 5.0,
                    ThresholdType.LEVERAGE: 5.0
                },
                EnvironmentType.STAGING: {
                    ThresholdType.DAILY_LOSS: 7.0,
                    ThresholdType.MAX_DRAWDOWN: 15.0,
                    ThresholdType.POSITION_SIZE: 3.0,
                    ThresholdType.LEVERAGE: 4.0
                },
                EnvironmentType.TESTING: {
                    ThresholdType.DAILY_LOSS: 15.0,
                    ThresholdType.MAX_DRAWDOWN: 30.0,
                    ThresholdType.POSITION_SIZE: 10.0,
                    ThresholdType.LEVERAGE: 10.0
                }
            }
            
            if environment in env_overrides and threshold_type in env_overrides[environment]:
                base_threshold = self.current_thresholds[threshold_type].copy()
                base_threshold['value'] = env_overrides[environment][threshold_type]
                base_threshold['environment'] = environment.value
                base_threshold['type'] = threshold_type.value
                base_threshold['status'] = ThresholdStatus.ACTIVE.value
                base_threshold['last_updated'] = datetime.utcnow().isoformat()
                return base_threshold
            
            return None
            
        except Exception as e:
            self.log.error(f"Error getting environment threshold: {e}")
            return None
    
    def _get_default_threshold(self, threshold_type: ThresholdType) -> Dict:
        """
        Get default threshold value.
        
        @param {ThresholdType} threshold_type - Type of threshold
        @returns {Dict} Default threshold information
        """
        try:
            if threshold_type in self.current_thresholds:
                threshold_info = self.current_thresholds[threshold_type].copy()
                threshold_info['type'] = threshold_type.value
                threshold_info['status'] = ThresholdStatus.ACTIVE.value
                threshold_info['last_updated'] = datetime.utcnow().isoformat()
                threshold_info['is_default'] = True
                return threshold_info
            
            return {
                "status": "error",
                "message": f"No default threshold available for type: {threshold_type.value}"
            }
            
        except Exception as e:
            self.log.error(f"Error getting default threshold: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def set_threshold(
        self,
        session: Session,
        threshold_type: ThresholdType,
        new_value: float,
        environment: Optional[EnvironmentType] = None,
        requested_by: str = "system",
        reason: Optional[str] = None,
        auto_approve: bool = False
    ) -> Dict[str, Any]:
        """
        Set a new threshold value.
        
        @param {Session} session - Database session
        @param {ThresholdType} threshold_type - Type of threshold
        @param {float} new_value - New threshold value
        @param {EnvironmentType} environment - Environment to set threshold for
        @param {str} requested_by - Who requested the change
        @param {str} reason - Reason for the change
        @param {bool} auto_approve - Whether to auto-approve the change
        @returns {Dict} Set threshold result
        """
        if not self.enable_threshold_management:
            return {
                "status": "error",
                "message": "Threshold management is disabled"
            }
        
        try:
            # Validate threshold value
            validation_result = self._validate_threshold_value(threshold_type, new_value)
            if validation_result["status"] != "success":
                return validation_result
            
            # Check if approval is required
            if self.require_approval_for_changes and not auto_approve:
                return self._request_threshold_change(
                    session, threshold_type, new_value, environment, requested_by, reason
                )
            
            # Auto-approve for development environment if configured
            if environment == EnvironmentType.DEVELOPMENT and self.auto_approve_dev_changes:
                auto_approve = True
            
            # Apply the change
            return self._apply_threshold_change(
                session, threshold_type, new_value, environment, requested_by, reason, auto_approve
            )
            
        except Exception as e:
            self.log.error(f"Error setting threshold: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _validate_threshold_value(self, threshold_type: ThresholdType, value: float) -> Dict[str, Any]:
        """
        Validate threshold value against constraints.
        
        @param {ThresholdType} threshold_type - Type of threshold
        @param {float} value - Value to validate
        @returns {Dict} Validation result
        """
        try:
            if threshold_type not in self.current_thresholds:
                return {
                    "status": "error",
                    "message": f"Unknown threshold type: {threshold_type.value}"
                }
            
            threshold_config = self.current_thresholds[threshold_type]
            min_value = threshold_config.get('min_value', float('-inf'))
            max_value = threshold_config.get('max_value', float('inf'))
            
            if value < min_value:
                return {
                    "status": "error",
                    "message": f"Value {value} is below minimum allowed {min_value} for {threshold_type.value}"
                }
            
            if value > max_value:
                return {
                    "status": "error",
                    "message": f"Value {value} exceeds maximum allowed {max_value} for {threshold_type.value}"
                }
            
            return {
                "status": "success",
                "message": "Threshold value is valid"
            }
            
        except Exception as e:
            self.log.error(f"Error validating threshold value: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _request_threshold_change(
        self,
        session: Session,
        threshold_type: ThresholdType,
        new_value: float,
        environment: Optional[EnvironmentType],
        requested_by: str,
        reason: Optional[str]
    ) -> Dict[str, Any]:
        """
        Request a threshold change (requires approval).
        
        @param {Session} session - Database session
        @param {ThresholdType} threshold_type - Type of threshold
        @param {float} new_value - New threshold value
        @param {EnvironmentType} environment - Environment to set threshold for
        @param {str} requested_by - Who requested the change
        @param {str} reason - Reason for the change
        @returns {Dict} Request result
        """
        try:
            # Find a default pair for the event
            pair = session.query(Pair).first()
            if not pair:
                pair = Pair(Coin("USDT", True), Coin("BTC", True))  # Default pair
                session.add(pair)
            
            # Create threshold change request event
            threshold_request = RiskEvent(
                pair=pair,
                coin=pair.from_coin,
                event_type=RiskEventType.CUSTOM,
                severity=RiskEventSeverity.MEDIUM,
                trigger_value=new_value,
                threshold_value=self.current_thresholds[threshold_type]['value'],
                current_value=new_value,
                description=f"Threshold change request for {threshold_type.value}: {self.current_thresholds[threshold_type]['value']} → {new_value}",
                metadata_json=json.dumps({
                    'request_type': 'threshold_change',
                    'threshold_type': threshold_type.value,
                    'old_value': self.current_thresholds[threshold_type]['value'],
                    'new_value': new_value,
                    'environment': environment.value if environment else self.default_environment,
                    'requested_by': requested_by,
                    'requested_at': datetime.utcnow().isoformat(),
                    'reason': reason,
                    'requires_approval': True
                }),
                created_by=requested_by
            )
            
            session.add(threshold_request)
            session.flush()
            
            # Send notification
            if self.enable_threshold_notifications:
                self._send_threshold_change_notification(threshold_request, "requested")
            
            self.log.info(f"Threshold change requested: {threshold_type.value} to {new_value} by {requested_by}")
            
            return {
                "status": "success",
                "message": "Threshold change request submitted and pending approval",
                "request_id": threshold_request.id,
                "requires_approval": True
            }
            
        except Exception as e:
            self.log.error(f"Error requesting threshold change: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _apply_threshold_change(
        self,
        session: Session,
        threshold_type: ThresholdType,
        new_value: float,
        environment: Optional[EnvironmentType],
        requested_by: str,
        reason: Optional[str],
        approved: bool = True
    ) -> Dict[str, Any]:
        """
        Apply a threshold change.
        
        @param {Session} session - Database session
        @param {ThresholdType} threshold_type - Type of threshold
        @param {float} new_value - New threshold value
        @param {EnvironmentType} environment - Environment to set threshold for
        @param {str} requested_by - Who requested the change
        @param {str} reason - Reason for the change
        @param {bool} approved - Whether the change is approved
        @returns {Dict} Application result
        """
        try:
            old_value = self.current_thresholds[threshold_type]['value']
            
            # Update threshold value
            self.current_thresholds[threshold_type]['value'] = new_value
            
            # Record change in history
            change_record = {
                'threshold_type': threshold_type.value,
                'old_value': old_value,
                'new_value': new_value,
                'environment': environment.value if environment else self.default_environment,
                'requested_by': requested_by,
                'requested_at': datetime.utcnow().isoformat(),
                'reason': reason,
                'approved': approved,
                'status': 'applied'
            }
            
            self.threshold_history.append(change_record)
            
            # Keep only recent history (last 1000)
            if len(self.threshold_history) > 1000:
                self.threshold_history = self.threshold_history[-1000:]
            
            # Create change confirmation event
            self._create_threshold_change_event(session, threshold_type, old_value, new_value, requested_by, reason, approved)
            
            # Send notification
            if self.enable_threshold_notifications:
                status = "approved" if approved else "rejected"
                self._send_threshold_change_notification(
                    session.query(RiskEvent).filter(
                        RiskEvent.event_type == RiskEventType.CUSTOM,
                        RiskEvent.description.like(f"%Threshold change request%{threshold_type.value}%")
                    ).order_by(RiskEvent.created_at.desc()).first(),
                    status
                )
            
            self.log.info(f"Threshold change applied: {threshold_type.value} from {old_value} to {new_value} by {requested_by}")
            
            return {
                "status": "success",
                "message": f"Threshold change {'approved' if approved else 'rejected'} successfully",
                "threshold_type": threshold_type.value,
                "old_value": old_value,
                "new_value": new_value,
                "environment": environment.value if environment else self.default_environment,
                "applied": approved
            }
            
        except Exception as e:
            self.log.error(f"Error applying threshold change: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _create_threshold_change_event(
        self,
        session: Session,
        threshold_type: ThresholdType,
        old_value: float,
        new_value: float,
        requested_by: str,
        reason: Optional[str],
        approved: bool
    ):
        """
        Create a threshold change event.
        
        @param {Session} session - Database session
        @param {ThresholdType} threshold_type - Type of threshold
        @param {float} old_value - Old threshold value
        @param {float} new_value - New threshold value
        @param {str} requested_by - Who requested the change
        @param {str} reason - Reason for the change
        @param {bool} approved - Whether the change is approved
        """
        try:
            # Find a default pair for the event
            pair = session.query(Pair).first()
            if not pair:
                pair = Pair(Coin("USDT", True), Coin("BTC", True))  # Default pair
                session.add(pair)
            
            # Create threshold change event
            change_event = RiskEvent(
                pair=pair,
                coin=pair.from_coin,
                event_type=RiskEventType.CUSTOM,
                severity=RiskEventSeverity.LOW,
                trigger_value=new_value,
                threshold_value=old_value,
                current_value=new_value,
                description=f"Threshold change {'approved' if approved else 'rejected'}: {threshold_type.value} {old_value} → {new_value}",
                metadata_json=json.dumps({
                    'event_type': 'threshold_change',
                    'threshold_type': threshold_type.value,
                    'old_value': old_value,
                    'new_value': new_value,
                    'requested_by': requested_by,
                    'requested_at': datetime.utcnow().isoformat(),
                    'reason': reason,
                    'approved': approved
                }),
                created_by=requested_by
            )
            
            session.add(change_event)
            
        except Exception as e:
            self.log.error(f"Error creating threshold change event: {e}")
    
    def _send_threshold_change_notification(self, risk_event: RiskEvent, status: str):
        """
        Send notification about threshold change.
        
        @param {RiskEvent} risk_event - Risk event for threshold change
        @param {str} status - Status of the change (requested, approved, rejected)
        """
        try:
            status_emoji = {
                "requested": "⏳",
                "approved": "✅",
                "rejected": "❌"
            }.get(status, "📋")
            
            message = f"{status_emoji} THRESHOLD CHANGE {status.upper()}\n\n"
            message += f"Type: {risk_event.metadata_json.get('threshold_type', 'Unknown')}\n"
            message += f"Old Value: {risk_event.threshold_value}\n"
            message += f"New Value: {risk_event.trigger_value}\n"
            message += f"Environment: {risk_event.metadata_json.get('environment', 'Unknown')}\n"
            message += f"Requested by: {risk_event.created_by}\n"
            message += f"Time: {risk_event.created_at.isoformat()}\n"
            
            if risk_event.metadata_json.get('reason'):
                message += f"Reason: {risk_event.metadata_json.get('reason')}\n"
            
            self.notification_handler.send_notification(message)
            
        except Exception as e:
            self.log.error(f"Error sending threshold change notification: {e}")
    
    def approve_threshold_change(
        self,
        session: Session,
        request_id: int,
        approver: str,
        comments: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Approve a threshold change request.
        
        @param {Session} session - Database session
        @param {int} request_id - ID of the threshold change request
        @param {str} approver - Who is approving the change
        @param {str} comments - Approval comments
        @returns {Dict} Approval result
        """
        try:
            # Get the threshold change request
            request_event = session.query(RiskEvent).get(request_id)
            if not request_event:
                return {
                    "status": "error",
                    "message": "Threshold change request not found"
                }
            
            # Parse metadata
            metadata = json.loads(request_event.metadata_json)
            threshold_type = ThresholdType(metadata['threshold_type'])
            new_value = metadata['new_value']
            environment = EnvironmentType(metadata['environment']) if metadata['environment'] else None
            requested_by = metadata['requested_by']
            reason = metadata.get('reason')
            
            # Apply the change
            return self._apply_threshold_change(
                session, threshold_type, new_value, environment, approver, reason, True
            )
            
        except Exception as e:
            self.log.error(f"Error approving threshold change: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def reject_threshold_change(
        self,
        session: Session,
        request_id: int,
        rejecter: str,
        reason: str,
        comments: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reject a threshold change request.
        
        @param {Session} session - Database session
        @param {int} request_id - ID of the threshold change request
        @param {str} rejecter - Who is rejecting the change
        @param {str} reason - Reason for rejection
        @param {str} comments - Additional comments
        @returns {Dict} Rejection result
        """
        try:
            # Get the threshold change request
            request_event = session.query(RiskEvent).get(request_id)
            if not request_event:
                return {
                    "status": "error",
                    "message": "Threshold change request not found"
                }
            
            # Parse metadata
            metadata = json.loads(request_event.metadata_json)
            threshold_type = ThresholdType(metadata['threshold_type'])
            new_value = metadata['new_value']
            environment = EnvironmentType(metadata['environment']) if metadata['environment'] else None
            requested_by = metadata['requested_by']
            original_reason = metadata.get('reason')
            
            # Apply rejected change
            return self._apply_threshold_change(
                session, threshold_type, new_value, environment, rejecter, original_reason, False
            )
            
        except Exception as e:
            self.log.error(f"Error rejecting threshold change: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_all_thresholds(self, environment: Optional[EnvironmentType] = None) -> Dict[str, Any]:
        """
        Get all current threshold values.
        
        @param {EnvironmentType} environment - Environment to get thresholds for
        @returns {Dict} All threshold values
        """
        try:
            thresholds = {}
            
            for threshold_type in ThresholdType:
                threshold_info = self.get_threshold(threshold_type, environment)
                if threshold_info["status"] == "success":
                    thresholds[threshold_type.value] = threshold_info
            
            return {
                "status": "success",
                "data": thresholds,
                "environment": environment.value if environment else self.default_environment,
                "total_thresholds": len(thresholds)
            }
            
        except Exception as e:
            self.log.error(f"Error getting all thresholds: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_threshold_history(
        self,
        threshold_type: Optional[ThresholdType] = None,
        environment: Optional[EnvironmentType] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get threshold change history.
        
        @param {ThresholdType} threshold_type - Filter by threshold type
        @param {EnvironmentType} environment - Filter by environment
        @param {int} limit - Maximum number of records to return
        @returns {Dict} Threshold history
        """
        try:
            # Filter history based on criteria
            filtered_history = self.threshold_history
            
            if threshold_type:
                filtered_history = [
                    record for record in filtered_history
                    if record['threshold_type'] == threshold_type.value
                ]
            
            if environment:
                filtered_history = [
                    record for record in filtered_history
                    if record['environment'] == environment.value
                ]
            
            # Sort by timestamp (newest first) and limit
            filtered_history.sort(key=lambda x: x['requested_at'], reverse=True)
            limited_history = filtered_history[:limit]
            
            return {
                "status": "success",
                "data": limited_history,
                "total_records": len(filtered_history),
                "returned_records": len(limited_history),
                "filters": {
                    "threshold_type": threshold_type.value if threshold_type else None,
                    "environment": environment.value if environment else None
                }
            }
            
        except Exception as e:
            self.log.error(f"Error getting threshold history: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def reset_threshold_to_default(
        self,
        session: Session,
        threshold_type: ThresholdType,
        environment: Optional[EnvironmentType] = None,
        reset_by: str = "system"
    ) -> Dict[str, Any]:
        """
        Reset a threshold to its default value.
        
        @param {Session} session - Database session
        @param {ThresholdType} threshold_type - Type of threshold to reset
        @param {EnvironmentType} environment - Environment to reset threshold for
        @param {str} reset_by - Who is resetting the threshold
        @returns {Dict} Reset result
        """
        try:
            # Get default value
            default_threshold = self._get_default_threshold(threshold_type)
            if default_threshold["status"] != "success":
                return default_threshold
            
            default_value = default_threshold['value']
            
            # Set threshold to default value
            return self.set_threshold(
                session, threshold_type, default_value, environment, reset_by, "Reset to default", True
            )
            
        except Exception as e:
            self.log.error(f"Error resetting threshold to default: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def check_threshold_compliance(self, current_values: Dict[ThresholdType, float]) -> Dict[str, Any]:
        """
        Check if current values comply with configured thresholds.
        
        @param {Dict} current_values - Current values to check against thresholds
        @returns {Dict} Compliance check result
        """
        try:
            violations = []
            compliant = True
            
            for threshold_type, current_value in current_values.items():
                if threshold_type in self.current_thresholds:
                    threshold_value = self.current_thresholds[threshold_type]['value']
                    
                    if current_value > threshold_value:
                        violations.append({
                            'threshold_type': threshold_type.value,
                            'threshold_value': threshold_value,
                            'current_value': current_value,
                            'severity': 'high' if current_value > threshold_value * 1.5 else 'medium'
                        })
                        compliant = False
            
            return {
                "status": "success",
                "compliant": compliant,
                "violations": violations,
                "violation_count": len(violations),
                "thresholds_checked": len(current_values)
            }
            
        except Exception as e:
            self.log.error(f"Error checking threshold compliance: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def update_configuration(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update threshold management configuration.
        
        @param {Dict} new_config - New configuration parameters
        @returns {Dict} Update result
        """
        try:
            # Update configuration parameters
            self.enable_threshold_management = new_config.get('enable_threshold_management', self.enable_threshold_management)
            self.require_approval_for_changes = new_config.get('require_approval_for_changes', self.require_approval_for_changes)
            self.auto_approve_dev_changes = new_config.get('auto_approve_dev_changes', self.auto_approve_dev_changes)
            self.threshold_change_cooldown_hours = new_config.get('threshold_change_cooldown_hours', self.threshold_change_cooldown_hours)
            self.enable_threshold_notifications = new_config.get('enable_threshold_notifications', self.enable_threshold_notifications)
            
            # Update default environment
            default_env = new_config.get('default_environment', self.default_environment)
            if default_env in [env.value for env in EnvironmentType]:
                self.default_environment = default_env
            
            # Update loss thresholds
            loss_thresholds = new_config.get('loss_thresholds', {})
            for threshold_type, value in loss_thresholds.items():
                try:
                    enum_type = ThresholdType(threshold_type.lower())
                    if enum_type in self.current_thresholds:
                        self.current_thresholds[enum_type]['value'] = float(value)
                except ValueError:
                    self.log.warning(f"Invalid threshold type or value in configuration: {threshold_type}={value}")
            
            self.log.info("Threshold management configuration updated")
            
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