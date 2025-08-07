"""
Migration script to add risk management enhancement tables.

This migration adds the following tables:
- manual_approvals: for storing manual approval requests and decisions
- threshold_settings: for storing configurable loss threshold settings
- emergency_shutdown_state: for storing emergency shutdown state and history
- risk_event_logs: for enhanced risk event logging and tracking

Created: 2025-08-05
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, Float, ForeignKey, Integer, String, Text, JSON, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import text

from binance_trade_bot.models.base import Base
from binance_trade_bot.models.coin import Coin
from binance_trade_bot.models.pair import Pair


class ApprovalStatus(Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ApprovalLevel(Enum):
    LEVEL_1 = "LEVEL_1"
    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"
    FINAL = "FINAL"


class ThresholdType(Enum):
    DAILY_LOSS = "DAILY_LOSS"
    MAX_DRAWDOWN = "MAX_DRAWDOWN"
    POSITION_SIZE = "POSITION_SIZE"
    LIQUIDITY = "LIQUIDITY"
    VOLATILITY = "VOLATILITY"


class ThresholdStatus(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    PENDING = "PENDING"
    EXPIRED = "EXPIRED"


class EnvironmentType(Enum):
    PRODUCTION = "PRODUCTION"
    STAGING = "STAGING"
    DEVELOPMENT = "DEVELOPMENT"
    TESTING = "TESTING"


class ShutdownReason(Enum):
    PORTFOLIO_LOSS = "PORTFOLIO_LOSS"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    MARKET_CRASH = "MARKET_CRASH"
    LIQUIDITY_ISSUE = "LIQUIDITY_ISSUE"
    MANUAL_TRIGGER = "MANUAL_TRIGGER"
    REGULATORY = "REGULATORY"


class ShutdownState(Enum):
    ACTIVE = "ACTIVE"
    SHUTDOWN = "SHUTDOWN"
    RECOVERY = "RECOVERY"


class ShutdownPriority(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskEventLogType(Enum):
    RISK_EVENT = "RISK_EVENT"
    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    THRESHOLD_CHANGE = "THRESHOLD_CHANGE"
    SHUTDOWN_EVENT = "SHUTDOWN_EVENT"
    RECOVERY_EVENT = "RECOVERY_EVENT"
    SYSTEM_ALERT = "SYSTEM_ALERT"


class RiskEventLogSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ManualApproval(Base):
    __tablename__ = "manual_approvals"

    id = Column(Integer, primary_key=True)

    request_id = Column(String, unique=True, index=True)
    request_type = Column(String, nullable=False)  # e.g., "trading_resume", "threshold_change"
    request_data = Column(Text, nullable=True)  # JSON string with request details

    status = Column(SQLAlchemyEnum(ApprovalStatus), default=ApprovalStatus.PENDING)
    level = Column(SQLAlchemyEnum(ApprovalLevel), default=ApprovalLevel.LEVEL_1)
    required_approvals = Column(Integer, default=1)
    current_approvals = Column(Integer, default=0)

    requested_by = Column(String, nullable=False)
    requested_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    approvals = Column(Text, nullable=True)  # JSON string with approval details
    rejections = Column(Text, nullable=True)  # JSON string with rejection details
    final_decision = Column(String, nullable=True)
    final_decision_by = Column(String, nullable=True)
    final_decision_at = Column(DateTime, nullable=True)

    description = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)

    def __init__(
        self,
        request_id: str,
        request_type: str,
        requested_by: str,
        description: str = None,
        required_approvals: int = 1,
        level: ApprovalLevel = ApprovalLevel.LEVEL_1,
        expires_at: datetime = None,
        request_data: dict = None,
        metadata_json: dict = None,
    ):
        self.request_id = request_id
        self.request_type = request_type
        self.requested_by = requested_by
        self.description = description
        self.required_approvals = required_approvals
        self.level = level
        self.expires_at = expires_at
        self.request_data = request_data
        self.metadata_json = metadata_json


class ThresholdSetting(Base):
    __tablename__ = "threshold_settings"

    id = Column(Integer, primary_key=True)

    threshold_type = Column(SQLAlchemyEnum(ThresholdType), nullable=False)
    environment = Column(SQLAlchemyEnum(EnvironmentType), default=EnvironmentType.PRODUCTION)
    
    value = Column(Float, nullable=False)
    unit = Column(String, default="percentage")  # percentage, absolute, etc.
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    
    status = Column(SQLAlchemyEnum(ThresholdStatus), default=ThresholdStatus.ACTIVE)
    is_default = Column(Boolean, default=False)

    description = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deactivated_at = Column(DateTime, nullable=True)

    # Ensure one threshold type per environment
    __table_args__ = (
        UniqueConstraint('threshold_type', 'environment', name='uq_threshold_type_environment'),
    )

    def __init__(
        self,
        threshold_type: ThresholdType,
        value: float,
        environment: EnvironmentType = EnvironmentType.PRODUCTION,
        unit: str = "percentage",
        min_value: float = None,
        max_value: float = None,
        description: str = None,
        metadata_json: dict = None,
    ):
        self.threshold_type = threshold_type
        self.value = value
        self.environment = environment
        self.unit = unit
        self.min_value = min_value
        self.max_value = max_value
        self.description = description
        self.metadata_json = metadata_json


class EmergencyShutdownState(Base):
    __tablename__ = "emergency_shutdown_state"

    id = Column(Integer, primary_key=True)

    shutdown_id = Column(String, unique=True, index=True)
    shutdown_reason = Column(String, nullable=False)
    shutdown_priority = Column(String, nullable=False)
    
    state = Column(String, default="ACTIVE")  # ACTIVE, SHUTDOWN, RECOVERY
    is_shutdown = Column(Boolean, default=False)
    is_in_recovery = Column(Boolean, default=False)
    
    shutdown_time = Column(DateTime, nullable=True)
    recovery_start_time = Column(DateTime, nullable=True)
    recovery_complete_time = Column(DateTime, nullable=True)
    
    shutdown_event_id = Column(Integer, ForeignKey("risk_events.id"), nullable=True)
    recovery_event_id = Column(Integer, ForeignKey("risk_events.id"), nullable=True)
    
    preserved_state = Column(Text, nullable=True)  # JSON string with preserved trading state
    restored_state = Column(Text, nullable=True)  # JSON string with restored trading state
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __init__(
        self,
        shutdown_id: str,
        shutdown_reason: str,
        shutdown_priority: str,
        state: str = "ACTIVE",
    ):
        self.shutdown_id = shutdown_id
        self.shutdown_reason = shutdown_reason
        self.shutdown_priority = shutdown_priority
        self.state = state


class RiskEventLog(Base):
    __tablename__ = "risk_event_logs"

    id = Column(Integer, primary_key=True)

    log_type = Column(SQLAlchemyEnum(RiskEventLogType), nullable=False)
    severity = Column(SQLAlchemyEnum(RiskEventLogSeverity), default=RiskEventLogSeverity.INFO)
    
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    details = Column(Text, nullable=True)  # JSON string with additional details
    
    source = Column(String, nullable=True)  # e.g., "daily_loss_manager", "emergency_shutdown"
    source_id = Column(String, nullable=True)  # ID of the source event/record
    
    pair_id = Column(String, ForeignKey("pairs.id"), nullable=True)
    pair = relationship("Pair")
    
    coin_id = Column(String, ForeignKey("coins.symbol"), nullable=True)
    coin = relationship("Coin")
    
    metadata_json = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    
    status = Column(String, default="OPEN")  # OPEN, PROCESSED, ACKNOWLEDGED, RESOLVED
    action_taken = Column(String, nullable=True)
    action_taken_by = Column(String, nullable=True)
    action_taken_at = Column(DateTime, nullable=True)

    def __init__(
        self,
        log_type: RiskEventLogType,
        title: str,
        description: str = None,
        severity: RiskEventLogSeverity = RiskEventLogSeverity.INFO,
        source: str = None,
        source_id: str = None,
        pair: Pair = None,
        coin: Coin = None,
        details: dict = None,
        metadata_json: dict = None,
    ):
        self.log_type = log_type
        self.title = title
        self.description = description
        self.severity = severity
        self.source = source
        self.source_id = source_id
        self.pair = pair
        self.coin = coin
        self.details = details
        self.metadata_json = metadata_json


def upgrade():
    """
    Upgrade the database schema by creating the new risk management tables.
    """
    try:
        # Create all tables
        ManualApproval.__table__.create(bind=Base.metadata.bind)
        print("ManualApproval table created successfully")
        
        ThresholdSetting.__table__.create(bind=Base.metadata.bind)
        print("ThresholdSetting table created successfully")
        
        EmergencyShutdownState.__table__.create(bind=Base.metadata.bind)
        print("EmergencyShutdownState table created successfully")
        
        RiskEventLog.__table__.create(bind=Base.metadata.bind)
        print("RiskEventLog table created successfully")
        
        # Add foreign key constraints for existing tables if needed
        # This is optional and depends on the specific requirements
        
        print("Migration completed successfully: Risk management enhancement tables created")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        raise


def downgrade():
    """
    Downgrade the database schema by dropping the new risk management tables.
    """
    try:
        # Drop tables in reverse order of creation to handle foreign key dependencies
        RiskEventLog.__table__.drop(bind=Base.metadata.bind)
        print("RiskEventLog table dropped successfully")
        
        EmergencyShutdownState.__table__.drop(bind=Base.metadata.bind)
        print("EmergencyShutdownState table dropped successfully")
        
        ThresholdSetting.__table__.drop(bind=Base.metadata.bind)
        print("ThresholdSetting table dropped successfully")
        
        ManualApproval.__table__.drop(bind=Base.metadata.bind)
        print("ManualApproval table dropped successfully")
        
        print("Migration rolled back successfully: Risk management enhancement tables dropped")
        
    except Exception as e:
        print(f"Error during migration rollback: {e}")
        raise


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