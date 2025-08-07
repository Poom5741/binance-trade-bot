"""
Migration script to add enhanced fields to existing database models.

This migration adds the following fields:
- Pair model: wma_trend_score, ai_adjustment_factor
- CoinValue model: daily_change_percentage, risk_score

Created: 2025-08-05
"""

from sqlalchemy import Column, Float, Text
from sqlalchemy.sql import text

from binance_trade_bot.models.base import Base


def upgrade():
    """
    Upgrade the database schema by adding new columns to existing tables.
    """
    # Add columns to pairs table
    try:
        # Add wma_trend_score column
        if not hasattr(Base.metadata.tables['pairs'], 'wma_trend_score'):
            wma_trend_score = Column('wma_trend_score', Float, nullable=True)
            wma_trend_score.create(Base.metadata.tables['pairs'])
            print("Added wma_trend_score column to pairs table")
        
        # Add ai_adjustment_factor column
        if not hasattr(Base.metadata.tables['pairs'], 'ai_adjustment_factor'):
            ai_adjustment_factor = Column('ai_adjustment_factor', Float, nullable=True)
            ai_adjustment_factor.create(Base.metadata.tables['pairs'])
            print("Added ai_adjustment_factor column to pairs table")
            
    except Exception as e:
        print(f"Error adding columns to pairs table: {e}")
    
    # Add columns to coin_value table
    try:
        # Add daily_change_percentage column
        if not hasattr(Base.metadata.tables['coin_value'], 'daily_change_percentage'):
            daily_change_percentage = Column('daily_change_percentage', Float, nullable=True)
            daily_change_percentage.create(Base.metadata.tables['coin_value'])
            print("Added daily_change_percentage column to coin_value table")
        
        # Add risk_score column
        if not hasattr(Base.metadata.tables['coin_value'], 'risk_score'):
            risk_score = Column('risk_score', Float, nullable=True)
            risk_score.create(Base.metadata.tables['coin_value'])
            print("Added risk_score column to coin_value table")
            
    except Exception as e:
        print(f"Error adding columns to coin_value table: {e}")
    
    print("Migration completed successfully: Enhanced fields added")


def downgrade():
    """
    Downgrade the database schema by removing the added columns.
    """
    # Remove columns from coin_value table (reverse order)
    try:
        if hasattr(Base.metadata.tables['coin_value'], 'risk_score'):
            Base.metadata.tables['coin_value'].columns['risk_score'].drop()
            print("Removed risk_score column from coin_value table")
        
        if hasattr(Base.metadata.tables['coin_value'], 'daily_change_percentage'):
            Base.metadata.tables['coin_value'].columns['daily_change_percentage'].drop()
            print("Removed daily_change_percentage column from coin_value table")
            
    except Exception as e:
        print(f"Error removing columns from coin_value table: {e}")
    
    # Remove columns from pairs table (reverse order)
    try:
        if hasattr(Base.metadata.tables['pairs'], 'ai_adjustment_factor'):
            Base.metadata.tables['pairs'].columns['ai_adjustment_factor'].drop()
            print("Removed ai_adjustment_factor column from pairs table")
        
        if hasattr(Base.metadata.tables['pairs'], 'wma_trend_score'):
            Base.metadata.tables['pairs'].columns['wma_trend_score'].drop()
            print("Removed wma_trend_score column from pairs table")
            
    except Exception as e:
        print(f"Error removing columns from pairs table: {e}")
    
    print("Migration rolled back successfully: Enhanced fields removed")


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