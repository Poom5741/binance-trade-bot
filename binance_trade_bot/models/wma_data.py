from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .base import Base
from .coin import Coin
from .pair import Pair


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


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

    def info(self):
        return {
            "id": self.id,
            "pair": self.pair.info(),
            "coin": self.coin.info(),
            "period": self.period,
            "wma_value": self.wma_value,
            "signal_type": self.signal_type.value,
            "confidence": self.confidence,
            "current_price": self.current_price,
            "trend_strength": self.trend_strength,
            "datetime": self.datetime.isoformat(),
        }