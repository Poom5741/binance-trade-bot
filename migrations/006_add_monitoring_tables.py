"""
Migration script to add monitoring and alert system tables.

This migration adds the following tables:
- monitoring_alerts: for storing monitoring alerts and their status
- volatility_data: for storing volatility measurements and metrics
- performance_data: for storing performance measurements and metrics
- trading_frequency_data: for storing trading frequency measurements
- api_error_data: for storing API error tracking data

Created: 2025-08-05
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, Float, ForeignKey, Integer, String, Text, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from binance_trade_bot.models.base import Base
from binance_trade_bot.models.coin import Coin
from binance_trade_bot.models.pair import Pair


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


def upgrade():
    """
    Upgrade the database schema by creating the new monitoring tables.
    """
    try:
        # Create all monitoring tables
        MonitoringAlert.__table__.create(bind=Base.metadata.bind)
        print("MonitoringAlert table created successfully")
        
        VolatilityData.__table__.create(bind=Base.metadata.bind)
        print("VolatilityData table created successfully")
        
        PerformanceData.__table__.create(bind=Base.metadata.bind)
        print("PerformanceData table created successfully")
        
        TradingFrequencyData.__table__.create(bind=Base.metadata.bind)
        print("TradingFrequencyData table created successfully")
        
        APIErrorData.__table__.create(bind=Base.metadata.bind)
        print("APIErrorData table created successfully")
        
        # Create indexes for better query performance
        _create_indexes()
        
        print("Migration completed successfully: Monitoring tables created")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        raise


def downgrade():
    """
    Downgrade the database schema by dropping the new monitoring tables.
    """
    try:
        # Drop tables in reverse order of creation to handle foreign key dependencies
        APIErrorData.__table__.drop(bind=Base.metadata.bind)
        print("APIErrorData table dropped successfully")
        
        TradingFrequencyData.__table__.drop(bind=Base.metadata.bind)
        print("TradingFrequencyData table dropped successfully")
        
        PerformanceData.__table__.drop(bind=Base.metadata.bind)
        print("PerformanceData table dropped successfully")
        
        VolatilityData.__table__.drop(bind=Base.metadata.bind)
        print("VolatilityData table dropped successfully")
        
        MonitoringAlert.__table__.drop(bind=Base.metadata.bind)
        print("MonitoringAlert table dropped successfully")
        
        print("Migration rolled back successfully: Monitoring tables dropped")
        
    except Exception as e:
        print(f"Error during migration rollback: {e}")
        raise


def _create_indexes():
    """
    Create additional indexes for better query performance.
    """
    try:
        # Index for monitoring alerts by status and created_at
        sql = text("""
            CREATE INDEX IF NOT EXISTS idx_monitoring_alerts_status_created 
            ON monitoring_alerts (status, created_at)
        """)
        Base.metadata.bind.execute(sql)
        print("Created index: idx_monitoring_alerts_status_created")
        
        # Index for monitoring alerts by severity
        sql = text("""
            CREATE INDEX IF NOT EXISTS idx_monitoring_alerts_severity 
            ON monitoring_alerts (severity)
        """)
        Base.metadata.bind.execute(sql)
        print("Created index: idx_monitoring_alerts_severity")
        
        # Index for volatility data by coin_id and calculated_at
        sql = text("""
            CREATE INDEX IF NOT EXISTS idx_volatility_data_coin_calculated 
            ON volatility_data (coin_id, calculated_at)
        """)
        Base.metadata.bind.execute(sql)
        print("Created index: idx_volatility_data_coin_calculated")
        
        # Index for performance data by pair_id and calculated_at
        sql = text("""
            CREATE INDEX IF NOT EXISTS idx_performance_data_pair_calculated 
            ON performance_data (pair_id, calculated_at)
        """)
        Base.metadata.bind.execute(sql)
        print("Created index: idx_performance_data_pair_calculated")
        
        # Index for API error data by error_type and occurred_at
        sql = text("""
            CREATE INDEX IF NOT EXISTS idx_api_error_data_type_occurred 
            ON api_error_data (error_type, occurred_at)
        """)
        Base.metadata.bind.execute(sql)
        print("Created index: idx_api_error_data_type_occurred")
        
    except Exception as e:
        print(f"Error creating indexes: {e}")
        # Don't raise the exception as indexes are not critical


if __name__ == "__main__":
    # This allows the migration to be run directly
    from binance_trade_bot.database import Database
    from binance_trade_bot.config import Config
    from binance_trade_bot.logger import Logger
    
    # Initialize database connection
    logger = Logger()
    config = Config()
    database = Database(logger, config)
    
    # Run upgrade
    upgrade()