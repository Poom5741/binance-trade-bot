"""
Integrated Risk Manager - Centralized risk management system.

This module provides a unified interface for all risk management components,
integrating daily loss tracking, emergency shutdown, manual confirmation,
risk event logging, and configurable thresholds into a cohesive system.

Created: 2025-08-05
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from sqlalchemy.orm import Session

from .base import RiskManagementBase
from .daily_loss_manager import DailyLossManager
from .emergency_shutdown_manager import EmergencyShutdownManager, ShutdownReason, ShutdownPriority
from .manual_confirmation_manager import ManualConfirmationManager, ApprovalLevel
from .risk_event_logger import RiskEventLogger, RiskEventLogType, RiskEventLogSeverity
from .configurable_loss_thresholds import ConfigurableLossThresholds, ThresholdType
from ..database import Database
from ..logger import Logger
from ..models import RiskEvent, RiskEventType, RiskEventSeverity, RiskEventStatus, Pair, Coin


class IntegratedRiskManager(RiskManagementBase):
    """
    Integrated risk management system that coordinates all risk management components.
    
    This class provides a unified interface for:
    - Daily loss tracking and protection
    - Emergency shutdown with state preservation
    - Manual confirmation requirements
    - Risk event logging and notifications
    - Configurable loss threshold settings
    """
    
    def __init__(self, database: Database, logger: Logger, config: Dict[str, Any]):
        """
        Initialize the integrated risk manager.
        
        @param {Database} database - Database instance
        @param {Logger} logger - Logger instance
        @param {Dict} config - Configuration dictionary
        """
        super().__init__(config)
        
        self.database = database
        self.logger = logger
        self.log = logging.getLogger(__name__)
        
        # Initialize individual risk management components
        self.daily_loss_manager = DailyLossManager(database, logger, config)
        self.emergency_shutdown_manager = EmergencyShutdownManager(database, logger, config)
        self.manual_confirmation_manager = ManualConfirmationManager(database, logger, config)
        self.risk_event_logger = RiskEventLogger(database, logger, config)
        self.configurable_thresholds = ConfigurableLossThresholds(database, logger, config)
        
        # Integration settings
        self.enable_integration = config.get('enable_risk_integration', True)
        self.auto_shutdown_on_threshold = config.get('auto_shutdown_on_threshold', True)
        self.require_manual_confirmation = config.get('require_manual_confirmation', True)
        self.notification_cooldown = config.get('notification_cooldown', 300)  # 5 minutes
        
        # Track last notification time
        self.last_notification_time = None
        
        # Initialize logger
        self.log.info("Integrated Risk Manager initialized")
    
    def calculate_position_size(self, account_balance, risk_per_trade, entry_price, stop_loss_price):
        """
        Calculate the appropriate position size based on risk parameters.
        
        @param {float} account_balance - Total account balance
        @param {float} risk_per_trade - Risk percentage per trade (0.01 = 1%)
        @param {float} entry_price - Entry price for the trade
        @param {float} stop_loss_price - Stop loss price for the trade
        @returns {float} Calculated position size
        """
        try:
            # Check if trading is allowed
            if not self.is_trading_allowed():
                self.log.warning("Trading not allowed due to risk management restrictions")
                return 0.0
            
            # Calculate position size using standard risk management formula
            risk_amount = account_balance * risk_per_trade
            price_difference = abs(entry_price - stop_loss_price)
            
            if price_difference == 0:
                return 0.0
            
            position_size = risk_amount / price_difference
            
            # Apply additional risk constraints from integrated components
            position_size = self._apply_position_size_constraints(position_size, account_balance)
            
            return position_size
            
        except Exception as e:
            self.log.error(f"Error calculating position size: {e}")
            return 0.0
    
    def check_risk_limits(self, proposed_trade, current_positions):
        """
        Check if a proposed trade complies with risk management rules.
        
        @param {dict} proposed_trade - Dictionary containing proposed trade details
        @param {dict} current_positions - Dictionary of current open positions
        @returns {dict} Dictionary with risk check results and any violations
        """
        try:
            # Initialize risk check result
            risk_check = {
                "status": "success",
                "allowed": True,
                "violations": [],
                "warnings": [],
                "adjusted_position_size": proposed_trade.get("quantity", 0),
                "risk_metrics": {}
            }
            
            # Check if trading is allowed
            if not self.is_trading_allowed():
                risk_check["status"] = "error"
                risk_check["allowed"] = False
                risk_check["violations"].append("Trading currently halted due to risk management")
                return risk_check
            
            # Check daily loss limits
            daily_loss_check = self.daily_loss_manager.check_daily_loss_tracking(self.database.db_session())
            if daily_loss_check.get("status") == "error":
                risk_check["status"] = "error"
                risk_check["allowed"] = False
                risk_check["violations"].append("Daily loss limit exceeded")
            
            # Check configurable thresholds
            threshold_check = self.configurable_thresholds.check_thresholds(
                proposed_trade, current_positions
            )
            if threshold_check["violations"]:
                risk_check["violations"].extend(threshold_check["violations"])
                if threshold_check["severity"] == "critical":
                    risk_check["status"] = "error"
                    risk_check["allowed"] = False
            
            # Check position size limits
            position_size_check = self._check_position_size_limits(
                proposed_trade, current_positions
            )
            if position_size_check["violations"]:
                risk_check["violations"].extend(position_size_check["violations"])
                if position_size_check["severity"] == "critical":
                    risk_check["status"] = "error"
                    risk_check["allowed"] = False
            
            # Check if manual confirmation is required
            if risk_check["allowed"] and self.require_manual_confirmation:
                confirmation_required = self.manual_confirmation_manager.is_confirmation_required(
                    proposed_trade, current_positions
                )
                if confirmation_required:
                    risk_check["warnings"].append("Manual confirmation required for this trade")
                    risk_check["confirmation_required"] = True
                    risk_check["confirmation_request_id"] = self._create_confirmation_request(proposed_trade)
            
            # Calculate adjusted position size
            if risk_check["allowed"]:
                risk_check["adjusted_position_size"] = self._calculate_adjusted_position_size(
                    proposed_trade, current_positions, risk_check["violations"]
                )
            
            # Log risk check result
            self.risk_event_logger.log_risk_check(
                proposed_trade, risk_check, current_positions
            )
            
            return risk_check
            
        except Exception as e:
            self.log.error(f"Error checking risk limits: {e}")
            return {
                "status": "error",
                "allowed": False,
                "violations": [f"Risk check failed: {str(e)}"],
                "warnings": [],
                "adjusted_position_size": 0,
                "risk_metrics": {}
            }
    
    def calculate_max_drawdown(self, equity_curve):
        """
        Calculate the maximum drawdown from an equity curve.
        
        @param {list} equity_curve - List of equity values over time
        @returns {dict} Dictionary containing max drawdown statistics
        """
        try:
            if not equity_curve or len(equity_curve) < 2:
                return {
                    "status": "error",
                    "message": "Insufficient equity curve data",
                    "max_drawdown": 0.0,
                    "max_drawdown_percentage": 0.0,
                    "drawdown_duration": 0
                }
            
            # Calculate peak and drawdown
            peak = equity_curve[0]
            max_drawdown = 0.0
            max_drawdown_percentage = 0.0
            current_drawdown_duration = 0
            max_drawdown_duration = 0
            
            for equity in equity_curve[1:]:
                if equity > peak:
                    peak = equity
                    current_drawdown_duration = 0
                else:
                    drawdown = peak - equity
                    drawdown_percentage = (drawdown / peak) * 100
                    
                    if drawdown > max_drawdown:
                        max_drawdown = drawdown
                        max_drawdown_percentage = drawdown_percentage
                    
                    current_drawdown_duration += 1
                    if current_drawdown_duration > max_drawdown_duration:
                        max_drawdown_duration = current_drawdown_duration
            
            # Check if drawdown exceeds emergency shutdown threshold
            if max_drawdown_percentage > 0:
                emergency_threshold = self.configurable_thresholds.get_threshold_value(
                    ThresholdType.MAX_DRAWDOWN
                )
                if emergency_threshold and max_drawdown_percentage >= emergency_threshold:
                    self._trigger_emergency_shutdown_if_needed(
                        "MAX_DRAWDOWN", max_drawdown_percentage
                    )
            
            return {
                "status": "success",
                "max_drawdown": max_drawdown,
                "max_drawdown_percentage": max_drawdown_percentage,
                "drawdown_duration": max_drawdown_duration,
                "peak_equity": peak,
                "current_equity": equity_curve[-1]
            }
            
        except Exception as e:
            self.log.error(f"Error calculating max drawdown: {e}")
            return {
                "status": "error",
                "message": str(e),
                "max_drawdown": 0.0,
                "max_drawdown_percentage": 0.0,
                "drawdown_duration": 0
            }
    
    def assess_trade_risk(self, trade_data, market_data):
        """
        Assess the risk level of a potential trade.
        
        @param {dict} trade_data - Dictionary containing trade parameters
        @param {dict} market_data - Dictionary containing current market conditions
        @returns {dict} Dictionary with risk assessment results
        """
        try:
            risk_assessment = {
                "status": "success",
                "risk_level": "low",
                "risk_score": 0.0,
                "factors": [],
                "recommendations": []
            }
            
            # Calculate base risk score
            risk_score = 0.0
            
            # Market volatility factor
            if "volatility" in market_data:
                volatility = market_data["volatility"]
                if volatility > 0.05:  # 5% volatility threshold
                    risk_score += min(volatility * 10, 30)  # Max 30 points
                    risk_assessment["factors"].append({
                        "factor": "high_volatility",
                        "impact": "high",
                        "description": f"High market volatility: {volatility:.2%}"
                    })
            
            # Position size factor
            if "position_size" in trade_data:
                position_size = trade_data["position_size"]
                account_size = market_data.get("account_size", 1.0)
                position_ratio = position_size / account_size
                
                if position_ratio > 0.1:  # 10% position size threshold
                    risk_score += min(position_ratio * 20, 25)  # Max 25 points
                    risk_assessment["factors"].append({
                        "factor": "large_position",
                        "impact": "medium",
                        "description": f"Large position size: {position_ratio:.1%} of account"
                    })
            
            # Stop distance factor
            if "entry_price" in trade_data and "stop_loss_price" in trade_data:
                entry_price = trade_data["entry_price"]
                stop_loss_price = trade_data["stop_loss_price"]
                stop_distance = abs(entry_price - stop_loss_price) / entry_price
                
                if stop_distance < 0.02:  # 2% stop distance threshold
                    risk_score += 15  # Add 15 points for tight stops
                    risk_assessment["factors"].append({
                        "factor": "tight_stop",
                        "impact": "medium",
                        "description": f"Tight stop distance: {stop_distance:.2%}"
                    })
            
            # Daily loss factor
            daily_loss_check = self.daily_loss_manager.get_daily_loss_summary(self.database.db_session())
            if daily_loss_check.get("status") == "success":
                daily_loss = daily_loss_check.get("data", {}).get("daily_loss_percentage", 0)
                if daily_loss > 0:
                    risk_score += min(daily_loss * 2, 20)  # Max 20 points
                    risk_assessment["factors"].append({
                        "factor": "daily_loss",
                        "impact": "medium",
                        "description": f"Current daily loss: {daily_loss:.2f}%"
                    })
            
            # Determine risk level
            if risk_score >= 70:
                risk_assessment["risk_level"] = "critical"
                risk_assessment["recommendations"].append("Consider avoiding this trade")
                risk_assessment["recommendations"].append("Review risk management settings")
            elif risk_score >= 40:
                risk_assessment["risk_level"] = "high"
                risk_assessment["recommendations"].append("Reduce position size")
                risk_assessment["recommendations"].append("Consider tighter stop loss")
            elif risk_score >= 20:
                risk_assessment["risk_level"] = "medium"
                risk_assessment["recommendations"].append("Monitor trade closely")
            else:
                risk_assessment["risk_level"] = "low"
                risk_assessment["recommendations"].append("Trade within normal parameters")
            
            risk_assessment["risk_score"] = risk_score
            
            # Log risk assessment
            self.risk_event_logger.log_risk_assessment(
                trade_data, market_data, risk_assessment
            )
            
            return risk_assessment
            
        except Exception as e:
            self.log.error(f"Error assessing trade risk: {e}")
            return {
                "status": "error",
                "message": str(e),
                "risk_level": "unknown",
                "risk_score": 0.0,
                "factors": [],
                "recommendations": []
            }
    
    def should_stop_trading(self, account_performance, market_conditions):
        """
        Determine if trading should be stopped based on risk parameters.
        
        @param {dict} account_performance - Dictionary with account performance metrics
        @param {dict} market_conditions - Dictionary with current market conditions
        @returns {bool} True if trading should be stopped, False otherwise
        """
        try:
            # Check daily loss limits
            if not self.daily_loss_manager.is_trading_allowed(self.database.db_session()):
                self.log.info("Trading stopped: Daily loss limit exceeded")
                return True
            
            # Check configurable thresholds
            threshold_check = self.configurable_thresholds.check_all_thresholds(
                account_performance, market_conditions
            )
            if threshold_check["should_stop"]:
                self.log.info(f"Trading stopped: {threshold_check['reason']}")
                return True
            
            # Check emergency shutdown conditions
            if self.emergency_shutdown_manager.is_shutdown_active():
                self.log.info("Trading stopped: Emergency shutdown active")
                return True
            
            # Check for extreme market conditions
            if "market_stress" in market_conditions and market_conditions["market_stress"] > 0.8:
                self.log.warning("High market stress detected, considering trading halt")
                # Create risk event for market stress
                self._create_market_stress_event(market_conditions["market_stress"])
                return True
            
            return False
            
        except Exception as e:
            self.log.error(f"Error determining if trading should stop: {e}")
            return True  # Default to stopping trading on error
    
    def get_risk_metrics(self, trading_history):
        """
        Calculate comprehensive risk metrics from trading history.
        
        @param {list} trading_history - List of completed trades
        @returns {dict} Dictionary with various risk metrics
        """
        try:
            if not trading_history:
                return {
                    "status": "error",
                    "message": "No trading history available",
                    "metrics": {}
                }
            
            # Calculate basic metrics
            total_trades = len(trading_history)
            winning_trades = sum(1 for trade in trading_history if trade.get("pnl", 0) > 0)
            losing_trades = total_trades - winning_trades
            
            win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
            total_pnl = sum(trade.get("pnl", 0) for trade in trading_history)
            avg_trade_pnl = total_pnl / total_trades if total_trades > 0 else 0
            
            # Calculate risk metrics
            largest_win = max((trade.get("pnl", 0) for trade in trading_history), default=0)
            largest_loss = min((trade.get("pnl", 0) for trade in trading_history), default=0)
            
            # Calculate profit factor
            gross_profit = sum(trade.get("pnl", 0) for trade in trading_history if trade.get("pnl", 0) > 0)
            gross_loss = abs(sum(trade.get("pnl", 0) for trade in trading_history if trade.get("pnl", 0) < 0))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            
            # Calculate Sharpe ratio (simplified)
            if total_trades > 1:
                trade_pnls = [trade.get("pnl", 0) for trade in trading_history]
                avg_return = sum(trade_pnls) / len(trade_pnls)
                variance = sum((x - avg_return) ** 2 for x in trade_pnls) / len(trade_pnls)
                sharpe_ratio = avg_return / (variance ** 0.5) if variance > 0 else 0
            else:
                sharpe_ratio = 0
            
            # Calculate maximum consecutive losses
            max_consecutive_losses = 0
            current_consecutive_losses = 0
            
            for trade in trading_history:
                if trade.get("pnl", 0) < 0:
                    current_consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, current_consecutive_losses)
                else:
                    current_consecutive_losses = 0
            
            # Compile risk metrics
            risk_metrics = {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "avg_trade_pnl": avg_trade_pnl,
                "largest_win": largest_win,
                "largest_loss": largest_loss,
                "profit_factor": profit_factor,
                "sharpe_ratio": sharpe_ratio,
                "max_consecutive_losses": max_consecutive_losses,
                "risk_score": self._calculate_overall_risk_score(trading_history)
            }
            
            # Log risk metrics calculation
            self.risk_event_logger.log_risk_metrics(trading_history, risk_metrics)
            
            return {
                "status": "success",
                "metrics": risk_metrics,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.log.error(f"Error calculating risk metrics: {e}")
            return {
                "status": "error",
                "message": str(e),
                "metrics": {}
            }
    
    def is_trading_allowed(self):
        """
        Check if trading is currently allowed based on all risk management rules.
        
        @returns {bool} True if trading allowed, False otherwise
        """
        try:
            # Check daily loss manager
            if not self.daily_loss_manager.is_trading_allowed(self.database.db_session()):
                return False
            
            # Check emergency shutdown manager
            if self.emergency_shutdown_manager.is_shutdown_active():
                return False
            
            # Check configurable thresholds
            threshold_check = self.configurable_thresholds.check_all_thresholds({}, {})
            if threshold_check["should_stop"]:
                return False
            
            return True
            
        except Exception as e:
            self.log.error(f"Error checking trading permission: {e}")
            return False
    
    def get_risk_status(self):
        """
        Get comprehensive risk status from all components.
        
        @returns {dict} Dictionary with risk status from all components
        """
        try:
            risk_status = {
                "status": "success",
                "overall_status": "active",
                "components": {},
                "alerts": [],
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Get daily loss status
            daily_loss_status = self.daily_loss_manager.get_daily_loss_summary(self.database.db_session())
            risk_status["components"]["daily_loss"] = daily_loss_status
            
            # Get emergency shutdown status
            shutdown_status = self.emergency_shutdown_manager.get_shutdown_status()
            risk_status["components"]["emergency_shutdown"] = shutdown_status
            
            # Get manual confirmation status
            confirmation_status = self.manual_confirmation_manager.get_pending_approvals()
            risk_status["components"]["manual_confirmation"] = confirmation_status
            
            # Get threshold status
            threshold_status = self.configurable_thresholds.get_all_thresholds()
            risk_status["components"]["thresholds"] = threshold_status
            
            # Get recent risk events
            recent_events = self.risk_event_logger.get_recent_events(limit=10)
            risk_status["components"]["recent_events"] = recent_events
            
            # Determine overall status
            if not self.is_trading_allowed():
                risk_status["overall_status"] = "halted"
                risk_status["alerts"].append("Trading is currently halted")
            
            # Check for high-priority alerts
            if shutdown_status.get("is_shutdown_active", False):
                risk_status["alerts"].append("Emergency shutdown is active")
            
            if daily_loss_status.get("status") == "success":
                daily_loss_data = daily_loss_status.get("data", {})
                if daily_loss_data.get("is_loss_threshold_exceeded", False):
                    risk_status["alerts"].append(f"Daily loss threshold exceeded: {daily_loss_data.get('daily_loss_percentage', 0):.2f}%")
            
            return risk_status
            
        except Exception as e:
            self.log.error(f"Error getting risk status: {e}")
            return {
                "status": "error",
                "message": str(e),
                "overall_status": "unknown",
                "components": {},
                "alerts": [],
                "last_updated": datetime.utcnow().isoformat()
            }
    
    def emergency_shutdown(self, reason: str = "manual", priority: str = "high", description: str = None):
        """
        Trigger emergency shutdown.
        
        @param {str} reason - Shutdown reason
        @param {str} priority - Shutdown priority
        @param {str} description - Shutdown description
        @returns {dict} Shutdown result
        """
        try:
            shutdown_reason = ShutdownReason(reason)
            shutdown_priority = ShutdownPriority(priority)
            
            result = self.emergency_shutdown_manager.trigger_shutdown(
                self.database.db_session(),
                shutdown_reason,
                shutdown_priority,
                description or f"Emergency shutdown triggered: {reason}"
            )
            
            # Log shutdown event
            self.risk_event_logger.log_shutdown_event(result)
            
            return result
            
        except Exception as e:
            self.log.error(f"Error triggering emergency shutdown: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def attempt_recovery(self, recovery_reason: str = "manual", description: str = None):
        """
        Attempt recovery from emergency shutdown.
        
        @param {str} recovery_reason - Recovery reason
        @param {str} description - Recovery description
        @returns {dict} Recovery result
        """
        try:
            result = self.emergency_shutdown_manager.attempt_recovery(
                self.database.db_session(),
                recovery_reason,
                description or f"Recovery attempt: {recovery_reason}"
            )
            
            # Log recovery event
            self.risk_event_logger.log_recovery_event(result)
            
            return result
            
        except Exception as e:
            self.log.error(f"Error attempting recovery: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def complete_recovery(self, completed_by: str = "system", completion_metadata: dict = None):
        """
        Complete recovery from emergency shutdown.
        
        @param {str} completed_by - Who completed the recovery
        @param {dict} completion_metadata - Additional metadata
        @returns {dict} Completion result
        """
        try:
            metadata_json = json.dumps(completion_metadata) if completion_metadata else None
            
            result = self.emergency_shutdown_manager.complete_recovery(
                self.database.db_session(),
                completed_by,
                metadata_json
            )
            
            # Log recovery completion
            self.risk_event_logger.log_recovery_completion(result, completed_by)
            
            return result
            
        except Exception as e:
            self.log.error(f"Error completing recovery: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def request_manual_confirmation(self, trade_data: dict, request_type: str = "trading_resume"):
        """
        Request manual confirmation for trading operations.
        
        @param {dict} trade_data - Trade data for confirmation
        @param {str} request_type - Type of confirmation request
        @returns {dict} Confirmation request result
        """
        try:
            result = self.manual_confirmation_manager.create_approval_request(
                self.database.db_session(),
                request_type,
                trade_data
            )
            
            # Log confirmation request
            self.risk_event_logger.log_confirmation_request(result, trade_data)
            
            return result
            
        except Exception as e:
            self.log.error(f"Error requesting manual confirmation: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def approve_confirmation_request(self, request_id: str, approved_by: str = "system"):
        """
        Approve a manual confirmation request.
        
        @param {str} request_id - Request ID to approve
        @param {str} approved_by - Who approved the request
        @returns {dict} Approval result
        """
        try:
            result = self.manual_confirmation_manager.approve_request(
                self.database.db_session(),
                request_id,
                approved_by
            )
            
            # Log approval
            self.risk_event_logger.log_approval_event(result, approved_by)
            
            return result
            
        except Exception as e:
            self.log.error(f"Error approving confirmation request: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def update_thresholds(self, threshold_updates: dict):
        """
        Update configurable loss thresholds.
        
        @param {dict} threshold_updates - Dictionary of threshold updates
        @returns {dict} Update result
        """
        try:
            result = self.configurable_thresholds.update_thresholds(threshold_updates)
            
            # Log threshold update
            self.risk_event_logger.log_threshold_update(threshold_updates, result)
            
            return result
            
        except Exception as e:
            self.log.error(f"Error updating thresholds: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def get_threshold_history(self, threshold_type: str = None, days: int = 7):
        """
        Get threshold change history.
        
        @param {str} threshold_type - Optional threshold type filter
        @param {int} days - Number of days to look back
        @returns {dict} History result
        """
        try:
            result = self.configurable_thresholds.get_threshold_history(threshold_type, days)
            
            return result
            
        except Exception as e:
            self.log.error(f"Error getting threshold history: {e}")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _apply_position_size_constraints(self, position_size, account_balance):
        """
        Apply position size constraints from integrated components.
        
        @param {float} position_size - Calculated position size
        @param {float} account_balance - Account balance
        @returns {float} Adjusted position size
        """
        try:
            # Apply daily loss constraints
            daily_loss_tracking = self.daily_loss_manager.get_daily_loss_summary(self.database.db_session())
            if daily_loss_tracking.get("status") == "success":
                daily_loss_data = daily_loss_tracking.get("data", {})
                if daily_loss_data.get("is_loss_threshold_exceeded", False):
                    # Reduce position size if daily loss threshold exceeded
                    reduction_factor = 0.5  # Reduce to 50% of calculated size
                    position_size *= reduction_factor
            
            # Apply configurable threshold constraints
            threshold_check = self.configurable_thresholds.check_position_size_constraints(
                position_size, account_balance
            )
            if threshold_check["adjusted_size"] is not None:
                position_size = threshold_check["adjusted_size"]
            
            # Ensure position size is not negative
            return max(0, position_size)
            
        except Exception as e:
            self.log.error(f"Error applying position size constraints: {e}")
            return position_size
    
    def _check_position_size_limits(self, proposed_trade, current_positions):
        """
        Check position size limits.
        
        @param {dict} proposed_trade - Proposed trade details
        @param {dict} current_positions - Current open positions
        @returns {dict} Position size check result
        """
        try:
            result = {
                "violations": [],
                "warnings": [],
                "severity": "low"
            }
            
            position_size = proposed_trade.get("quantity", 0)
            account_balance = proposed_trade.get("account_balance", 1.0)
            
            # Check maximum position size
            max_position_size = self.configurable_thresholds.get_threshold_value("position_size")
            if max_position_size and position_size > account_balance * max_position_size:
                result["violations"].append(f"Position size exceeds maximum limit of {max_position_size:.1%}")
                result["severity"] = "critical"
            
            # Check total position exposure
            total_exposure = sum(pos.get("size", 0) for pos in current_positions.values())
            total_exposure += position_size
            
            max_exposure = self.configurable_thresholds.get_threshold_value("max_exposure")
            if max_exposure and total_exposure > account_balance * max_exposure:
                result["violations"].append(f"Total position exposure exceeds maximum limit of {max_exposure:.1%}")
                result["severity"] = "critical"
            
            return result
            
        except Exception as e:
            self.log.error(f"Error checking position size limits: {e}")
            return {
                "violations": [f"Position size check failed: {str(e)}"],
                "warnings": [],
                "severity": "critical"
            }
    
    def _calculate_adjusted_position_size(self, proposed_trade, current_positions, violations):
        """
        Calculate adjusted position size based on violations.
        
        @param {dict} proposed_trade - Proposed trade details
        @param {dict} current_positions - Current open positions
        @param {list} violations - List of violations
        @returns {float} Adjusted position size
        """
        try:
            original_size = proposed_trade.get("quantity", 0)
            adjusted_size = original_size
            
            # Apply reduction based on violation severity
            critical_violations = [v for v in violations if "critical" in v.lower()]
            if critical_violations:
                adjusted_size *= 0.1  # Reduce to 10% for critical violations
            else:
                # Check for medium violations
                medium_violations = [v for v in violations if "medium" in v.lower() or "high" in v.lower()]
                if medium_violations:
                    adjusted_size *= 0.5  # Reduce to 50% for medium violations
            
            return max(0, adjusted_size)
            
        except Exception as e:
            self.log.error(f"Error calculating adjusted position size: {e}")
            return proposed_trade.get("quantity", 0)
    
    def _create_confirmation_request(self, trade_data):
        """
        Create a confirmation request for manual approval.
        
        @param {dict} trade_data - Trade data
        @returns {str} Request ID
        """
        try:
            result = self.manual_confirmation_manager.create_approval_request(
                self.database.db_session(),
                "trading_operation",
                trade_data
            )
            
            return result.get("request_id")
            
        except Exception as e:
            self.log.error(f"Error creating confirmation request: {e}")
            return None
    
    def _trigger_emergency_shutdown_if_needed(self, reason, value):
        """
        Trigger emergency shutdown if conditions are met.
        
        @param {str} reason - Shutdown reason
        @param {float} value - Trigger value
        @returns {bool} True if shutdown triggered, False otherwise
        """
        try:
            if self.auto_shutdown_on_threshold:
                result = self.emergency_shutdown_manager.trigger_shutdown(
                    self.database.db_session(),
                    ShutdownReason(reason),
                    ShutdownPriority.HIGH,
                    f"Auto-triggered shutdown: {reason} threshold exceeded ({value})"
                )
                return result.get("shutdown_triggered", False)
            
            return False
            
        except Exception as e:
            self.log.error(f"Error triggering emergency shutdown: {e}")
            return False
    
    def _create_market_stress_event(self, stress_level):
        """
        Create a market stress risk event.
        
        @param {float} stress_level - Market stress level (0-1)
        """
        try:
            with self.database.db_session() as session:
                # Find a default pair for the event
                pair = session.query(Pair).first()
                if not pair:
                    pair = Pair(Coin("USDT", True), Coin("BTC", True))
                    session.add(pair)
                
                # Create risk event
                risk_event = RiskEvent(
                    pair=pair,
                    coin=pair.from_coin,
                    event_type=RiskEventType.CUSTOM,
                    severity=RiskEventSeverity.HIGH if stress_level > 0.8 else RiskEventSeverity.MEDIUM,
                    trigger_value=stress_level,
                    threshold_value=0.8,
                    current_value=stress_level,
                    description=f"Market stress detected: {stress_level:.2%}",
                    created_by="integrated_risk_manager"
                )
                
                session.add(risk_event)
                self.log.info(f"Created market stress event: {stress_level:.2%}")
                
        except Exception as e:
            self.log.error(f"Error creating market stress event: {e}")
    
    def _calculate_overall_risk_score(self, trading_history):
        """
        Calculate overall risk score from trading history.
        
        @param {list} trading_history - Trading history
        @returns {float} Risk score (0-100)
        """
        try:
            if not trading_history:
                return 0.0
            
            # Calculate various risk factors
            total_trades = len(trading_history)
            if total_trades == 0:
                return 0.0
            
            # Win rate factor (0-30 points)
            winning_trades = sum(1 for trade in trading_history if trade.get("pnl", 0) > 0)
            win_rate = (winning_trades / total_trades) * 100
            win_rate_score = max(0, 30 - (100 - win_rate) * 0.3)
            
            # Loss factor (0-30 points)
            losing_trades = total_trades - winning_trades
            loss_factor_score = min(30, losing_trades * 2)
            
            # Average loss factor (0-20 points)
            avg_loss = sum(abs(trade.get("pnl", 0)) for trade in trading_history if trade.get("pnl", 0) < 0) / losing_trades if losing_trades > 0 else 0
            avg_loss_score = min(20, avg_loss / 1000)  # Assuming 1000 is a significant loss amount
            
            # Consecutive losses factor (0-20 points)
            max_consecutive_losses = 0
            current_consecutive_losses = 0
            
            for trade in trading_history:
                if trade.get("pnl", 0) < 0:
                    current_consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, current_consecutive_losses)
                else:
                    current_consecutive_losses = 0
            
            consecutive_losses_score = min(20, max_consecutive_losses * 2)
            
            # Calculate overall risk score
            risk_score = win_rate_score + loss_factor_score + avg_loss_score + consecutive_losses_score
            
            return min(100, max(0, risk_score))
            
        except Exception as e:
            self.log.error(f"Error calculating risk score: {e}")
            return 0.0