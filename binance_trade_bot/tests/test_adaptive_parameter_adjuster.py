"""
Unit tests for Adaptive Parameter Adjuster.
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from binance_trade_bot.ai_adapter.adaptive_parameter_adjuster import (
    AdaptiveParameterAdjuster, ParameterSafetyLevel, ParameterBoundType
)
from binance_trade_bot.models.trade import Trade, TradeState
from binance_trade_bot.models.coin import Coin
from binance_trade_bot.models.pair import Pair
from binance_trade_bot.database import Database
from binance_trade_bot.statistics.manager import StatisticsManager
from binance_trade_bot.logger import Logger


class TestAdaptiveParameterAdjuster(unittest.TestCase):
    """Test cases for AdaptiveParameterAdjuster."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'parameter_bounds': {
                'risk_per_trade': {
                    'min': 0.001,
                    'max': 0.1,
                    'default': 0.02,
                    'safety_level': 'HIGH',
                    'step': 0.001
                },
                'position_size': {
                    'min': 0.1,
                    'max': 2.0,
                    'default': 1.0,
                    'safety_level': 'MEDIUM',
                    'step': 0.1
                },
                'stop_loss_percentage': {
                    'min': 0.01,
                    'max': 0.2,
                    'default': 0.05,
                    'safety_level': 'CRITICAL',
                    'step': 0.01
                }
            },
            'enable_bounds_validation': True,
            'enable_confidence_capping': True,
            'confidence_cap_threshold': 0.95,
            'min_trades_for_learning': 10,
            'performance_window_size': 50,
            'learning_rate': 0.1,
            'enable_adaptive_learning': True,
            'enable_fallback_to_defaults': True,
            'min_data_points_for_recommendation': 5,
            'fallback_confidence_threshold': 0.3,
            'enable_parameter_correlation_checks': True,
            'max_parameter_change_rate': 0.5
        }
        
        self.mock_database = Mock(spec=Database)
        self.mock_statistics_manager = Mock(spec=StatisticsManager)
        self.mock_logger = Mock(spec=Logger)
        
        self.adjuster = AdaptiveParameterAdjuster(
            self.config,
            self.mock_database,
            self.mock_statistics_manager,
            self.mock_logger
        )
        
        # Create sample data
        self.sample_data = self._create_sample_data()
        
        # Create test objects
        self.mock_coin = Mock(spec=Coin)
        self.mock_coin.symbol = 'BTC'
        
        self.mock_pair = Mock(spec=Pair)
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
            'volume': np.random.randint(1000, 10000, 100),
            'target': np.random.choice([0, 1], len(prices))  # Binary target for classification
        })
        
        return data
    
    def test_init(self):
        """Test initialization of AdaptiveParameterAdjuster."""
        self.assertEqual(self.adjuster.parameter_bounds, self.config['parameter_bounds'])
        self.assertTrue(self.adjuster.enable_bounds_validation)
        self.assertTrue(self.adjuster.enable_confidence_capping)
        self.assertEqual(self.adjuster.confidence_cap_threshold, 0.95)
        self.assertEqual(self.adjuster.min_trades_for_learning, 10)
        self.assertFalse(self.adjuster.is_trained)
        self.assertEqual(len(self.adjuster.parameter_history), 0)
    
    def test_train_model_success(self):
        """Test successful model training."""
        result = self.adjuster.train_model(self.sample_data, 'target')
        
        self.assertTrue(result)
        self.assertTrue(self.adjuster.is_trained)
        self.assertGreater(len(self.adjuster.learning_model_state), 0)
    
    def test_train_model_empty_data(self):
        """Test model training with empty data."""
        empty_data = pd.DataFrame()
        result = self.adjuster.train_model(empty_data, 'target')
        
        self.assertFalse(result)
        self.assertFalse(self.adjuster.is_trained)
    
    def test_train_model_missing_target_column(self):
        """Test model training with missing target column."""
        result = self.adjuster.train_model(self.sample_data, 'nonexistent_target')
        
        self.assertFalse(result)
        self.assertFalse(self.adjuster.is_trained)
    
    def test_predict_success(self):
        """Test successful prediction."""
        # Train model first
        self.adjuster.train_model(self.sample_data, 'target')
        
        # Make prediction
        result = self.adjuster.predict(self.sample_data)
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('recommendations', result)
        self.assertIn('validation_results', result)
        self.assertIn('model_info', result)
        self.assertGreater(len(result['recommendations']), 0)
    
    def test_predict_untrained_model(self):
        """Test prediction with untrained model."""
        result = self.adjuster.predict(self.sample_data)
        
        self.assertEqual(result['status'], 'warning')
        self.assertIn('Model is not trained', result['message'])
        self.assertIn('recommendations', result)
    
    def test_predict_error_handling(self):
        """Test error handling in prediction."""
        # Mock preprocess_data to raise exception
        with patch.object(self.adjuster, 'preprocess_data', side_effect=Exception("Test error")):
            result = self.adjuster.predict(self.sample_data)
            
            self.assertEqual(result['status'], 'error')
            self.assertIn('Test error', result['message'])
    
    def test_get_feature_importance(self):
        """Test feature importance calculation."""
        # Train model first
        self.adjuster.train_model(self.sample_data, 'target')
        
        feature_importance = self.adjuster.get_feature_importance()
        
        self.assertIsInstance(feature_importance, dict)
        # Feature importance should be normalized (sum to 1)
        if feature_importance:
            total_importance = sum(feature_importance.values())
            self.assertAlmostEqual(total_importance, 1.0, places=5)
    
    def test_get_feature_importance_empty_model(self):
        """Test feature importance with empty model."""
        feature_importance = self.adjuster.get_feature_importance()
        
        self.assertEqual(feature_importance, {})
    
    def test_save_and_load_model(self):
        """Test model saving and loading."""
        # Train model
        self.adjuster.train_model(self.sample_data, 'target')
        
        # Save model
        with patch('builtins.open', unittest.mock.mock_open()):
            result = self.adjuster.save_model('test_model.json')
            self.assertTrue(result)
        
        # Load model
        with patch('builtins.open', unittest.mock.mock_open(read_data='{"parameter_bounds": {}, "learning_model_state": {}, "is_trained": true}')):
            result = self.adjuster.load_model('test_model.json')
            self.assertTrue(result)
            self.assertTrue(self.adjuster.is_trained)
    
    def test_evaluate_model(self):
        """Test model evaluation."""
        # Train model
        self.adjuster.train_model(self.sample_data, 'target')
        
        # Evaluate model
        evaluation = self.adjuster.evaluate_model(self.sample_data, 'target')
        
        self.assertIn('recommendations_count', evaluation)
        self.assertIn('valid_recommendations', evaluation)
        self.assertIn('validation_success_rate', evaluation)
        self.assertIn('average_confidence', evaluation)
    
    def test_evaluate_untrained_model(self):
        """Test evaluation of untrained model."""
        evaluation = self.adjuster.evaluate_model(self.sample_data, 'target')
        
        self.assertIn('error', evaluation)
        self.assertIn('Model is not trained', evaluation['error'])
    
    def test_preprocess_data(self):
        """Test data preprocessing."""
        processed_data = self.adjuster.preprocess_data(self.sample_data)
        
        self.assertIsInstance(processed_data, pd.DataFrame)
        self.assertEqual(len(processed_data), len(self.sample_data))
        # Check if technical indicators were added
        self.assertIn('sma_20', processed_data.columns)
        self.assertIn('rsi', processed_data.columns)
        self.assertIn('macd', processed_data.columns)
    
    def test_get_model_info(self):
        """Test getting model information."""
        model_info = self.adjuster.get_model_info()
        
        self.assertEqual(model_info['model_type'], 'AdaptiveParameterAdjuster')
        self.assertEqual(model_info['is_trained'], False)
        self.assertEqual(model_info['parameter_count'], len(self.config['parameter_bounds']))
        self.assertIn('config', model_info)
        self.assertIn('feature_importance', model_info)
    
    def test_validate_parameter_bounds_success(self):
        """Test successful parameter bounds validation."""
        result = self.adjuster.validate_parameter_bounds('risk_per_trade', 0.02)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['validation_status'], 'valid')
        self.assertEqual(result['parameter_name'], 'risk_per_trade')
        self.assertEqual(result['value'], 0.02)
    
    def test_validate_parameter_bounds_below_minimum(self):
        """Test parameter validation below minimum."""
        result = self.adjuster.validate_parameter_bounds('risk_per_trade', 0.0005)
        
        self.assertFalse(result['is_valid'])
        self.assertEqual(result['validation_status'], 'bounds_violation')
        self.assertEqual(result['corrected_value'], 0.001)
    
    def test_validate_parameter_bounds_above_maximum(self):
        """Test parameter validation above maximum."""
        result = self.adjuster.validate_parameter_bounds('risk_per_trade', 0.15)
        
        self.assertFalse(result['is_valid'])
        self.assertEqual(result['validation_status'], 'bounds_violation')
        self.assertEqual(result['corrected_value'], 0.1)
    
    def test_validate_parameter_bounds_unknown_parameter(self):
        """Test validation of unknown parameter."""
        result = self.adjuster.validate_parameter_bounds('unknown_param', 1.0)
        
        self.assertFalse(result['is_valid'])
        self.assertEqual(result['validation_status'], 'unknown_parameter')
    
    def test_validate_parameter_bounds_validation_disabled(self):
        """Test parameter validation with validation disabled."""
        adjuster = AdaptiveParameterAdjuster(
            {'enable_bounds_validation': False},
            self.mock_database,
            self.mock_statistics_manager,
            self.mock_logger
        )
        
        result = adjuster.validate_parameter_bounds('risk_per_trade', 0.0005)
        
        self.assertTrue(result['is_valid'])
        self.assertEqual(result['validation_status'], 'validation_disabled')
    
    def test_get_default_parameters(self):
        """Test getting default parameters."""
        default_params = self.adjuster.get_default_parameters()
        
        self.assertIsInstance(default_params, dict)
        self.assertEqual(default_params['risk_per_trade'], 0.02)
        self.assertEqual(default_params['position_size'], 1.0)
        self.assertEqual(default_params['stop_loss_percentage'], 0.05)
    
    def test_update_parameters_from_trading_results_success(self):
        """Test successful parameter update from trading results."""
        # Train model first
        self.adjuster.train_model(self.sample_data, 'target')
        
        # Create mock trades
        mock_trades = self._create_mock_trades(15)
        
        # Create performance metrics
        performance_metrics = {
            'win_rate': 0.6,
            'profit_factor': 1.2,
            'sharpe_ratio': 1.5,
            'max_drawdown': 0.1,
            'total_return': 0.15
        }
        
        result = self.adjuster.update_parameters_from_trading_results(mock_trades, performance_metrics)
        
        self.assertEqual(result['status'], 'success')
        self.assertIn('updated_recommendations', result)
        self.assertIn('performance_insights', result)
        self.assertEqual(result['trades_analyzed'], 15)
    
    def test_update_parameters_from_trading_results_insufficient_data(self):
        """Test parameter update with insufficient data."""
        # Train model first
        self.adjuster.train_model(self.sample_data, 'target')
        
        # Create mock trades (insufficient)
        mock_trades = self._create_mock_trades(5)
        
        performance_metrics = {'win_rate': 0.6}
        
        result = self.adjuster.update_parameters_from_trading_results(mock_trades, performance_metrics)
        
        self.assertEqual(result['status'], 'warning')
        self.assertIn('Insufficient data for learning', result['message'])
    
    def test_update_parameters_from_trading_results_untrained_model(self):
        """Test parameter update with untrained model."""
        mock_trades = self._create_mock_trades(15)
        performance_metrics = {'win_rate': 0.6}
        
        result = self.adjuster.update_parameters_from_trading_results(mock_trades, performance_metrics)
        
        self.assertEqual(result['status'], 'warning')
        self.assertIn('Model is not trained', result['message'])
    
    def test_extract_performance_patterns(self):
        """Test performance pattern extraction."""
        patterns = self.adjuster._extract_performance_patterns(self.sample_data, 'target')
        
        self.assertIsInstance(patterns, list)
        self.assertGreater(len(patterns), 0)
        
        # Check pattern structure
        if patterns:
            pattern = patterns[0]
            self.assertIn('parameter_name', pattern)
            self.assertIn('correlation', pattern)
            self.assertIn('performance_impact', pattern)
            self.assertIn('optimal_range', pattern)
            self.assertIn('data_quality', pattern)
    
    def test_build_learning_model_state(self):
        """Test learning model state building."""
        patterns = [
            {
                'parameter_name': 'risk_per_trade',
                'correlation': 0.5,
                'performance_impact': 0.5,
                'optimal_range': {'min': 0.01, 'max': 0.03},
                'data_quality': {'quality_score': 0.8}
            }
        ]
        
        self.adjuster._build_learning_model_state(patterns)
        
        self.assertIn('risk_per_trade', self.adjuster.learning_model_state)
        self.assertEqual(self.adjuster.learning_model_state['risk_per_trade']['correlation'], 0.5)
        self.assertEqual(self.adjuster.learning_model_state['risk_per_trade']['performance_impact'], 0.5)
    
    def test_get_ai_recommendations(self):
        """Test AI recommendations generation."""
        # Build learning model state first
        patterns = [
            {
                'parameter_name': 'risk_per_trade',
                'correlation': 0.5,
                'performance_impact': 0.5,
                'optimal_range': {'min': 0.01, 'max': 0.03},
                'data_quality': {'quality_score': 0.8}
            }
        ]
        self.adjuster._build_learning_model_state(patterns)
        
        recommendations = self.adjuster._get_ai_recommendations(self.sample_data)
        
        self.assertIsInstance(recommendations, list)
        self.assertGreater(len(recommendations), 0)
        
        # Check recommendation structure
        if recommendations:
            rec = recommendations[0]
            self.assertIn('parameter_name', rec)
            self.assertIn('recommended_value', rec)
            self.assertIn('confidence', rec)
            self.assertIn('reasoning', rec)
            self.assertIn('source', rec)
    
    def test_validate_and_bound_recommendations(self):
        """Test recommendation validation and bounding."""
        # Create test recommendations
        recommendations = [
            {
                'parameter_name': 'risk_per_trade',
                'recommended_value': 0.15,  # Exceeds maximum
                'confidence': 0.8,
                'reasoning': 'Test recommendation',
                'source': 'ai_model',
                'validation_status': 'pending'
            }
        ]
        
        validated_recommendations = self.adjuster._validate_and_bound_recommendations(recommendations)
        
        self.assertEqual(len(validated_recommendations), 1)
        self.assertFalse(validated_recommendations[0]['validation_result']['is_valid'])
        self.assertEqual(validated_recommendations[0]['validation_status'], 'bounds_violation')
        self.assertEqual(validated_recommendations[0]['recommended_value'], 0.1)  # Corrected to max
        self.assertTrue(validated_recommendations[0]['correction_applied'])
    
    def test_apply_confidence_capping(self):
        """Test confidence capping."""
        recommendations = [
            {
                'parameter_name': 'risk_per_trade',
                'recommended_value': 0.02,
                'confidence': 0.98,  # Exceeds threshold
                'reasoning': 'Test recommendation',
                'source': 'ai_model'
            }
        ]
        
        capped_recommendations = self.adjuster._apply_confidence_capping(recommendations)
        
        self.assertEqual(capped_recommendations[0]['confidence'], 0.95)  # Capped to threshold
        self.assertTrue(capped_recommendations[0]['confidence_capped'])
    
    def test_check_parameter_correlations(self):
        """Test parameter correlation checking."""
        recommendations = [
            {
                'parameter_name': 'risk_per_trade',
                'recommended_value': 0.03,
                'confidence': 0.8,
                'reasoning': 'Test recommendation',
                'source': 'ai_model'
            },
            {
                'parameter_name': 'position_size',
                'recommended_value': 1.5,
                'confidence': 0.8,
                'reasoning': 'Test recommendation',
                'source': 'ai_model'
            }
        ]
        
        correlated_recommendations = self.adjuster._check_parameter_correlations(recommendations)
        
        # Check if correlation adjustments were applied
        self.assertEqual(len(correlated_recommendations), 2)
        # The exact values depend on the correlation adjustment logic
    
    def test_apply_rate_limiting(self):
        """Test rate limiting to parameter changes."""
        # Set up parameter history with previous value
        self.adjuster.parameter_history = [{
            'timestamp': datetime.utcnow().isoformat(),
            'recommendations': [
                {
                    'parameter_name': 'risk_per_trade',
                    'recommended_value': 0.02
                }
            ]
        }]
        
        recommendations = [
            {
                'parameter_name': 'risk_per_trade',
                'recommended_value': 0.04,  # 100% increase
                'confidence': 0.8,
                'reasoning': 'Test recommendation',
                'source': 'ai_model'
            }
        ]
        
        rate_limited_recommendations = self.adjuster._apply_rate_limiting(recommendations)
        
        self.assertTrue(rate_limited_recommendations[0]['rate_limited'])
        self.assertLess(rate_limited_recommendations[0]['recommended_value'], 0.04)
        self.assertEqual(rate_limited_recommendations[0]['previous_value'], 0.02)
    
    def test_generate_fallback_recommendations(self):
        """Test fallback recommendation generation."""
        recommendations = [
            {
                'parameter_name': 'risk_per_trade',
                'recommended_value': 0.15,
                'confidence': 0.2,  # Below threshold
                'validation_status': 'bounds_violation',
                'reasoning': 'Test recommendation',
                'source': 'ai_model'
            }
        ]
        
        fallback_recommendations = self.adjuster._generate_fallback_recommendations(recommendations)
        
        self.assertEqual(len(fallback_recommendations), 1)
        self.assertTrue(fallback_recommendations[0]['is_fallback'])
        self.assertEqual(fallback_recommendations[0]['source'], 'fallback')
        self.assertEqual(fallback_recommendations[0]['recommended_value'], 0.02)  # Default value
    
    def test_get_fallback_predictions(self):
        """Test fallback predictions when model is not trained."""
        # Create untrained adjuster
        untrained_adjuster = AdaptiveParameterAdjuster(
            self.config,
            self.mock_database,
            self.mock_statistics_manager,
            self.mock_logger
        )
        
        result = untrained_adjuster._get_fallback_predictions()
        
        self.assertEqual(result['status'], 'warning')
        self.assertIn('Model is not trained', result['message'])
        self.assertIn('recommendations', result)
        self.assertGreater(len(result['recommendations']), 0)
    
    def test_calculate_optimal_range(self):
        """Test optimal range calculation."""
        # Create data with known correlation
        data = self.sample_data.copy()
        data['target'] = data['close'] > data['close'].quantile(0.7)  # High price = positive target
        
        optimal_range = self.adjuster._calculate_optimal_range(data, 'close', 'target')
        
        self.assertIsInstance(optimal_range, dict)
        if optimal_range:
            self.assertIn('min', optimal_range)
            self.assertIn('max', optimal_range)
    
    def test_assess_data_quality(self):
        """Test data quality assessment."""
        quality = self.adjuster._assess_data_quality(self.sample_data, 'close')
        
        self.assertIsInstance(quality, dict)
        self.assertIn('quality_score', quality)
        self.assertIn('missing_data_ratio', quality)
        self.assertIn('variance_score', quality)
        self.assertIn('data_points', quality)
    
    def test_extract_performance_insights(self):
        """Test performance insights extraction."""
        mock_trades = self._create_mock_trades(10)
        performance_metrics = {
            'win_rate': 0.6,
            'profit_factor': 1.2,
            'sharpe_ratio': 1.5,
            'max_drawdown': 0.1,
            'total_return': 0.15
        }
        
        insights = self.adjuster._extract_performance_insights(mock_trades, performance_metrics)
        
        self.assertIsInstance(insights, dict)
        self.assertIn('total_trades', insights)
        self.assertIn('win_rate', insights)
        self.assertIn('profit_factor', insights)
        self.assertIn('sharpe_ratio', insights)
        self.assertIn('max_drawdown', insights)
        self.assertIn('total_return', insights)
        self.assertIn('trade_duration_stats', insights)
        self.assertIn('volume_stats', insights)
    
    def test_calculate_performance_score(self):
        """Test performance score calculation."""
        performance_insights = {
            'win_rate': 0.6,
            'profit_factor': 1.2,
            'sharpe_ratio': 1.5,
            'total_return': 0.15
        }
        
        score = self.adjuster._calculate_performance_score(performance_insights)
        
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
    
    def test_calculate_trade_duration_stats(self):
        """Test trade duration statistics calculation."""
        mock_trades = self._create_mock_trades(5)
        
        duration_stats = self.adjuster._calculate_trade_duration_stats(mock_trades)
        
        self.assertIsInstance(duration_stats, dict)
        if duration_stats:
            self.assertIn('avg_duration', duration_stats)
            self.assertIn('min_duration', duration_stats)
            self.assertIn('max_duration', duration_stats)
            self.assertIn('median_duration', duration_stats)
    
    def test_calculate_volume_stats(self):
        """Test volume statistics calculation."""
        mock_trades = self._create_mock_trades(5)
        
        volume_stats = self.adjuster._calculate_volume_stats(mock_trades)
        
        self.assertIsInstance(volume_stats, dict)
        if volume_stats:
            self.assertIn('avg_volume', volume_stats)
            self.assertIn('min_volume', volume_stats)
            self.assertIn('max_volume', volume_stats)
            self.assertIn('total_volume', volume_stats)
    
    def test_calculate_correlation_adjustment(self):
        """Test correlation adjustment calculation."""
        primary_rec = {
            'parameter_name': 'risk_per_trade',
            'recommended_value': 0.03
        }
        
        correlated_recs = [
            {
                'parameter_name': 'position_size',
                'recommended_value': 1.5
            }
        ]
        
        adjustment_factor = self.adjuster._calculate_correlation_adjustment(
            primary_rec, correlated_recs, 'risk_per_trade'
        )
        
        self.assertIsInstance(adjustment_factor, float)
        self.assertGreaterEqual(adjustment_factor, 0.0)
    
    def test_get_previous_parameter_value(self):
        """Test getting previous parameter value."""
        # Set up parameter history
        self.adjuster.parameter_history = [{
            'timestamp': datetime.utcnow().isoformat(),
            'recommendations': [
                {
                    'parameter_name': 'risk_per_trade',
                    'recommended_value': 0.02
                }
            ]
        }]
        
        previous_value = self.adjuster._get_previous_parameter_value('risk_per_trade')
        
        self.assertEqual(previous_value, 0.02)
        
        # Test with non-existent parameter
        non_existent_value = self.adjuster._get_previous_parameter_value('non_existent')
        self.assertIsNone(non_existent_value)
    
    def test_calculate_technical_indicators(self):
        """Test technical indicators calculation."""
        result = self.adjuster._calculate_technical_indicators(self.sample_data)
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), len(self.sample_data))
        self.assertIn('sma_20', result.columns)
        self.assertIn('sma_50', result.columns)
        self.assertIn('rsi', result.columns)
        self.assertIn('macd', result.columns)
    
    def _create_mock_trades(self, count):
        """Create mock trades for testing."""
        mock_trades = []
        for i in range(count):
            trade = Mock(spec=Trade)
            trade.id = i + 1
            trade.state = TradeState.COMPLETE
            trade.datetime = datetime.utcnow() - timedelta(hours=i)
            trade.selling = i % 2 == 0
            trade.alt_trade_amount = 1000 + i * 100
            trade.crypto_trade_amount = 500 + i * 50
            mock_trades.append(trade)
        
        return mock_trades


if __name__ == '__main__':
    unittest.main()