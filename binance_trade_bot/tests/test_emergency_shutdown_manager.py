"""
Unit tests for emergency shutdown manager functionality.
"""

import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger
from binance_trade_bot.models import RiskEvent, RiskEventType, RiskEventSeverity, RiskEventStatus, Pair, Coin
from binance_trade_bot.notifications import NotificationHandler
from binance_trade_bot.risk_management.emergency_shutdown_manager import (
    EmergencyShutdownManager,
    ShutdownReason,
    ShutdownState,
    ShutdownPriority
)


class TestEmergencyShutdownManager(unittest.TestCase):
    """Test cases for EmergencyShutdownManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock(spec=Database)
        self.mock_logger = Mock(spec=Logger)
        self.mock_notification_handler = Mock(spec=NotificationHandler)
        self.mock_session = Mock()
        
        # Test configuration
        self.test_config = {
            'enable_emergency_shutdown': True,
            'auto_shutdown_thresholds': {
                'daily_loss': 10.0,
                'max_drawdown': 15.0,
                'position_size': 5.0
            },
            'shutdown_cooldown_period': 300,  # 5 minutes
            'enable_state_preservation': True,
            'enable_auto_recovery': False,
            'recovery_conditions': {
                'portfolio_value_recovery': 5.0,
                'time_based_recovery': 3600  # 1 hour
            },
            'notification_settings': {
                'enable_shutdown_notifications': True,
                'enable_recovery_notifications': True,
                'notification_cooldown': 60
            }
        }
        
        # Create emergency shutdown manager instance
        self.emergency_shutdown_manager = EmergencyShutdownManager(
            self.mock_database,
            self.mock_logger,
            self.test_config,
            self.mock_notification_handler
        )
        
        # Create test objects
        self.test_pair = Pair(Coin("BTC", True), Coin("USDT", True))
        self.test_coin = Coin("BTC", True)
    
    def test_init(self):
        """Test EmergencyShutdownManager initialization."""
        self.assertIsInstance(self.emergency_shutdown_manager, EmergencyShutdownManager)
        self.assertEqual(self.emergency_shutdown_manager.enable_emergency_shutdown, True)
        self.assertEqual(self.emergency_shutdown_manager.shutdown_cooldown_period, 300)
        self.assertEqual(self.emergency_shutdown_manager.enable_state_preservation, True)
        self.assertEqual(self.emergency_shutdown_manager.enable_auto_recovery, False)
        self.assertEqual(self.emergency_shutdown_manager.current_shutdown_state, ShutdownState.ACTIVE)
    
    def test_init_shutdown_disabled(self):
        """Test EmergencyShutdownManager initialization when disabled."""
        # Disable emergency shutdown
        self.emergency_shutdown_manager.enable_emergency_shutdown = False
        
        # Verify state
        self.assertEqual(self.emergency_shutdown_manager.current_shutdown_state, ShutdownState.ACTIVE)
        self.assertTrue(self.emergency_shutdown_manager.is_trading_allowed())
    
    def test_trigger_shutdown_success(self):
        """Test successful emergency shutdown trigger."""
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Test data
        reason = ShutdownReason.PORTFOLIO_LOSS
        priority = ShutdownPriority.HIGH
        description = "Emergency shutdown due to portfolio loss"
        metadata = {"custom_field": "custom_value"}
        
        # Call method
        result = self.emergency_shutdown_manager.trigger_shutdown(
            self.mock_session,
            reason,
            priority,
            description,
            self.test_pair,
            self.test_coin,
            json.dumps(metadata)
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("shutdown_triggered", result)
        self.assertTrue(result["shutdown_triggered"])
        self.assertEqual(result["shutdown_reason"], reason.value)
        self.assertEqual(result["shutdown_priority"], priority.value)
        self.assertEqual(result["shutdown_id"], self.emergency_shutdown_manager.shutdown_id)
        
        # Verify state change
        self.assertEqual(self.emergency_shutdown_manager.current_shutdown_state, ShutdownState.SHUTDOWN)
        self.assertFalse(self.emergency_shutdown_manager.is_trading_allowed())
        
        # Verify database operations
        self.mock_session.add.assert_called()
        self.mock_session.flush.assert_called()
        
        # Verify risk event created
        self.assertIsNotNone(self.emergency_shutdown_manager.shutdown_event)
        self.assertEqual(self.emergency_shutdown_manager.shutdown_event.event_type, RiskEventType.PORTFOLIO_LIMIT)
        self.assertEqual(self.emergency_shutdown_manager.shutdown_event.severity, RiskEventSeverity.CRITICAL)
        self.assertEqual(self.emergency_shutdown_manager.shutdown_event.status, RiskEventStatus.OPEN)
    
    def test_trigger_shutdown_already_shutdown(self):
        """Test emergency shutdown trigger when already shutdown."""
        # Set to shutdown state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.SHUTDOWN
        self.emergency_shutdown_manager.shutdown_event = Mock(spec=RiskEvent)
        
        # Test data
        reason = ShutdownReason.PORTFOLIO_LOSS
        priority = ShutdownPriority.HIGH
        
        # Call method
        result = self.emergency_shutdown_manager.trigger_shutdown(
            self.mock_session,
            reason,
            priority
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("already_shutdown", result)
        self.assertTrue(result["already_shutdown"])
        self.assertEqual(result["shutdown_reason"], reason.value)
        
        # Verify no new shutdown triggered
        self.mock_session.add.assert_not_called()
    
    def test_trigger_shutdown_disabled(self):
        """Test emergency shutdown trigger when disabled."""
        # Disable emergency shutdown
        self.emergency_shutdown_manager.enable_emergency_shutdown = False
        
        # Test data
        reason = ShutdownReason.PORTFOLIO_LOSS
        priority = ShutdownPriority.HIGH
        
        # Call method
        result = self.emergency_shutdown_manager.trigger_shutdown(
            self.mock_session,
            reason,
            priority
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Emergency shutdown is disabled", result["message"])
        
        # Verify state unchanged
        self.assertEqual(self.emergency_shutdown_manager.current_shutdown_state, ShutdownState.ACTIVE)
        self.assertTrue(self.emergency_shutdown_manager.is_trading_allowed())
    
    def test_trigger_shutdown_cooldown_active(self):
        """Test emergency shutdown trigger when cooldown is active."""
        # Set shutdown time to within cooldown period
        self.emergency_shutdown_manager.shutdown_time = datetime.utcnow() - timedelta(minutes=2)  # 2 minutes ago
        self.emergency_shutdown_manager.shutdown_event = Mock(spec=RiskEvent)
        
        # Test data
        reason = ShutdownReason.PORTFOLIO_LOSS
        priority = ShutdownPriority.HIGH
        
        # Call method
        result = self.emergency_shutdown_manager.trigger_shutdown(
            self.mock_session,
            reason,
            priority
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("cooldown_active", result)
        self.assertTrue(result["cooldown_active"])
        self.assertIn("cooldown_period", result)
        
        # Verify no new shutdown triggered
        self.mock_session.add.assert_not_called()
    
    def test_trigger_shutdown_with_metadata(self):
        """Test emergency shutdown trigger with metadata."""
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Test data
        reason = ShutdownReason.PORTFOLIO_LOSS
        priority = ShutdownPriority.HIGH
        metadata = {
            "portfolio_value": 10000.0,
            "loss_percentage": 12.5,
            "triggering_trade": "BTCUSDT",
            "market_conditions": "volatile"
        }
        
        # Call method
        result = self.emergency_shutdown_manager.trigger_shutdown(
            self.mock_session,
            reason,
            priority,
            metadata=json.dumps(metadata)
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["shutdown_triggered"])
        
        # Verify metadata
        shutdown_event = self.emergency_shutdown_manager.shutdown_event
        parsed_metadata = json.loads(shutdown_event.metadata_json)
        self.assertEqual(parsed_metadata["portfolio_value"], 10000.0)
        self.assertEqual(parsed_metadata["loss_percentage"], 12.5)
        self.assertEqual(parsed_metadata["triggering_trade"], "BTCUSDT")
        self.assertEqual(parsed_metadata["market_conditions"], "volatile")
    
    def test_attempt_recovery_success(self):
        """Test successful emergency recovery attempt."""
        # Set to shutdown state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.SHUTDOWN
        self.emergency_shutdown_manager.shutdown_event = Mock(spec=RiskEvent)
        self.emergency_shutdown_manager.shutdown_time = datetime.utcnow() - timedelta(minutes=10)
        
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Test data
        recovery_reason = "Portfolio value recovered"
        recovery_metadata = {"recovery_percentage": 3.5}
        
        # Call method
        result = self.emergency_shutdown_manager.attempt_recovery(
            self.mock_session,
            recovery_reason,
            json.dumps(recovery_metadata)
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("recovery_attempted", result)
        self.assertTrue(result["recovery_attempted"])
        self.assertEqual(result["recovery_reason"], recovery_reason)
        
        # Verify state change
        self.assertEqual(self.emergency_shutdown_manager.current_shutdown_state, ShutdownState.RECOVERY)
        self.assertTrue(self.emergency_shutdown_manager.is_trading_allowed())
        
        # Verify database operations
        self.mock_session.add.assert_called()
        self.mock_session.flush.assert_called()
        
        # Verify recovery event created
        self.assertIsNotNone(self.emergency_shutdown_manager.recovery_event)
        self.assertEqual(self.emergency_shutdown_manager.recovery_event.event_type, RiskEventType.PORTFOLIO_LIMIT)
        self.assertEqual(self.emergency_shutdown_manager.recovery_event.severity, RiskEventSeverity.MEDIUM)
        self.assertEqual(self.emergency_shutdown_manager.recovery_event.status, RiskEventStatus.OPEN)
    
    def test_attempt_recovery_not_shutdown(self):
        """Test recovery attempt when not shutdown."""
        # Set to active state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.ACTIVE
        
        # Test data
        recovery_reason = "Portfolio value recovered"
        
        # Call method
        result = self.emergency_shutdown_manager.attempt_recovery(
            self.mock_session,
            recovery_reason
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("not_shutdown", result)
        self.assertTrue(result["not_shutdown"])
        self.assertEqual(result["current_state"], ShutdownState.ACTIVE.value)
        
        # Verify no recovery attempted
        self.mock_session.add.assert_not_called()
    
    def test_attempt_recovery_disabled(self):
        """Test recovery attempt when disabled."""
        # Set to shutdown state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.SHUTDOWN
        self.emergency_shutdown_manager.shutdown_event = Mock(spec=RiskEvent)
        
        # Disable emergency shutdown
        self.emergency_shutdown_manager.enable_emergency_shutdown = False
        
        # Test data
        recovery_reason = "Portfolio value recovered"
        
        # Call method
        result = self.emergency_shutdown_manager.attempt_recovery(
            self.mock_session,
            recovery_reason
        )
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Emergency shutdown is disabled", result["message"])
        
        # Verify state unchanged
        self.assertEqual(self.emergency_shutdown_manager.current_shutdown_state, ShutdownState.SHUTDOWN)
        self.assertFalse(self.emergency_shutdown_manager.is_trading_allowed())
    
    def test_attempt_recovery_cooldown_active(self):
        """Test recovery attempt when cooldown is active."""
        # Set to shutdown state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.SHUTDOWN
        self.emergency_shutdown_manager.shutdown_event = Mock(spec=RiskEvent)
        self.emergency_shutdown_manager.shutdown_time = datetime.utcnow() - timedelta(minutes=2)  # 2 minutes ago
        
        # Test data
        recovery_reason = "Portfolio value recovered"
        
        # Call method
        result = self.emergency_shutdown_manager.attempt_recovery(
            self.mock_session,
            recovery_reason
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("cooldown_active", result)
        self.assertTrue(result["cooldown_active"])
        self.assertIn("cooldown_period", result)
        
        # Verify no recovery attempted
        self.mock_session.add.assert_not_called()
    
    def test_complete_recovery_success(self):
        """Test successful recovery completion."""
        # Set to recovery state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.RECOVERY
        self.emergency_shutdown_manager.recovery_event = Mock(spec=RiskEvent)
        self.emergency_shutdown_manager.recovery_start_time = datetime.utcnow() - timedelta(minutes=5)
        
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Test data
        completed_by = "admin"
        completion_metadata = {"final_recovery_percentage": 5.2}
        
        # Call method
        result = self.emergency_shutdown_manager.complete_recovery(
            self.mock_session,
            completed_by,
            json.dumps(completion_metadata)
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("recovery_completed", result)
        self.assertTrue(result["recovery_completed"])
        self.assertEqual(result["completed_by"], completed_by)
        
        # Verify state change
        self.assertEqual(self.emergency_shutdown_manager.current_shutdown_state, ShutdownState.ACTIVE)
        self.assertTrue(self.emergency_shutdown_manager.is_trading_allowed())
        
        # Verify database operations
        self.mock_session.add.assert_called()
        self.mock_session.flush.assert_called()
        
        # Verify recovery event resolved
        self.emergency_shutdown_manager.recovery_event.resolve.assert_called_with(completed_by)
        
        # Verify metadata updated
        parsed_metadata = json.loads(self.emergency_shutdown_manager.recovery_event.metadata_json)
        self.assertEqual(parsed_metadata["final_recovery_percentage"], 5.2)
    
    def test_complete_recovery_not_in_recovery(self):
        """Test recovery completion when not in recovery state."""
        # Set to active state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.ACTIVE
        
        # Test data
        completed_by = "admin"
        
        # Call method
        result = self.emergency_shutdown_manager.complete_recovery(
            self.mock_session,
            completed_by
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("not_in_recovery", result)
        self.assertTrue(result["not_in_recovery"])
        self.assertEqual(result["current_state"], ShutdownState.ACTIVE.value)
        
        # Verify no recovery completed
        self.mock_session.add.assert_not_called()
    
    def test_cancel_recovery_success(self):
        """Test successful recovery cancellation."""
        # Set to recovery state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.RECOVERY
        self.emergency_shutdown_manager.recovery_event = Mock(spec=RiskEvent)
        
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Test data
        cancelled_by = "admin"
        cancellation_reason = "Insufficient recovery"
        
        # Call method
        result = self.emergency_shutdown_manager.cancel_recovery(
            self.mock_session,
            cancelled_by,
            cancellation_reason
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("recovery_cancelled", result)
        self.assertTrue(result["recovery_cancelled"])
        self.assertEqual(result["cancelled_by"], cancelled_by)
        
        # Verify state change
        self.assertEqual(self.emergency_shutdown_manager.current_shutdown_state, ShutdownState.SHUTDOWN)
        self.assertFalse(self.emergency_shutdown_manager.is_trading_allowed())
        
        # Verify database operations
        self.mock_session.add.assert_called()
        self.mock_session.flush.assert_called()
        
        # Verify recovery event ignored
        self.emergency_shutdown_manager.recovery_event.ignore.assert_called_with(cancelled_by)
    
    def test_cancel_recovery_not_in_recovery(self):
        """Test recovery cancellation when not in recovery state."""
        # Set to active state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.ACTIVE
        
        # Test data
        cancelled_by = "admin"
        cancellation_reason = "Test reason"
        
        # Call method
        result = self.emergency_shutdown_manager.cancel_recovery(
            self.mock_session,
            cancelled_by,
            cancellation_reason
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("not_in_recovery", result)
        self.assertTrue(result["not_in_recovery"])
        self.assertEqual(result["current_state"], ShutdownState.ACTIVE.value)
        
        # Verify no recovery cancelled
        self.mock_session.add.assert_not_called()
    
    def test_is_trading_allowed_active(self):
        """Test trading permission check when active."""
        # Set to active state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.ACTIVE
        
        result = self.emergency_shutdown_manager.is_trading_allowed()
        
        self.assertTrue(result)
    
    def test_is_trading_allowed_shutdown(self):
        """Test trading permission check when shutdown."""
        # Set to shutdown state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.SHUTDOWN
        
        result = self.emergency_shutdown_manager.is_trading_allowed()
        
        self.assertFalse(result)
    
    def test_is_trading_allowed_recovery(self):
        """Test trading permission check when in recovery."""
        # Set to recovery state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.RECOVERY
        
        result = self.emergency_shutdown_manager.is_trading_allowed()
        
        self.assertTrue(result)
    
    def test_get_shutdown_status_success(self):
        """Test successful shutdown status retrieval."""
        # Set shutdown state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.SHUTDOWN
        self.emergency_shutdown_manager.shutdown_time = datetime.utcnow() - timedelta(minutes=30)
        self.emergency_shutdown_manager.shutdown_event = Mock(spec=RiskEvent, id=1)
        self.emergency_shutdown_manager.shutdown_reason = ShutdownReason.PORTFOLIO_LOSS
        self.emergency_shutdown_manager.shutdown_priority = ShutdownPriority.HIGH
        
        # Call method
        result = self.emergency_shutdown_manager.get_shutdown_status()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["current_state"], ShutdownState.SHUTDOWN.value)
        self.assertEqual(result["shutdown_id"], self.emergency_shutdown_manager.shutdown_id)
        self.assertEqual(result["shutdown_reason"], ShutdownReason.PORTFOLIO_LOSS.value)
        self.assertEqual(result["shutdown_priority"], ShutdownPriority.HIGH.value)
        self.assertIsNotNone(result["shutdown_time"])
        self.assertEqual(result["shutdown_event_id"], 1)
        self.assertFalse(result["is_trading_allowed"])
        self.assertTrue(result["is_shutdown"])
        self.assertFalse(result["is_in_recovery"])
    
    def test_get_shutdown_status_active(self):
        """Test shutdown status retrieval when active."""
        # Set to active state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.ACTIVE
        
        # Call method
        result = self.emergency_shutdown_manager.get_shutdown_status()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["current_state"], ShutdownState.ACTIVE.value)
        self.assertIsNone(result["shutdown_id"])
        self.assertIsNone(result["shutdown_reason"])
        self.assertIsNone(result["shutdown_priority"])
        self.assertIsNone(result["shutdown_time"])
        self.assertIsNone(result["shutdown_event_id"])
        self.assertTrue(result["is_trading_allowed"])
        self.assertFalse(result["is_shutdown"])
        self.assertFalse(result["is_in_recovery"])
    
    def test_get_shutdown_status_recovery(self):
        """Test shutdown status retrieval when in recovery."""
        # Set to recovery state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.RECOVERY
        self.emergency_shutdown_manager.recovery_start_time = datetime.utcnow() - timedelta(minutes=15)
        self.emergency_shutdown_manager.recovery_event = Mock(spec=RiskEvent, id=2)
        
        # Call method
        result = self.emergency_shutdown_manager.get_shutdown_status()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["current_state"], ShutdownState.RECOVERY.value)
        self.assertIsNotNone(result["shutdown_id"])
        self.assertIsNotNone(result["recovery_start_time"])
        self.assertEqual(result["recovery_event_id"], 2)
        self.assertTrue(result["is_trading_allowed"])
        self.assertFalse(result["is_shutdown"])
        self.assertTrue(result["is_in_recovery"])
    
    def test_check_auto_shutdown_conditions_true(self):
        """Test auto shutdown condition check when conditions are met."""
        # Mock current values
        current_values = {
            'daily_loss': 12.0,  # Exceeds threshold of 10.0
            'max_drawdown': 8.0,  # Below threshold of 15.0
            'position_size': 6.0  # Exceeds threshold of 5.0
        }
        
        # Call method
        result = self.emergency_shutdown_manager.check_auto_shutdown_conditions(current_values)
        
        # Verify results
        self.assertTrue(result["should_shutdown"])
        self.assertEqual(len(result["triggered_conditions"]), 2)
        self.assertIn("daily_loss", result["triggered_conditions"])
        self.assertIn("position_size", result["triggered_conditions"])
        self.assertEqual(result["triggered_conditions"]["daily_loss"], 12.0)
        self.assertEqual(result["triggered_conditions"]["position_size"], 6.0)
    
    def test_check_auto_shutdown_conditions_false(self):
        """Test auto shutdown condition check when conditions are not met."""
        # Mock current values
        current_values = {
            'daily_loss': 8.0,   # Below threshold of 10.0
            'max_drawdown': 12.0, # Below threshold of 15.0
            'position_size': 3.0  # Below threshold of 5.0
        }
        
        # Call method
        result = self.emergency_shutdown_manager.check_auto_shutdown_conditions(current_values)
        
        # Verify results
        self.assertFalse(result["should_shutdown"])
        self.assertEqual(len(result["triggered_conditions"]), 0)
    
    def test_check_auto_shutdown_conditions_disabled(self):
        """Test auto shutdown condition check when disabled."""
        # Disable auto shutdown
        self.emergency_shutdown_manager.enable_emergency_shutdown = False
        
        # Mock current values
        current_values = {
            'daily_loss': 12.0,  # Exceeds threshold of 10.0
            'max_drawdown': 8.0,  # Below threshold of 15.0
            'position_size': 6.0  # Exceeds threshold of 5.0
        }
        
        # Call method
        result = self.emergency_shutdown_manager.check_auto_shutdown_conditions(current_values)
        
        # Verify results
        self.assertFalse(result["should_shutdown"])
        self.assertEqual(len(result["triggered_conditions"]), 0)
    
    def test_check_auto_recovery_conditions_true(self):
        """Test auto recovery condition check when conditions are met."""
        # Set to shutdown state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.SHUTDOWN
        self.emergency_shutdown_manager.shutdown_time = datetime.utcnow() - timedelta(minutes=3600)  # 1 hour ago
        
        # Mock current values
        current_values = {
            'portfolio_value': 10500.0,  # Exceeds recovery threshold
            'time_since_shutdown': 3700  # Exceeds time threshold
        }
        
        # Enable auto recovery
        self.emergency_shutdown_manager.enable_auto_recovery = True
        
        # Call method
        result = self.emergency_shutdown_manager.check_auto_recovery_conditions(current_values)
        
        # Verify results
        self.assertTrue(result["should_attempt_recovery"])
        self.assertEqual(len(result["met_conditions"]), 2)
        self.assertIn("portfolio_value_recovery", result["met_conditions"])
        self.assertIn("time_based_recovery", result["met_conditions"])
        self.assertEqual(result["met_conditions"]["portfolio_value_recovery"], 10500.0)
        self.assertEqual(result["met_conditions"]["time_based_recovery"], 3700)
    
    def test_check_auto_recovery_conditions_false(self):
        """Test auto recovery condition check when conditions are not met."""
        # Set to shutdown state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.SHUTDOWN
        self.emergency_shutdown_manager.shutdown_time = datetime.utcnow() - timedelta(minutes=1800)  # 30 minutes ago
        
        # Mock current values
        current_values = {
            'portfolio_value': 9500.0,   # Below recovery threshold
            'time_since_shutdown': 1800  # Below time threshold
        }
        
        # Enable auto recovery
        self.emergency_shutdown_manager.enable_auto_recovery = True
        
        # Call method
        result = self.emergency_shutdown_manager.check_auto_recovery_conditions(current_values)
        
        # Verify results
        self.assertFalse(result["should_attempt_recovery"])
        self.assertEqual(len(result["met_conditions"]), 0)
    
    def test_check_auto_recovery_conditions_not_shutdown(self):
        """Test auto recovery condition check when not shutdown."""
        # Set to active state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.ACTIVE
        
        # Mock current values
        current_values = {
            'portfolio_value': 10500.0,
            'time_since_shutdown': 3700
        }
        
        # Enable auto recovery
        self.emergency_shutdown_manager.enable_auto_recovery = True
        
        # Call method
        result = self.emergency_shutdown_manager.check_auto_recovery_conditions(current_values)
        
        # Verify results
        self.assertFalse(result["should_attempt_recovery"])
        self.assertEqual(len(result["met_conditions"]), 0)
        self.assertIn("not_shutdown", result)
        self.assertTrue(result["not_shutdown"])
    
    def test_check_auto_recovery_conditions_disabled(self):
        """Test auto recovery condition check when disabled."""
        # Set to shutdown state
        self.emergency_shutdown_manager.current_shutdown_state = ShutdownState.SHUTDOWN
        self.emergency_shutdown_manager.shutdown_time = datetime.utcnow() - timedelta(minutes=3600)
        
        # Mock current values
        current_values = {
            'portfolio_value': 10500.0,
            'time_since_shutdown': 3700
        }
        
        # Disable auto recovery
        self.emergency_shutdown_manager.enable_auto_recovery = False
        
        # Call method
        result = self.emergency_shutdown_manager.check_auto_recovery_conditions(current_values)
        
        # Verify results
        self.assertFalse(result["should_attempt_recovery"])
        self.assertEqual(len(result["met_conditions"]), 0)
        self.assertIn("auto_recovery_disabled", result)
        self.assertTrue(result["auto_recovery_disabled"])
    
    def test_update_configuration_success(self):
        """Test successful configuration update."""
        new_config = {
            'enable_emergency_shutdown': False,
            'shutdown_cooldown_period': 600,
            'enable_state_preservation': False,
            'enable_auto_recovery': True,
            'recovery_conditions': {
                'portfolio_value_recovery': 3.0,
                'time_based_recovery': 1800
            },
            'notification_settings': {
                'enable_shutdown_notifications': False,
                'enable_recovery_notifications': False,
                'notification_cooldown': 120
            }
        }
        
        # Call method
        result = self.emergency_shutdown_manager.update_configuration(new_config)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        
        # Verify configuration updated
        self.assertEqual(self.emergency_shutdown_manager.enable_emergency_shutdown, False)
        self.assertEqual(self.emergency_shutdown_manager.shutdown_cooldown_period, 600)
        self.assertEqual(self.emergency_shutdown_manager.enable_state_preservation, False)
        self.assertEqual(self.emergency_shutdown_manager.enable_auto_recovery, True)
        self.assertEqual(self.emergency_shutdown_manager.recovery_conditions['portfolio_value_recovery'], 3.0)
        self.assertEqual(self.emergency_shutdown_manager.recovery_conditions['time_based_recovery'], 1800)
        self.assertFalse(self.emergency_shutdown_manager.notification_settings['enable_shutdown_notifications'])
        self.assertFalse(self.emergency_shutdown_manager.notification_settings['enable_recovery_notifications'])
        self.assertEqual(self.emergency_shutdown_manager.notification_settings['notification_cooldown'], 120)
    
    def test_update_configuration_invalid_recovery_conditions(self):
        """Test configuration update with invalid recovery conditions."""
        new_config = {
            'recovery_conditions': {
                'invalid_condition': 10.0  # Invalid recovery condition
            }
        }
        
        # Call method
        result = self.emergency_shutdown_manager.update_configuration(new_config)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        
        # Verify invalid condition is ignored
        self.assertNotIn('invalid_condition', self.emergency_shutdown_manager.recovery_conditions)
    
    def test_get_shutdown_history_success(self):
        """Test successful shutdown history retrieval."""
        # Add shutdown history
        self.emergency_shutdown_manager.shutdown_history = [
            {
                'shutdown_id': 'shutdown_1',
                'shutdown_reason': 'portfolio_loss',
                'shutdown_priority': 'high',
                'shutdown_time': datetime.utcnow().isoformat(),
                'recovery_time': datetime.utcnow().isoformat(),
                'duration_minutes': 45,
                'completed_by': 'admin',
                'status': 'completed'
            },
            {
                'shutdown_id': 'shutdown_2',
                'shutdown_reason': 'system_error',
                'shutdown_priority': 'critical',
                'shutdown_time': datetime.utcnow().isoformat(),
                'recovery_time': None,
                'duration_minutes': None,
                'completed_by': None,
                'status': 'active'
            }
        ]
        
        # Call method
        result = self.emergency_shutdown_manager.get_shutdown_history(limit=10)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 2)
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(result["returned_records"], 2)
    
    def test_get_shutdown_history_empty(self):
        """Test shutdown history retrieval when empty."""
        # Clear shutdown history
        self.emergency_shutdown_manager.shutdown_history = []
        
        # Call method
        result = self.emergency_shutdown_manager.get_shutdown_history()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 0)
        self.assertEqual(result["total_count"], 0)
    
    def test_is_shutdown_cooldown_active_true(self):
        """Test shutdown cooldown check when active."""
        # Set shutdown time to within cooldown period
        self.emergency_shutdown_manager.shutdown_time = datetime.utcnow() - timedelta(minutes=2)  # 2 minutes ago
        cooldown_period = 300  # 5 minutes
        
        result = self.emergency_shutdown_manager._is_shutdown_cooldown_active(cooldown_period)
        
        self.assertTrue(result)
    
    def test_is_shutdown_cooldown_active_false(self):
        """Test shutdown cooldown check when not active."""
        # Set shutdown time to outside cooldown period
        self.emergency_shutdown_manager.shutdown_time = datetime.utcnow() - timedelta(minutes=10)  # 10 minutes ago
        cooldown_period = 300  # 5 minutes
        
        result = self.emergency_shutdown_manager._is_shutdown_cooldown_active(cooldown_period)
        
        self.assertFalse(result)
    
    def test_is_shutdown_cooldown_active_no_shutdown(self):
        """Test shutdown cooldown check when no shutdown has occurred."""
        # No shutdown time set
        self.emergency_shutdown_manager.shutdown_time = None
        cooldown_period = 300  # 5 minutes
        
        result = self.emergency_shutdown_manager._is_shutdown_cooldown_active(cooldown_period)
        
        self.assertFalse(result)
    
    def test_preserve_trading_state_success(self):
        """Test successful trading state preservation."""
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Mock current trading state
        current_state = {
            'open_positions': [
                {'symbol': 'BTCUSDT', 'size': 0.1, 'entry_price': 50000.0}
            ],
            'pending_orders': [
                {'symbol': 'ETHUSDT', 'side': 'buy', 'quantity': 1.0}
            ],
            'portfolio_value': 10000.0
        }
        
        # Call method
        result = self.emergency_shutdown_manager._preserve_trading_state(
            self.mock_session,
            current_state
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("state_preserved", result)
        self.assertTrue(result["state_preserved"])
        self.assertIsNotNone(result["state_id"])
        
        # Verify database operations
        self.mock_session.add.assert_called()
        self.mock_session.flush.assert_called()
        
        # Verify state stored
        self.assertIsNotNone(self.emergency_shutdown_manager.preserved_state)
        self.assertEqual(self.emergency_shutdown_manager.preserved_state['open_positions'][0]['symbol'], 'BTCUSDT')
    
    def test_restore_trading_state_success(self):
        """Test successful trading state restoration."""
        # Mock preserved state
        self.emergency_shutdown_manager.preserved_state = {
            'open_positions': [
                {'symbol': 'BTCUSDT', 'size': 0.1, 'entry_price': 50000.0}
            ],
            'pending_orders': [
                {'symbol': 'ETHUSDT', 'side': 'buy', 'quantity': 1.0}
            ],
            'portfolio_value': 10000.0
        }
        
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Call method
        result = self.emergency_shutdown_manager._restore_trading_state(self.mock_session)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("state_restored", result)
        self.assertTrue(result["state_restored"])
        self.assertIsNotNone(result["state_id"])
        
        # Verify database operations
        self.mock_session.add.assert_called()
        self.mock_session.flush.assert_called()
        
        # Verify state cleared
        self.assertIsNone(self.emergency_shutdown_manager.preserved_state)
    
    def test_restore_trading_state_no_state(self):
        """Test trading state restoration when no state preserved."""
        # Clear preserved state
        self.emergency_shutdown_manager.preserved_state = None
        
        # Call method
        result = self.emergency_shutdown_manager._restore_trading_state(self.mock_session)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("no_state_to_restore", result)
        self.assertTrue(result["no_state_to_restore"])
        
        # Verify no database operations
        self.mock_session.add.assert_not_called()
    
    def test_send_shutdown_notification_success(self):
        """Test successful shutdown notification."""
        # Mock notification handler
        self.mock_notification_handler.send_notification = Mock()
        
        # Test data
        message = "Emergency shutdown triggered"
        metadata = {"reason": "portfolio_loss", "priority": "high"}
        
        # Call method
        result = self.emergency_shutdown_manager._send_shutdown_notification(
            message,
            json.dumps(metadata)
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("notification_sent", result)
        self.assertTrue(result["notification_sent"])
        
        # Verify notification sent
        self.mock_notification_handler.send_notification.assert_called_once_with(
            message,
            []
        )
    
    def test_send_shutdown_notification_disabled(self):
        """Test shutdown notification when disabled."""
        # Disable shutdown notifications
        self.emergency_shutdown_manager.notification_settings['enable_shutdown_notifications'] = False
        
        # Mock notification handler
        self.mock_notification_handler.send_notification = Mock()
        
        # Test data
        message = "Emergency shutdown triggered"
        
        # Call method
        result = self.emergency_shutdown_manager._send_shutdown_notification(message)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("notifications_disabled", result)
        self.assertTrue(result["notifications_disabled"])
        
        # Verify no notification sent
        self.mock_notification_handler.send_notification.assert_not_called()
    
    def test_send_recovery_notification_success(self):
        """Test successful recovery notification."""
        # Mock notification handler
        self.mock_notification_handler.send_notification = Mock()
        
        # Test data
        message = "Recovery attempt initiated"
        metadata = {"recovery_percentage": 3.5}
        
        # Call method
        result = self.emergency_shutdown_manager._send_recovery_notification(
            message,
            json.dumps(metadata)
        )
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("notification_sent", result)
        self.assertTrue(result["notification_sent"])
        
        # Verify notification sent
        self.mock_notification_handler.send_notification.assert_called_once_with(
            message,
            []
        )
    
    def test_send_recovery_notification_disabled(self):
        """Test recovery notification when disabled."""
        # Disable recovery notifications
        self.emergency_shutdown_manager.notification_settings['enable_recovery_notifications'] = False
        
        # Mock notification handler
        self.mock_notification_handler.send_notification = Mock()
        
        # Test data
        message = "Recovery attempt initiated"
        
        # Call method
        result = self.emergency_shutdown_manager._send_recovery_notification(message)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertIn("notifications_disabled", result)
        self.assertTrue(result["notifications_disabled"])
        
        # Verify no notification sent
        self.mock_notification_handler.send_notification.assert_not_called()


if __name__ == '__main__':
    unittest.main()