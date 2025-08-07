from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship

from .base import Base
from .coin import Coin
from .pair import Pair


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


class AiParameters(Base):
    __tablename__ = "ai_parameters"

    id = Column(Integer, primary_key=True)

    pair_id = Column(String, ForeignKey("pairs.id"))
    pair = relationship("Pair")

    coin_id = Column(String, ForeignKey("coins.symbol"))
    coin = relationship("Coin")

    parameter_type = Column(SQLAlchemyEnum(ParameterType))
    parameter_name = Column(String)
    parameter_value = Column(JSON)  # Store complex parameters as JSON
    confidence_score = Column(Float)  # AI confidence in this parameter (0.0 to 1.0)
    accuracy_score = Column(Float)  # Historical accuracy of this parameter

    status = Column(SQLAlchemyEnum(ParameterStatus), default=ParameterStatus.ACTIVE)
    description = Column(Text)
    metadata_json = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tested_at = Column(DateTime)
    deployed_at = Column(DateTime)

    model_version = Column(String)  # AI model version that generated this parameter
    model_source = Column(String)  # Source of the AI recommendation
    recommendation_id = Column(String)  # External recommendation ID

    backtest_results = Column(JSON)  # Store backtest results as JSON
    performance_metrics = Column(JSON)  # Store performance metrics as JSON

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

    def update_parameter(self, new_value, confidence_score: float = None, accuracy_score: float = None):
        self.parameter_value = new_value
        self.updated_at = datetime.utcnow()
        if confidence_score is not None:
            self.confidence_score = confidence_score
        if accuracy_score is not None:
            self.accuracy_score = accuracy_score

    def activate(self):
        self.status = ParameterStatus.ACTIVE
        self.deployed_at = datetime.utcnow()

    def deactivate(self):
        self.status = ParameterStatus.INACTIVE

    def set_testing(self):
        self.status = ParameterStatus.TESTING
        self.tested_at = datetime.utcnow()

    def set_deprecated(self):
        self.status = ParameterStatus.DEPRECATED

    def add_backtest_results(self, results):
        self.backtest_results = results
        self.tested_at = datetime.utcnow()

    def add_performance_metrics(self, metrics):
        self.performance_metrics = metrics

    def info(self):
        return {
            "id": self.id,
            "pair": self.pair.info() if self.pair else None,
            "coin": self.coin.info() if self.coin else None,
            "parameter_type": self.parameter_type.value,
            "parameter_name": self.parameter_name,
            "parameter_value": self.parameter_value,
            "confidence_score": self.confidence_score,
            "accuracy_score": self.accuracy_score,
            "status": self.status.value,
            "description": self.description,
            "metadata_json": self.metadata_json,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "tested_at": self.tested_at.isoformat() if self.tested_at else None,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "model_version": self.model_version,
            "model_source": self.model_source,
            "recommendation_id": self.recommendation_id,
            "backtest_results": self.backtest_results,
            "performance_metrics": self.performance_metrics,
        }