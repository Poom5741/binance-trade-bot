"""
Statistics models for performance tracking.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, DateTime, Float, Integer, String, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
import pandas as pd

from ..models.base import Base


class Statistics(Base):
    """
    Main statistics model for storing aggregated performance data.
    """
    __tablename__ = "statistics"

    id = Column(Integer, primary_key=True)
    period_type = Column(String)  # daily, weekly, total
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    
    # Basic metrics
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    
    # Profit/Loss metrics
    total_profit_loss = Column(Float, default=0.0)
    total_profit_loss_percentage = Column(Float, default=0.0)
    average_profit_loss = Column(Float, default=0.0)
    average_win = Column(Float, default=0.0)
    average_loss = Column(Float, default=0.0)
    
    # Volume metrics
    total_volume = Column(Float, default=0.0)
    average_trade_size = Column(Float, default=0.0)
    
    # Advanced metrics
    roi = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    volatility = Column(Float, default=0.0)
    
    # Additional data
    profit_factor = Column(Float, default=0.0)
    recovery_factor = Column(Float, default=0.0)
    calmar_ratio = Column(Float, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # JSON data for additional metrics
    additional_metrics = Column(Text, nullable=True)
    
    def __init__(self, period_type: str, period_start: Optional[datetime] = None, 
                 period_end: Optional[datetime] = None):
        self.period_type = period_type
        self.period_start = period_start
        self.period_end = period_end
    
    def info(self) -> dict:
        """
        Get information about this statistics record.
        
        @returns {dict} Dictionary containing statistics information
        """
        return {
            "id": self.id,
            "period_type": self.period_type,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_profit_loss": self.total_profit_loss,
            "total_profit_loss_percentage": self.total_profit_loss_percentage,
            "average_profit_loss": self.average_profit_loss,
            "average_win": self.average_win,
            "average_loss": self.average_loss,
            "total_volume": self.total_volume,
            "average_trade_size": self.average_trade_size,
            "roi": self.roi,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "volatility": self.volatility,
            "profit_factor": self.profit_factor,
            "recovery_factor": self.recovery_factor,
            "calmar_ratio": self.calmar_ratio,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "additional_metrics": self.additional_metrics,
        }


class DailyPerformance(Statistics):
    """
    Daily performance statistics.
    """
    __tablename__ = "daily_performance"
    
    date = Column(DateTime, unique=True)
    
    def __init__(self, date: datetime):
        super().__init__("daily")
        self.date = date
        self.period_start = date
        self.period_end = date.replace(hour=23, minute=59, second=59, microsecond=999999)


class WeeklyPerformance(Statistics):
    """
    Weekly performance statistics.
    """
    __tablename__ = "weekly_performance"
    
    week_start = Column(DateTime)
    week_end = Column(DateTime)
    
    def __init__(self, week_start: datetime, week_end: datetime):
        super().__init__("weekly")
        self.week_start = week_start
        self.week_end = week_end
        self.period_start = week_start
        self.period_end = week_end


class TotalPerformance(Statistics):
    """
    Total performance statistics.
    """
    __tablename__ = "total_performance"
    
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    
    def __init__(self, start_date: datetime, end_date: datetime):
        super().__init__("total")
        self.start_date = start_date
        self.end_date = end_date
        self.period_start = start_date
        self.period_end = end_date


class TradeRecord(Base):
    """
    Individual trade record for detailed analysis.
    """
    __tablename__ = "trade_records"
    
    id = Column(Integer, primary_key=True)
    trade_id = Column(String, ForeignKey("trade_history.id"))
    symbol = Column(String)
    trade_type = Column(String)  # buy, sell
    entry_price = Column(Float)
    exit_price = Column(Float)
    quantity = Column(Float)
    profit_loss = Column(Float)
    profit_loss_percentage = Column(Float)
    fees = Column(Float, default=0.0)
    entry_time = Column(DateTime)
    exit_time = Column(DateTime)
    holding_period = Column(Float)  # in hours
    
    def __init__(self, trade_id: str, symbol: str, trade_type: str, 
                 entry_price: float, exit_price: float, quantity: float,
                 entry_time: datetime, exit_time: datetime, fees: float = 0.0):
        self.trade_id = trade_id
        self.symbol = symbol
        self.trade_type = trade_type
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.quantity = quantity
        self.entry_time = entry_time
        self.exit_time = exit_time
        self.fees = fees
        self.holding_period = (exit_time - entry_time).total_seconds() / 3600
    
    @property
    def profit_loss(self) -> float:
        """Calculate profit/loss for this trade."""
        if self.trade_type == "buy":
            return (self.exit_price - self.entry_price) * self.quantity - self.fees
        else:  # sell
            return (self.entry_price - self.exit_price) * self.quantity - self.fees
    
    @property
    def profit_loss_percentage(self) -> float:
        """Calculate profit/loss percentage for this trade."""
        if self.trade_type == "buy":
            return ((self.exit_price - self.entry_price) / self.entry_price) * 100
        else:  # sell
            return ((self.entry_price - self.exit_price) / self.exit_price) * 100
    
    def info(self) -> dict:
        """
        Get information about this trade record.
        
        @returns {dict} Dictionary containing trade record information
        """
        return {
            "id": self.id,
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "trade_type": self.trade_type,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "profit_loss": self.profit_loss,
            "profit_loss_percentage": self.profit_loss_percentage,
            "fees": self.fees,
            "entry_time": self.entry_time.isoformat() if self.entry_time else None,
            "exit_time": self.exit_time.isoformat() if self.exit_time else None,
            "holding_period": self.holding_period,
        }