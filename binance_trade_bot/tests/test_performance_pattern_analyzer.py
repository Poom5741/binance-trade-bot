"""
Unit tests for Performance Pattern Analyzer.
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from binance_trade_bot.ai_adapter.performance_pattern_analyzer import (
    PerformancePatternAnalyzer, TradingMode, PatternType
)
from binance_trade_bot.models.trade import Trade, TradeState
from binance_trade_bot.models.coin import Coin
from binance_trade_bot.models.pair import Pair
from binance_trade_bot.models.ai_parameters import ParameterType, ParameterStatus


class TestPerformancePatternAnalyzer(unittest.TestCase):
    """Test cases for PerformancePatternAnalyzer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'pattern_window_size': 50,
            'volatility_threshold': 0.05,
            'confidence_threshold': 0.7,
            'mode_switch_threshold': 0.15,
            'performance_lookback_period': 30
        }
        
        self.mock_database = Mock()
        self.mock_statistics_manager = Mock()
        self.mock_logger = Mock()
        
        self.analyzer = PerformancePatternAnalyzer(
            self.config,
            self.mock_database,
            self.mock_statistics_manager,
            self.mock_logger
        )
        
        # Create sample data
        self.sample_data = self._create_sample_data()
        
        # Create test objects
        self.mock_coin = Mock()
        self.mock_coin.symbol = 'BTC'
        
        self.mock_pair = Mock()
        self.mock_pair.id = 'BTC/USDT'
        self.mock_pair.symbol = 'BTC/USDT'
    
    def _create_sample_data(self):
        """Create sample trading data for testing."""
        dates = pd.date_range(start='2023-01-01', periods=100, freq='H')
        np.random.seed(42)
        
        # Generate price data with some patterns
        base_price = 50000
        price_changes = np.random.normal(0, 0.02, 100)
        prices = [base_price]
        
        for change in price_changes[1:]:
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, 100))  # Ensure positive prices
        
        data = pd.DataFrame({
            'datetime': dates,
            'open': prices,
            'high': [p * 1.01 for p in prices],
            'low': [p * 0.99 for p in prices],
            'close': prices,
            'volume': np.random.randint(1000, 10000, 100)
        })
        
        return data
    
    def test_init(self):
        """Test initialization of PerformancePatternAnalyzer."""
        self.assertEqual(self.analyzer.pattern_window_size, 50)
        self.assertEqual(self.analyzer.volatility_threshold, 0.05)
        self.assertEqual(self.analyzer.confidence_threshold, 0.7)
        self.assertEqual(self.analyzer.current_mode, TradingMode.BALANCED)
        self.assertFalse(self.analyzer.is_trained)
        self.assertEqual(len(self.analyzer.pattern_history), 0)
    
    def test_train_model_success(self):
        """Test successful model training."""
        # Add target column
        self.sample_data['target'] = np.random.choice([0, 1], len(self.sample_data))
        
        result = self.analyzer.train_model(self.sample_data, 'target')
        
        self.assertTrue(result)
        self.assertTrue(self.analyzer.is_trained)
        self.assertGreater(len(self.analyzer.pattern_history), 0)
    
    def test_train_model_empty_data(self):
        """Test model training with empty data."""
        empty_data = pd.DataFrame()
        result = self.analyzer.train_model(empty_data, 'target')
        
        self.assertFalse(result)
        self.assertFalse(self.analyzer.is_trained)
    
    def test_train_model_missing_target_column(self):
        """Test model training with missing target column."""
        result = self.analyzer.train_model(self.sample_data, 'nonexistent_target')
        
        self.assertFalse(result)
        self.assertFalse(self.analyzer.is_trained)
    
    def test_predict_success(self):
        """Test successful prediction."""
        # Train model first
        self.sample_data['target'] = np.random.choice([0, 1], len(self.sample_data))
        self.analyzer.train_model(self.sample_data, 'target')
        
        # Make prediction
        result = self.analyzer.predict(self.sample_data)
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('market_analysis', result)
        self.assertIn('recognized_patterns', result)
        self.assertIn('volatility_assessment', result)
        self.assertIn('recommendations', result)
        self.assertIn('optimal_mode', result)
    
    def test_predict_untrained_model(self):
        """Test prediction with untrained model."""
        result = self.analyzer.predict(self.sample_data)
        
        self.assertEqual(result['status'], 'warning')
        self.assertIn('Model is not trained', result['message'])
        self.assertIn('recommendations', result)
    
    def test_predict_error_handling(self):
        """Test error handling in prediction."""
        # Mock preprocess_data to raise exception
        with patch.object(self.analyzer, 'preprocess_data', side_effect=Exception("Test error")):
            result = self.analyzer.predict(self.sample_data)
            
            self.assertEqual(result['status'], 'error')
            self.assertIn('Test error', result['message'])
    
    def test_get_feature_importance(self):
        """Test feature importance calculation."""
        # Train model first
        self.sample_data['target'] = np.random.choice([0, 1], len(self.sample_data))
        self.analyzer.train_model(self.sample_data, 'target')
        
        feature_importance = self.analyzer.get_feature_importance()
        
        self.assertIsInstance(feature_importance, dict)
        # Feature importance should be normalized (sum to 1)
        if feature_importance:
            total_importance = sum(feature_importance.values())
            self.assertAlmostEqual(total_importance, 1.0, places=5)
    
    def test_get_feature_importance_empty_model(self):
        """Test feature importance with empty model."""
        feature_importance = self.analyzer.get_feature_importance()
        
        self.assertEqual(feature_importance, {})
    
    def test_save_and_load_model(self):
        """Test model saving and loading."""
        # Train model
        self.sample_data['target'] = np.random.choice([0, 1], len(self.sample_data))
        self.analyzer.train_model(self.sample_data, 'target')
        
        # Save model
        with patch('builtins.open', unittest.mock.mock_open()):
            result = self.analyzer.save_model('test_model.json')
            self.assertTrue(result)
        
        # Load model
        with patch('builtins.open', unittest.mock.mock_open(read_data='{"pattern_history": [], "current_mode": "BALANCED"}')):
            result = self.analyzer.load_model('test_model.json')
            self.assertTrue(result)
            self.assertEqual(self.analyzer.current_mode, TradingMode.BALANCED)
    
    def test_evaluate_model(self):
        """Test model evaluation."""
        # Train model
        self.sample_data['target'] = np.random.choice([0, 1], len(self.sample_data))
        self.analyzer.train_model(self.sample_data, 'target')
        
        # Evaluate model
        evaluation = self.analyzer.evaluate_model(self.sample_data, 'target')
        
        self.assertIn('accuracy', evaluation)
        self.assertIn('precision', evaluation)
        self.assertIn('recall', evaluation)
        self.assertIn('f1_score', evaluation)
    
    def test_evaluate_untrained_model(self):
        """Test evaluation of untrained model."""
        evaluation = self.analyzer.evaluate_model(self.sample_data, 'target')
        
        self.assertIn('error', evaluation)
        self.assertIn('Model is not trained', evaluation['error'])
    
    def test_preprocess_data(self):
        """Test data preprocessing."""
        processed_data = self.analyzer.preprocess_data(self.sample_data)
        
        self.assertIsInstance(processed_data, pd.DataFrame)
        self.assertEqual(len(processed_data), len(self.sample_data))
        # Check if technical indicators were added
        self.assertIn('sma_20', processed_data.columns)
        self.assertIn('rsi', processed_data.columns)
    
    def test_get_model_info(self):
        """Test getting model information."""
        model_info = self.analyzer.get_model_info()
        
        self.assertEqual(model_info['model_type'], 'PerformancePatternAnalyzer')
        self.assertEqual(model_info['is_trained'], False)
        self.assertEqual(model_info['pattern_count'], 0)
        self.assertEqual(model_info['current_mode'], 'BALANCED')
    
    def test_analyze_trading_history(self):
        """Test trading history analysis."""
        # Mock database session and trades
        mock_trades = [
            Mock(spec=Trade),
            Mock(spec=Trade),
            Mock(spec=Trade)
        ]
        
        # Configure mock trades
        for i, trade in enumerate(mock_trades):
            trade.id = i + 1
            trade.state = TradeState.COMPLETE
            trade.datetime = datetime.now() - timedelta(days=i)
            trade.selling = i % 2 == 0
            trade.alt_trade_amount = 1000 + i * 100
            trade.crypto_trade_amount = 500 + i * 50
        
        with self.mock_database.db_session() as mock_session:
            mock_session.query.return_value.filter.return_value.all.return_value = mock_trades
            
            result = self.analyzer.analyze_trading_history(self.mock_pair, self.mock_coin)
            
            self.assertEqual(result['status'], 'success')
            self.assertEqual(result['trade_count'], 3)
            self.assertIn('patterns', result)
            self.assertIn('recommendations', result)
    
    def test_analyze_trading_history_no_data(self):
        """Test trading history analysis with no data."""
        with self.mock_database.db_session() as mock_session:
            mock_session.query.return_value.filter.return_value.all.return_value = []
            
            result = self.analyzer.analyze_trading_history(self.mock_pair, self.mock_coin)
            
            self.assertEqual(result['status'], 'warning')
            self.assertIn('No trading data found', result['message'])
    
    def test_assess_market_volatility(self):
        """Test market volatility assessment."""
        # Mock trades
        mock_trades = [Mock(spec=Trade) for _ in range(5)]
        for i, trade in enumerate(mock_trades):
            trade.state = TradeState.COMPLETE
            trade.datetime = datetime.now() - timedelta(hours=i)
            trade.alt_trade_amount = 1000
            trade.crypto_trade_amount = 500
        
        with self.mock_database.db_session() as mock_session:
            mock_session.query.return_value.filter.return_value.all.return_value = mock_trades
            
            result = self.analyzer.assess_market_volatility(self.mock_pair, self.mock_coin)
            
            self.assertEqual(result['status'], 'success')
            self.assertIn('volatility_score', result)
            self.assertIn('volatility_level', result)
            self.assertIn('data_points', result)
    
    def test_assess_market_volatility_no_data(self):
        """Test volatility assessment with no data."""
        with self.mock_database.db_session() as mock_session:
            mock_session.query.return_value.filter.return_value.all.return_value = []
            
            result = self.analyzer.assess_market_volatility(self.mock_pair, self.mock_coin)
            
            self.assertEqual(result['status'], 'warning')
            self.assertIn('No data available', result['message'])
    
    def test_generate_parameter_recommendations(self):
        """Test parameter recommendation generation."""
        # Mock the analysis methods
        with patch.object(self.analyzer, 'analyze_trading_history') as mock_history, \
             patch.object(self.analyzer, 'assess_market_volatility') as mock_volatility, \
             patch.object(self.analyzer, '_get_current_parameters') as mock_current, \
             patch.object(self.analyzer, '_generate_ai_recommendations') as mock_generate, \
             patch.object(self.analyzer, '_save_parameter_recommendations') as mock_save:
            
            # Configure mocks
            mock_history.return_value = {'patterns': []}
            mock_volatility.return_value = {'volatility_level': 'LOW'}
            mock_current.return_value = []
            mock_generate.return_value = [
                {
                    'parameter_name': 'risk_per_trade',
                    'recommended_value': 0.02,
                    'confidence': 0.8,
                    'reasoning': 'Test recommendation',
                    'parameter_type': ParameterType.RISK_MANAGEMENT.value
                }
            ]
            
            result = self.analyzer.generate_parameter_recommendations(
                self.mock_pair, self.mock_coin
            )
            
            self.assertEqual(result['status'], 'success')
            self.assertIn('recommendations', result)
            self.assertEqual(len(result['recommendations']), 1)
    
    def test_switch_trading_mode_force(self):
        """Test forced trading mode switch."""
        result = self.analyzer.switch_trading_mode(TradingMode.AGGRESSIVE, force_switch=True)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['old_mode'], 'BALANCED')
        self.assertEqual(result['new_mode'], 'AGGRESSIVE')
        self.assertEqual(self.analyzer.current_mode, TradingMode.AGGRESSIVE)
    
    def test_switch_trading_mode_based_on_performance(self):
        """Test trading mode switch based on performance."""
        # Mock current performance to trigger switch
        with patch.object(self.analyzer, '_get_current_performance') as mock_performance:
            mock_performance.return_value = {
                'total_return': -0.2,  # Poor performance
                'win_rate': 0.3,
                'sharpe_ratio': -0.5
            }
            
            result = self.analyzer.switch_trading_mode(TradingMode.CONSERVATIVE)
            
            self.assertEqual(result['status'], 'success')
            self.assertEqual(self.analyzer.current_mode, TradingMode.CONSERVATIVE)
    
    def test_switch_trading_mode_no_switch_needed(self):
        """Test trading mode switch when not needed."""
        # Mock current performance to prevent switch
        with patch.object(self.analyzer, '_get_current_performance') as mock_performance:
            mock_performance.return_value = {
                'total_return': 0.1,  # Good performance
                'win_rate': 0.6,
                'sharpe_ratio': 1.0
            }
            
            result = self.analyzer.switch_trading_mode(TradingMode.AGGRESSIVE)
            
            self.assertEqual(result['status'], 'info')
            self.assertIn('No mode switch needed', result['message'])
            self.assertEqual(self.analyzer.current_mode, TradingMode.BALANCED)  # Should not change
    
    def test_extract_patterns_from_data(self):
        """Test pattern extraction from data."""
        patterns = self.analyzer._extract_patterns_from_data(self.sample_data)
        
        self.assertIsInstance(patterns, list)
        # Should extract patterns based on window size
        expected_patterns = len(self.sample_data) - self.analyzer.pattern_window_size + 1
        self.assertEqual(len(patterns), expected_patterns)
        
        # Check pattern structure
        if patterns:
            pattern = patterns[0]
            self.assertIn('pattern_type', pattern)
            self.assertIn('price_change_percentage', pattern)
            self.assertIn('volatility', pattern)
            self.assertIn('feature_contributions', pattern)
            self.assertIn('success_indicator', pattern)
    
    def test_analyze_market_conditions(self):
        """Test market condition analysis."""
        market_analysis = self.analyzer._analyze_market_conditions(self.sample_data)
        
        self.assertIn('current_price', market_analysis)
        self.assertIn('price_change_24h', market_analysis)
        self.assertIn('trend', market_analysis)
        self.assertIn('moving_average_short', market_analysis)
        self.assertIn('moving_average_long', market_analysis)
        self.assertIn('volatility', market_analysis)
        self.assertIn('market_regime', market_analysis)
    
    def test_recognize_patterns(self):
        """Test pattern recognition."""
        patterns = self.analyzer._recognize_patterns(self.sample_data)
        
        self.assertIsInstance(patterns, list)
        for pattern in patterns:
            self.assertIn('pattern_type', pattern)
            self.assertIn('confidence', pattern)
            self.assertIn('description', pattern)
    
    def test_assess_volatility(self):
        """Test volatility assessment."""
        volatility_assessment = self.analyzer._assess_volatility(self.sample_data)
        
        self.assertIn('historical_volatility', volatility_assessment)
        self.assertIn('average_true_range', volatility_assessment)
        self.assertIn('volatility_level', volatility_assessment)
        self.assertIn('volatility_score', volatility_assessment)
        self.assertIn('risk_assessment', volatility_assessment)
    
    def test_determine_optimal_mode(self):
        """Test optimal mode determination."""
        # Test with good performance
        with patch.object(self.analyzer, '_get_current_performance') as mock_performance:
            mock_performance.return_value = {
                'total_return': 0.3,
                'win_rate': 0.7,
                'sharpe_ratio': 2.0
            }
            
            optimal_mode = self.analyzer._determine_optimal_mode()
            self.assertEqual(optimal_mode, TradingMode.AGGRESSIVE)
        
        # Test with poor performance
        with patch.object(self.analyzer, '_get_current_performance') as mock_performance:
            mock_performance.return_value = {
                'total_return': -0.2,
                'win_rate': 0.3,
                'sharpe_ratio': -1.0
            }
            
            optimal_mode = self.analyzer._determine_optimal_mode()
            self.assertEqual(optimal_mode, TradingMode.CONSERVATIVE)
    
    def test_calculate_performance_metrics(self):
        """Test performance metrics calculation."""
        patterns = [
            {'pattern_type': 'TRENDING_UP', 'success_indicator': True, 'confidence_score': 0.8},
            {'pattern_type': 'TRENDING_DOWN', 'success_indicator': False, 'confidence_score': 0.6},
            {'pattern_type': 'SIDEWAYS', 'success_indicator': True, 'confidence_score': 0.7}
        ]
        
        self.analyzer._calculate_performance_metrics(patterns)
        
        self.assertEqual(self.analyzer.performance_metrics['total_patterns'], 3)
        self.assertEqual(self.analyzer.performance_metrics['successful_patterns'], 2)
        self.assertAlmostEqual(self.analyzer.performance_metrics['success_rate'], 2/3, places=4)
        self.assertAlmostEqual(self.analyzer.performance_metrics['average_confidence'], 0.7, places=4)
        self.assertIn('pattern_distribution', self.analyzer.performance_metrics)
    
    def test_calculate_total_return(self):
        """Test total return calculation."""
        # Create mock trades
        mock_trades = []
        for i in range(3):
            trade = Mock(spec=Trade)
            trade.selling = i % 2 == 0  # Alternate between buying and selling
            trade.alt_trade_amount = 1000 + i * 100
            trade.crypto_trade_amount = 500 + i * 50
            mock_trades.append(trade)
        
        total_return = self.analyzer._calculate_total_return(mock_trades)
        
        self.assertIsInstance(total_return, float)
        self.assertGreaterEqual(total_return, -1.0)  # Should be between -1 and 1
        self.assertLessEqual(total_return, 1.0)
    
    def test_calculate_win_rate(self):
        """Test win rate calculation."""
        # Create mock trades with known outcomes
        mock_trades = []
        for i in range(4):
            trade = Mock(spec=Trade)
            trade.selling = i % 2 == 0
            trade.alt_trade_amount = 1000 if i % 2 == 0 else 800
            trade.crypto_trade_amount = 500 if i % 2 == 0 else 600
            mock_trades.append(trade)
        
        win_rate = self.analyzer._calculate_win_rate(mock_trades)
        
        self.assertEqual(win_rate, 0.5)  # 2 out of 4 trades should be profitable
    
    def test_calculate_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        # Create mock trades
        mock_trades = [Mock(spec=Trade) for _ in range(5)]
        for i, trade in enumerate(mock_trades):
            trade.selling = i % 2 == 0
            trade.alt_trade_amount = 1000
            trade.crypto_trade_amount = 500 + i * 100
        
        sharpe_ratio = self.analyzer._calculate_sharpe_ratio(mock_trades)
        
        self.assertIsInstance(sharpe_ratio, float)
    
    def test_calculate_technical_indicators(self):
        """Test technical indicator calculation."""
        result = self.analyzer._calculate_technical_indicators(self.sample_data)
        
        self.assertIn('sma_20', result.columns)
        self.assertIn('sma_50', result.columns)
        self.assertIn('rsi', result.columns)
        self.assertIn('macd', result.columns)
        self.assertEqual(len(result), len(self.sample_data))
    
    def test_calculate_feature_contributions(self):
        """Test feature contribution calculation."""
        contributions = self.analyzer._calculate_feature_contributions(self.sample_data)
        
        self.assertIsInstance(contributions, dict)
        # Contributions should be normalized (sum to 1)
        if contributions:
            total = sum(contributions.values())
            self.assertAlmostEqual(total, 1.0, places=5)
    
    def test_calculate_success_indicator(self):
        """Test success indicator calculation."""
        # Create data with known price movement
        test_data = self.sample_data.copy()
        price_change_pct = 0.03  # 3% price increase
        
        result = self.analyzer._calculate_success_indicator(test_data)
        
        self.assertTrue(result)  # Should be successful for > 2% movement
    
    def test_determine_market_regime(self):
        """Test market regime determination."""
        # Test different combinations
        self.assertEqual(self.analyzer._determine_market_regime('BULLISH', 0.03), 'BULLISH_STABLE')
        self.assertEqual(self.analyzer._determine_market_regime('BULLISH', 0.06), 'BULLISH_VOLATILE')
        self.assertEqual(self.analyzer._determine_market_regime('BEARISH', 0.03), 'BEARISH_STABLE')
        self.assertEqual(self.analyzer._determine_market_regime('BEARISH', 0.06), 'BEARISH_VOLATILE')
        self.assertEqual(self.analyzer._determine_market_regime('NEUTRAL', 0.03), 'RANGING_STABLE')
        self.assertEqual(self.analyzer._determine_market_regime('NEUTRAL', 0.06), 'RANGING_VOLATILE')
    
    def test_assess_volatility_risk(self):
        """Test volatility risk assessment."""
        self.assertEqual(self.analyzer._assess_volatility_risk(0.01), 'LOW')
        self.assertEqual(self.analyzer._assess_volatility_risk(0.03), 'MEDIUM')
        self.assertEqual(self.analyzer._assess_volatility_risk(0.06), 'HIGH')
    
    def test_get_default_prediction(self):
        """Test default prediction for untrained model."""
        prediction = self.analyzer._get_default_prediction()
        
        self.assertEqual(prediction['status'], 'warning')
        self.assertIn('Model is not trained', prediction['message'])
        self.assertIn('recommendations', prediction)
        self.assertEqual(len(prediction['recommendations']), 1)
        self.assertEqual(prediction['recommendations'][0]['parameter_name'], 'risk_per_trade')
    
    def test_calculate_confidence_scores(self):
        """Test confidence score calculation."""
        market_analysis = {'trend': 'BULLISH'}
        patterns = [{'confidence': 0.8}]
        volatility_assessment = {'volatility_level': 'MEDIUM'}
        
        confidence_scores = self.analyzer._calculate_confidence_scores(
            market_analysis, patterns, volatility_assessment
        )
        
        self.assertIn('market_analysis', confidence_scores)
        self.assertIn('pattern_recognition', confidence_scores)
        self.assertIn('volatility_assessment', confidence_scores)
        self.assertIn('overall', confidence_scores)
        
        # All confidence scores should be between 0 and 1
        for score in confidence_scores.values():
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)


if __name__ == '__main__':
    unittest.main()