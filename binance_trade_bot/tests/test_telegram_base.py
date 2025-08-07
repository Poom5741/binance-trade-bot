"""
Unit tests for Telegram base abstract class.

This module contains tests for the abstract base class that defines
the interface for all Telegram bot implementations.
"""

import unittest
from unittest.mock import Mock, patch
from abc import ABC, abstractmethod

from binance_trade_bot.telegram.base import TelegramBase


class TestTelegramBase(unittest.TestCase):
    """
    Test suite for Telegram base abstract class.
    """
    
    def test_abstract_class_definition(self):
        """
        Test that TelegramBase is properly defined as an abstract class.
        """
        # Verify it's an abstract class
        self.assertTrue(issubclass(TelegramBase, ABC))
        
        # Verify it has the required abstract methods
        abstract_methods = ['send_message', 'send_trade_notification', 'send_alert', 'start_bot', 'stop_bot']
        for method in abstract_methods:
            self.assertTrue(hasattr(TelegramBase, method))
            self.assertTrue(getattr(TelegramBase, method).__isabstractmethod__)
    
    def test_initialization(self):
        """
        Test TelegramBase initialization with configuration.
        """
        # Create a concrete implementation for testing
        class TestBot(TelegramBase):
            def send_message(self, chat_id, text, parse_mode=None):
                pass
            def send_trade_notification(self, trade_data):
                pass
            def send_alert(self, alert_type, message, details=None):
                pass
            def start_bot(self):
                pass
            def stop_bot(self):
                pass
        
        # Test initialization with config
        config = {'test_key': 'test_value'}
        bot = TestBot(config)
        
        # Verify config is stored
        self.assertEqual(bot.config, config)
    
    def test_initialization_without_config(self):
        """
        Test TelegramBase initialization without configuration.
        """
        # Create a concrete implementation for testing
        class TestBot(TelegramBase):
            def send_message(self, chat_id, text, parse_mode=None):
                pass
            def send_trade_notification(self, trade_data):
                pass
            def send_alert(self, alert_type, message, details=None):
                pass
            def start_bot(self):
                pass
            def stop_bot(self):
                pass
        
        # Test initialization without config
        bot = TestBot({})
        
        # Verify config is empty dict
        self.assertEqual(bot.config, {})
    
    def test_abstract_method_signatures(self):
        """
        Test that abstract methods have correct signatures.
        """
        # Create a concrete implementation for testing
        class TestBot(TelegramBase):
            def send_message(self, chat_id, text, parse_mode=None):
                """Send a message to a specified chat."""
                pass
            def send_trade_notification(self, trade_data):
                """Send a trade notification message."""
                pass
            def send_alert(self, alert_type, message, details=None):
                """Send an alert message based on alert type."""
                pass
            def start_bot(self):
                """Start the telegram bot and begin listening for messages."""
                pass
            def stop_bot(self):
                """Stop the telegram bot and clean up resources."""
                pass
        
        # Test that methods can be called with correct parameters
        bot = TestBot({})
        
        # Test send_message signature
        try:
            bot.send_message("123", "test message")
            bot.send_message("123", "test message", "HTML")
        except Exception as e:
            self.fail(f"send_message signature is incorrect: {e}")
        
        # Test send_trade_notification signature
        try:
            bot.send_trade_notification({})
            bot.send_trade_notification({'action': 'buy'})
        except Exception as e:
            self.fail(f"send_trade_notification signature is incorrect: {e}")
        
        # Test send_alert signature
        try:
            bot.send_alert('error', 'test message')
            bot.send_alert('warning', 'test message', {'detail': 'value'})
        except Exception as e:
            self.fail(f"send_alert signature is incorrect: {e}")
        
        # Test start_bot signature
        try:
            bot.start_bot()
        except Exception as e:
            self.fail(f"start_bot signature is incorrect: {e}")
        
        # Test stop_bot signature
        try:
            bot.stop_bot()
        except Exception as e:
            self.fail(f"stop_bot signature is incorrect: {e}")


class TestTelegramBaseImplementation(unittest.TestCase):
    """
    Test suite for testing concrete implementations of TelegramBase.
    """
    
    def setUp(self):
        """
        Set up test fixtures.
        """
        # Create a concrete implementation for testing
        class MockBot(TelegramBase):
            def __init__(self, config):
                super().__init__(config)
                self.messages_sent = []
                self.notifications_sent = []
                self.alerts_sent = []
                self.bot_started = False
                self.bot_stopped = False
            
            def send_message(self, chat_id, text, parse_mode=None):
                """Mock implementation that records messages."""
                self.messages_sent.append({
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': parse_mode
                })
                return True
            
            def send_trade_notification(self, trade_data):
                """Mock implementation that records notifications."""
                self.notifications_sent.append(trade_data)
                return True
            
            def send_alert(self, alert_type, message, details=None):
                """Mock implementation that records alerts."""
                self.alerts_sent.append({
                    'alert_type': alert_type,
                    'message': message,
                    'details': details
                })
                return True
            
            def start_bot(self):
                """Mock implementation that records bot start."""
                self.bot_started = True
                return True
            
            def stop_bot(self):
                """Mock implementation that records bot stop."""
                self.bot_stopped = True
                return True
        
        self.bot = MockBot({'test': 'config'})
    
    def test_send_message_functionality(self):
        """
        Test send_message functionality in concrete implementation.
        """
        # Test basic message sending
        result = self.bot.send_message("123456789", "Hello, World!")
        self.assertTrue(result)
        self.assertEqual(len(self.bot.messages_sent), 1)
        self.assertEqual(self.bot.messages_sent[0]['chat_id'], "123456789")
        self.assertEqual(self.bot.messages_sent[0]['text'], "Hello, World!")
        self.assertIsNone(self.bot.messages_sent[0]['parse_mode'])
        
        # Test message with parse mode
        result = self.bot.send_message("123456789", "Bold text", "HTML")
        self.assertTrue(result)
        self.assertEqual(len(self.bot.messages_sent), 2)
        self.assertEqual(self.bot.messages_sent[1]['parse_mode'], "HTML")
    
    def test_send_trade_notification_functionality(self):
        """
        Test send_trade_notification functionality in concrete implementation.
        """
        # Test basic trade notification
        trade_data = {'action': 'buy', 'pair': 'BTCUSDT', 'price': '50000'}
        result = self.bot.send_trade_notification(trade_data)
        
        self.assertTrue(result)
        self.assertEqual(len(self.bot.notifications_sent), 1)
        self.assertEqual(self.bot.notifications_sent[0], trade_data)
        
        # Test multiple notifications
        trade_data2 = {'action': 'sell', 'pair': 'ETHUSDT', 'price': '3000'}
        result = self.bot.send_trade_notification(trade_data2)
        
        self.assertTrue(result)
        self.assertEqual(len(self.bot.notifications_sent), 2)
        self.assertEqual(self.bot.notifications_sent[1], trade_data2)
    
    def test_send_alert_functionality(self):
        """
        Test send_alert functionality in concrete implementation.
        """
        # Test basic alert
        result = self.bot.send_alert('error', 'System error occurred')
        self.assertTrue(result)
        self.assertEqual(len(self.bot.alerts_sent), 1)
        self.assertEqual(self.bot.alerts_sent[0]['alert_type'], 'error')
        self.assertEqual(self.bot.alerts_sent[0]['message'], 'System error occurred')
        self.assertIsNone(self.bot.alerts_sent[0]['details'])
        
        # Test alert with details
        details = {'code': 500, 'module': 'trading'}
        result = self.bot.send_alert('warning', 'High risk detected', details)
        self.assertTrue(result)
        self.assertEqual(len(self.bot.alerts_sent), 2)
        self.assertEqual(self.bot.alerts_sent[1]['alert_type'], 'warning')
        self.assertEqual(self.bot.alerts_sent[1]['message'], 'High risk detected')
        self.assertEqual(self.bot.alerts_sent[1]['details'], details)
    
    def test_bot_lifecycle(self):
        """
        Test bot start/stop lifecycle in concrete implementation.
        """
        # Initially bot should not be started or stopped
        self.assertFalse(self.bot.bot_started)
        self.assertFalse(self.bot.bot_stopped)
        
        # Start bot
        result = self.bot.start_bot()
        self.assertTrue(result)
        self.assertTrue(self.bot.bot_started)
        self.assertFalse(self.bot.bot_stopped)
        
        # Stop bot
        result = self.bot.stop_bot()
        self.assertTrue(result)
        self.assertTrue(self.bot.bot_started)
        self.assertTrue(self.bot.bot_stopped)
    
    def test_configuration_access(self):
        """
        Test configuration access in concrete implementation.
        """
        # Test accessing configuration
        self.assertEqual(self.bot.config['test'], 'config')
        
        # Test modifying configuration
        self.bot.config['new_key'] = 'new_value'
        self.assertEqual(self.bot.config['new_key'], 'new_value')
    
    def test_method_return_types(self):
        """
        Test that all methods return the expected types.
        """
        # Test send_message returns bool
        result = self.bot.send_message("123", "test")
        self.assertIsInstance(result, bool)
        
        # Test send_trade_notification returns bool
        result = self.bot.send_trade_notification({})
        self.assertIsInstance(result, bool)
        
        # Test send_alert returns bool
        result = self.bot.send_alert('info', 'test')
        self.assertIsInstance(result, bool)
        
        # Test start_bot returns bool
        result = self.bot.start_bot()
        self.assertIsInstance(result, bool)
        
        # Test stop_bot returns bool
        result = self.bot.stop_bot()
        self.assertIsInstance(result, bool)


if __name__ == '__main__':
    unittest.main()