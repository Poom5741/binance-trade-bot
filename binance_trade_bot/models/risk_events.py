from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .base import Base
from .coin import Coin
from .pair import Pair


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

    created_by = Column(String)  # System, user, or service name
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

    def resolve(self, resolved_by: str = "system"):
        self.status = RiskEventStatus.RESOLVED
        self.resolved_at = datetime.utcnow()
        self.acknowledged_by = resolved_by

    def acknowledge(self, acknowledged_by: str = "system"):
        self.status = RiskEventStatus.OPEN
        self.acknowledged_at = datetime.utcnow()
        self.acknowledged_by = acknowledged_by

    def escalate(self, escalated_by: str = "system"):
        self.status = RiskEventStatus.ESCALATED
        self.acknowledged_at = datetime.utcnow()
        self.acknowledged_by = escalated_by

    def ignore(self, ignored_by: str = "system"):
        self.status = RiskEventStatus.IGNORED
        self.acknowledged_at = datetime.utcnow()
        self.acknowledged_by = ignored_by

    def info(self):
        return {
            "id": self.id,
            "pair": self.pair.info() if self.pair else None,
            "coin": self.coin.info() if self.coin else None,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "status": self.status.value,
            "trigger_value": self.trigger_value,
            "threshold_value": self.threshold_value,
            "current_value": self.current_value,
            "description": self.description,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "created_by": self.created_by,
            "acknowledged_by": self.acknowledged_by,
        }