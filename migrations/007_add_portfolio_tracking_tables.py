"""
Migration to add portfolio tracking tables for the portfolio change monitoring system.

This migration creates the necessary database tables for storing portfolio change
monitoring data, including portfolio_data table for tracking portfolio metrics
and changes over time.

Created: 2025-08-05
"""

import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, Float, ForeignKey, Integer, String, Text, Boolean, JSON
from sqlalchemy.orm import relationship

from binance_trade_bot.models.base import Base
from binance_trade_bot.monitoring.models import AlertSeverity, PortfolioMetric


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


def upgrade():
    """
    Upgrade the database schema by creating the portfolio_data table.
    """
    try:
        # Create portfolio_data table
        PortfolioData.__table__.create(bind=Base.metadata.bind)
        print("PortfolioData table created successfully")
        
        # Create indexes for better query performance
        _create_indexes()
        
        print("Migration completed successfully: Portfolio tracking tables created")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        raise


def downgrade():
    """
    Downgrade the database schema by dropping the portfolio_data table.
    """
    try:
        # Drop portfolio_data table
        PortfolioData.__table__.drop(bind=Base.metadata.bind)
        print("PortfolioData table dropped successfully")
        
        print("Migration rolled back successfully: Portfolio tracking tables dropped")
        
    except Exception as e:
        print(f"Error during migration rollback: {e}")
        raise


def _create_indexes():
    """
    Create additional indexes for better query performance.
    """
    try:
        # Index for portfolio data by metric_type and calculated_at
        sql = text("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_data_metric_calculated 
            ON portfolio_data (metric_type, calculated_at)
        """)
        Base.metadata.bind.execute(sql)
        print("Created index: idx_portfolio_data_metric_calculated")
        
        # Index for portfolio data by period_hours and calculated_at
        sql = text("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_data_period_calculated 
            ON portfolio_data (period_hours, calculated_at)
        """)
        Base.metadata.bind.execute(sql)
        print("Created index: idx_portfolio_data_period_calculated")
        
        # Index for portfolio data by severity and calculated_at
        sql = text("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_data_severity_calculated 
            ON portfolio_data (severity, calculated_at)
        """)
        Base.metadata.bind.execute(sql)
        print("Created index: idx_portfolio_data_severity_calculated")
        
        # Index for portfolio data by alert_uuid (foreign key)
        sql = text("""
            CREATE INDEX IF NOT EXISTS idx_portfolio_data_alert_uuid 
            ON portfolio_data (alert_uuid)
        """)
        Base.metadata.bind.execute(sql)
        print("Created index: idx_portfolio_data_alert_uuid")
        
    except Exception as e:
        print(f"Error creating indexes: {e}")
        # Don't raise the exception as indexes are not critical


if __name__ == "__main__":
    # This allows the migration to be run directly
    from binance_trade_bot.database import Database
    from binance_trade_bot.config import Config
    from binance_trade_bot.logger import Logger
    from sqlalchemy import text
    
    # Initialize database connection
    logger = Logger()
    config = Config()
    database = Database(logger, config)
    
    # Run upgrade
    upgrade()