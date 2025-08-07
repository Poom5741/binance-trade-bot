"""
Unit tests for configurable loss thresholds functionality.
"""

import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger
from binance_trade_bot.models import RiskEvent, RiskEventType, RiskEventSeverity, RiskEventStatus, Pair, Coin
from binance_trade_bot.notifications import NotificationHandler
from binance_trade_bot.risk_management.configurable_loss_thresholds import (
    ConfigurableLossThresholds,
    ThresholdType,
    ThresholdStatus,
    EnvironmentType
)


class TestConfigurableLossThresholds(unittest.TestCase):
    """Test cases for ConfigurableLossThresholds class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock(spec=Database)
        self.mock_logger = Mock(spec=Logger)
        self.mock_notification_handler = Mock(spec=NotificationHandler)
        self.mock_session = Mock()
        
        # Test configuration
        self.test_config = {
            'enable_threshold_management': True,
            'require_approval_for_changes': True,
            'auto_approve_dev_changes': True,
            'threshold_change_cooldown_hours': 24,
            'enable_threshold_notifications': True,
            'loss_thresholds': {
                'daily_loss': 3.0,
                'max_drawdown': 8.0,
                'position_size': 1.5
            }
        }
        
        # Create configurable loss thresholds instance
        self.configurable_thresholds = ConfigurableLossThresholds(
            self.mock_database,
            self.mock_logger,
            self.test_config,
            self.mock_notification_handler
        )
        
        # Create test objects
        self.test_pair = Pair(Coin("BTC", True), Coin("USDT", True))
        self.test_coin = Coin("BTC", True)
    
    def test_init(self):
        """Test ConfigurableLossThresholds initialization."""
        self.assertIsInstance(self.configurable_thresholds, ConfigurableLossThresholds)
        self.assertEqual(self.configurable_thresholds.enable_threshold_management, True)
        self.assertEqual(self.configurable_thresholds.require_approval_for_changes, True)
        self.assertEqual(self.configurable_thresholds.auto_approve_dev_changes, True)
        self.assertEqual(self.configurable_thresholds.threshold_change_cooldown_hours, 24)
        self.assertEqual(self.configurable_thresholds.enable_threshold_notifications, True)
        self.assertEqual(self.configurable_thresholds.default_environment, 'production')
    
    def test_get_threshold_success(self):
        """Test successful threshold retrieval."""
        threshold_type = ThresholdType.DAILY_LOSS
        
        result = self.configurable_thresholds.get_threshold(threshold_type)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["type"], threshold_type.value)
        self.assertEqual(result["value"], 3.0)  # From test config
        self.assertEqual(result["unit"], "percentage")
        self.assertEqual(result["status"], ThresholdStatus.ACTIVE.value)
    
    def test_get_threshold_not_found(self):
        """Test threshold retrieval when threshold type not found."""
        # Create an invalid threshold type
        class InvalidThresholdType:
            value = "invalid_threshold"
        
        threshold_type = InvalidThresholdType()
        
        result = self.configurable_thresholds.get_threshold(threshold_type, use_default=False)
        
        self.assertEqual(result["status"], "error")
        self.assertIn("Threshold not found", result["message"])
    
    def test_get_threshold_environment_specific(self):
        """Test environment-specific threshold retrieval."""
        threshold_type = ThresholdType.DAILY_LOSS
        environment = EnvironmentType.DEVELOPMENT
        
        result = self.configurable_thresholds.get_threshold(threshold_type, environment)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["type"], threshold_type.value)
        self.assertEqual(result["value"], 10.0)  # Development override
        self.assertEqual(result["environment"], environment.value)
    
    def test_get_threshold_default_fallback(self):
        """Test threshold retrieval with default fallback."""
        threshold_type = ThresholdType.DAILY_LOSS
        
        # Clear current thresholds to test default fallback
        self.configurable_thresholds.current_thresholds = {}
        
        result = self.configurable_thresholds.get_threshold(threshold_type, use_default=True)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["type"], threshold_type.value)
        self.assertEqual(result["is_default"], True)
    
    def test_set_threshold_success_with_approval(self):
        """Test successful threshold setting with approval required."""
        threshold_type = ThresholdType.DAILY_LOSS
        new_value = 4.0
        environment = EnvironmentType.PRODUCTION
        requested_by = "test_user"
        
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Call method
        result = self.configurable_thresholds.set_threshold(
            self.mock_session,
            threshold_type,
            new_value,
            environment,
            requested_by,
            "Test reason"
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("request_id", result)
        self.assertTrue(result["requires_approval"])
        self.assertIn("Threshold change request submitted", result["message"])
        
        # Verify database operations
        self.mock_session.add.assert_called()
        self.mock_session.flush.assert_called()
    
    def test_set_threshold_success_auto_approved(self):
        """Test successful threshold setting with auto-approval."""
        threshold_type = ThresholdType.DAILY_LOSS
        new_value = 4.0
        environment = EnvironmentType.DEVELOPMENT
        requested_by = "test_user"
        
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Call method
        result = self.configurable_thresholds.set_threshold(
            self.mock_session,
            threshold_type,
            new_value,
            environment,
            requested_by,
            "Test reason",
            auto_approve=True
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("Threshold change approved successfully", result["message"])
        self.assertEqual(result["old_value"], 3.0)
        self.assertEqual(result["new_value"], 4.0)
        self.assertTrue(result["applied"])
        
        # Verify threshold updated
        self.assertEqual(self.configurable_thresholds.current_thresholds[threshold_type]["value"], 4.0)
    
    def test_set_threshold_disabled(self):
        """Test threshold setting when threshold management is disabled."""
        # Disable threshold management
        self.configurable_thresholds.enable_threshold_management = False
        
        threshold_type = ThresholdType.DAILY_LOSS
        new_value = 4.0
        requested_by = "test_user"
        
        # Call method
        result = self.configurable_thresholds.set_threshold(
            self.mock_session,
            threshold_type,
            new_value,
            requested_by=requested_by
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Threshold management is disabled", result["message"])
    
    def test_set_threshold_invalid_value(self):
        """Test threshold setting with invalid value."""
        threshold_type = ThresholdType.DAILY_LOSS
        new_value = 25.0  # Exceeds maximum of 20.0
        requested_by = "test_user"
        
        # Call method
        result = self.configurable_thresholds.set_threshold(
            self.mock_session,
            threshold_type,
            new_value,
            requested_by=requested_by
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("exceeds maximum allowed", result["message"])
    
    def test_approve_threshold_change_success(self):
        """Test successful threshold change approval."""
        # Setup threshold change request
        request_id = 1
        mock_request_event = Mock(spec=RiskEvent, id=request_id)
        mock_request_event.metadata_json = json.dumps({
            'threshold_type': 'daily_loss',
            'old_value': 3.0,
            'new_value': 4.0,
            'environment': 'production',
            'requested_by': 'test_user',
            'reason': 'Test reason',
            'requires_approval': True
        })
        
        # Mock session
        self.mock_session.query.return_value.get.return_value = mock_request_event
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Test data
        approver = "admin"
        
        # Call method
        result = self.configurable_thresholds.approve_threshold_change(
            self.mock_session,
            request_id,
            approver
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("Threshold change approved successfully", result["message"])
        self.assertEqual(result["old_value"], 3.0)
        self.assertEqual(result["new_value"], 4.0)
        self.assertTrue(result["applied"])
        
        # Verify threshold updated
        self.assertEqual(self.configurable_thresholds.current_thresholds[ThresholdType.DAILY_LOSS]["value"], 4.0)
    
    def test_approve_threshold_change_not_found(self):
        """Test threshold change approval when request not found."""
        # Mock session
        self.mock_session.query.return_value.get.return_value = None
        
        # Test data
        request_id = 999
        approver = "admin"
        
        # Call method
        result = self.configurable_thresholds.approve_threshold_change(
            self.mock_session,
            request_id,
            approver
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Threshold change request not found", result["message"])
    
    def test_reject_threshold_change_success(self):
        """Test successful threshold change rejection."""
        # Setup threshold change request
        request_id = 1
        mock_request_event = Mock(spec=RiskEvent, id=request_id)
        mock_request_event.metadata_json = json.dumps({
            'threshold_type': 'daily_loss',
            'old_value': 3.0,
            'new_value': 4.0,
            'environment': 'production',
            'requested_by': 'test_user',
            'reason': 'Test reason',
            'requires_approval': True
        })
        
        # Mock session
        self.mock_session.query.return_value.get.return_value = mock_request_event
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Test data
        rejecter = "admin"
        reason = "Insufficient risk management"
        
        # Call method
        result = self.configurable_thresholds.reject_threshold_change(
            self.mock_session,
            request_id,
            rejecter,
            reason
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("Threshold change rejected successfully", result["message"])
        self.assertEqual(result["old_value"], 3.0)
        self.assertEqual(result["new_value"], 4.0)
        self.assertFalse(result["applied"])
        
        # Verify threshold not updated
        self.assertEqual(self.configurable_thresholds.current_thresholds[ThresholdType.DAILY_LOSS]["value"], 3.0)
    
    def test_reject_threshold_change_not_found(self):
        """Test threshold change rejection when request not found."""
        # Mock session
        self.mock_session.query.return_value.get.return_value = None
        
        # Test data
        request_id = 999
        rejecter = "admin"
        reason = "Test reason"
        
        # Call method
        result = self.configurable_thresholds.reject_threshold_change(
            self.mock_session,
            request_id,
            rejecter,
            reason
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Threshold change request not found", result["message"])
    
    def test_get_all_thresholds_success(self):
        """Test successful retrieval of all thresholds."""
        # Call method
        result = self.configurable_thresholds.get_all_thresholds()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("data", result)
        self.assertIsInstance(result["data"], dict)
        self.assertGreater(result["total_thresholds"], 0)
        
        # Verify threshold types
        self.assertIn("daily_loss", result["data"])
        self.assertIn("max_drawdown", result["data"])
        self.assertIn("position_size", result["data"])
    
    def test_get_all_thresholds_environment_specific(self):
        """Test retrieval of all thresholds for specific environment."""
        environment = EnvironmentType.DEVELOPMENT
        
        # Call method
        result = self.configurable_thresholds.get_all_thresholds(environment)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["environment"], environment.value)
        
        # Verify development-specific values
        daily_loss_threshold = result["data"]["daily_loss"]
        self.assertEqual(daily_loss_threshold["value"], 10.0)  # Development override
    
    def test_get_threshold_history_success(self):
        """Test successful retrieval of threshold history."""
        # Add some history
        self.configurable_thresholds.threshold_history = [
            {
                'threshold_type': 'daily_loss',
                'old_value': 3.0,
                'new_value': 4.0,
                'environment': 'production',
                'requested_by': 'user1',
                'requested_at': datetime.utcnow().isoformat(),
                'reason': 'Test reason',
                'approved': True,
                'status': 'applied'
            },
            {
                'threshold_type': 'daily_loss',
                'old_value': 4.0,
                'new_value': 5.0,
                'environment': 'production',
                'requested_by': 'user2',
                'requested_at': datetime.utcnow().isoformat(),
                'reason': 'Another test',
                'approved': False,
                'status': 'applied'
            }
        ]
        
        # Call method
        result = self.configurable_thresholds.get_threshold_history(limit=10)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 2)
        self.assertEqual(result["total_records"], 2)
        self.assertEqual(result["returned_records"], 2)
    
    def test_get_threshold_history_filtered(self):
        """Test retrieval of filtered threshold history."""
        # Add some history
        self.configurable_thresholds.threshold_history = [
            {
                'threshold_type': 'daily_loss',
                'old_value': 3.0,
                'new_value': 4.0,
                'environment': 'production',
                'requested_by': 'user1',
                'requested_at': datetime.utcnow().isoformat(),
                'reason': 'Test reason',
                'approved': True,
                'status': 'applied'
            },
            {
                'threshold_type': 'max_drawdown',
                'old_value': 8.0,
                'new_value': 10.0,
                'environment': 'development',
                'requested_by': 'user2',
                'requested_at': datetime.utcnow().isoformat(),
                'reason': 'Development test',
                'approved': True,
                'status': 'applied'
            }
        ]
        
        # Filter by threshold type
        threshold_type = ThresholdType.DAILY_LOSS
        result = self.configurable_thresholds.get_threshold_history(threshold_type=threshold_type)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["data"][0]["threshold_type"], threshold_type.value)
        
        # Filter by environment
        environment = EnvironmentType.DEVELOPMENT
        result = self.configurable_thresholds.get_threshold_history(environment=environment)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 1)
        self.assertEqual(result["data"][0]["environment"], environment.value)
    
    def test_get_threshold_history_empty(self):
        """Test retrieval of threshold history when empty."""
        # Clear history
        self.configurable_thresholds.threshold_history = []
        
        # Call method
        result = self.configurable_thresholds.get_threshold_history()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 0)
        self.assertEqual(result["total_records"], 0)
    
    def test_reset_threshold_to_default_success(self):
        """Test successful threshold reset to default."""
        threshold_type = ThresholdType.DAILY_LOSS
        environment = EnvironmentType.PRODUCTION
        reset_by = "admin"
        
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Call method
        result = self.configurable_thresholds.reset_threshold_to_default(
            self.mock_session,
            threshold_type,
            environment,
            reset_by
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("Threshold change approved successfully", result["message"])
        self.assertEqual(result["old_value"], 3.0)  # Current value
        self.assertEqual(result["new_value"], 5.0)  # Default value
        self.assertTrue(result["applied"])
        
        # Verify threshold reset to default
        self.assertEqual(self.configurable_thresholds.current_thresholds[threshold_type]["value"], 5.0)
    
    def test_reset_threshold_to_default_not_found(self):
        """Test threshold reset when threshold type not found."""
        # Create an invalid threshold type
        class InvalidThresholdType:
            value = "invalid_threshold"
        
        threshold_type = InvalidThresholdType()
        
        # Call method
        result = self.configurable_thresholds.reset_threshold_to_default(
            self.mock_session,
            threshold_type
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Threshold not found", result["message"])
    
    def test_check_threshold_compliance_success(self):
        """Test successful threshold compliance check."""
        current_values = {
            ThresholdType.DAILY_LOSS: 6.0,  # Exceeds threshold of 5.0
            ThresholdType.MAX_DRAWDOWN: 5.0,  # Below threshold of 10.0
            ThresholdType.POSITION_SIZE: 3.0  # Exceeds threshold of 2.0
        }
        
        # Call method
        result = self.configurable_thresholds.check_threshold_compliance(current_values)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["compliant"])
        self.assertEqual(result["violation_count"], 2)
        self.assertEqual(result["thresholds_checked"], 3)
        
        # Verify violations
        violations = result["violations"]
        self.assertEqual(len(violations), 2)
        
        # Check daily_loss violation
        daily_loss_violation = next(v for v in violations if v["threshold_type"] == "daily_loss")
        self.assertEqual(daily_loss_violation["threshold_value"], 5.0)
        self.assertEqual(daily_loss_violation["current_value"], 6.0)
        self.assertEqual(daily_loss_violation["severity"], "medium")
        
        # Check position_size violation
        position_size_violation = next(v for v in violations if v["threshold_type"] == "position_size")
        self.assertEqual(position_size_violation["threshold_value"], 2.0)
        self.assertEqual(position_size_violation["current_value"], 3.0)
        self.assertEqual(position_size_violation["severity"], "high")
    
    def test_check_threshold_compliance_compliant(self):
        """Test threshold compliance check when compliant."""
        current_values = {
            ThresholdType.DAILY_LOSS: 3.0,  # Below threshold of 5.0
            ThresholdType.MAX_DRAWDOWN: 8.0,  # Below threshold of 10.0
            ThresholdType.POSITION_SIZE: 1.0  # Below threshold of 2.0
        }
        
        # Call method
        result = self.configurable_thresholds.check_threshold_compliance(current_values)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["compliant"])
        self.assertEqual(result["violation_count"], 0)
        self.assertEqual(len(result["violations"]), 0)
    
    def test_check_threshold_compliance_empty(self):
        """Test threshold compliance check with empty values."""
        current_values = {}
        
        # Call method
        result = self.configurable_thresholds.check_threshold_compliance(current_values)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["compliant"])
        self.assertEqual(result["violation_count"], 0)
        self.assertEqual(result["thresholds_checked"], 0)
    
    def test_update_configuration_success(self):
        """Test successful configuration update."""
        new_config = {
            'enable_threshold_management': False,
            'require_approval_for_changes': False,
            'auto_approve_dev_changes': False,
            'threshold_change_cooldown_hours': 48,
            'enable_threshold_notifications': False,
            'default_environment': 'staging',
            'loss_thresholds': {
                'daily_loss': 2.0,
                'max_drawdown': 6.0,
                'position_size': 1.0
            }
        }
        
        # Call method
        result = self.configurable_thresholds.update_configuration(new_config)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        
        # Verify configuration updated
        self.assertEqual(self.configurable_thresholds.enable_threshold_management, False)
        self.assertEqual(self.configurable_thresholds.require_approval_for_changes, False)
        self.assertEqual(self.configurable_thresholds.auto_approve_dev_changes, False)
        self.assertEqual(self.configurable_thresholds.threshold_change_cooldown_hours, 48)
        self.assertEqual(self.configurable_thresholds.enable_threshold_notifications, False)
        self.assertEqual(self.configurable_thresholds.default_environment, 'staging')
        
        # Verify thresholds updated
        self.assertEqual(self.configurable_thresholds.current_thresholds[ThresholdType.DAILY_LOSS]["value"], 2.0)
        self.assertEqual(self.configurable_thresholds.current_thresholds[ThresholdType.MAX_DRAWDOWN]["value"], 6.0)
        self.assertEqual(self.configurable_thresholds.current_thresholds[ThresholdType.POSITION_SIZE]["value"], 1.0)
    
    def test_update_configuration_invalid_threshold_type(self):
        """Test configuration update with invalid threshold type."""
        new_config = {
            'loss_thresholds': {
                'invalid_threshold': 10.0  # Invalid threshold type
            }
        }
        
        # Call method
        result = self.configurable_thresholds.update_configuration(new_config)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        
        # Verify invalid threshold is ignored
        self.assertNotIn('invalid_threshold', self.configurable_thresholds.current_thresholds)
    
    def test_validate_threshold_value_success(self):
        """Test successful threshold value validation."""
        threshold_type = ThresholdType.DAILY_LOSS
        value = 3.0  # Valid value between 0.1 and 20.0
        
        # Call method
        result = self.configurable_thresholds._validate_threshold_value(threshold_type, value)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("Threshold value is valid", result["message"])
    
    def test_validate_threshold_value_below_minimum(self):
        """Test threshold value validation below minimum."""
        threshold_type = ThresholdType.DAILY_LOSS
        value = 0.05  # Below minimum of 0.1
        
        # Call method
        result = self.configurable_thresholds._validate_threshold_value(threshold_type, value)
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("below minimum allowed", result["message"])
    
    def test_validate_threshold_value_above_maximum(self):
        """Test threshold value validation above maximum."""
        threshold_type = ThresholdType.DAILY_LOSS
        value = 25.0  # Above maximum of 20.0
        
        # Call method
        result = self.configurable_thresholds._validate_threshold_value(threshold_type, value)
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("exceeds maximum allowed", result["message"])
    
    def test_validate_threshold_value_invalid_type(self):
        """Test threshold value validation with invalid type."""
        # Create an invalid threshold type
        class InvalidThresholdType:
            value = "invalid_threshold"
        
        threshold_type = InvalidThresholdType()
        value = 5.0
        
        # Call method
        result = self.configurable_thresholds._validate_threshold_value(threshold_type, value)
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Unknown threshold type", result["message"])
    
    def test_get_environment_threshold_success(self):
        """Test successful environment-specific threshold retrieval."""
        threshold_type = ThresholdType.DAILY_LOSS
        environment = EnvironmentType.DEVELOPMENT
        
        result = self.configurable_thresholds._get_environment_threshold(threshold_type, environment)
        
        # Verify results
        self.assertIsNotNone(result)
        self.assertEqual(result["value"], 10.0)  # Development override
        self.assertEqual(result["environment"], environment.value)
        self.assertEqual(result["type"], threshold_type.value)
    
    def test_get_environment_threshold_not_found(self):
        """Test environment-specific threshold retrieval when not found."""
        threshold_type = ThresholdType.LIQUIDITY  # Not in environment overrides
        environment = EnvironmentType.DEVELOPMENT
        
        result = self.configurable_thresholds._get_environment_threshold(threshold_type, environment)
        
        # Verify results
        self.assertIsNone(result)
    
    def test_get_default_threshold_success(self):
        """Test successful default threshold retrieval."""
        threshold_type = ThresholdType.DAILY_LOSS
        
        result = self.configurable_thresholds._get_default_threshold(threshold_type)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["value"], 5.0)  # Default value
        self.assertEqual(result["type"], threshold_type.value)
        self.assertTrue(result["is_default"])
    
    def test_get_default_threshold_not_found(self):
        """Test default threshold retrieval when not found."""
        # Create an invalid threshold type
        class InvalidThresholdType:
            value = "invalid_threshold"
        
        threshold_type = InvalidThresholdType()
        
        result = self.configurable_thresholds._get_default_threshold(threshold_type)
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("No default threshold available", result["message"])


if __name__ == '__main__':
    unittest.main()