"""
Migration script to add daily loss tracking table.

This migration adds the following table:
- daily_loss_tracking: for tracking daily portfolio values and loss percentages

Created: 2025-08-05
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SQLAlchemyEnum, Float, Integer, String, Boolean
from sqlalchemy.sql import text

from binance_trade_bot.models.base import Base
from binance_trade_bot.models.daily_loss_tracking import DailyLossStatus


def upgrade():
    """
    Upgrade the database schema by creating the daily_loss_tracking table.
    """
    try:
        # Create the daily_loss_tracking table
        DailyLossTracking.__table__.create(bind=Base.metadata.bind)
        print("Daily loss tracking table created successfully")
        
        # Add some initial data for today if needed
        # This is optional and can be done through the application
        print("Migration completed successfully: Daily loss tracking table created")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        raise


def downgrade():
    """
    Downgrade the database schema by dropping the daily_loss_tracking table.
    """
    try:
        # Drop the daily_loss_tracking table
        DailyLossTracking.__table__.drop(bind=Base.metadata.bind)
        print("Daily loss tracking table dropped successfully")
        
        print("Migration rolled back successfully: Daily loss tracking table dropped")
        
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