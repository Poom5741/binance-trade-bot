"""
Base abstract class for telegram integration.
"""

from abc import ABC, abstractmethod


class TelegramBase(ABC):
    """
    Abstract base class for telegram bot implementations.
    
    This class defines the interface that all telegram bot implementations
    must follow, ensuring consistent functionality across different telegram
    service providers or custom implementations.
    """
    
    def __init__(self, config):
        """
        Initialize the telegram bot with configuration.
        
        @param {dict} config - Configuration dictionary containing telegram settings
        """
        self.config = config
    
    @abstractmethod
    def send_message(self, chat_id, text, parse_mode=None):
        """
        Send a message to a specified chat.
        
        @param {str} chat_id - Unique identifier for the target chat
        @param {str} text - Text of the message to be sent
        @param {str} parse_mode - Optional. Mode for parsing entities (HTML/Markdown)
        @returns {bool} True if message was sent successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def send_trade_notification(self, trade_data):
        """
        Send a trade notification message.
        
        @param {dict} trade_data - Dictionary containing trade information
        @returns {bool} True if notification was sent successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def send_alert(self, alert_type, message, details=None):
        """
        Send an alert message based on alert type.
        
        @param {str} alert_type - Type of alert (e.g., 'error', 'warning', 'info')
        @param {str} message - Alert message
        @param {dict} details - Optional additional details about the alert
        @returns {bool} True if alert was sent successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def start_bot(self):
        """
        Start the telegram bot and begin listening for messages.
        
        @returns {bool} True if bot started successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def stop_bot(self):
        """
        Stop the telegram bot and clean up resources.
        
        @returns {bool} True if bot stopped successfully, False otherwise
        """
        pass