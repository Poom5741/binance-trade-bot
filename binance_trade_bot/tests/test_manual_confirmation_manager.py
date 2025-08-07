"""
Unit tests for manual confirmation manager functionality.
"""

import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger
from binance_trade_bot.models import RiskEvent, RiskEventType, RiskEventSeverity, RiskEventStatus, Pair, Coin
from binance_trade_bot.notifications import NotificationHandler
from binance_trade_bot.risk_management.manual_confirmation_manager import (
    ManualConfirmationManager, 
    ApprovalStatus, 
    ApprovalLevel
)


class TestManualConfirmationManager(unittest.TestCase):
    """Test cases for ManualConfirmationManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock(spec=Database)
        self.mock_logger = Mock(spec=Logger)
        self.mock_notification_handler = Mock(spec=NotificationHandler)
        self.mock_session = Mock()
        
        # Test configuration
        self.test_config = {
            'enable_manual_confirmation': True,
            'approval_levels_required': 2,
            'auto_approve_low_severity': True,
            'approval_timeout_minutes': 60,
            'enable_multi_level_approval': True,
            'required_approvers': ['admin', 'manager'],
            'approver_permissions': {
                'admin': ['level_1', 'level_2', 'level_3'],
                'manager': ['level_1', 'level_2'],
                'user': ['level_1']
            }
        }
        
        # Create manual confirmation manager instance
        self.manual_confirmation_manager = ManualConfirmationManager(
            self.mock_database,
            self.mock_logger,
            self.test_config,
            self.mock_notification_handler
        )
        
        # Create test objects
        self.test_pair = Pair(Coin("BTC", True), Coin("USDT", True))
        self.test_coin = Coin("BTC", True)
    
    def test_init(self):
        """Test ManualConfirmationManager initialization."""
        self.assertIsInstance(self.manual_confirmation_manager, ManualConfirmationManager)
        self.assertEqual(self.manual_confirmation_manager.enable_manual_confirmation, True)
        self.assertEqual(self.manual_confirmation_manager.approval_levels_required, 2)
        self.assertEqual(self.manual_confirmation_manager.auto_approve_low_severity, True)
        self.assertEqual(self.manual_confirmation_manager.approval_timeout_minutes, 60)
        self.assertEqual(self.manual_confirmation_manager.required_approvers, {'admin', 'manager'})
    
    def test_submit_resume_request_success(self):
        """Test successful resume request submission."""
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Mock shutdown event
        mock_shutdown_event = Mock(spec=RiskEvent, id=1, severity=RiskEventSeverity.HIGH)
        self.mock_session.query.return_value.get.return_value = mock_shutdown_event
        
        # Test data
        shutdown_event_id = 1
        requested_by = "test_user"
        reason = "Test reason"
        urgency = "high"
        
        # Call method
        result = self.manual_confirmation_manager.submit_resume_request(
            self.mock_session,
            shutdown_event_id,
            requested_by,
            reason,
            urgency
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("request_id", result)
        self.assertTrue(result["requires_approval"])
        self.assertEqual(result["approval_levels"], 2)
        
        # Verify database operations
        self.mock_session.add.assert_called()
        self.mock_session.flush.assert_called()
        
        # Verify pending approval added
        self.assertIn(result["request_id"], self.manual_confirmation_manager.pending_approvals)
    
    def test_submit_resume_request_disabled(self):
        """Test resume request submission when manual confirmation is disabled."""
        # Disable manual confirmation
        self.manual_confirmation_manager.enable_manual_confirmation = False
        
        # Mock shutdown event
        mock_shutdown_event = Mock(spec=RiskEvent, id=1, severity=RiskEventSeverity.HIGH)
        self.mock_session.query.return_value.get.return_value = mock_shutdown_event
        
        # Test data
        shutdown_event_id = 1
        requested_by = "test_user"
        
        # Call method
        result = self.manual_confirmation_manager.submit_resume_request(
            self.mock_session,
            shutdown_event_id,
            requested_by
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("auto_approved", result)
        self.assertTrue(result["auto_approved"])
        self.assertIn("Manual confirmation is disabled", result["message"])
    
    def test_submit_resume_request_auto_approve_low_severity(self):
        """Test resume request auto-approval for low severity events."""
        # Mock shutdown event
        mock_shutdown_event = Mock(spec=RiskEvent, id=1, severity=RiskEventSeverity.LOW)
        self.mock_session.query.return_value.get.return_value = mock_shutdown_event
        
        # Test data
        shutdown_event_id = 1
        requested_by = "test_user"
        
        # Call method
        result = self.manual_confirmation_manager.submit_resume_request(
            self.mock_session,
            shutdown_event_id,
            requested_by
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("auto_approved", result)
        self.assertTrue(result["auto_approved"])
        self.assertIn("low severity", result["message"])
    
    def test_submit_resume_request_not_found(self):
        """Test resume request submission when shutdown event not found."""
        # Mock shutdown event not found
        self.mock_session.query.return_value.get.return_value = None
        
        # Test data
        shutdown_event_id = 999
        requested_by = "test_user"
        
        # Call method
        result = self.manual_confirmation_manager.submit_resume_request(
            self.mock_session,
            shutdown_event_id,
            requested_by
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Shutdown event not found", result["message"])
    
    def test_approve_resume_request_success(self):
        """Test successful resume request approval."""
        # Setup pending approval
        request_id = 1
        self.manual_confirmation_manager.pending_approvals[request_id] = {
            'shutdown_event_id': 1,
            'requested_by': 'test_user',
            'requested_at': datetime.utcnow(),
            'urgency': 'normal',
            'reason': 'Test reason',
            'current_level': 0,
            'required_levels': 2,
            'approvals': [],
            'status': 'pending'
        }
        
        # Mock session
        self.mock_session.query.return_value.get.return_value = Mock(spec=RiskEvent, id=request_id)
        
        # Test data
        approver = "admin"
        approval_level = ApprovalLevel.LEVEL_1
        comments = "Approved"
        
        # Call method
        result = self.manual_confirmation_manager.approve_resume_request(
            self.mock_session,
            request_id,
            approver,
            approval_level,
            comments
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("Partial approval recorded", result["message"])
        self.assertEqual(result["current_level"], 1)
        self.assertEqual(result["required_levels"], 2)
        
        # Verify approval recorded
        approval_data = self.manual_confirmation_manager.pending_approvals[request_id]
        self.assertEqual(approval_data['current_level'], 1)
        self.assertEqual(len(approval_data['approvals']), 1)
    
    def test_approve_resume_request_final_approval(self):
        """Test final resume request approval."""
        # Setup pending approval with one existing approval
        request_id = 1
        self.manual_confirmation_manager.pending_approvals[request_id] = {
            'shutdown_event_id': 1,
            'requested_by': 'test_user',
            'requested_at': datetime.utcnow(),
            'urgency': 'normal',
            'reason': 'Test reason',
            'current_level': 1,
            'required_levels': 2,
            'approvals': [{'approver': 'user1', 'approval_level': 'level_1'}],
            'status': 'pending'
        }
        
        # Mock session
        mock_resume_request = Mock(spec=RiskEvent, id=request_id)
        self.mock_session.query.return_value.get.return_value = mock_resume_request
        
        # Test data
        approver = "admin"
        approval_level = ApprovalLevel.LEVEL_2
        comments = "Final approval"
        
        # Call method
        result = self.manual_confirmation_manager.approve_resume_request(
            self.mock_session,
            request_id,
            approver,
            approval_level,
            comments
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("fully approved", result["message"])
        self.assertEqual(result["final_approver"], approver)
        self.assertEqual(result["approvals_count"], 2)
        
        # Verify approval finalized
        approval_data = self.manual_confirmation_manager.pending_approvals[request_id]
        self.assertEqual(approval_data['status'], 'approved')
        self.assertEqual(approval_data['current_level'], 2)
        self.assertEqual(len(approval_data['approvals']), 2)
        
        # Verify risk event resolved
        mock_resume_request.resolve.assert_called_with(approver)
    
    def test_approve_resume_request_not_found(self):
        """Test resume request approval when request not found."""
        # Test data
        request_id = 999
        approver = "admin"
        
        # Call method
        result = self.manual_confirmation_manager.approve_resume_request(
            self.mock_session,
            request_id,
            approver
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Resume request not found", result["message"])
    
    def test_approve_resume_request_insufficient_permissions(self):
        """Test resume request approval with insufficient permissions."""
        # Setup pending approval
        request_id = 1
        self.manual_confirmation_manager.pending_approvals[request_id] = {
            'shutdown_event_id': 1,
            'requested_by': 'test_user',
            'requested_at': datetime.utcnow(),
            'urgency': 'normal',
            'reason': 'Test reason',
            'current_level': 0,
            'required_levels': 2,
            'approvals': [],
            'status': 'pending'
        }
        
        # Test data
        approver = "user"  # User only has level_1 permissions
        approval_level = ApprovalLevel.LEVEL_2  # Trying to approve level_2
        
        # Call method
        result = self.manual_confirmation_manager.approve_resume_request(
            self.mock_session,
            request_id,
            approver,
            approval_level
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Insufficient approval permissions", result["message"])
    
    def test_approve_resume_request_expired(self):
        """Test resume request approval when request has expired."""
        # Setup expired pending approval
        request_id = 1
        expired_time = datetime.utcnow() - timedelta(minutes=70)  # Expired
        self.manual_confirmation_manager.pending_approvals[request_id] = {
            'shutdown_event_id': 1,
            'requested_by': 'test_user',
            'requested_at': expired_time,
            'urgency': 'normal',
            'reason': 'Test reason',
            'current_level': 0,
            'required_levels': 2,
            'approvals': [],
            'status': 'pending'
        }
        
        # Test data
        approver = "admin"
        
        # Call method
        result = self.manual_confirmation_manager.approve_resume_request(
            self.mock_session,
            request_id,
            approver
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Resume request has expired", result["message"])
    
    def test_reject_resume_request_success(self):
        """Test successful resume request rejection."""
        # Setup pending approval
        request_id = 1
        self.manual_confirmation_manager.pending_approvals[request_id] = {
            'shutdown_event_id': 1,
            'requested_by': 'test_user',
            'requested_at': datetime.utcnow(),
            'urgency': 'normal',
            'reason': 'Test reason',
            'current_level': 0,
            'required_levels': 2,
            'approvals': [],
            'status': 'pending'
        }
        
        # Mock session
        mock_resume_request = Mock(spec=RiskEvent, id=request_id)
        self.mock_session.query.return_value.get.return_value = mock_resume_request
        
        # Test data
        rejecter = "admin"
        reason = "Insufficient risk management"
        comments = "Additional comments"
        
        # Call method
        result = self.manual_confirmation_manager.reject_resume_request(
            self.mock_session,
            request_id,
            rejecter,
            reason,
            comments
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("rejected successfully", result["message"])
        self.assertEqual(result["rejected_by"], rejecter)
        self.assertEqual(result["rejection_reason"], reason)
        
        # Verify rejection recorded
        approval_data = self.manual_confirmation_manager.pending_approvals[request_id]
        self.assertEqual(approval_data['status'], 'rejected')
        self.assertEqual(approval_data['rejected_by'], rejecter)
        self.assertEqual(approval_data['rejection_reason'], reason)
        
        # Verify risk event ignored
        mock_resume_request.ignore.assert_called_with(rejecter)
    
    def test_reject_resume_request_not_found(self):
        """Test resume request rejection when request not found."""
        # Test data
        request_id = 999
        rejecter = "admin"
        reason = "Test reason"
        
        # Call method
        result = self.manual_confirmation_manager.reject_resume_request(
            self.mock_session,
            request_id,
            rejecter,
            reason
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Resume request not found", result["message"])
    
    def test_escalate_resume_request_success(self):
        """Test successful resume request escalation."""
        # Setup pending approval
        request_id = 1
        self.manual_confirmation_manager.pending_approvals[request_id] = {
            'shutdown_event_id': 1,
            'requested_by': 'test_user',
            'requested_at': datetime.utcnow(),
            'urgency': 'normal',
            'reason': 'Test reason',
            'current_level': 0,
            'required_levels': 2,
            'approvals': [],
            'status': 'pending'
        }
        
        # Mock session
        mock_resume_request = Mock(spec=RiskEvent, id=request_id)
        self.mock_session.query.return_value.get.return_value = mock_resume_request
        
        # Test data
        escalator = "user"
        reason = "Need higher level approval"
        target_level = 3
        
        # Call method
        result = self.manual_confirmation_manager.escalate_resume_request(
            self.mock_session,
            request_id,
            escalator,
            reason,
            target_level
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("escalated successfully", result["message"])
        self.assertEqual(result["escalated_by"], escalator)
        self.assertEqual(result["escalation_reason"], reason)
        
        # Verify escalation recorded
        approval_data = self.manual_confirmation_manager.pending_approvals[request_id]
        self.assertEqual(approval_data['status'], 'escalated')
        self.assertEqual(approval_data['escalated_by'], escalator)
        self.assertEqual(approval_data['escalation_reason'], reason)
        self.assertEqual(approval_data['target_level'], target_level)
        
        # Verify risk event escalated
        mock_resume_request.escalate.assert_called_with(escalator)
    
    def test_escalate_resume_request_not_found(self):
        """Test resume request escalation when request not found."""
        # Test data
        request_id = 999
        escalator = "user"
        reason = "Test reason"
        
        # Call method
        result = self.manual_confirmation_manager.escalate_resume_request(
            self.mock_session,
            request_id,
            escalator,
            reason
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Resume request not found", result["message"])
    
    def test_get_pending_approvals_success(self):
        """Test successful retrieval of pending approvals."""
        # Setup pending approvals
        self.manual_confirmation_manager.pending_approvals = {
            1: {
                'shutdown_event_id': 1,
                'requested_by': 'user1',
                'requested_at': datetime.utcnow(),
                'urgency': 'normal',
                'reason': 'Reason 1',
                'current_level': 1,
                'required_levels': 2,
                'approvals': [],
                'status': 'pending'
            },
            2: {
                'shutdown_event_id': 2,
                'requested_by': 'user2',
                'requested_at': datetime.utcnow(),
                'urgency': 'high',
                'reason': 'Reason 2',
                'current_level': 0,
                'required_levels': 1,
                'approvals': [],
                'status': 'pending'
            }
        }
        
        # Call method
        result = self.manual_confirmation_manager.get_pending_approvals()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 2)
        self.assertEqual(result["total_count"], 2)
    
    def test_get_pending_approvals_empty(self):
        """Test retrieval of pending approvals when empty."""
        # Clear pending approvals
        self.manual_confirmation_manager.pending_approvals = {}
        
        # Call method
        result = self.manual_confirmation_manager.get_pending_approvals()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 0)
        self.assertEqual(result["total_count"], 0)
    
    def test_get_approval_history_success(self):
        """Test successful retrieval of approval history."""
        # Setup approval history
        self.manual_confirmation_manager.approval_history = [
            {
                'request_id': 1,
                'approver': 'admin',
                'approval_level': 'level_1',
                'approved_at': datetime.utcnow().isoformat(),
                'comments': 'Approved'
            },
            {
                'request_id': 2,
                'approver': 'manager',
                'approval_level': 'level_2',
                'approved_at': datetime.utcnow().isoformat(),
                'comments': 'Final approval'
            }
        ]
        
        # Call method
        result = self.manual_confirmation_manager.get_approval_history(limit=10)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 2)
        self.assertEqual(result["total_count"], 2)
    
    def test_get_approval_history_empty(self):
        """Test retrieval of approval history when empty."""
        # Clear approval history
        self.manual_confirmation_manager.approval_history = []
        
        # Call method
        result = self.manual_confirmation_manager.get_approval_history()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 0)
        self.assertEqual(result["total_count"], 0)
    
    def test_cleanup_expired_approvals_success(self):
        """Test successful cleanup of expired approvals."""
        # Setup expired and valid pending approvals
        expired_time = datetime.utcnow() - timedelta(minutes=70)  # Expired
        valid_time = datetime.utcnow() - timedelta(minutes=30)  # Valid
        
        self.manual_confirmation_manager.pending_approvals = {
            1: {  # Expired
                'shutdown_event_id': 1,
                'requested_by': 'user1',
                'requested_at': expired_time,
                'urgency': 'normal',
                'reason': 'Reason 1',
                'current_level': 0,
                'required_levels': 1,
                'approvals': [],
                'status': 'pending'
            },
            2: {  # Valid
                'shutdown_event_id': 2,
                'requested_by': 'user2',
                'requested_at': valid_time,
                'urgency': 'high',
                'reason': 'Reason 2',
                'current_level': 0,
                'required_levels': 1,
                'approvals': [],
                'status': 'pending'
            }
        }
        
        # Mock session
        mock_event1 = Mock(spec=RiskEvent, id=1)
        mock_event2 = Mock(spec=RiskEvent, id=2)
        self.mock_session.query.return_value.get.side_effect = [mock_event1, mock_event2]
        
        # Call method
        result = self.manual_confirmation_manager.cleanup_expired_approvals(self.mock_session)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["expired_count"], 1)
        self.assertIn("Cleaned up 1 expired approval requests", result["message"])
        
        # Verify only expired approval was cleaned up
        self.assertNotIn(1, self.manual_confirmation_manager.pending_approvals)
        self.assertIn(2, self.manual_confirmation_manager.pending_approvals)
        
        # Verify expired event was ignored
        mock_event1.ignore.assert_called_with("system")
        mock_event2.ignore.assert_not_called()
    
    def test_cleanup_expired_approvals_none_expired(self):
        """Test cleanup of expired approvals when none are expired."""
        # Setup valid pending approvals
        valid_time = datetime.utcnow() - timedelta(minutes=30)  # Valid
        
        self.manual_confirmation_manager.pending_approvals = {
            1: {
                'shutdown_event_id': 1,
                'requested_by': 'user1',
                'requested_at': valid_time,
                'urgency': 'normal',
                'reason': 'Reason 1',
                'current_level': 0,
                'required_levels': 1,
                'approvals': [],
                'status': 'pending'
            }
        }
        
        # Call method
        result = self.manual_confirmation_manager.cleanup_expired_approvals(self.mock_session)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["expired_count"], 0)
        self.assertIn("Cleaned up 0 expired approval requests", result["message"])
        
        # Verify no approvals were cleaned up
        self.assertIn(1, self.manual_confirmation_manager.pending_approvals)
    
    def test_update_configuration_success(self):
        """Test successful configuration update."""
        new_config = {
            'enable_manual_confirmation': False,
            'approval_levels_required': 3,
            'auto_approve_low_severity': False,
            'approval_timeout_minutes': 120,
            'required_approvers': ['admin', 'manager', 'supervisor'],
            'approver_permissions': {
                'admin': ['level_1', 'level_2', 'level_3'],
                'manager': ['level_1', 'level_2'],
                'supervisor': ['level_1']
            }
        }
        
        # Call method
        result = self.manual_confirmation_manager.update_configuration(new_config)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        
        # Verify configuration updated
        self.assertEqual(self.manual_confirmation_manager.enable_manual_confirmation, False)
        self.assertEqual(self.manual_confirmation_manager.approval_levels_required, 3)
        self.assertEqual(self.manual_confirmation_manager.auto_approve_low_severity, False)
        self.assertEqual(self.manual_confirmation_manager.approval_timeout_minutes, 120)
        self.assertEqual(self.manual_confirmation_manager.required_approvers, {'admin', 'manager', 'supervisor'})
    
    def test_has_approval_permission_success(self):
        """Test successful permission check."""
        approver = "admin"
        approval_level = ApprovalLevel.LEVEL_2
        
        result = self.manual_confirmation_manager._has_approval_permission(approver, approval_level)
        
        self.assertTrue(result)
    
    def test_has_approval_permission_insufficient(self):
        """Test permission check with insufficient permissions."""
        approver = "user"
        approval_level = ApprovalLevel.LEVEL_2  # User only has level_1
        
        result = self.manual_confirmation_manager._has_approval_permission(approver, approval_level)
        
        self.assertFalse(result)
    
    def test_has_approval_permission_not_in_required_list(self):
        """Test permission check when approver not in required list."""
        approver = "guest"
        approval_level = ApprovalLevel.LEVEL_1
        
        result = self.manual_confirmation_manager._has_approval_permission(approver, approval_level)
        
        self.assertFalse(result)
    
    def test_is_approval_expired_true(self):
        """Test expiration check when approval is expired."""
        request_id = 1
        expired_time = datetime.utcnow() - timedelta(minutes=70)  # Expired
        
        self.manual_confirmation_manager.pending_approvals[request_id] = {
            'requested_at': expired_time
        }
        
        result = self.manual_confirmation_manager._is_approval_expired(request_id)
        
        self.assertTrue(result)
    
    def test_is_approval_expired_false(self):
        """Test expiration check when approval is not expired."""
        request_id = 1
        valid_time = datetime.utcnow() - timedelta(minutes=30)  # Valid
        
        self.manual_confirmation_manager.pending_approvals[request_id] = {
            'requested_at': valid_time
        }
        
        result = self.manual_confirmation_manager._is_approval_expired(request_id)
        
        self.assertFalse(result)
    
    def test_is_approval_expired_not_found(self):
        """Test expiration check when approval not found."""
        request_id = 999
        
        result = self.manual_confirmation_manager._is_approval_expired(request_id)
        
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()