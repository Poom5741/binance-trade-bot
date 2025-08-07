"""
Base abstract class for risk management implementations.
"""

from abc import ABC, abstractmethod


class RiskManagementBase(ABC):
    """
    Abstract base class for risk management implementations.
    
    This class defines the interface that all risk management implementations
    must follow, ensuring consistent functionality across different risk
    control strategies and position sizing methods.
    """
    
    def __init__(self, config):
        """
        Initialize the risk management module with configuration.
        
        @param {dict} config - Configuration dictionary containing risk management settings
        """
        self.config = config
    
    @abstractmethod
    def calculate_position_size(self, account_balance, risk_per_trade, entry_price, stop_loss_price):
        """
        Calculate the appropriate position size based on risk parameters.
        
        @param {float} account_balance - Total account balance
        @param {float} risk_per_trade - Risk percentage per trade (0.01 = 1%)
        @param {float} entry_price - Entry price for the trade
        @param {float} stop_loss_price - Stop loss price for the trade
        @returns {float} Calculated position size
        """
        pass
    
    @abstractmethod
    def check_risk_limits(self, proposed_trade, current_positions):
        """
        Check if a proposed trade complies with risk management rules.
        
        @param {dict} proposed_trade - Dictionary containing proposed trade details
        @param {dict} current_positions - Dictionary of current open positions
        @returns {dict} Dictionary with risk check results and any violations
        """
        pass
    
    @abstractmethod
    def calculate_max_drawdown(self, equity_curve):
        """
        Calculate the maximum drawdown from an equity curve.
        
        @param {list} equity_curve - List of equity values over time
        @returns {dict} Dictionary containing max drawdown statistics
        """
        pass
    
    @abstractmethod
    def assess_trade_risk(self, trade_data, market_data):
        """
        Assess the risk level of a potential trade.
        
        @param {dict} trade_data - Dictionary containing trade parameters
        @param {dict} market_data - Dictionary containing current market conditions
        @returns {dict} Dictionary with risk assessment results
        """
        pass
    
    @abstractmethod
    def should_stop_trading(self, account_performance, market_conditions):
        """
        Determine if trading should be stopped based on risk parameters.
        
        @param {dict} account_performance - Dictionary with account performance metrics
        @param {dict} market_conditions - Dictionary with current market conditions
        @returns {bool} True if trading should be stopped, False otherwise
        """
        pass
    
    @abstractmethod
    def get_risk_metrics(self, trading_history):
        """
        Calculate comprehensive risk metrics from trading history.
        
        @param {list} trading_history - List of completed trades
        @returns {dict} Dictionary with various risk metrics
        """
        pass