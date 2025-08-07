"""
Database models for the monitoring and alert system.

This module defines the database tables and models needed for storing
monitoring data, alerts, and related information.

Created: 2025-08-05
"""

import json
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, Float, ForeignKey, Integer, String, Text, Boolean, JSON
from sqlalchemy.orm import relationship

from ..models.base import Base
from ..models.coin import Coin
from ..models.pair import Pair


class AlertSeverity(Enum):
    """Alert severity levels for monitoring events."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertType(Enum):
    """Alert types for different monitoring scenarios."""
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    PERFORMANCE_ANOMALY = "PERFORMANCE_ANOMALY"
    TRADING_FREQUENCY_EXCEEDED = "TRADING_FREQUENCY_EXCEEDED"
    API_ERROR_THRESHOLD = "API_ERROR_THRESHOLD"
    MARKET_CONDITION_CHANGE = "MARKET_CONDITION_CHANGE"
    COIN_PERFORMANCE_EXCEPTIONAL = "COIN_PERFORMANCE_EXCEPTIONAL"


class AlertStatus(Enum):
    """Alert status tracking."""
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    SUPPRESSED = "SUPPRESSED"


class VolatilityMetric(Enum):
    """Types of volatility metrics to track."""
    STANDARD_DEVIATION = "STANDARD_DEVIATION"
    ATR = "ATR"  # Average True Range
    BOLLINGER_BANDS = "BOLLINGER_BANDS"
    KELTNER_CHANNEL = "KELTNER_CHANNEL"
    HISTORICAL_VOLATILITY = "HISTORICAL_VOLATILITY"


class PerformanceMetric(Enum):
    """Types of performance metrics to track."""
    PRICE_CHANGE = "PRICE_CHANGE"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    MARKET_CAP_CHANGE = "MARKET_CAP_CHANGE"
    LIQUIDITY_CHANGE = "LIQUIDITY_CHANGE"
    TREND_STRENGTH = "TREND_STRENGTH"


class TradingFrequencyMetric(Enum):
    """Types of trading frequency metrics to track."""
    TRADES_PER_HOUR = "TRADES_PER_HOUR"
    TRADES_PER_DAY = "TRADES_PER_DAY"
    TRADES_PER_WEEK = "TRADES_PER_WEEK"
    CONSECUTIVE_TRADES = "CONSECUTIVE_TRADES"
    HOLDING_PERIOD = "HOLDING_PERIOD"


class APIErrorType(Enum):
    """Types of API errors to track."""
    CONNECTION_ERROR = "CONNECTION_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    SERVER_ERROR = "SERVER_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"


class PortfolioMetric(Enum):
    """Types of portfolio metrics to track."""
    TOTAL_VALUE_CHANGE = "TOTAL_VALUE_CHANGE"
    ALLOCATION_CHANGE = "ALLOCATION_CHANGE"
    ROI_CHANGE = "ROI_CHANGE"
    RISK_ADJUSTED_RETURN = "RISK_ADJUSTED_RETURN"
    DRAWDOWN_CHANGE = "DRAWDOWN_CHANGE"
    VOLATILITY_CHANGE = "VOLATILITY_CHANGE"


class PortfolioChangeDirection(Enum):
    """Direction of portfolio value change."""
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"


class MonitoringAlert(Base):
    """
    Database model for storing monitoring alerts.
    """
    __tablename__ = "monitoring_alerts"

    id = Column(Integer, primary_key=True)
    
    # Alert identification
    alert_uuid = Column(String, unique=True, index=True)
    alert_type = Column(SQLAlchemyEnum(AlertType), nullable=False)
    severity = Column(SQLAlchemyEnum(AlertSeverity), nullable=False)
    status = Column(SQLAlchemyEnum(AlertStatus), default=AlertStatus.ACTIVE)
    
    # Alert content
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    
    # Associations
    coin_id = Column(String, ForeignKey("coins.symbol"), nullable=True)
    coin = relationship("Coin")
    
    pair_id = Column(Integer, ForeignKey("pairs.id"), nullable=True)
    pair = relationship("Pair")
    
    # Threshold and current values
    threshold_value = Column(Float, nullable=True)
    current_value = Column(Float, nullable=True)
    
    # Metadata and context
    metadata_json = Column(Text, nullable=True)  # JSON string with additional data
    context_json = Column(Text, nullable=True)   # JSON string with context information
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    
    # User tracking
    acknowledged_by = Column(String, nullable=True)
    resolved_by = Column(String, nullable=True)
    
    # Additional fields
    is_acknowledgement_required = Column(Boolean, default=True)
    is_resolvable = Column(Boolean, default=True)
    suppression_reason = Column(String, nullable=True)
    
    def __init__(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        description: str = None,
        coin: Coin = None,
        pair: Pair = None,
        threshold_value: float = None,
        current_value: float = None,
        metadata: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
        is_acknowledgement_required: bool = True,
        is_resolvable: bool = True,
    ):
        """
        Initialize a monitoring alert database record.
        
        @description Create a new monitoring alert database record
        @param {AlertType} alert_type - Type of alert
        @param {AlertSeverity} severity - Severity level
        @param {str} title - Alert title
        @param {str} description - Alert description
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {float} threshold_value - Threshold value that was exceeded
        @param {float} current_value - Current value that triggered the alert
        @param {Dict} metadata - Additional metadata
        @param {Dict} context - Context information
        @param {bool} is_acknowledgement_required - Whether acknowledgement is required
        @param {bool} is_resolvable - Whether alert can be resolved
        @returns {MonitoringAlert} New monitoring alert instance
        """
        self.alert_uuid = f"alert_{datetime.utcnow().timestamp()}_{id(self)}"
        self.alert_type = alert_type
        self.severity = severity
        self.title = title
        self.description = description
        self.coin = coin
        self.pair = pair
        self.threshold_value = threshold_value
        self.current_value = current_value
        self.metadata_json = json.dumps(metadata) if metadata else None
        self.context_json = json.dumps(context) if context else None
        self.is_acknowledgement_required = is_acknowledgement_required
        self.is_resolvable = is_resolvable
        
    def acknowledge(self, acknowledged_by: str = "system"):
        """
        Acknowledge the alert.
        
        @description Mark alert as acknowledged
        @param {str} acknowledged_by - User who acknowledged the alert
        @returns {void}
        """
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.utcnow()
        self.acknowledged_by = acknowledged_by
        
    def resolve(self, resolved_by: str = "system"):
        """
        Resolve the alert.
        
        @description Mark alert as resolved
        @param {str} resolved_by - User who resolved the alert
        @returns {void}
        """
        if self.is_resolvable:
            self.status = AlertStatus.RESOLVED
            self.resolved_at = datetime.utcnow()
            self.resolved_by = resolved_by
            
    def suppress(self, reason: str = "Manual suppression"):
        """
        Suppress the alert.
        
        @description Mark alert as suppressed
        @param {str} reason - Reason for suppression
        @returns {void}
        """
        self.status = AlertStatus.SUPPRESSED
        self.suppression_reason = reason
        
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get metadata as dictionary.
        
        @description Retrieve metadata from JSON string
        @returns {Dict} Metadata dictionary
        """
        return json.loads(self.metadata_json) if self.metadata_json else {}
        
    def get_context(self) -> Dict[str, Any]:
        """
        Get context as dictionary.
        
        @description Retrieve context from JSON string
        @returns {Dict} Context dictionary
        """
        return json.loads(self.context_json) if self.context_json else {}
        
    def info(self) -> Dict[str, Any]:
        """
        Get alert information as dictionary.
        
        @description Convert alert to serializable dictionary
        @returns {Dict} Alert information dictionary
        """
        return {
            'id': self.id,
            'alert_uuid': self.alert_uuid,
            'alert_type': self.alert_type.value,
            'severity': self.severity.value,
            'status': self.status.value,
            'title': self.title,
            'description': self.description,
            'coin': self.coin.info() if self.coin else None,
            'pair': self.pair.info() if self.pair else None,
            'threshold_value': self.threshold_value,
            'current_value': self.current_value,
            'metadata': self.get_metadata(),
            'context': self.get_context(),
            'created_at': self.created_at.isoformat(),
            'acknowledged_at': self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'acknowledged_by': self.acknowledged_by,
            'resolved_by': self.resolved_by,
            'is_acknowledgement_required': self.is_acknowledgement_required,
            'is_resolvable': self.is_resolvable,
            'suppression_reason': self.suppression_reason,
        }


class VolatilityData(Base):
    """
    Database model for storing volatility measurements.
    """
    __tablename__ = "volatility_data"

    id = Column(Integer, primary_key=True)
    
    # Associations
    coin_id = Column(String, ForeignKey("coins.symbol"), nullable=True)
    coin = relationship("Coin")
    
    pair_id = Column(Integer, ForeignKey("pairs.id"), nullable=True)
    pair = relationship("Pair")
    
    # Volatility metrics
    metric_type = Column(SQLAlchemyEnum(VolatilityMetric), nullable=False)
    period = Column(Integer, nullable=False)  # Period for the calculation (e.g., 24 hours)
    volatility_value = Column(Float, nullable=False)
    
    # Price context
    current_price = Column(Float, nullable=True)
    price_change_percentage = Column(Float, nullable=True)
    
    # Additional data
    metadata_json = Column(Text, nullable=True)  # JSON string with additional metrics
    
    # Timestamps
    calculated_at = Column(DateTime, default=datetime.utcnow)
    
    def __init__(
        self,
        coin: Coin = None,
        pair: Pair = None,
        metric_type: VolatilityMetric = None,
        period: int = None,
        volatility_value: float = None,
        current_price: float = None,
        price_change_percentage: float = None,
        metadata: Dict[str, Any] = None,
    ):
        """
        Initialize volatility data record.
        
        @description Create a new volatility data record
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {VolatilityMetric} metric_type - Type of volatility metric
        @param {int} period - Calculation period
        @param {float} volatility_value - Calculated volatility value
        @param {float} current_price - Current price at time of calculation
        @param {float} price_change_percentage - Price change percentage
        @param {Dict} metadata - Additional metadata
        @returns {VolatilityData} New volatility data instance
        """
        self.coin = coin
        self.pair = pair
        self.metric_type = metric_type
        self.period = period
        self.volatility_value = volatility_value
        self.current_price = current_price
        self.price_change_percentage = price_change_percentage
        self.metadata_json = json.dumps(metadata) if metadata else None
        
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get metadata as dictionary.
        
        @description Retrieve metadata from JSON string
        @returns {Dict} Metadata dictionary
        """
        return json.loads(self.metadata_json) if self.metadata_json else {}
        
    def info(self) -> Dict[str, Any]:
        """
        Get volatility data information as dictionary.
        
        @description Convert volatility data to serializable dictionary
        @returns {Dict} Volatility data information dictionary
        """
        return {
            'id': self.id,
            'coin': self.coin.info() if self.coin else None,
            'pair': self.pair.info() if self.pair else None,
            'metric_type': self.metric_type.value,
            'period': self.period,
            'volatility_value': self.volatility_value,
            'current_price': self.current_price,
            'price_change_percentage': self.price_change_percentage,
            'metadata': self.get_metadata(),
            'calculated_at': self.calculated_at.isoformat(),
        }


class PerformanceData(Base):
    """
    Database model for storing performance measurements.
    """
    __tablename__ = "performance_data"

    id = Column(Integer, primary_key=True)
    
    # Associations
    coin_id = Column(String, ForeignKey("coins.symbol"), nullable=True)
    coin = relationship("Coin")
    
    pair_id = Column(Integer, ForeignKey("pairs.id"), nullable=True)
    pair = relationship("Pair")
    
    # Performance metrics
    metric_type = Column(SQLAlchemyEnum(PerformanceMetric), nullable=False)
    period = Column(Integer, nullable=False)  # Period for the calculation
    performance_value = Column(Float, nullable=False)
    
    # Baseline for comparison
    baseline_value = Column(Float, nullable=True)
    deviation_percentage = Column(Float, nullable=True)
    
    # Additional data
    metadata_json = Column(Text, nullable=True)  # JSON string with additional metrics
    
    # Timestamps
    calculated_at = Column(DateTime, default=datetime.utcnow)
    
    def __init__(
        self,
        coin: Coin = None,
        pair: Pair = None,
        metric_type: PerformanceMetric = None,
        period: int = None,
        performance_value: float = None,
        baseline_value: float = None,
        deviation_percentage: float = None,
        metadata: Dict[str, Any] = None,
    ):
        """
        Initialize performance data record.
        
        @description Create a new performance data record
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {PerformanceMetric} metric_type - Type of performance metric
        @param {int} period - Calculation period
        @param {float} performance_value - Calculated performance value
        @param {float} baseline_value - Baseline value for comparison
        @param {float} deviation_percentage - Deviation from baseline percentage
        @param {Dict} metadata - Additional metadata
        @returns {PerformanceData} New performance data instance
        """
        self.coin = coin
        self.pair = pair
        self.metric_type = metric_type
        self.period = period
        self.performance_value = performance_value
        self.baseline_value = baseline_value
        self.deviation_percentage = deviation_percentage
        self.metadata_json = json.dumps(metadata) if metadata else None
        
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get metadata as dictionary.
        
        @description Retrieve metadata from JSON string
        @returns {Dict} Metadata dictionary
        """
        return json.loads(self.metadata_json) if self.metadata_json else {}
        
    def info(self) -> Dict[str, Any]:
        """
        Get performance data information as dictionary.
        
        @description Convert performance data to serializable dictionary
        @returns {Dict} Performance data information dictionary
        """
        return {
            'id': self.id,
            'coin': self.coin.info() if self.coin else None,
            'pair': self.pair.info() if self.pair else None,
            'metric_type': self.metric_type.value,
            'period': self.period,
            'performance_value': self.performance_value,
            'baseline_value': self.baseline_value,
            'deviation_percentage': self.deviation_percentage,
            'metadata': self.get_metadata(),
            'calculated_at': self.calculated_at.isoformat(),
        }


class TradingFrequencyData(Base):
    """
    Database model for storing trading frequency measurements.
    """
    __tablename__ = "trading_frequency_data"

    id = Column(Integer, primary_key=True)
    
    # Associations
    coin_id = Column(String, ForeignKey("coins.symbol"), nullable=True)
    coin = relationship("Coin")
    
    pair_id = Column(Integer, ForeignKey("pairs.id"), nullable=True)
    pair = relationship("Pair")
    
    # Frequency metrics
    metric_type = Column(SQLAlchemyEnum(TradingFrequencyMetric), nullable=False)
    period = Column(Integer, nullable=False)  # Period for the calculation
    frequency_value = Column(Float, nullable=False)
    
    # Threshold information
    threshold_value = Column(Float, nullable=True)
    is_threshold_exceeded = Column(Boolean, default=False)
    
    # Additional data
    metadata_json = Column(Text, nullable=True)  # JSON string with additional metrics
    
    # Timestamps
    calculated_at = Column(DateTime, default=datetime.utcnow)
    
    def __init__(
        self,
        coin: Coin = None,
        pair: Pair = None,
        metric_type: TradingFrequencyMetric = None,
        period: int = None,
        frequency_value: float = None,
        threshold_value: float = None,
        metadata: Dict[str, Any] = None,
    ):
        """
        Initialize trading frequency data record.
        
        @description Create a new trading frequency data record
        @param {Coin} coin - Associated coin
        @param {Pair} pair - Associated trading pair
        @param {TradingFrequencyMetric} metric_type - Type of frequency metric
        @param {int} period - Calculation period
        @param {float} frequency_value - Calculated frequency value
        @param {float} threshold_value - Threshold value for comparison
        @param {Dict} metadata - Additional metadata
        @returns {TradingFrequencyData} New trading frequency data instance
        """
        self.coin = coin
        self.pair = pair
        self.metric_type = metric_type
        self.period = period
        self.frequency_value = frequency_value
        self.threshold_value = threshold_value
        self.is_threshold_exceeded = frequency_value > threshold_value if threshold_value else False
        self.metadata_json = json.dumps(metadata) if metadata else None
        
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get metadata as dictionary.
        
        @description Retrieve metadata from JSON string
        @returns {Dict} Metadata dictionary
        """
        return json.loads(self.metadata_json) if self.metadata_json else {}
        
    def info(self) -> Dict[str, Any]:
        """
        Get trading frequency data information as dictionary.
        
        @description Convert trading frequency data to serializable dictionary
        @returns {Dict} Trading frequency data information dictionary
        """
        return {
            'id': self.id,
            'coin': self.coin.info() if self.coin else None,
            'pair': self.pair.info() if self.pair else None,
            'metric_type': self.metric_type.value,
            'period': self.period,
            'frequency_value': self.frequency_value,
            'threshold_value': self.threshold_value,
            'is_threshold_exceeded': self.is_threshold_exceeded,
            'metadata': self.get_metadata(),
            'calculated_at': self.calculated_at.isoformat(),
        }


class APIErrorData(Base):
    """
    Database model for storing API error tracking data.
    """
    __tablename__ = "api_error_data"

    id = Column(Integer, primary_key=True)
    
    # Error information
    error_type = Column(SQLAlchemyEnum(APIErrorType), nullable=False)
    error_message = Column(Text, nullable=True)
    error_code = Column(String, nullable=True)
    
    # Request context
    endpoint = Column(String, nullable=True)
    method = Column(String, nullable=True)
    request_params = Column(Text, nullable=True)  # JSON string
    
    # Error context
    retry_count = Column(Integer, default=0)
    is_retriable = Column(Boolean, default=True)
    error_duration = Column(Float, nullable=True)  # Duration in seconds
    
    # Additional data
    metadata_json = Column(Text, nullable=True)  # JSON string with additional data
    
    # Timestamps
    occurred_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


class PortfolioData(Base):
    """
    Database model for storing portfolio change monitoring data.
    """
    __tablename__ = "portfolio_data"

    id = Column(Integer, primary_key=True)
    
    # Alert identification
    alert_uuid = Column(String, ForeignKey("monitoring_alerts.alert_uuid"), nullable=True)
    
    # Portfolio metrics
    metric_type = Column(SQLAlchemyEnum(PortfolioMetric), nullable=False)
    period_hours = Column(Integer, nullable=False)
    
    # Change tracking
    current_value = Column(Float, nullable=True)
    historical_value = Column(Float, nullable=True)
    percentage_change = Column(Float, nullable=True)
    direction = Column(String, nullable=True)  # INCREASE or DECREASE
    
    # Severity information
    severity = Column(SQLAlchemyEnum(AlertSeverity), nullable=True)
    
    # Additional data
    metadata_json = Column(Text, nullable=True)  # JSON string with additional metrics
    context_json = Column(Text, nullable=True)   # JSON string with context information
    
    # Timestamps
    calculated_at = Column(DateTime, default=datetime.utcnow)
    
    def __init__(
        self,
        error_type: APIErrorType = None,
        error_message: str = None,
        error_code: str = None,
        endpoint: str = None,
        method: str = None,
        request_params: Dict[str, Any] = None,
        retry_count: int = 0,
        is_retriable: bool = True,
        error_duration: float = None,
        metadata: Dict[str, Any] = None,
    ):
        """
        Initialize API error data record.
        
        @description Create a new API error data record
        @param {APIErrorType} error_type - Type of API error
        @param {str} error_message - Error message
        @param {str} error_code - Error code
        @param {str} endpoint - API endpoint that failed
        @param {str} method - HTTP method used
        @param {Dict} request_params - Request parameters
        @param {int} retry_count - Number of retry attempts
        @param {bool} is_retriable - Whether error is retriable
        @param {float} error_duration - Duration of the error in seconds
        @param {Dict} metadata - Additional metadata
        @returns {APIErrorData} New API error data instance
        """
        self.error_type = error_type
        self.error_message = error_message
        self.error_code = error_code
        self.endpoint = endpoint
        self.method = method
        self.request_params = json.dumps(request_params) if request_params else None
        self.retry_count = retry_count
        self.is_retriable = is_retriable
        self.error_duration = error_duration
        self.metadata_json = json.dumps(metadata) if metadata else None
        
    def get_request_params(self) -> Dict[str, Any]:
        """
        Get request parameters as dictionary.
        
        @description Retrieve request parameters from JSON string
        @returns {Dict} Request parameters dictionary
        """
        return json.loads(self.request_params) if self.request_params else {}
        
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get metadata as dictionary.
        
        @description Retrieve metadata from JSON string
        @returns {Dict} Metadata dictionary
        """
        return json.loads(self.metadata_json) if self.metadata_json else {}
        
    def resolve(self):
        """
        Mark error as resolved.
        
        @description Mark API error as resolved
        @returns {void}
        """
        self.resolved_at = datetime.utcnow()
        
    def info(self) -> Dict[str, Any]:
        """
        Get API error data information as dictionary.
        
        @description Convert API error data to serializable dictionary
        @returns {Dict} API error data information dictionary
        """
        return {
            'id': self.id,
            'error_type': self.error_type.value,
            'error_message': self.error_message,
            'error_code': self.error_code,
            'endpoint': self.endpoint,
            'method': self.method,
            'request_params': self.get_request_params(),
            'retry_count': self.retry_count,
            'is_retriable': self.is_retriable,
            'error_duration': self.error_duration,
            'metadata': self.get_metadata(),
            'occurred_at': self.occurred_at.isoformat(),
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
        }