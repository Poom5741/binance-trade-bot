"""
Migration script to add new database tables for enhanced functionality.

This migration adds the following tables:
- wma_data: for storing WMA calculations and trend signals
- risk_events: for tracking risk management events
- ai_parameters: for storing AI recommendations
- telegram_users: for user authentication

Created: 2025-08-05
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, Float, ForeignKey, Integer, String, Text, JSON, Boolean
from sqlalchemy.orm import relationship

from binance_trade_bot.models.base import Base
from binance_trade_bot.models.coin import Coin
from binance_trade_bot.models.pair import Pair


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class RiskEventType(Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    POSITION_SIZE = "POSITION_SIZE"
    VOLATILITY_ALERT = "VOLATILITY_ALERT"
    LIQUIDITY_ALERT = "LIQUIDITY_ALERT"
    PRICE_DEVIATION = "PRICE_DEVIATION"
    PORTFOLIO_LIMIT = "PORTFOLIO_LIMIT"
    LEVERAGE_ALERT = "LEVERAGE_ALERT"
    CUSTOM = "CUSTOM"


class RiskEventSeverity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskEventStatus(Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"
    ESCALATED = "ESCALATED"


class ParameterType(Enum):
    TRADING_STRATEGY = "TRADING_STRATEGY"
    RISK_MANAGEMENT = "RISK_MANAGEMENT"
    TECHNICAL_INDICATOR = "TECHNICAL_INDICATOR"
    PORTFOLIO_OPTIMIZATION = "PORTFOLIO_OPTIMIZATION"
    MARKET_SENTIMENT = "MARKET_SENTIMENT"
    VOLATILITY_MODEL = "VOLATILITY_MODEL"
    LIQUIDITY_ANALYSIS = "LIQUIDITY_ANALYSIS"
    CUSTOM = "CUSTOM"


class ParameterStatus(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    TESTING = "TESTING"
    DEPRECATED = "DEPRECATED"


class UserRole(Enum):
    ADMIN = "ADMIN"
    TRADER = "TRADER"
    VIEWER = "VIEWER"
    API_USER = "API_USER"


class UserStatus(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BANNED = "BANNED"
    PENDING = "PENDING"


class WmaData(Base):
    __tablename__ = "wma_data"

    id = Column(Integer, primary_key=True)

    pair_id = Column(String, ForeignKey("pairs.id"))
    pair = relationship("Pair")

    coin_id = Column(String, ForeignKey("coins.symbol"))
    coin = relationship("Coin")

    period = Column(Integer)
    wma_value = Column(Float)
    signal_type = Column(SQLAlchemyEnum(SignalType))
    confidence = Column(Float)

    current_price = Column(Float)
    trend_strength = Column(Float)

    datetime = Column(DateTime)

    def __init__(
        self,
        pair: Pair,
        coin: Coin,
        period: int,
        wma_value: float,
        signal_type: SignalType,
        confidence: float,
        current_price: float,
        trend_strength: float,
    ):
        self.pair = pair
        self.coin = coin
        self.period = period
        self.wma_value = wma_value
        self.signal_type = signal_type
        self.confidence = confidence
        self.current_price = current_price
        self.trend_strength = trend_strength
        self.datetime = datetime.utcnow()


class RiskEvent(Base):
    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True)

    pair_id = Column(String, ForeignKey("pairs.id"))
    pair = relationship("Pair")

    coin_id = Column(String, ForeignKey("coins.symbol"))
    coin = relationship("Coin")

    event_type = Column(SQLAlchemyEnum(RiskEventType))
    severity = Column(SQLAlchemyEnum(RiskEventSeverity))
    status = Column(SQLAlchemyEnum(RiskEventStatus), default=RiskEventStatus.OPEN)

    trigger_value = Column(Float)
    threshold_value = Column(Float)
    current_value = Column(Float)

    description = Column(Text)
    metadata_json = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)
    acknowledged_at = Column(DateTime)

    created_by = Column(String)
    acknowledged_by = Column(String)

    def __init__(
        self,
        pair: Pair,
        coin: Coin,
        event_type: RiskEventType,
        severity: RiskEventSeverity,
        trigger_value: float,
        threshold_value: float,
        current_value: float,
        description: str,
        created_by: str = "system",
        metadata_json: str = None,
    ):
        self.pair = pair
        self.coin = coin
        self.event_type = event_type
        self.severity = severity
        self.trigger_value = trigger_value
        self.threshold_value = threshold_value
        self.current_value = current_value
        self.description = description
        self.created_by = created_by
        self.metadata_json = metadata_json


class AiParameters(Base):
    __tablename__ = "ai_parameters"

    id = Column(Integer, primary_key=True)

    pair_id = Column(String, ForeignKey("pairs.id"))
    pair = relationship("Pair")

    coin_id = Column(String, ForeignKey("coins.symbol"))
    coin = relationship("Coin")

    parameter_type = Column(SQLAlchemyEnum(ParameterType))
    parameter_name = Column(String)
    parameter_value = Column(JSON)
    confidence_score = Column(Float)
    accuracy_score = Column(Float)

    status = Column(SQLAlchemyEnum(ParameterStatus), default=ParameterStatus.ACTIVE)
    description = Column(Text)
    metadata_json = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tested_at = Column(DateTime)
    deployed_at = Column(DateTime)

    model_version = Column(String)
    model_source = Column(String)
    recommendation_id = Column(String)

    backtest_results = Column(JSON)
    performance_metrics = Column(JSON)

    def __init__(
        self,
        pair: Pair,
        coin: Coin,
        parameter_type: ParameterType,
        parameter_name: str,
        parameter_value,
        confidence_score: float,
        accuracy_score: float = None,
        description: str = None,
        model_version: str = None,
        model_source: str = None,
        recommendation_id: str = None,
        metadata_json: str = None,
    ):
        self.pair = pair
        self.coin = coin
        self.parameter_type = parameter_type
        self.parameter_name = parameter_name
        self.parameter_value = parameter_value
        self.confidence_score = confidence_score
        self.accuracy_score = accuracy_score
        self.description = description
        self.model_version = model_version
        self.model_source = model_source
        self.recommendation_id = recommendation_id
        self.metadata_json = metadata_json


class TelegramUsers(Base):
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True)

    telegram_id = Column(String, unique=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)

    role = Column(SQLAlchemyEnum(UserRole), default=UserRole.VIEWER)
    status = Column(SQLAlchemyEnum(UserStatus), default=UserStatus.PENDING)

    is_bot = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)

    language_code = Column(String, nullable=True)
    timezone = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime)
    verified_at = Column(DateTime)

    api_key = Column(String, unique=True, nullable=True)
    api_key_expires_at = Column(DateTime, nullable=True)

    notification_settings = Column(Text, nullable=True)
    trading_preferences = Column(Text, nullable=True)

    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String, nullable=True)

    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)

    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    def __init__(
        self,
        telegram_id: str,
        username: str = None,
        first_name: str = None,
        last_name: str = None,
        role: UserRole = UserRole.VIEWER,
        is_bot: bool = False,
        language_code: str = None,
        timezone: str = None,
    ):
        self.telegram_id = telegram_id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
        self.role = role
        self.is_bot = is_bot
        self.language_code = language_code
        self.timezone = timezone


def upgrade():
    """
    Upgrade the database schema by creating the new tables.
    """
    # Create all tables
    WmaData.__table__.create(bind=Base.metadata.bind)
    RiskEvent.__table__.create(bind=Base.metadata.bind)
    AiParameters.__table__.create(bind=Base.metadata.bind)
    TelegramUsers.__table__.create(bind=Base.metadata.bind)
    
    print("Migration completed successfully: New tables created")


def downgrade():
    """
    Downgrade the database schema by dropping the new tables.
    """
    # Drop tables in reverse order of creation to handle foreign key dependencies
    TelegramUsers.__table__.drop(bind=Base.metadata.bind)
    AiParameters.__table__.drop(bind=Base.metadata.bind)
    RiskEvent.__table__.drop(bind=Base.metadata.bind)
    WmaData.__table__.drop(bind=Base.metadata.bind)
    
    print("Migration rolled back successfully: New tables dropped")


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