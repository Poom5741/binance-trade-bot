"""
Daily loss management system for portfolio value monitoring and risk protection.

This module implements:
- Daily portfolio value tracking
- Loss percentage calculation
- Automatic trading halt when thresholds are exceeded
- Daily counter reset at midnight
"""

import logging
from datetime import datetime, date, time, timedelta
from typing import Optional, Dict, Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..database import Database
from ..models import DailyLossTracking, DailyLossStatus, CoinValue, Coin, Trade, TradeState
from ..logger import Logger


class DailyLossManager:
    """
    Manager class for handling daily loss tracking and portfolio protection.
    
    This class provides methods to:
    - Monitor portfolio values at day start
    - Calculate daily loss percentages
    - Halt trading when loss thresholds are exceeded
    - Reset counters at midnight
    """
    
    def __init__(self, database: Database, logger: Logger, config: Dict[str, Any]):
        """
        Initialize the daily loss manager.
        
        @param {Database} database - Database instance
        @param {Logger} logger - Logger instance
        @param {Dict} config - Configuration dictionary
        """
        self.database = database
        self.logger = logger
        self.config = config
        
        # Configuration parameters
        self.max_daily_loss_percentage = config.get('max_daily_loss_percentage', 5.0)
        self.portfolio_update_interval = config.get('portfolio_update_interval', 300)  # 5 minutes
        self.enable_daily_loss_protection = config.get('enable_daily_loss_protection', True)
        
        # Track last portfolio update
        self.last_portfolio_update = None
        
        # Initialize logger
        self.log = logging.getLogger(__name__)
    
    def get_or_create_daily_tracking(self, session: Session, tracking_date: datetime) -> DailyLossTracking:
        """
        Get existing daily tracking record or create a new one.
        
        @param {Session} session - Database session
        @param {datetime} tracking_date - Date to track
        @returns {DailyLossTracking} Daily tracking record
        """
        # Try to get existing record for this date
        tracking = session.query(DailyLossTracking).filter(
            func.date(DailyLossTracking.tracking_date) == func.date(tracking_date)
        ).first()
        
        if tracking:
            return tracking
        
        # Create new tracking record
        portfolio_value = self._calculate_current_portfolio_value(session)
        tracking = DailyLossTracking(
            tracking_date=tracking_date,
            starting_portfolio_value=portfolio_value,
            max_daily_loss_percentage=self.max_daily_loss_percentage
        )
        
        session.add(tracking)
        self.log.info(f"Created new daily loss tracking record for {tracking_date.date()}")
        
        return tracking
    
    def _calculate_current_portfolio_value(self, session: Session) -> float:
        """
        Calculate the current total portfolio value.
        
        @param {Session} session - Database session
        @returns {float} Total portfolio value in USD
        """
        try:
            # Get all coin values and calculate total portfolio value
            coin_values = session.query(CoinValue).filter(
                CoinValue.interval == CoinValue.Interval.DAILY
            ).all()
            
            total_value = 0.0
            for coin_value in coin_values:
                if coin_value.usd_value:
                    total_value += coin_value.usd_value
            
            return total_value
            
        except Exception as e:
            self.log.error(f"Error calculating portfolio value: {e}")
            return 0.0
    
    def update_portfolio_value(self, session: Session) -> bool:
        """
        Update the current portfolio value and check for loss thresholds.
        
        @param {Session} session - Database session
        @returns {bool} True if update successful, False otherwise
        """
        if not self.enable_daily_loss_protection:
            self.log.info("Daily loss protection is disabled")
            return True
        
        try:
            # Get today's tracking record
            today = datetime.now()
            tracking = self.get_or_create_daily_tracking(session, today)
            
            # Calculate current portfolio value
            current_value = self._calculate_current_portfolio_value(session)
            
            # Update tracking
            tracking.update_portfolio_value(current_value)
            
            # Check if trading should be halted
            if tracking.trading_halted:
                self.log.warning(f"Trading halted: {tracking.halt_reason}")
                self._create_risk_event(session, tracking)
                return False
            
            self.last_portfolio_update = datetime.now()
            return True
            
        except Exception as e:
            self.log.error(f"Error updating portfolio value: {e}")
            return False
    
    def check_daily_reset(self, session: Session) -> bool:
        """
        Check if daily reset is needed (at midnight) and perform reset.
        
        @param {Session} session - Database session
        @returns {bool} True if reset performed, False otherwise
        """
        try:
            now = datetime.now()
            midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Check if we need to reset (first run after midnight)
            if self.last_portfolio_update and self.last_portfolio_update.date() < now.date():
                # Get yesterday's tracking record
                yesterday = midnight - timedelta(days=1)
                tracking = session.query(DailyLossTracking).filter(
                    func.date(DailyLossTracking.tracking_date) == func.date(yesterday)
                ).first()
                
                if tracking:
                    tracking.reset_daily_tracking()
                    self.log.info(f"Daily reset completed for {yesterday.date()}")
                
                self.last_portfolio_update = now
                return True
            
            return False
            
        except Exception as e:
            self.log.error(f"Error checking daily reset: {e}")
            return False
    
    def add_trade_result(self, session: Session, trade: Trade, is_profit: bool, profit_amount: float):
        """
        Add a trade result to the daily tracking.
        
        @param {Session} session - Database session
        @param {Trade} trade - Trade object
        @param {bool} is_profit - True if trade was profitable
        @param {float} profit_amount - Profit/loss amount
        """
        if not self.enable_daily_loss_protection:
            return
        
        try:
            # Get today's tracking record
            today = datetime.now()
            tracking = self.get_or_create_daily_tracking(session, today)
            
            # Add trade result
            tracking.add_trade_result(is_profit, abs(profit_amount))
            
            # Update portfolio value after trade
            self.update_portfolio_value(session)
            
        except Exception as e:
            self.log.error(f"Error adding trade result: {e}")
    
    def is_trading_allowed(self, session: Session) -> bool:
        """
        Check if trading is currently allowed based on daily loss limits.
        
        @param {Session} session - Database session
        @returns {bool} True if trading allowed, False otherwise
        """
        if not self.enable_daily_loss_protection:
            return True
        
        try:
            # Get today's tracking record
            today = datetime.now()
            tracking = self.get_or_create_daily_tracking(session, today)
            
            return not tracking.trading_halted
            
        except Exception as e:
            self.log.error(f"Error checking trading permission: {e}")
            return False  # Default to no trading if error
    
    def get_daily_loss_summary(self, session: Session, date_filter: Optional[date] = None) -> Dict[str, Any]:
        """
        Get daily loss summary for a specific date or today.
        
        @param {Session} session - Database session
        @param {date} date_filter - Optional date filter
        @returns {Dict} Daily loss summary
        """
        try:
            if date_filter:
                tracking_date = datetime.combine(date_filter, time.min)
            else:
                tracking_date = datetime.now()
            
            tracking = session.query(DailyLossTracking).filter(
                func.date(DailyLossTracking.tracking_date) == func.date(tracking_date)
            ).first()
            
            if not tracking:
                return {
                    "status": "no_data",
                    "message": "No daily tracking data available for the specified date"
                }
            
            return {
                "status": "success",
                "data": tracking.info()
            }
            
        except Exception as e:
            self.log.error(f"Error getting daily loss summary: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_daily_loss_history(self, session: Session, days: int = 7) -> Dict[str, Any]:
        """
        Get daily loss history for the specified number of days.
        
        @param {Session} session - Database session
        @param {int} days - Number of days to look back
        @returns {Dict} Daily loss history
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            trackings = session.query(DailyLossTracking).filter(
                DailyLossTracking.tracking_date >= cutoff_date
            ).order_by(DailyLossTracking.tracking_date.desc()).all()
            
            history = [tracking.info() for tracking in trackings]
            
            return {
                "status": "success",
                "data": history,
                "total_days": len(history)
            }
            
        except Exception as e:
            self.log.error(f"Error getting daily loss history: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _create_risk_event(self, session: Session, tracking: DailyLossTracking):
        """
        Create a risk event when daily loss threshold is exceeded.
        
        @param {Session} session - Database session
        @param {DailyLossTracking} tracking - Tracking record
        """
        try:
            from ..models import RiskEvent, RiskEventType, RiskEventSeverity, RiskEventStatus, Pair
            
            # Create a risk event for the daily loss
            # Find a default pair for the event
            pair = session.query(Pair).first()
            if not pair:
                pair = Pair(Coin("USDT", True), Coin("BTC", True))  # Default pair
                session.add(pair)
            
            risk_event = RiskEvent(
                pair=pair,
                coin=pair.from_coin,  # Use from_coin as the main coin
                event_type=RiskEventType.PORTFOLIO_LIMIT,
                severity=RiskEventSeverity.HIGH,
                trigger_value=tracking.daily_loss_percentage,
                threshold_value=tracking.max_daily_loss_percentage,
                current_value=tracking.daily_loss_percentage,
                description=f"Daily loss threshold exceeded: {tracking.daily_loss_percentage:.2f}% (threshold: {tracking.max_daily_loss_percentage}%)",
                created_by="daily_loss_manager"
            )
            
            session.add(risk_event)
            self.log.info(f"Created risk event for daily loss: {tracking.daily_loss_percentage:.2f}%")
            
        except Exception as e:
            self.log.error(f"Error creating risk event: {e}")
    
    def force_daily_reset(self, session: Session, reset_date: Optional[date] = None) -> bool:
        """
        Force a daily reset for a specific date.
        
        @param {Session} session - Database session
        @param {date} reset_date - Date to reset (defaults to today)
        @returns {bool} True if reset successful
        """
        try:
            if reset_date:
                reset_datetime = datetime.combine(reset_date, time.min)
            else:
                reset_datetime = datetime.now()
            
            tracking = session.query(DailyLossTracking).filter(
                func.date(DailyLossTracking.tracking_date) == func.date(reset_datetime)
            ).first()
            
            if tracking:
                tracking.reset_daily_tracking()
                self.log.info(f"Forced daily reset for {reset_date}")
                return True
            else:
                self.log.warning(f"No tracking record found for {reset_date}")
                return False
                
        except Exception as e:
            self.log.error(f"Error forcing daily reset: {e}")
            return False