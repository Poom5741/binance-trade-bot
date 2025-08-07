"""
Unit tests for risk event logger functionality.
"""

import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger
from binance_trade_bot.models import RiskEvent, RiskEventType, RiskEventSeverity, RiskEventStatus, Pair, Coin
from binance_trade_bot.notifications import NotificationHandler
from binance_trade_bot.risk_management.risk_event_logger import RiskEventLogger, RiskEventCategory


class TestRiskEventLogger(unittest.TestCase):
    """Test cases for RiskEventLogger class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_database = Mock(spec=Database)
        self.mock_logger = Mock(spec=Logger)
        self.mock_notification_handler = Mock(spec=NotificationHandler)
        self.mock_session = Mock()
        
        # Test configuration
        self.test_config = {
            'enable_risk_logging': True,
            'enable_risk_notifications': True,
            'auto_resolve_low_severity': True,
            'notification_cooldown_period': 300,
            'severity_notification_thresholds': {
                'LOW': False,
                'MEDIUM': True,
                'HIGH': True,
                'CRITICAL': True
            }
        }
        
        # Create risk event logger instance
        self.risk_event_logger = RiskEventLogger(
            self.mock_database,
            self.mock_logger,
            self.test_config,
            self.mock_notification_handler
        )
        
        # Create test objects
        self.test_pair = Pair(Coin("BTC", True), Coin("USDT", True))
        self.test_coin = Coin("BTC", True)
    
    def test_init(self):
        """Test RiskEventLogger initialization."""
        self.assertIsInstance(self.risk_event_logger, RiskEventLogger)
        self.assertEqual(self.risk_event_logger.enable_risk_logging, True)
        self.assertEqual(self.risk_event_logger.enable_notifications, True)
        self.assertEqual(self.risk_event_logger.auto_resolve_low_severity, True)
    
    def test_log_risk_event_success(self):
        """Test successful risk event logging."""
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Test data
        event_type = RiskEventType.PORTFOLIO_LIMIT
        severity = RiskEventSeverity.HIGH
        trigger_value = 10.0
        threshold_value = 5.0
        current_value = 10.0
        description = "Test risk event"
        
        # Call method
        result = self.risk_event_logger.log_risk_event(
            self.mock_session,
            self.test_pair,
            self.test_coin,
            event_type,
            severity,
            trigger_value,
            threshold_value,
            current_value,
            description,
            RiskEventCategory.PORTFOLIO_RISK,
            "test_user"
        )
        
        # Verify results
        self.assertIsNotNone(result)
        self.assertIsInstance(result, RiskEvent)
        self.assertEqual(result.event_type, event_type)
        self.assertEqual(result.severity, severity)
        self.assertEqual(result.trigger_value, trigger_value)
        self.assertEqual(result.threshold_value, threshold_value)
        self.assertEqual(result.current_value, current_value)
        self.assertEqual(result.description, description)
        self.assertEqual(result.created_by, "test_user")
        
        # Verify database operations
        self.mock_session.add.assert_called_once()
        self.mock_session.flush.assert_called_once()
    
    def test_log_risk_event_disabled(self):
        """Test risk event logging when disabled."""
        # Disable risk logging
        self.risk_event_logger.enable_risk_logging = False
        
        # Mock session
        self.mock_session.add = Mock()
        
        # Test data
        event_type = RiskEventType.PORTFOLIO_LIMIT
        severity = RiskEventSeverity.HIGH
        trigger_value = 10.0
        threshold_value = 5.0
        current_value = 10.0
        description = "Test risk event"
        
        # Call method
        result = self.risk_event_logger.log_risk_event(
            self.mock_session,
            self.test_pair,
            self.test_coin,
            event_type,
            severity,
            trigger_value,
            threshold_value,
            current_value,
            description,
            RiskEventCategory.PORTFOLIO_RISK,
            "test_user"
        )
        
        # Verify results
        self.assertIsNone(result)
        
        # Verify no database operations
        self.mock_session.add.assert_not_called()
    
    def test_log_risk_event_with_metadata(self):
        """Test risk event logging with metadata."""
        # Mock session
        self.mock_session.add = Mock()
        self.mock_session.flush = Mock()
        
        # Test data
        event_type = RiskEventType.PORTFOLIO_LIMIT
        severity = RiskEventSeverity.HIGH
        trigger_value = 10.0
        threshold_value = 5.0
        current_value = 10.0
        description = "Test risk event"
        metadata = {"custom_field": "custom_value"}
        
        # Call method
        result = self.risk_event_logger.log_risk_event(
            self.mock_session,
            self.test_pair,
            self.test_coin,
            event_type,
            severity,
            trigger_value,
            threshold_value,
            current_value,
            description,
            RiskEventCategory.PORTFOLIO_RISK,
            "test_user",
            json.dumps(metadata)
        )
        
        # Verify results
        self.assertIsNotNone(result)
        self.assertIsInstance(result, RiskEvent)
        
        # Verify metadata
        parsed_metadata = json.loads(result.metadata_json)
        self.assertEqual(parsed_metadata['category'], 'portfolio_risk')
        self.assertEqual(parsed_metadata['custom_field'], 'custom_value')
    
    def test_should_notify_true(self):
        """Test should_notify method when notification should be sent."""
        event_type = RiskEventType.PORTFOLIO_LIMIT
        severity = RiskEventSeverity.HIGH
        
        result = self.risk_event_logger.should_notify(event_type, severity)
        
        self.assertTrue(result)
    
    def test_should_notify_false_low_severity(self):
        """Test should_notify method when notification should not be sent for low severity."""
        event_type = RiskEventType.PORTFOLIO_LIMIT
        severity = RiskEventSeverity.LOW
        
        result = self.risk_event_logger.should_notify(event_type, severity)
        
        self.assertFalse(result)
    
    def test_should_notify_false_disabled(self):
        """Test should_notify method when notifications are disabled."""
        self.risk_event_logger.enable_notifications = False
        
        event_type = RiskEventType.PORTFOLIO_LIMIT
        severity = RiskEventSeverity.HIGH
        
        result = self.risk_event_logger.should_notify(event_type, severity)
        
        self.assertFalse(result)
    
    def test_get_risk_events_success(self):
        """Test successful retrieval of risk events."""
        # Mock query results
        mock_events = [
            Mock(spec=RiskEvent, id=1, info=lambda: {"id": 1}),
            Mock(spec=RiskEvent, id=2, info=lambda: {"id": 2})
        ]
        
        self.mock_session.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = mock_events
        self.mock_session.query.return_value.filter.return_value.order_by.return_value.count.return_value = 2
        
        # Call method
        result = self.risk_event_logger.get_risk_events(self.mock_session, limit=10, offset=0)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 2)
        self.assertEqual(result["total_count"], 2)
    
    def test_get_risk_events_error(self):
        """Test error handling in risk event retrieval."""
        # Mock query to raise exception
        self.mock_session.query.side_effect = Exception("Database error")
        
        # Call method
        result = self.risk_event_logger.get_risk_events(self.mock_session)
        
        # Verify results
        self.assertEqual(result["status"], "error")
        self.assertIn("Database error", result["message"])
    
    def test_get_risk_event_statistics_success(self):
        """Test successful retrieval of risk event statistics."""
        # Mock query results
        mock_events = [
            Mock(spec=RiskEvent, 
                 event_type=RiskEventType.PORTFOLIO_LIMIT,
                 severity=RiskEventSeverity.HIGH,
                 status=RiskEventStatus.OPEN,
                 created_at=datetime.now(),
                 acknowledged_at=None),
            Mock(spec=RiskEvent, 
                 event_type=RiskEventType.PORTFOLIO_LIMIT,
                 severity=RiskEventSeverity.MEDIUM,
                 status=RiskEventStatus.RESOLVED,
                 created_at=datetime.now(),
                 acknowledged_at=datetime.now())
        ]
        
        self.mock_session.query.return_value.filter.return_value.all.return_value = mock_events
        
        # Call method
        result = self.risk_event_logger.get_risk_event_statistics(self.mock_session, days=7)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["total_events"], 2)
        self.assertEqual(result["data"]["by_type"]["PORTFOLIO_LIMIT"], 2)
        self.assertEqual(result["data"]["by_severity"]["HIGH"], 1)
        self.assertEqual(result["data"]["by_severity"]["MEDIUM"], 1)
        self.assertEqual(result["data"]["by_status"]["OPEN"], 1)
        self.assertEqual(result["data"]["by_status"]["RESOLVED"], 1)
        self.assertEqual(result["data"]["resolution_rate"], 50.0)
        self.assertEqual(result["data"]["acknowledgment_rate"], 50.0)
    
    def test_get_risk_event_statistics_no_events(self):
        """Test retrieval of risk event statistics with no events."""
        # Mock empty query results
        self.mock_session.query.return_value.filter.return_value.all.return_value = []
        
        # Call method
        result = self.risk_event_logger.get_risk_event_statistics(self.mock_session, days=7)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["data"]["total_events"], 0)
        self.assertEqual(result["data"]["resolution_rate"], 0)
        self.assertEqual(result["data"]["acknowledgment_rate"], 0)
    
    def test_update_configuration_success(self):
        """Test successful configuration update."""
        new_config = {
            'enable_risk_logging': False,
            'enable_risk_notifications': False,
            'auto_resolve_low_severity': False,
            'severity_notification_thresholds': {
                'LOW': True,
                'MEDIUM': False,
                'HIGH': True,
                'CRITICAL': True
            }
        }
        
        # Call method
        result = self.risk_event_logger.update_configuration(new_config)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        
        # Verify configuration updated
        self.assertEqual(self.risk_event_logger.enable_risk_logging, False)
        self.assertEqual(self.risk_event_logger.enable_notifications, False)
        self.assertEqual(self.risk_event_logger.auto_resolve_low_severity, False)
        self.assertFalse(self.risk_event_logger.severity_notification_thresholds[RiskEventSeverity.LOW])
        self.assertFalse(self.risk_event_logger.severity_notification_thresholds[RiskEventSeverity.MEDIUM])
    
    def test_update_configuration_invalid_severity(self):
        """Test configuration update with invalid severity value."""
        new_config = {
            'severity_notification_thresholds': {
                'INVALID': True  # Invalid severity value
            }
        }
        
        # Call method
        result = self.risk_event_logger.update_configuration(new_config)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        
        # Verify invalid severity is ignored
        self.assertNotIn('INVALID', self.risk_event_logger.severity_notification_thresholds)
    
    def test_get_notification_history_success(self):
        """Test successful retrieval of notification history."""
        # Mock notification history
        self.risk_event_logger.notification_history = [
            {"id": 1, "message": "Test notification 1"},
            {"id": 2, "message": "Test notification 2"}
        ]
        
        # Call method
        result = self.risk_event_logger.get_notification_history(limit=10)
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 2)
        self.assertEqual(result["total_count"], 2)
    
    def test_get_notification_history_empty(self):
        """Test retrieval of notification history when empty."""
        # Clear notification history
        self.risk_event_logger.notification_history = []
        
        # Call method
        result = self.risk_event_logger.get_notification_history()
        
        # Verify results
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["data"]), 0)
        self.assertEqual(result["total_count"], 0)


if __name__ == '__main__':
    unittest.main()