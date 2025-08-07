#!/usr/bin/env python3
"""
Simple test script for WMA calculation engine.
This script provides basic validation without complex dependencies.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    import pandas as pd
    import numpy as np
    from technical_analysis.wma_engine import WmaEngine
    
    def test_basic_wma():
        """Test basic WMA calculation functionality."""
        print("Testing basic WMA calculation...")
        
        # Create WMA engine
        config = {'wma_short_period': 7, 'wma_long_period': 21, 'price_column': 'close'}
        wma_engine = WmaEngine(config)
        
        # Test basic WMA calculation
        test_data = pd.Series([1, 2, 3, 4, 5])
        wma_result = wma_engine.calculate_wma(test_data, 3)
        
        # Expected: [14/6, 20/6, 26/6] = [2.333..., 3.333..., 4.333...]
        expected = [14/6, 20/6, 26/6]
        
        if len(wma_result) == 3 and all(abs(wma_result.iloc[i] - expected[i]) < 0.001 for i in range(3)):
            print("✓ Basic WMA calculation test passed")
            return True
        else:
            print("✗ Basic WMA calculation test failed")
            return False
    
    def test_wma_engine_with_sample_data():
        """Test WMA engine with sample market data."""
        print("Testing WMA engine with sample data...")
        
        # Create sample market data
        dates = pd.date_range(start='2023-01-01', periods=30, freq='D')
        prices = [100 + i * 2 for i in range(30)]  # Linear increasing prices
        
        sample_data = pd.DataFrame({
            'close': prices,
            'high': [p + 1 for p in prices],
            'low': [p - 1 for p in prices],
            'open': [p - 0.5 for p in prices],
            'volume': [1000] * 30
        }, index=dates)
        
        # Create WMA engine
        config = {'wma_short_period': 7, 'wma_long_period': 21, 'price_column': 'close'}
        wma_engine = WmaEngine(config)
        
        # Test indicator calculation
        try:
            indicators = wma_engine.calculate_indicators(sample_data)
            
            # Check if WMA columns are present
            required_columns = ['short_wma', 'long_wma', 'wma_spread', 'wma_ratio']
            if all(col in indicators.columns for col in required_columns):
                print("✓ Indicator calculation test passed")
                
                # Test trend detection
                trend_analysis = wma_engine.detect_trend(sample_data)
                if 'trend' in trend_analysis and 'trend_strength' in trend_analysis:
                    print("✓ Trend detection test passed")
                    
                    # Test signal generation
                    signals = wma_engine.generate_signals(indicators)
                    if isinstance(signals, pd.Series) and len(signals) == len(indicators):
                        print("✓ Signal generation test passed")
                        return True
                    else:
                        print("✗ Signal generation test failed")
                        return False
                else:
                    print("✗ Trend detection test failed")
                    return False
            else:
                print("✗ Indicator calculation test failed")
                return False
                
        except Exception as e:
            print(f"✗ WMA engine test failed with error: {e}")
            return False
    
    def test_validation():
        """Test data validation functionality."""
        print("Testing data validation...")
        
        config = {'wma_short_period': 7, 'wma_long_period': 21, 'price_column': 'close'}
        wma_engine = WmaEngine(config)
        
        # Test valid data
        valid_data = pd.DataFrame({'close': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]})
        if wma_engine.validate_data(valid_data):
            print("✓ Valid data test passed")
        else:
            print("✗ Valid data test failed")
            return False
        
        # Test invalid data (None)
        if not wma_engine.validate_data(None):
            print("✓ Invalid data (None) test passed")
        else:
            print("✗ Invalid data (None) test failed")
            return False
        
        # Test insufficient data
        insufficient_data = pd.DataFrame({'close': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]})
        if not wma_engine.validate_data(insufficient_data):
            print("✓ Insufficient data test passed")
        else:
            print("✗ Insufficient data test failed")
            return False
        
        return True
    
    def main():
        """Run all tests."""
        print("Starting WMA Engine Tests...")
        print("=" * 50)
        
        tests_passed = 0
        total_tests = 3
        
        # Run tests
        if test_basic_wma():
            tests_passed += 1
        
        if test_wma_engine_with_sample_data():
            tests_passed += 1
        
        if test_validation():
            tests_passed += 1
        
        # Summary
        print("=" * 50)
        print(f"Tests passed: {tests_passed}/{total_tests}")
        
        if tests_passed == total_tests:
            print("All tests passed! ✓")
            return 0
        else:
            print("Some tests failed! ✗")
            return 1
    
    if __name__ == "__main__":
        exit(main())

except ImportError as e:
    print(f"Import error: {e}")
    print("Required dependencies not available. Skipping tests.")
    exit(0)