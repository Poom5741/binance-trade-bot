"""
Manual confirmation manager for resuming after loss limits.

This module implements:
- Manual confirmation workflow for resuming trading after emergency shutdown
- Approval queue management for pending resume requests
- Multi-level approval support if configured
- Approval tracking and audit logging
- Integration with risk event logging system
- Configurable approval rules and thresholds
"""

import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List, Set

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..database import Database
from ..logger import Logger
from ..models import RiskEvent, RiskEventType, RiskEventSeverity, RiskEventStatus, Pair, Coin
from ..notifications import NotificationHandler


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class ApprovalLevel(Enum):
    LEVEL_1 = "level_1"  # Basic approval
    LEVEL_2 = "level_2"  # Secondary approval
    LEVEL_3 = "level_3"  # Final approval
    AUTO = "auto"  # Automatic approval


class ManualConfirmationManager:
    """
    Manager class for handling manual confirmation requirements after emergency shutdown.
    
    This class provides methods to:
    - Manage approval workflow for resume requests
    - Support multi-level approval if configured
    - Track approval history and audit trail
    - Integrate with risk event logging system
    - Configure approval rules and thresholds
    - Handle approval expiration and timeouts
    """
    
    def __init__(self, database: Database, logger: Logger, config: Dict[str, Any], notification_handler: NotificationHandler):
        """
        Initialize the manual confirmation manager.
        
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
        self.enable_manual_confirmation = config.get('enable_manual_confirmation', True)
        self.approval_levels_required = config.get('approval_levels_required', 1)
        self.auto_approve_low_severity = config.get('auto_approve_low_severity', False)
        self.approval_timeout_minutes = config.get('approval_timeout_minutes', 60)
        self.enable_multi_level_approval = config.get('enable_multi_level_approval', False)
        self.required_approvers = config.get('required_approvers', set())
        self.approver_permissions = config.get('approver_permissions', {})
        
        # Approval tracking
        self.pending_approvals: Dict[int, Dict] = {}
        self.approval_history: List[Dict] = []
        
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
            self.log.info("Manual confirmation manager configuration loaded")
        except Exception as e:
            self.log.error(f"Error loading configuration: {e}")
    
    def submit_resume_request(
        self,
        session: Session,
        shutdown_event_id: int,
        requested_by: str,
        reason: Optional[str] = None,
        urgency: str = "normal"
    ) -> Dict[str, Any]:
        """
        Submit a new resume request for manual confirmation.
        
        @param {Session} session - Database session
        @param {int} shutdown_event_id - ID of the shutdown event
        @param {str} requested_by - Who is requesting the resume
        @param {str} reason - Reason for the resume request
        @param {str} urgency - Urgency level (low, normal, high, critical)
        @returns {Dict} Resume request submission result
        """
        if not self.enable_manual_confirmation:
            return {
                "status": "success",
                "message": "Manual confirmation is disabled, auto-approving resume",
                "auto_approved": True
            }
        
        try:
            # Verify shutdown event exists
            shutdown_event = session.query(RiskEvent).get(shutdown_event_id)
            if not shutdown_event:
                return {
                    "status": "error",
                    "message": "Shutdown event not found"
                }
            
            # Check if already approved
            existing_approval = session.query(RiskEvent).filter(
                RiskEvent.event_type == RiskEventType.CUSTOM,
                RiskEvent.description.like(f"%resume_request%{requested_by}%"),
                RiskEvent.status == RiskEventStatus.RESOLVED
            ).first()
            
            if existing_approval:
                return {
                    "status": "error",
                    "message": "Resume request already approved"
                }
            
            # Auto-approve low severity if configured
            if self.auto_approve_low_severity and shutdown_event.severity == RiskEventSeverity.LOW:
                return self._auto_approve_resume(session, shutdown_event_id, requested_by, reason)
            
            # Create resume request event
            resume_request = self._create_resume_request_event(
                session, shutdown_event, requested_by, reason, urgency
            )
            
            # Add to pending approvals
            self.pending_approvals[resume_request.id] = {
                'shutdown_event_id': shutdown_event_id,
                'requested_by': requested_by,
                'requested_at': datetime.utcnow(),
                'urgency': urgency,
                'reason': reason,
                'current_level': 0,
                'required_levels': self.approval_levels_required,
                'approvals': [],
                'status': ApprovalStatus.PENDING.value
            }
            
            # Send notification to approvers
            self._send_resume_request_notification(resume_request, urgency)
            
            self.log.info(f"Resume request submitted: {resume_request.id} by {requested_by}")
            
            return {
                "status": "success",
                "message": "Resume request submitted successfully",
                "request_id": resume_request.id,
                "requires_approval": True,
                "approval_levels": self.approval_levels_required
            }
            
        except Exception as e:
            self.log.error(f"Error submitting resume request: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _auto_approve_resume(
        self,
        session: Session,
        shutdown_event_id: int,
        requested_by: str,
        reason: Optional[str]
    ) -> Dict[str, Any]:
        """
        Auto-approve resume request for low severity events.
        
        @param {Session} session - Database session
        @param {int} shutdown_event_id - ID of the shutdown event
        @param {str} requested_by - Who requested the resume
        @param {str} reason - Reason for the resume request
        @returns {Dict} Auto-approval result
        """
        try:
            shutdown_event = session.query(RiskEvent).get(shutdown_event_id)
            if not shutdown_event:
                return {
                    "status": "error",
                    "message": "Shutdown event not found"
                }
            
            # Create auto-approval event
            auto_approval = self._create_auto_approval_event(
                session, shutdown_event, requested_by, reason
            )
            
            self.log.info(f"Resume request auto-approved: {auto_approval.id} by {requested_by}")
            
            return {
                "status": "success",
                "message": "Resume request auto-approved (low severity)",
                "request_id": auto_approval.id,
                "auto_approved": True
            }
            
        except Exception as e:
            self.log.error(f"Error auto-approving resume: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _create_resume_request_event(
        self,
        session: Session,
        shutdown_event: RiskEvent,
        requested_by: str,
        reason: Optional[str],
        urgency: str
    ) -> RiskEvent:
        """
        Create a resume request risk event.
        
        @param {Session} session - Database session
        @param {RiskEvent} shutdown_event - Original shutdown event
        @param {str} requested_by - Who requested the resume
        @param {str} reason - Reason for the resume request
        @param {str} urgency - Urgency level
        @returns {RiskEvent} Created resume request event
        """
        try:
            # Find a default pair for the event
            pair = session.query(Pair).first()
            if not pair:
                pair = Pair(Coin("USDT", True), Coin("BTC", True))  # Default pair
                session.add(pair)
            
            # Create resume request event
            resume_request = RiskEvent(
                pair=pair,
                coin=pair.from_coin,
                event_type=RiskEventType.CUSTOM,
                severity=RiskEventSeverity.MEDIUM,
                trigger_value=0,
                threshold_value=0,
                current_value=0,
                description=f"Resume request after emergency shutdown - requested by {requested_by}",
                metadata_json=json.dumps({
                    'request_type': 'resume_request',
                    'shutdown_event_id': shutdown_event.id,
                    'original_shutdown_reason': shutdown_event.event_type.value,
                    'requested_by': requested_by,
                    'requested_at': datetime.utcnow().isoformat(),
                    'reason': reason,
                    'urgency': urgency,
                    'approval_levels_required': self.approval_levels_required,
                    'auto_approve_low_severity': self.auto_approve_low_severity
                }),
                created_by=requested_by
            )
            
            session.add(resume_request)
            session.flush()
            
            return resume_request
            
        except Exception as e:
            self.log.error(f"Error creating resume request event: {e}")
            raise
    
    def _create_auto_approval_event(
        self,
        session: Session,
        shutdown_event: RiskEvent,
        requested_by: str,
        reason: Optional[str]
    ) -> RiskEvent:
        """
        Create an auto-approval risk event.
        
        @param {Session} session - Database session
        @param {RiskEvent} shutdown_event - Original shutdown event
        @param {str} requested_by - Who requested the resume
        @param {str} reason - Reason for the resume request
        @returns {RiskEvent} Created auto-approval event
        """
        try:
            # Find a default pair for the event
            pair = session.query(Pair).first()
            if not pair:
                pair = Pair(Coin("USDT", True), Coin("BTC", True))  # Default pair
                session.add(pair)
            
            # Create auto-approval event
            auto_approval = RiskEvent(
                pair=pair,
                coin=pair.from_coin,
                event_type=RiskEventType.CUSTOM,
                severity=RiskEventSeverity.LOW,
                trigger_value=0,
                threshold_value=0,
                current_value=0,
                description=f"Auto-approved resume after emergency shutdown - requested by {requested_by}",
                metadata_json=json.dumps({
                    'request_type': 'auto_approval',
                    'shutdown_event_id': shutdown_event.id,
                    'original_shutdown_reason': shutdown_event.event_type.value,
                    'requested_by': requested_by,
                    'requested_at': datetime.utcnow().isoformat(),
                    'reason': reason,
                    'auto_approved': True,
                    'auto_appro_reason': 'Low severity event'
                }),
                created_by=requested_by
            )
            
            session.add(auto_approval)
            session.flush()
            
            return auto_approval
            
        except Exception as e:
            self.log.error(f"Error creating auto-approval event: {e}")
            raise
    
    def approve_resume_request(
        self,
        session: Session,
        request_id: int,
        approver: str,
        approval_level: ApprovalLevel = ApprovalLevel.LEVEL_1,
        comments: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Approve a resume request.
        
        @param {Session} session - Database session
        @param {int} request_id - ID of the resume request
        @param {str} approver - Who is approving the request
        @param {ApprovalLevel} approval_level - Approval level
        @param {str} comments - Approval comments
        @returns {Dict} Approval result
        """
        try:
            # Check if request exists and is pending
            if request_id not in self.pending_approvals:
                return {
                    "status": "error",
                    "message": "Resume request not found or already processed"
                }
            
            approval_data = self.pending_approvals[request_id]
            
            # Check if approver has permission
            if not self._has_approval_permission(approver, approval_level):
                return {
                    "status": "error",
                    "message": "Insufficient approval permissions"
                }
            
            # Check if approval is still valid (not expired)
            if self._is_approval_expired(request_id):
                return {
                    "status": "error",
                    "message": "Resume request has expired"
                }
            
            # Record approval
            approval_record = {
                'request_id': request_id,
                'approver': approver,
                'approval_level': approval_level.value,
                'approved_at': datetime.utcnow().isoformat(),
                'comments': comments
            }
            
            approval_data['approvals'].append(approval_record)
            approval_data['current_level'] += 1
            
            # Log approval
            self._log_approval(approval_record)
            
            # Check if all required approvals are obtained
            if approval_data['current_level'] >= approval_data['required_levels']:
                return self._finalize_approval(session, request_id, approver)
            else:
                # Send notification for partial approval
                self._send_partial_approval_notification(request_id, approver)
                
                return {
                    "status": "success",
                    "message": f"Partial approval recorded. {approval_data['current_level']}/{approval_data['required_levels']} approvals obtained",
                    "request_id": request_id,
                    "current_level": approval_data['current_level'],
                    "required_levels": approval_data['required_levels']
                }
            
        except Exception as e:
            self.log.error(f"Error approving resume request: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _has_approval_permission(self, approver: str, approval_level: ApprovalLevel) -> bool:
        """
        Check if approver has permission for the specified approval level.
        
        @param {str} approver - Approver identifier
        @param {ApprovalLevel} approval_level - Approval level
        @returns {bool} True if permission granted
        """
        try:
            # Check if approver is in required approvers list
            if self.required_approvers and approver not in self.required_approvers:
                return False
            
            # Check approver permissions
            approver_perms = self.approver_permissions.get(approver, [])
            return approval_level.value in approver_perms
            
        except Exception as e:
            self.log.error(f"Error checking approval permission: {e}")
            return False
    
    def _is_approval_expired(self, request_id: int) -> bool:
        """
        Check if a resume request has expired.
        
        @param {int} request_id - ID of the resume request
        @returns {bool} True if expired
        """
        try:
            if request_id not in self.pending_approvals:
                return True
            
            approval_data = self.pending_approvals[request_id]
            expiry_time = approval_data['requested_at'] + timedelta(minutes=self.approval_timeout_minutes)
            
            return datetime.utcnow() > expiry_time
            
        except Exception as e:
            self.log.error(f"Error checking approval expiration: {e}")
            return True
    
    def _finalize_approval(self, session: Session, request_id: int, final_approver: str) -> Dict[str, Any]:
        """
        Finalize approval process and update the resume request.
        
        @param {Session} session - Database session
        @param {int} request_id - ID of the resume request
        @param {str} final_approver - Who gave the final approval
        @returns {Dict} Finalization result
        """
        try:
            approval_data = self.pending_approvals[request_id]
            
            # Update approval status
            approval_data['status'] = ApprovalStatus.APPROVED.value
            approval_data['approved_at'] = datetime.utcnow().isoformat()
            approval_data['final_approver'] = final_approver
            
            # Get the resume request event
            resume_request = session.query(RiskEvent).get(request_id)
            if not resume_request:
                return {
                    "status": "error",
                    "message": "Resume request event not found"
                }
            
            # Resolve the resume request
            resume_request.resolve(final_approver)
            
            # Send final approval notification
            self._send_final_approval_notification(resume_request, final_approver)
            
            # Remove from pending approvals
            del self.pending_approvals[request_id]
            
            self.log.info(f"Resume request approved: {request_id} by {final_approver}")
            
            return {
                "status": "success",
                "message": "Resume request fully approved",
                "request_id": request_id,
                "final_approver": final_approver,
                "approvals_count": len(approval_data['approvals'])
            }
            
        except Exception as e:
            self.log.error(f"Error finalizing approval: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _log_approval(self, approval_record: Dict):
        """
        Log approval action.
        
        @param {Dict} approval_record - Approval record to log
        """
        try:
            log_entry = {
                **approval_record,
                'logged_at': datetime.utcnow().isoformat()
            }
            
            self.approval_history.append(log_entry)
            
            # Keep only recent approval history (last 1000)
            if len(self.approval_history) > 1000:
                self.approval_history = self.approval_history[-1000:]
            
        except Exception as e:
            self.log.error(f"Error logging approval: {e}")
    
    def _send_resume_request_notification(self, resume_request: RiskEvent, urgency: str):
        """
        Send notification about new resume request.
        
        @param {RiskEvent} resume_request - Resume request event
        @param {str} urgency - Urgency level
        """
        try:
            urgency_emoji = {
                "low": "ℹ️",
                "normal": "⚠️",
                "high": "🚨",
                "critical": "🔥"
            }.get(urgency, "⚠️")
            
            message = f"{urgency_emoji} RESUME REQUEST SUBMITTED\n\n"
            message += f"Request ID: {resume_request.id}\n"
            message += f"Requested by: {resume_request.created_by}\n"
            message += f"Request time: {resume_request.created_at.isoformat()}\n"
            message += f"Urgency: {urgency.upper()}\n"
            message += f"Original shutdown: {resume_request.metadata_json.get('original_shutdown_reason', 'Unknown')}\n"
            message += f"Reason: {resume_request.metadata_json.get('reason', 'Not specified')}\n"
            message += f"Approval levels required: {resume_request.metadata_json.get('approval_levels_required', 1)}\n"
            message += f"\n⚠️  Awaiting manual approval to resume trading"
            
            self.notification_handler.send_notification(message)
            
        except Exception as e:
            self.log.error(f"Error sending resume request notification: {e}")
    
    def _send_partial_approval_notification(self, request_id: int, approver: str):
        """
        Send notification about partial approval.
        
        @param {int} request_id - ID of the resume request
        @param {str} approver - Who gave the partial approval
        """
        try:
            approval_data = self.pending_approvals[request_id]
            
            message = f"📋 PARTIAL APPROVAL RECORDED\n\n"
            message += f"Request ID: {request_id}\n"
            message += f"Approved by: {approver}\n"
            message += f"Current progress: {approval_data['current_level']}/{approval_data['required_levels']} approvals\n"
            message += f"Time: {datetime.utcnow().isoformat()}\n"
            message += f"\n⏳ Awaiting additional approvals"
            
            self.notification_handler.send_notification(message)
            
        except Exception as e:
            self.log.error(f"Error sending partial approval notification: {e}")
    
    def _send_final_approval_notification(self, resume_request: RiskEvent, final_approver: str):
        """
        Send notification about final approval.
        
        @param {RiskEvent} resume_request - Resume request event
        @param {str} final_approver - Who gave the final approval
        """
        try:
            message = f"✅ RESUME REQUEST APPROVED\n\n"
            message += f"Request ID: {resume_request.id}\n"
            message += f"Final approval by: {final_approver}\n"
            message += f"Original shutdown: {resume_request.metadata_json.get('original_shutdown_reason', 'Unknown')}\n"
            message += f"Requested by: {resume_request.created_by}\n"
            message += f"Approval time: {datetime.utcnow().isoformat()}\n"
            message += f"\n✅ Trading can now be resumed"
            
            self.notification_handler.send_notification(message)
            
        except Exception as e:
            self.log.error(f"Error sending final approval notification: {e}")
    
    def reject_resume_request(
        self,
        session: Session,
        request_id: int,
        rejecter: str,
        reason: str,
        comments: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reject a resume request.
        
        @param {Session} session - Database session
        @param {int} request_id - ID of the resume request
        @param {str} rejecter - Who is rejecting the request
        @param {str} reason - Reason for rejection
        @param {str} comments - Additional comments
        @returns {Dict} Rejection result
        """
        try:
            # Check if request exists and is pending
            if request_id not in self.pending_approvals:
                return {
                    "status": "error",
                    "message": "Resume request not found or already processed"
                }
            
            approval_data = self.pending_approvals[request_id]
            
            # Update approval status
            approval_data['status'] = ApprovalStatus.REJECTED.value
            approval_data['rejected_at'] = datetime.utcnow().isoformat()
            approval_data['rejected_by'] = rejecter
            approval_data['rejection_reason'] = reason
            approval_data['rejection_comments'] = comments
            
            # Get the resume request event
            resume_request = session.query(RiskEvent).get(request_id)
            if not resume_request:
                return {
                    "status": "error",
                    "message": "Resume request event not found"
                }
            
            # Ignore the resume request (mark as rejected)
            resume_request.ignore(rejecter)
            
            # Send rejection notification
            self._send_rejection_notification(resume_request, rejecter, reason, comments)
            
            # Remove from pending approvals
            del self.pending_approvals[request_id]
            
            self.log.info(f"Resume request rejected: {request_id} by {rejecter}")
            
            return {
                "status": "success",
                "message": "Resume request rejected successfully",
                "request_id": request_id,
                "rejected_by": rejecter,
                "rejection_reason": reason
            }
            
        except Exception as e:
            self.log.error(f"Error rejecting resume request: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _send_rejection_notification(
        self,
        resume_request: RiskEvent,
        rejecter: str,
        reason: str,
        comments: Optional[str]
    ):
        """
        Send notification about resume request rejection.
        
        @param {RiskEvent} resume_request - Resume request event
        @param {str} rejecter - Who rejected the request
        @param {str} reason - Reason for rejection
        @param {str} comments - Additional comments
        """
        try:
            message = f"❌ RESUME REQUEST REJECTED\n\n"
            message += f"Request ID: {resume_request.id}\n"
            message += f"Rejected by: {rejecter}\n"
            message += f"Rejection reason: {reason}\n"
            message += f"Original shutdown: {resume_request.metadata_json.get('original_shutdown_reason', 'Unknown')}\n"
            message += f"Requested by: {resume_request.created_by}\n"
            message += f"Rejection time: {datetime.utcnow().isoformat()}\n"
            
            if comments:
                message += f"Comments: {comments}\n"
            
            message += f"\n❌ Trading remains halted"
            
            self.notification_handler.send_notification(message)
            
        except Exception as e:
            self.log.error(f"Error sending rejection notification: {e}")
    
    def escalate_resume_request(
        self,
        session: Session,
        request_id: int,
        escalator: str,
        reason: str,
        target_level: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Escalate a resume request to higher approval level.
        
        @param {Session} session - Database session
        @param {int} request_id - ID of the resume request
        @param {str} escalator - Who is escalating the request
        @param {str} reason - Reason for escalation
        @param {int} target_level - Target approval level (optional)
        @returns {Dict} Escalation result
        """
        try:
            # Check if request exists and is pending
            if request_id not in self.pending_approvals:
                return {
                    "status": "error",
                    "message": "Resume request not found or already processed"
                }
            
            approval_data = self.pending_approvals[request_id]
            
            # Update approval status
            approval_data['status'] = ApprovalStatus.ESCALATED.value
            approval_data['escalated_at'] = datetime.utcnow().isoformat()
            approval_data['escalated_by'] = escalator
            approval_data['escalation_reason'] = reason
            approval_data['target_level'] = target_level
            
            # Get the resume request event
            resume_request = session.query(RiskEvent).get(request_id)
            if not resume_request:
                return {
                    "status": "error",
                    "message": "Resume request event not found"
                }
            
            # Escalate the resume request
            resume_request.escalate(escalator)
            
            # Send escalation notification
            self._send_escalation_notification(resume_request, escalator, reason, target_level)
            
            self.log.info(f"Resume request escalated: {request_id} by {escalator}")
            
            return {
                "status": "success",
                "message": "Resume request escalated successfully",
                "request_id": request_id,
                "escalated_by": escalator,
                "escalation_reason": reason
            }
            
        except Exception as e:
            self.log.error(f"Error escalating resume request: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _send_escalation_notification(
        self,
        resume_request: RiskEvent,
        escalator: str,
        reason: str,
        target_level: Optional[int]
    ):
        """
        Send notification about resume request escalation.
        
        @param {RiskEvent} resume_request - Resume request event
        @param {str} escalator - Who escalated the request
        @param {str} reason - Reason for escalation
        @param {int} target_level - Target approval level
        """
        try:
            message = f"🚨 RESUME REQUEST ESCALATED\n\n"
            message += f"Request ID: {resume_request.id}\n"
            message += f"Escalated by: {escalator}\n"
            message += f"Escalation reason: {reason}\n"
            message += f"Original shutdown: {resume_request.metadata_json.get('original_shutdown_reason', 'Unknown')}\n"
            message += f"Requested by: {resume_request.created_by}\n"
            message += f"Escalation time: {datetime.utcnow().isoformat()}\n"
            
            if target_level:
                message += f"Target level: {target_level}\n"
            
            message += f"\n🚨 Immediate attention required"
            
            self.notification_handler.send_notification(message)
            
        except Exception as e:
            self.log.error(f"Error sending escalation notification: {e}")
    
    def get_pending_approvals(self) -> Dict[str, Any]:
        """
        Get all pending resume requests.
        
        @returns {Dict} Pending approvals
        """
        try:
            return {
                "status": "success",
                "data": list(self.pending_approvals.values()),
                "total_count": len(self.pending_approvals)
            }
        except Exception as e:
            self.log.error(f"Error getting pending approvals: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_approval_history(self, limit: int = 100) -> Dict[str, Any]:
        """
        Get approval history.
        
        @param {int} limit - Maximum number of records to return
        @returns {Dict} Approval history
        """
        try:
            return {
                "status": "success",
                "data": self.approval_history[-limit:],
                "total_count": len(self.approval_history)
            }
        except Exception as e:
            self.log.error(f"Error getting approval history: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def cleanup_expired_approvals(self, session: Session) -> Dict[str, Any]:
        """
        Clean up expired approval requests.
        
        @param {Session} session - Database session
        @returns {Dict} Cleanup result
        """
        try:
            expired_count = 0
            
            for request_id, approval_data in list(self.pending_approvals.items()):
                if self._is_approval_expired(request_id):
                    # Mark as expired
                    approval_data['status'] = ApprovalStatus.EXPIRED.value
                    approval_data['expired_at'] = datetime.utcnow().isoformat()
                    
                    # Get the resume request event
                    resume_request = session.query(RiskEvent).get(request_id)
                    if resume_request:
                        resume_request.ignore("system")
                    
                    # Remove from pending approvals
                    del self.pending_approvals[request_id]
                    expired_count += 1
                    
                    self.log.info(f"Expired approval cleaned up: {request_id}")
            
            return {
                "status": "success",
                "message": f"Cleaned up {expired_count} expired approval requests",
                "expired_count": expired_count
            }
            
        except Exception as e:
            self.log.error(f"Error cleaning up expired approvals: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def update_configuration(self, new_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update manual confirmation manager configuration.
        
        @param {Dict} new_config - New configuration parameters
        @returns {Dict} Update result
        """
        try:
            # Update configuration parameters
            self.enable_manual_confirmation = new_config.get('enable_manual_confirmation', self.enable_manual_confirmation)
            self.approval_levels_required = new_config.get('approval_levels_required', self.approval_levels_required)
            self.auto_approve_low_severity = new_config.get('auto_approve_low_severity', self.auto_approve_low_severity)
            self.approval_timeout_minutes = new_config.get('approval_timeout_minutes', self.approval_timeout_minutes)
            self.enable_multi_level_approval = new_config.get('enable_multi_level_approval', self.enable_multi_level_approval)
            
            # Update required approvers
            required_approvers = new_config.get('required_approvers', [])
            self.required_approvers = set(required_approvers) if isinstance(required_approvers, list) else self.required_approvers
            
            # Update approver permissions
            self.approver_permissions = new_config.get('approver_permissions', self.approver_permissions)
            
            self.log.info("Manual confirmation manager configuration updated")
            
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