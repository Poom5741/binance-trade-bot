"""
Unit tests for the Integrated Risk Manager.

This test suite covers the integration of all risk management components:
- Daily loss tracking
- Emergency shutdown
- Manual confirmation
- Risk event logging
- Configurable thresholds
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json

from binance_trade_bot.database import Database
from binance_trade_bot.logger import Logger
from binance_trade_bot.risk_management.integrated_risk_manager import IntegratedRiskManager
from binance_trade_bot.risk_management.emergency_shutdown_manager import ShutdownReason, ShutdownPriority
from binance_trade_bot.risk_management.manual_confirmation_manager import ApprovalLevel
from binance_trade_bot.risk_management.configurable_loss_thresholds import ThresholdType
from binance_trade_bot.models import RiskEventType, RiskEventSeverity, RiskEventStatus, Pair, Coin


class TestIntegratedRiskManager(unittest.TestCase):
    """
    Test suite for IntegratedRiskManager class.
    """
    
    def setUp(self):
        """
        Set up test fixtures before each test method.
        """
        # Mock database
        self.mock_database = Mock(spec=Database)
        self.mock_database.db_session = Mock()
        
        # Mock logger
        self.mock_logger = Mock(spec=Logger)
        
        # Mock configuration
        self.test_config = {
            'enable_risk_integration': True,
            'auto_shutdown_on_threshold': True,
            'require_manual_confirmation': True,
            'notification_cooldown': 300,
            'max_daily_loss_percentage': 5.0,
            'enable_daily_loss_protection': True
        }
        
        # Create integrated risk manager instance
        self.risk_manager = IntegratedRiskManager(
            self.mock_database,
            self.mock_logger,
            self.test_config
        )
        
        # Mock session
        self.mock_session = Mock()
        self.mock_database.db_session.return_value.__enter__.return_value = self.mock_session
    
    def test_initialization(self):
        """
        Test that IntegratedRiskManager initializes correctly.
        """
        self.assertIsNotNone(self.risk_manager)
        self.assertTrue(self.risk_manager.enable_integration)
        self.assertTrue(self.risk_manager.auto_shutdown_on_threshold)
        self.assertTrue(self.risk_manager.require_manual_confirmation)
        self.assertEqual(self.risk_manager.notification_cooldown, 300)
        
        # Check that all components are initialized
        self.assertIsNotNone(self.risk_manager.daily_loss_manager)
        self.assertIsNotNone(self.risk_manager.emergency_shutdown_manager)
        self.assertIsNotNone(self.risk_manager.manual_confirmation_manager)
        self.assertIsNotNone(self.risk_manager.risk_event_logger)
        self.assertIsNotNone(self.risk_manager.configurable_thresholds)
    
    def test_calculate_position_size(self):
        """
        Test position size calculation with risk constraints.
        """
        # Test normal calculation
        account_balance = 10000
        risk_per_trade = 0.02  # 2%
        entry_price = 50000
        stop_loss_price = 49000
        
        position_size = self.risk_manager.calculate_position_size(
            account_balance, risk_per_trade, entry_price, stop_loss_price
        )
        
        # Expected: (10000 * 0.02) / (50000 - 49000) = 200 / 1000 = 0.2
        expected_size = 0.2
        self.assertAlmostEqual(position_size, expected_size, places=2)
        
        # Test with trading not allowed
        with patch.object(self.risk_manager, 'is_trading_allowed', return_value=False):
            position_size = self.risk_manager.calculate_position_size(
                account_balance, risk_per_trade, entry_price, stop_loss_price
            )
            self.assertEqual(position_size, 0.0)
    
    def test_check_risk_limits(self):
        """
        Test risk limits checking with various scenarios.
        """
        # Test normal trade
        proposed_trade = {
            'quantity': 0.1,
            'entry_price': 50000,
            'stop_loss_price': 49000,
            'account_balance': 10000
        }
        current_positions = {}
        
        result = self.risk_manager.check_risk_limits(proposed_trade, current_positions)
        
        self.assertEqual(result['status'], 'success')
        self.assertTrue(result['allowed'])
        self.assertEqual(len(result['violations']), 0)
        
        # Test with trading not allowed
        with patch.object(self.risk_manager, 'is_trading_allowed', return_value=False):
            result = self.risk_manager.check_risk_limits(proposed_trade, current_positions)
            self.assertEqual(result['status'], 'error')
            self.assertFalse(result['allowed'])
            self.assertIn('Trading currently halted', result['violations'])
    
    def test_calculate_max_drawdown(self):
        """
        Test maximum drawdown calculation.
        """
        # Test normal equity curve
        equity_curve = [10000, 10500, 10300, 10800, 10600, 10400, 10200]
        
        result = self.risk_manager.calculate_max_drawdown(equity_curve)
        
        self.assertEqual(result['status'], 'success')
        self.assertGreater(result['max_drawdown'], 0)
        self.assertGreater(result['max_drawdown_percentage'], 0)
        self.assertGreater(result['drawdown_duration'], 0)
        
        # Test insufficient data
        result = self.risk_manager.calculate_max_drawdown([])
        self.assertEqual(result['status'], 'error')
    
    def test_assess_trade_risk(self):
        """
        Test trade risk assessment.
        """
        trade_data = {
            'position_size': 1000,
            'entry_price': 50000,
            'stop_loss_price': 49000
        }
        market_data = {
            'volatility': 0.03,
            'account_size': 10000
        }
        
        result = self.risk_manager.assess_trade_risk(trade_data, market_data)
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('risk_level', result)
        self.assertIn('risk_score', result)
        self.assertIn('factors', result)
        self.assertIn('recommendations', result)
        
        # Test with high volatility
        market_data['volatility'] = 0.08
        result = self.risk_manager.assess_trade_risk(trade_data, market_data)
        self.assertIn('high_volatility', [f['factor'] for f in result['factors']])
    
    def test_should_stop_trading(self):
        """
        Test trading stop conditions.
        """
        account_performance = {}
        market_conditions = {}
        
        # Test normal conditions
        result = self.risk_manager.should_stop_trading(account_performance, market_conditions)
        self.assertFalse(result)
        
        # Test with emergency shutdown active
        with patch.object(self.risk_manager.emergency_shutdown_manager, 'is_shutdown_active', return_value=True):
            result = self.risk_manager.should_stop_trading(account_performance, market_conditions)
            self.assertTrue(result)
    
    def test_get_risk_metrics(self):
        """
        Test risk metrics calculation.
        """
        trading_history = [
            {'pnl': 100},
            {'pnl': -50},
            {'pnl': 200},
            {'pnl': -75},
            {'pnl': 150}
        ]
        
        result = self.risk_manager.get_risk_metrics(trading_history)
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('metrics', result)
        self.assertIn('total_trades', result['metrics'])
        self.assertIn('win_rate', result['metrics'])
        self.assertIn('total_pnl', result['metrics'])
        self.assertIn('profit_factor', result['metrics'])
        
        # Test empty history
        result = self.risk_manager.get_risk_metrics([])
        self.assertEqual(result['status'], 'error')
    
    def test_is_trading_allowed(self):
        """
        Test trading permission checks.
        """
        # Test normal conditions
        with patch.object(self.risk_manager.daily_loss_manager, 'is_trading_allowed', return_value=True), \
             patch.object(self.risk_manager.emergency_shutdown_manager, 'is_shutdown_active', return_value=False), \
             patch.object(self.risk_manager.configurable_thresholds, 'check_all_thresholds', return_value={'should_stop': False}):
            
            result = self.risk_manager.is_trading_allowed()
            self.assertTrue(result)
        
        # Test with daily loss exceeded
        with patch.object(self.risk_manager.daily_loss_manager, 'is_trading_allowed', return_value=False):
            result = self.risk_manager.is_trading_allowed()
            self.assertFalse(result)
    
    def test_get_risk_status(self):
        """
        Test comprehensive risk status retrieval.
        """
        result = self.risk_manager.get_risk_status()
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('overall_status', result)
        self.assertIn('components', result)
        self.assertIn('alerts', result)
        self.assertIn('last_updated', result)
        
        # Check that all components are present
        self.assertIn('daily_loss', result['components'])
        self.assertIn('emergency_shutdown', result['components'])
        self.assertIn('manual_confirmation', result['components'])
        self.assertIn('thresholds', result['components'])
        self.assertIn('recent_events', result['components'])
    
    def test_emergency_shutdown(self):
        """
        Test emergency shutdown functionality.
        """
        result = self.risk_manager.emergency_shutdown('test_reason', 'high', 'test_description')
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('shutdown_triggered', result)
        
        # Test with invalid reason
        result = self.risk_manager.emergency_shutdown('invalid_reason', 'high', 'test_description')
        self.assertEqual(result['status'], 'error')
    
    def test_attempt_recovery(self):
        """
        Test recovery functionality.
        """
        result = self.risk_manager.attempt_recovery('test_reason', 'test_description')
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('recovery_attempted', result)
    
    def test_complete_recovery(self):
        """
        Test recovery completion.
        """
        result = self.risk_manager.complete_recovery('test_user', {'test': 'metadata'})
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('recovery_completed', result)
    
    def test_request_manual_confirmation(self):
        """
        Test manual confirmation requests.
        """
        trade_data = {'test': 'trade_data'}
        
        result = self.risk_manager.request_manual_confirmation(trade_data, 'test_request')
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('request_id', result)
    
    def test_approve_confirmation_request(self):
        """
        Test confirmation request approval.
        """
        result = self.risk_manager.approve_confirmation_request('test_request_id', 'test_user')
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('request_approved', result)
    
    def test_update_thresholds(self):
        """
        Test threshold updates.
        """
        threshold_updates = {
            'daily_loss': {'value': 3.0},
            'max_drawdown': {'value': 10.0}
        }
        
        result = self.risk_manager.update_thresholds(threshold_updates)
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('thresholds_updated', result)
    
    def test_get_threshold_history(self):
        """
        Test threshold history retrieval.
        """
        result = self.risk_manager.get_threshold_history('daily_loss', 7)
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('history', result)
    
    def test_apply_position_size_constraints(self):
        """
        Test position size constraint application.
        """
        position_size = 1.0
        account_balance = 10000
        
        result = self.risk_manager._apply_position_size_constraints(position_size, account_balance)
        
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, position_size)
    
    def test_check_position_size_limits(self):
        """
        Test position size limit checking.
        """
        proposed_trade = {'quantity': 1.0}
        current_positions = {}
        
        result = self.risk_manager._check_position_size_limits(proposed_trade, current_positions)
        
        self.assertIn('violations', result)
        self.assertIn('warnings', result)
        self.assertIn('severity', result)
    
    def test_calculate_adjusted_position_size(self):
        """
        Test adjusted position size calculation.
        """
        proposed_trade = {'quantity': 1.0}
        current_positions = {}
        violations = []
        
        result = self.risk_manager._calculate_adjusted_position_size(proposed_trade, current_positions, violations)
        
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, proposed_trade['quantity'])
    
    def test_create_confirmation_request(self):
        """
        Test confirmation request creation.
        """
        trade_data = {'test': 'trade_data'}
        
        result = self.risk_manager._create_confirmation_request(trade_data)
        
        self.assertIsNotNone(result)
    
    def test_trigger_emergency_shutdown_if_needed(self):
        """
        Test emergency shutdown triggering.
        """
        # Test with auto_shutdown_on_threshold = True
        with patch.object(self.risk_manager.emergency_shutdown_manager, 'trigger_shutdown', return_value={'shutdown_triggered': True}):
            result = self.risk_manager._trigger_emergency_shutdown_if_needed('test_reason', 0.1)
            self.assertTrue(result)
        
        # Test with auto_shutdown_on_threshold = False
        self.risk_manager.auto_shutdown_on_threshold = False
        result = self.risk_manager._trigger_emergency_shutdown_if_needed('test_reason', 0.1)
        self.assertFalse(result)
    
    def test_create_market_stress_event(self):
        """
        Test market stress event creation.
        """
        # Mock session to avoid database operations
        with patch.object(self.risk_manager, 'database') as mock_db:
            mock_session = Mock()
            mock_db.db_session.return_value.__enter__.return_value = mock_session
            
            self.risk_manager._create_market_stress_event(0.85)
            
            # Check that risk event was created
            mock_session.add.assert_called()
    
    def test_calculate_overall_risk_score(self):
        """
        Test overall risk score calculation.
        """
        trading_history = [
            {'pnl': 100},
            {'pnl': -50},
            {'pnl': 200},
            {'pnl': -75},
            {'pnl': 150}
        ]
        
        result = self.risk_manager._calculate_overall_risk_score(trading_history)
        
        self.assertGreaterEqual(result, 0)
        self.assertLessEqual(result, 100)
        
        # Test empty history
        result = self.risk_manager._calculate_overall_risk_score([])
        self.assertEqual(result, 0.0)


if __name__ == '__main__':
    unittest.main()