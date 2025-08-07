"""
Daily loss tracking model for portfolio value monitoring and risk management.
"""

from datetime import datetime, date
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, Float, Integer, String, Boolean, UniqueConstraint
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship

from .base import Base


class DailyLossStatus(Enum):
    ACTIVE = "ACTIVE"
    HALTED = "HALTED"
    RESET = "RESET"
    CLOSED = "CLOSED"


class DailyLossTracking(Base):
    """
    Model for tracking daily portfolio values and calculating daily loss percentages.
    
    This model stores:
    - Daily portfolio value snapshots
    - Daily loss calculations
    - Trading halt status
    - Reset timestamps
    """
    
    __tablename__ = "daily_loss_tracking"
    
    id = Column(Integer, primary_key=True)
    
    # Date tracking - using date instead of datetime for daily aggregation
    tracking_date = Column(DateTime, nullable=False, index=True)
    
    # Portfolio value tracking
    starting_portfolio_value = Column(Float, nullable=False)
    current_portfolio_value = Column(Float, nullable=False)
    daily_loss_amount = Column(Float, default=0.0)
    daily_loss_percentage = Column(Float, default=0.0)
    
    # Risk management thresholds
    max_daily_loss_percentage = Column(Float, default=5.0)  # 5% default
    trading_halted = Column(Boolean, default=False)
    halt_reason = Column(String, nullable=True)
    
    # Status tracking
    status = Column(SQLAlchemyEnum(DailyLossStatus), default=DailyLossStatus.ACTIVE)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    reset_at = Column(DateTime, nullable=True)
    
    # Additional tracking fields
    total_trades_today = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    largest_win_amount = Column(Float, default=0.0)
    largest_loss_amount = Column(Float, default=0.0)
    
    # Ensure one entry per day
    __table_args__ = (
        UniqueConstraint('tracking_date', name='uq_daily_loss_tracking_date'),
    )
    
    def __init__(
        self,
        tracking_date: datetime,
        starting_portfolio_value: float,
        max_daily_loss_percentage: float = 5.0,
    ):
        self.tracking_date = tracking_date
        self.starting_portfolio_value = starting_portfolio_value
        self.current_portfolio_value = starting_portfolio_value
        self.max_daily_loss_percentage = max_daily_loss_percentage
        self.daily_loss_amount = 0.0
        self.daily_loss_percentage = 0.0
    
    @hybrid_property
    def is_loss_threshold_exceeded(self):
        """
        Check if the daily loss threshold has been exceeded.
        
        @returns {bool} True if loss threshold exceeded, False otherwise
        """
        return self.daily_loss_percentage >= self.max_daily_loss_percentage
    
    @hybrid_property
    def portfolio_value_change(self):
        """
        Calculate the absolute change in portfolio value.
        
        @returns {float} Change in portfolio value (current - starting)
        """
        return self.current_portfolio_value - self.starting_portfolio_value
    
    @hybrid_property
    def win_rate(self):
        """
        Calculate the win rate for the day.
        
        @returns {float} Win rate as percentage (0-100)
        """
        total_trades = self.total_trades_today
        if total_trades == 0:
            return 0.0
        return (self.winning_trades / total_trades) * 100
    
    def update_portfolio_value(self, new_value: float):
        """
        Update the current portfolio value and recalculate loss metrics.
        
        @param {float} new_value - New portfolio value
        """
        self.current_portfolio_value = new_value
        self.daily_loss_amount = self.starting_portfolio_value - new_value
        self.daily_loss_percentage = (self.daily_loss_amount / self.starting_portfolio_value) * 100
        
        # Update timestamp
        self.updated_at = datetime.utcnow()
        
        # Check if trading should be halted
        if self.is_loss_threshold_exceeded and not self.trading_halted:
            self.trading_halted = True
            self.halt_reason = f"Daily loss threshold exceeded: {self.daily_loss_percentage:.2f}%"
            self.status = DailyLossStatus.HALTED
    
    def add_trade_result(self, is_win: bool, amount: float):
        """
        Add a trade result to the daily tracking.
        
        @param {bool} is_win - True if trade was profitable, False otherwise
        @param {float} amount - Trade amount (positive for wins, negative for losses)
        """
        self.total_trades_today += 1
        
        if is_win:
            self.winning_trades += 1
            if amount > self.largest_win_amount:
                self.largest_win_amount = amount
        else:
            self.losing_trades += 1
            if abs(amount) > abs(self.largest_loss_amount):
                self.largest_loss_amount = amount
        
        # Update timestamp
        self.updated_at = datetime.utcnow()
    
    def reset_daily_tracking(self):
        """
        Reset the daily tracking for a new day.
        """
        self.status = DailyLossStatus.RESET
        self.reset_at = datetime.utcnow()
        self.trading_halted = False
        self.halt_reason = None
        self.total_trades_today = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.largest_win_amount = 0.0
        self.largest_loss_amount = 0.0
        
        # Update timestamp
        self.updated_at = datetime.utcnow()
    
    def reactivate_trading(self):
        """
        Reactivate trading after a halt (e.g., after daily reset).
        """
        self.trading_halted = False
        self.halt_reason = None
        self.status = DailyLossStatus.ACTIVE
        self.updated_at = datetime.utcnow()
    
    def info(self):
        """
        Get information about the daily loss tracking record.
        
        @returns {dict} Dictionary containing tracking information
        """
        return {
            "id": self.id,
            "tracking_date": self.tracking_date.isoformat(),
            "starting_portfolio_value": self.starting_portfolio_value,
            "current_portfolio_value": self.current_portfolio_value,
            "daily_loss_amount": self.daily_loss_amount,
            "daily_loss_percentage": self.daily_loss_percentage,
            "max_daily_loss_percentage": self.max_daily_loss_percentage,
            "is_loss_threshold_exceeded": self.is_loss_threshold_exceeded,
            "trading_halted": self.trading_halted,
            "halt_reason": self.halt_reason,
            "status": self.status.value,
            "total_trades_today": self.total_trades_today,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "largest_win_amount": self.largest_win_amount,
            "largest_loss_amount": self.largest_loss_amount,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "reset_at": self.reset_at.isoformat() if self.reset_at else None,
        }