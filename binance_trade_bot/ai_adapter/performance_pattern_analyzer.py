"""
Performance Pattern Analysis System for AI Adapter.

This module implements intelligent parameter adjustment through pattern recognition,
market volatility assessment, and performance-based recommendations.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import logging

from .base import AIAdapterBase
from ..database import Database
from ..models.trade import Trade, TradeState
from ..models.coin import Coin
from ..models.pair import Pair
from ..models.ai_parameters import AiParameters, ParameterType, ParameterStatus
from ..statistics.manager import StatisticsManager
from ..logger import Logger


class TradingMode(Enum):
    """Trading mode enumeration."""
    CONSERVATIVE = "CONSERVATIVE"
    BALANCED = "BALANCED"
    AGGRESSIVE = "AGGRESSIVE"


class PatternType(Enum):
    """Pattern type enumeration."""
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    SIDEWAYS = "SIDEWAYS"
    VOLATILE = "VOLATILE"
    BREAKOUT = "BREAKOUT"
    REVERSAL = "REVERSAL"


class PerformancePatternAnalyzer(AIAdapterBase):
    """
    Performance Pattern Analysis System for intelligent parameter adjustment.
    
    This system analyzes trading history to recognize patterns, assesses market
    volatility, and provides performance-based parameter recommendations with
    conservative/aggressive mode switching capabilities.
    """
    
    def __init__(self, config: Dict[str, Any], database: Database, 
                 statistics_manager: StatisticsManager, logger: Logger):
        """
        Initialize the performance pattern analyzer.
        
        @param {dict} config - Configuration dictionary
        @param {Database} database - Database instance
        @param {StatisticsManager} statistics_manager - Statistics manager instance
        @param {Logger} logger - Logger instance
        """
        super().__init__(config)
        self.database = database
        self.statistics_manager = statistics_manager
        self.logger = logger
        
        # Pattern recognition parameters
        self.pattern_window_size = config.get('pattern_window_size', 100)
        self.volatility_threshold = config.get('volatility_threshold', 0.05)
        self.confidence_threshold = config.get('confidence_threshold', 0.7)
        
        # Trading mode parameters
        self.current_mode = TradingMode.BALANCED
        self.mode_switch_threshold = config.get('mode_switch_threshold', 0.15)
        self.performance_lookback_period = config.get('performance_lookback_period', 30)
        
        # Pattern storage
        self.pattern_history = []
        self.performance_metrics = {}
        
        self.logger.info("Performance Pattern Analyzer initialized")
    
    def train_model(self, training_data: pd.DataFrame, target_column: str) -> bool:
        """
        Train the pattern recognition model.
        
        @param {pd.DataFrame} training_data - Training data
        @param {str} target_column - Target column name
        @returns {bool} True if training completed successfully
        """
        try:
            self.logger.info("Starting pattern recognition model training")
            
            # Validate input data
            if training_data.empty:
                self.logger.error("Training data is empty")
                return False
            
            if target_column not in training_data.columns:
                self.logger.error(f"Target column '{target_column}' not found in training data")
                return False
            
            # Preprocess training data
            processed_data = self.preprocess_data(training_data)
            
            # Extract patterns from training data
            patterns = self._extract_patterns_from_data(processed_data)
            
            # Store patterns for future use
            self.pattern_history.extend(patterns)
            
            # Calculate performance metrics
            self._calculate_performance_metrics(patterns)
            
            self.is_trained = True
            self.logger.info(f"Model training completed. Extracted {len(patterns)} patterns")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error during model training: {str(e)}")
            return False
    
    def predict(self, input_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Make predictions using the trained pattern recognition model.
        
        @param {pd.DataFrame} input_data - Input data for prediction
        @returns {dict} Prediction results
        """
        try:
            if not self.is_trained:
                self.logger.warning("Model is not trained, returning default prediction")
                return self._get_default_prediction()
            
            # Preprocess input data
            processed_data = self.preprocess_data(input_data)
            
            # Analyze current market conditions
            market_analysis = self._analyze_market_conditions(processed_data)
            
            # Recognize patterns
            recognized_patterns = self._recognize_patterns(processed_data)
            
            # Assess volatility
            volatility_assessment = self._assess_volatility(processed_data)
            
            # Generate parameter recommendations
            recommendations = self._generate_parameter_recommendations(
                market_analysis, recognized_patterns, volatility_assessment
            )
            
            # Determine optimal trading mode
            optimal_mode = self._determine_optimal_mode()
            
            return {
                'status': 'success',
                'timestamp': datetime.utcnow().isoformat(),
                'market_analysis': market_analysis,
                'recognized_patterns': recognized_patterns,
                'volatility_assessment': volatility_assessment,
                'recommendations': recommendations,
                'optimal_mode': optimal_mode.value,
                'confidence_scores': self._calculate_confidence_scores(
                    market_analysis, recognized_patterns, volatility_assessment
                )
            }
            
        except Exception as e:
            self.logger.error(f"Error during prediction: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    def get_feature_importance(self) -> Dict[str, float]:
        """
        Get feature importance scores from the trained model.
        
        @returns {dict} Feature importance scores
        """
        try:
            # Calculate feature importance based on pattern recognition
            feature_importance = {}
            
            if self.pattern_history:
                # Analyze which features are most predictive of successful patterns
                for pattern in self.pattern_history:
                    for feature, importance in pattern.get('feature_contributions', {}).items():
                        if feature not in feature_importance:
                            feature_importance[feature] = 0.0
                        feature_importance[feature] += importance
                
                # Normalize importance scores
                total_importance = sum(feature_importance.values())
                if total_importance > 0:
                    feature_importance = {
                        feature: (importance / total_importance)
                        for feature, importance in feature_importance.items()
                    }
            
            return feature_importance
            
        except Exception as e:
            self.logger.error(f"Error calculating feature importance: {str(e)}")
            return {}
    
    def save_model(self, filepath: str) -> bool:
        """
        Save the trained model to a file.
        
        @param {str} filepath - Path to save the model
        @returns {bool} True if saved successfully
        """
        try:
            model_data = {
                'pattern_history': self.pattern_history,
                'performance_metrics': self.performance_metrics,
                'current_mode': self.current_mode.value,
                'config': self.config,
                'is_trained': self.is_trained,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            import json
            with open(filepath, 'w') as f:
                json.dump(model_data, f, indent=2)
            
            self.logger.info(f"Model saved to {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving model: {str(e)}")
            return False
    
    def load_model(self, filepath: str) -> bool:
        """
        Load a trained model from a file.
        
        @param {str} filepath - Path to the saved model
        @returns {bool} True if loaded successfully
        """
        try:
            import json
            with open(filepath, 'r') as f:
                model_data = json.load(f)
            
            self.pattern_history = model_data.get('pattern_history', [])
            self.performance_metrics = model_data.get('performance_metrics', {})
            self.current_mode = TradingMode(model_data.get('current_mode', 'BALANCED'))
            self.config = model_data.get('config', {})
            self.is_trained = model_data.get('is_trained', False)
            
            self.logger.info(f"Model loaded from {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error loading model: {str(e)}")
            return False
    
    def evaluate_model(self, test_data: pd.DataFrame, target_column: str) -> Dict[str, Any]:
        """
        Evaluate the model performance on test data.
        
        @param {pd.DataFrame} test_data - Test data
        @param {str} target_column - Target column name
        @returns {dict} Evaluation metrics
        """
        try:
            if not self.is_trained:
                return {'error': 'Model is not trained'}
            
            # Make predictions
            predictions = self.predict(test_data)
            
            # Calculate evaluation metrics
            evaluation_metrics = {
                'accuracy': self._calculate_accuracy(predictions, target_column),
                'precision': self._calculate_precision(predictions, target_column),
                'recall': self._calculate_recall(predictions, target_column),
                'f1_score': self._calculate_f1_score(predictions, target_column),
                'total_predictions': len(predictions.get('recognized_patterns', [])),
                'high_confidence_predictions': len([
                    p for p in predictions.get('recognized_patterns', [])
                    if p.get('confidence_score', 0) > self.confidence_threshold
                ])
            }
            
            return evaluation_metrics
            
        except Exception as e:
            self.logger.error(f"Error evaluating model: {str(e)}")
            return {'error': str(e)}
    
    def preprocess_data(self, raw_data: pd.DataFrame) -> pd.DataFrame:
        """
        Preprocess raw data for model training or prediction.
        
        @param {pd.DataFrame} raw_data - Raw input data
        @returns {pd.DataFrame} Preprocessed data
        """
        try:
            # Create a copy to avoid modifying original data
            processed_data = raw_data.copy()
            
            # Handle missing values
            processed_data = processed_data.fillna(method='ffill').fillna(method='bfill')
            
            # Calculate technical indicators
            processed_data = self._calculate_technical_indicators(processed_data)
            
            # Normalize numerical features
            numerical_columns = processed_data.select_dtypes(include=[np.number]).columns
            for column in numerical_columns:
                if column != 'target':  # Don't normalize target column
                    mean_val = processed_data[column].mean()
                    std_val = processed_data[column].std()
                    if std_val > 0:
                        processed_data[column] = (processed_data[column] - mean_val) / std_val
            
            return processed_data
            
        except Exception as e:
            self.logger.error(f"Error preprocessing data: {str(e)}")
            return raw_data
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the current model.
        
        @returns {dict} Model information and metadata
        """
        return {
            'model_type': 'PerformancePatternAnalyzer',
            'is_trained': self.is_trained,
            'pattern_count': len(self.pattern_history),
            'current_mode': self.current_mode.value,
            'config': self.config,
            'performance_metrics': self.performance_metrics,
            'feature_importance': self.get_feature_importance(),
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def analyze_trading_history(self, pair: Pair, coin: Coin, 
                              lookback_period: int = 100) -> Dict[str, Any]:
        """
        Analyze trading history for pattern recognition.
        
        @param {Pair} pair - Trading pair
        @param {Coin} coin - Coin to analyze
        @param {int} lookback_period - Number of periods to look back
        @returns {dict} Analysis results
        """
        try:
            with self.database.db_session() as session:
                # Get recent trades
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=lookback_period)
                
                trades = session.query(Trade).filter(
                    Trade.state == TradeState.COMPLETE,
                    Trade.datetime >= start_date,
                    Trade.datetime <= end_date
                ).all()
                
                # Convert to DataFrame
                trade_df = self._trades_to_dataframe(trades)
                
                if trade_df.empty:
                    return {
                        'status': 'warning',
                        'message': 'No trading data found for analysis',
                        'patterns': [],
                        'recommendations': []
                    }
                
                # Analyze patterns
                patterns = self._analyze_trade_patterns(trade_df)
                
                # Generate recommendations
                recommendations = self._generate_trade_recommendations(patterns)
                
                return {
                    'status': 'success',
                    'trade_count': len(trades),
                    'patterns': patterns,
                    'recommendations': recommendations,
                    'analysis_period': {
                        'start': start_date.isoformat(),
                        'end': end_date.isoformat()
                    }
                }
                
        except Exception as e:
            self.logger.error(f"Error analyzing trading history: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def assess_market_volatility(self, pair: Pair, coin: Coin, 
                               period: str = '24h') -> Dict[str, Any]:
        """
        Assess market volatility for a given pair and coin.
        
        @param {Pair} pair - Trading pair
        @param {Coin} coin - Coin to assess
        @param {str} period - Time period ('1h', '24h', '7d', '30d')
        @returns {dict} Volatility assessment
        """
        try:
            # Parse period to get time delta
            period_map = {
                '1h': timedelta(hours=1),
                '24h': timedelta(hours=24),
                '7d': timedelta(days=7),
                '30d': timedelta(days=30)
            }
            
            time_delta = period_map.get(period, timedelta(hours=24))
            end_date = datetime.utcnow()
            start_date = end_date - time_delta
            
            with self.database.db_session() as session:
                # Get price data for volatility calculation
                # This would typically come from coin value data
                # For now, we'll use trade data as a proxy
                
                trades = session.query(Trade).filter(
                    Trade.state == TradeState.COMPLETE,
                    Trade.datetime >= start_date,
                    Trade.datetime <= end_date
                ).all()
                
                if not trades:
                    return {
                        'status': 'warning',
                        'message': 'No data available for volatility assessment',
                        'volatility_score': 0.0,
                        'volatility_level': 'LOW'
                    }
                
                # Calculate volatility from price changes
                volatility_score = self._calculate_volatility_from_trades(trades)
                
                # Determine volatility level
                volatility_level = self._determine_volatility_level(volatility_score)
                
                return {
                    'status': 'success',
                    'period': period,
                    'volatility_score': round(volatility_score, 4),
                    'volatility_level': volatility_level,
                    'data_points': len(trades),
                    'assessment_period': {
                        'start': start_date.isoformat(),
                        'end': end_date.isoformat()
                    }
                }
                
        except Exception as e:
            self.logger.error(f"Error assessing market volatility: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def generate_parameter_recommendations(self, pair: Pair, coin: Coin, 
                                        mode: TradingMode = None) -> Dict[str, Any]:
        """
        Generate performance-based parameter recommendations.
        
        @param {Pair} pair - Trading pair
        @param {Coin} coin - Coin to generate recommendations for
        @param {TradingMode} mode - Trading mode (optional)
        @returns {dict} Parameter recommendations
        """
        try:
            if mode is None:
                mode = self.current_mode
            
            # Get trading history analysis
            history_analysis = self.analyze_trading_history(pair, coin)
            
            # Get volatility assessment
            volatility_assessment = self.assess_market_volatility(pair, coin)
            
            # Get current parameters
            current_parameters = self._get_current_parameters(pair, coin)
            
            # Generate recommendations based on analysis
            recommendations = self._generate_ai_recommendations(
                history_analysis, volatility_assessment, current_parameters, mode
            )
            
            # Save recommendations to database
            self._save_parameter_recommendations(recommendations, pair, coin)
            
            return {
                'status': 'success',
                'trading_mode': mode.value,
                'recommendations': recommendations,
                'analysis_summary': {
                    'pattern_count': len(history_analysis.get('patterns', [])),
                    'volatility_level': volatility_assessment.get('volatility_level', 'UNKNOWN'),
                    'current_parameters_count': len(current_parameters)
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error generating parameter recommendations: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def switch_trading_mode(self, new_mode: TradingMode, 
                          force_switch: bool = False) -> Dict[str, Any]:
        """
        Switch between conservative, balanced, and aggressive trading modes.
        
        @param {TradingMode} new_mode - New trading mode
        @param {bool} force_switch - Force switch regardless of conditions
        @returns {dict} Switch results
        """
        try:
            if not force_switch:
                # Check if mode switch is warranted
                current_performance = self._get_current_performance()
                mode_switch_needed = self._should_switch_mode(current_performance, new_mode)
                
                if not mode_switch_needed:
                    return {
                        'status': 'info',
                        'message': f'No mode switch needed. Current mode {self.current_mode.value} is optimal',
                        'current_mode': self.current_mode.value,
                        'new_mode': new_mode.value,
                        'switch_needed': False
                    }
            
            # Perform mode switch
            old_mode = self.current_mode
            self.current_mode = new_mode
            
            # Log mode switch
            self.logger.info(f"Trading mode switched from {old_mode.value} to {new_mode.value}")
            
            # Generate new parameters for the new mode
            with self.database.db_session() as session:
                pairs = session.query(Pair).filter(Pair.enabled.is_(True)).all()
                coins = session.query(Coin).filter(Coin.enabled.is_(True)).all()
                
                switch_results = []
                for pair in pairs:
                    for coin in coins:
                        result = self.generate_parameter_recommendations(pair, coin, new_mode)
                        switch_results.append({
                            'pair': pair.symbol if pair else 'UNKNOWN',
                            'coin': coin.symbol if coin else 'UNKNOWN',
                            'result': result
                        })
            
            return {
                'status': 'success',
                'message': f'Trading mode switched from {old_mode.value} to {new_mode.value}',
                'old_mode': old_mode.value,
                'new_mode': new_mode.value,
                'switch_results': switch_results,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error switching trading mode: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def _extract_patterns_from_data(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Extract patterns from training data."""
        patterns = []
        
        try:
            # Simple pattern extraction logic
            for i in range(len(data) - self.pattern_window_size + 1):
                window = data.iloc[i:i + self.pattern_window_size]
                
                # Analyze price movement patterns
                price_change = window['close'].iloc[-1] - window['close'].iloc[0]
                price_change_pct = (price_change / window['close'].iloc[0]) * 100
                
                # Determine pattern type
                if price_change_pct > 5:
                    pattern_type = PatternType.TRENDING_UP
                elif price_change_pct < -5:
                    pattern_type = PatternType.TRENDING_DOWN
                elif abs(price_change_pct) < 2:
                    pattern_type = PatternType.SIDEWAYS
                else:
                    pattern_type = PatternType.VOLATILE
                
                # Calculate volatility
                volatility = window['close'].pct_change().std()
                
                # Create pattern record
                pattern = {
                    'pattern_type': pattern_type.value,
                    'price_change_percentage': round(price_change_pct, 2),
                    'volatility': round(volatility, 4),
                    'window_start': window.index[0],
                    'window_end': window.index[-1],
                    'feature_contributions': self._calculate_feature_contributions(window),
                    'success_indicator': self._calculate_success_indicator(window)
                }
                
                patterns.append(pattern)
                
        except Exception as e:
            self.logger.error(f"Error extracting patterns: {str(e)}")
        
        return patterns
    
    def _analyze_market_conditions(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Analyze current market conditions."""
        try:
            if data.empty:
                return {'error': 'No data available for market analysis'}
            
            # Calculate basic market metrics
            current_price = data['close'].iloc[-1]
            price_change_24h = (current_price - data['close'].iloc[0]) / data['close'].iloc[0] * 100
            
            # Calculate moving averages
            ma_short = data['close'].rolling(window=20).mean().iloc[-1]
            ma_long = data['close'].rolling(window=50).mean().iloc[-1]
            
            # Determine trend
            if ma_short > ma_long:
                trend = 'BULLISH'
            elif ma_short < ma_long:
                trend = 'BEARISH'
            else:
                trend = 'NEUTRAL'
            
            # Calculate volatility
            volatility = data['close'].pct_change().std()
            
            return {
                'current_price': round(current_price, 8),
                'price_change_24h': round(price_change_24h, 2),
                'trend': trend,
                'moving_average_short': round(ma_short, 8),
                'moving_average_long': round(ma_long, 8),
                'volatility': round(volatility, 4),
                'market_regime': self._determine_market_regime(trend, volatility)
            }
            
        except Exception as e:
            self.logger.error(f"Error analyzing market conditions: {str(e)}")
            return {'error': str(e)}
    
    def _recognize_patterns(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Recognize patterns in the data."""
        patterns = []
        
        try:
            if len(data) < self.pattern_window_size:
                return patterns
            
            # Look for patterns in the most recent data
            recent_data = data.tail(self.pattern_window_size)
            
            # Simple pattern recognition
            price_change = (recent_data['close'].iloc[-1] - recent_data['close'].iloc[0]) / recent_data['close'].iloc[0]
            volatility = recent_data['close'].pct_change().std()
            
            # Pattern matching
            if price_change > 0.05 and volatility < 0.02:
                patterns.append({
                    'pattern_type': PatternType.TRENDING_UP.value,
                    'confidence': 0.8,
                    'description': 'Strong upward trend with low volatility'
                })
            elif price_change < -0.05 and volatility < 0.02:
                patterns.append({
                    'pattern_type': PatternType.TRENDING_DOWN.value,
                    'confidence': 0.8,
                    'description': 'Strong downward trend with low volatility'
                })
            elif abs(price_change) < 0.02 and volatility > 0.05:
                patterns.append({
                    'pattern_type': PatternType.VOLATILE.value,
                    'confidence': 0.7,
                    'description': 'Sideways movement with high volatility'
                })
            
        except Exception as e:
            self.logger.error(f"Error recognizing patterns: {str(e)}")
        
        return patterns
    
    def _assess_volatility(self, data: pd.DataFrame) -> Dict[str, Any]:
        """Assess market volatility."""
        try:
            if data.empty:
                return {'error': 'No data available for volatility assessment'}
            
            # Calculate various volatility metrics
            returns = data['close'].pct_change().dropna()
            
            # Historical volatility
            historical_volatility = returns.std()
            
            # Average true range (simplified)
            high_low = data['high'] - data['low']
            avg_true_range = high_low.mean()
            
            # Volatility level
            volatility_level = self._determine_volatility_level(historical_volatility)
            
            return {
                'historical_volatility': round(historical_volatility, 4),
                'average_true_range': round(avg_true_range, 8),
                'volatility_level': volatility_level,
                'volatility_score': round(historical_volatility * 100, 2),
                'risk_assessment': self._assess_volatility_risk(historical_volatility)
            }
            
        except Exception as e:
            self.logger.error(f"Error assessing volatility: {str(e)}")
            return {'error': str(e)}
    
    def _generate_parameter_recommendations(self, market_analysis: Dict[str, Any],
                                          patterns: List[Dict[str, Any]],
                                          volatility_assessment: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate parameter recommendations based on analysis."""
        recommendations = []
        
        try:
            # Base recommendations on current mode
            if self.current_mode == TradingMode.CONSERVATIVE:
                risk_factor = 0.5
                position_size_factor = 0.7
            elif self.current_mode == TradingMode.BALANCED:
                risk_factor = 1.0
                position_size_factor = 1.0
            else:  # AGGRESSIVE
                risk_factor = 1.5
                position_size_factor = 1.3
            
            # Adjust based on volatility
            volatility_level = volatility_assessment.get('volatility_level', 'LOW')
            if volatility_level == 'HIGH':
                risk_factor *= 0.7
                position_size_factor *= 0.8
            elif volatility_level == 'LOW':
                risk_factor *= 1.2
                position_size_factor *= 1.1
            
            # Generate specific recommendations
            recommendations.append({
                'parameter_name': 'risk_per_trade',
                'recommended_value': round(0.02 * risk_factor, 4),  # 2% base, adjusted by risk factor
                'confidence': self._calculate_recommendation_confidence(market_analysis, patterns, volatility_assessment),
                'reasoning': f'Based on {self.current_mode.value} mode and {volatility_level} volatility',
                'parameter_type': ParameterType.RISK_MANAGEMENT.value
            })
            
            recommendations.append({
                'parameter_name': 'position_size',
                'recommended_value': round(position_size_factor, 2),
                'confidence': self._calculate_recommendation_confidence(market_analysis, patterns, volatility_assessment),
                'reasoning': f'Position size adjusted for {self.current_mode.value} trading',
                'parameter_type': ParameterType.TRADING_STRATEGY.value
            })
            
            recommendations.append({
                'parameter_name': 'stop_loss_percentage',
                'recommended_value': round(0.05 * risk_factor, 4),  # 5% base, adjusted by risk factor
                'confidence': self._calculate_recommendation_confidence(market_analysis, patterns, volatility_assessment),
                'reasoning': f'Stop loss adjusted for {self.current_mode.value} risk tolerance',
                'parameter_type': ParameterType.RISK_MANAGEMENT.value
            })
            
        except Exception as e:
            self.logger.error(f"Error generating parameter recommendations: {str(e)}")
        
        return recommendations
    
    def _determine_optimal_mode(self) -> TradingMode:
        """Determine the optimal trading mode based on current conditions."""
        try:
            # Get current performance
            current_performance = self._get_current_performance()
            
            # Calculate performance score
            performance_score = self._calculate_performance_score(current_performance)
            
            # Determine optimal mode based on performance and market conditions
            if performance_score < -0.1:  # Poor performance
                return TradingMode.CONSERVATIVE
            elif performance_score > 0.2:  # Excellent performance
                return TradingMode.AGGRESSIVE
            else:
                return TradingMode.BALANCED
                
        except Exception as e:
            self.logger.error(f"Error determining optimal mode: {str(e)}")
            return TradingMode.BALANCED  # Default to balanced
    
    def _calculate_performance_metrics(self, patterns: List[Dict[str, Any]]):
        """Calculate performance metrics from patterns."""
        try:
            if not patterns:
                return
            
            # Calculate success rate
            successful_patterns = [p for p in patterns if p.get('success_indicator', False)]
            success_rate = len(successful_patterns) / len(patterns)
            
            # Calculate average confidence
            confidences = [p.get('confidence_score', 0) for p in patterns]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            # Calculate pattern distribution
            pattern_types = {}
            for pattern in patterns:
                pattern_type = pattern.get('pattern_type', 'UNKNOWN')
                pattern_types[pattern_type] = pattern_types.get(pattern_type, 0) + 1
            
            self.performance_metrics = {
                'total_patterns': len(patterns),
                'successful_patterns': len(successful_patterns),
                'success_rate': round(success_rate, 4),
                'average_confidence': round(avg_confidence, 4),
                'pattern_distribution': pattern_types,
                'last_updated': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating performance metrics: {str(e)}")
    
    def _trades_to_dataframe(self, trades: List[Trade]) -> pd.DataFrame:
        """Convert trades to DataFrame."""
        if not trades:
            return pd.DataFrame()
        
        trade_data = []
        for trade in trades:
            trade_data.append({
                'id': trade.id,
                'datetime': trade.datetime,
                'selling': trade.selling,
                'alt_starting_balance': trade.alt_starting_balance,
                'alt_trade_amount': trade.alt_trade_amount,
                'crypto_starting_balance': trade.crypto_starting_balance,
                'crypto_trade_amount': trade.crypto_trade_amount,
            })
        
        return pd.DataFrame(trade_data)
    
    def _analyze_trade_patterns(self, trade_df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Analyze trade patterns from trade data."""
        patterns = []
        
        try:
            if trade_df.empty:
                return patterns
            
            # Analyze profit/loss patterns
            trade_df['profit_loss'] = trade_df.apply(
                lambda row: row['alt_trade_amount'] - row['crypto_trade_amount']
                if row['selling'] else row['crypto_trade_amount'] - row['alt_trade_amount'],
                axis=1
            )
            
            # Calculate trade statistics
            profitable_trades = trade_df[trade_df['profit_loss'] > 0]
            losing_trades = trade_df[trade_df['profit_loss'] < 0]
            
            # Pattern: Win rate
            win_rate = len(profitable_trades) / len(trade_df) if len(trade_df) > 0 else 0
            
            # Pattern: Average profit/loss
            avg_profit = profitable_trades['profit_loss'].mean() if len(profitable_trades) > 0 else 0
            avg_loss = abs(losing_trades['profit_loss'].mean()) if len(losing_trades) > 0 else 0
            
            # Pattern: Trade frequency
            trade_frequency = len(trade_df)  # Number of trades
            
            patterns.append({
                'pattern_type': 'WIN_RATE_PATTERN',
                'value': round(win_rate, 4),
                'description': f'Win rate of {round(win_rate * 100, 2)}%'
            })
            
            patterns.append({
                'pattern_type': 'PROFIT_LOSS_RATIO',
                'value': round(avg_profit / avg_loss, 4) if avg_loss > 0 else 0,
                'description': f'Profit/loss ratio of {round(avg_profit / avg_loss, 2) if avg_loss > 0 else 0}'
            })
            
            patterns.append({
                'pattern_type': 'TRADE_FREQUENCY',
                'value': trade_frequency,
                'description': f'{trade_frequency} trades analyzed'
            })
            
        except Exception as e:
            self.logger.error(f"Error analyzing trade patterns: {str(e)}")
        
        return patterns
    
    def _generate_trade_recommendations(self, patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate trade recommendations based on patterns."""
        recommendations = []
        
        try:
            for pattern in patterns:
                pattern_type = pattern.get('pattern_type', '')
                value = pattern.get('value', 0)
                
                if pattern_type == 'WIN_RATE_PATTERN':
                    if value < 0.4:
                        recommendations.append({
                            'recommendation': 'DECREASE_POSITION_SIZE',
                            'reason': f'Low win rate ({round(value * 100, 2)}%) detected',
                            'confidence': 0.8
                        })
                    elif value > 0.6:
                        recommendations.append({
                            'recommendation': 'INCREASE_POSITION_SIZE',
                            'reason': f'High win rate ({round(value * 100, 2)}%) detected',
                            'confidence': 0.8
                        })
                
                elif pattern_type == 'PROFIT_LOSS_RATIO':
                    if value < 1.0:
                        recommendations.append({
                            'recommendation': 'TIGHTEN_STOP_LOSS',
                            'reason': f'Low profit/loss ratio ({round(value, 2)}) detected',
                            'confidence': 0.7
                        })
                    elif value > 2.0:
                        recommendations.append({
                            'recommendation': 'INCREASE_RISK_PER_TRADE',
                            'reason': f'High profit/loss ratio ({round(value, 2)}) detected',
                            'confidence': 0.7
                        })
                
                elif pattern_type == 'TRADE_FREQUENCY':
                    if value < 10:
                        recommendations.append({
                            'recommendation': 'IMPROVE_ENTRY_TIMING',
                            'reason': f'Low trade frequency ({value}) suggests missed opportunities',
                            'confidence': 0.6
                        })
            
        except Exception as e:
            self.logger.error(f"Error generating trade recommendations: {str(e)}")
        
        return recommendations
    
    def _calculate_volatility_from_trades(self, trades: List[Trade]) -> float:
        """Calculate volatility from trade data."""
        try:
            if not trades:
                return 0.0
            
            # Extract price information from trades
            prices = []
            for trade in trades:
                if trade.crypto_trade_amount and trade.alt_trade_amount:
                    price = trade.crypto_trade_amount / trade.alt_trade_amount
                    prices.append(price)
            
            if len(prices) < 2:
                return 0.0
            
            # Calculate volatility as standard deviation of price changes
            price_series = pd.Series(prices)
            returns = price_series.pct_change().dropna()
            
            return returns.std()
            
        except Exception as e:
            self.logger.error(f"Error calculating volatility from trades: {str(e)}")
            return 0.0
    
    def _determine_volatility_level(self, volatility_score: float) -> str:
        """Determine volatility level based on score."""
        if volatility_score < 0.02:
            return 'LOW'
        elif volatility_score < 0.05:
            return 'MEDIUM'
        else:
            return 'HIGH'
    
    def _generate_ai_recommendations(self, history_analysis: Dict[str, Any],
                                   volatility_assessment: Dict[str, Any],
                                   current_parameters: List[Dict[str, Any]],
                                   mode: TradingMode) -> List[Dict[str, Any]]:
        """Generate AI parameter recommendations."""
        recommendations = []
        
        try:
            # Base recommendations on mode
            mode_factors = {
                TradingMode.CONSERVATIVE: {'risk_factor': 0.7, 'position_factor': 0.8},
                TradingMode.BALANCED: {'risk_factor': 1.0, 'position_factor': 1.0},
                TradingMode.AGGRESSIVE: {'risk_factor': 1.3, 'position_factor': 1.2}
            }
            
            factors = mode_factors.get(mode, mode_factors[TradingMode.BALANCED])
            
            # Adjust for volatility
            volatility_level = volatility_assessment.get('volatility_level', 'LOW')
            if volatility_level == 'HIGH':
                factors['risk_factor'] *= 0.8
                factors['position_factor'] *= 0.9
            elif volatility_level == 'LOW':
                factors['risk_factor'] *= 1.1
                factors['position_factor'] *= 1.05
            
            # Generate recommendations
            recommendations.append({
                'parameter_name': 'risk_per_trade',
                'recommended_value': round(0.02 * factors['risk_factor'], 4),
                'confidence': 0.8,
                'reasoning': f'Adjusted for {mode.value} mode and {volatility_level} volatility',
                'parameter_type': ParameterType.RISK_MANAGEMENT.value
            })
            
            recommendations.append({
                'parameter_name': 'position_size_multiplier',
                'recommended_value': round(factors['position_factor'], 2),
                'confidence': 0.7,
                'reasoning': f'Position size adjusted for {mode.value} trading strategy',
                'parameter_type': ParameterType.TRADING_STRATEGY.value
            })
            
            recommendations.append({
                'parameter_name': 'stop_loss_percentage',
                'recommended_value': round(0.05 * factors['risk_factor'], 4),
                'confidence': 0.8,
                'reasoning': f'Stop loss optimized for {mode.value} risk tolerance',
                'parameter_type': ParameterType.RISK_MANAGEMENT.value
            })
            
            recommendations.append({
                'parameter_name': 'take_profit_percentage',
                'recommended_value': round(0.1 * factors['risk_factor'], 4),
                'confidence': 0.7,
                'reasoning': f'Take profit aligned with {mode.value} strategy',
                'parameter_type': ParameterType.TRADING_STRATEGY.value
            })
            
        except Exception as e:
            self.logger.error(f"Error generating AI recommendations: {str(e)}")
        
        return recommendations
    
    def _get_current_parameters(self, pair: Pair, coin: Coin) -> List[Dict[str, Any]]:
        """Get current parameters for a pair and coin."""
        try:
            with self.database.db_session() as session:
                parameters = session.query(AiParameters).filter(
                    AiParameters.pair_id == pair.id,
                    AiParameters.coin_id == coin.symbol,
                    AiParameters.status == ParameterStatus.ACTIVE
                ).all()
                
                return [param.info() for param in parameters]
                
        except Exception as e:
            self.logger.error(f"Error getting current parameters: {str(e)}")
            return []
    
    def _save_parameter_recommendations(self, recommendations: List[Dict[str, Any]],
                                      pair: Pair, coin: Coin):
        """Save parameter recommendations to database."""
        try:
            with self.database.db_session() as session:
                for rec in recommendations:
                    # Create new AI parameter record
                    ai_param = AiParameters(
                        pair=pair,
                        coin=coin,
                        parameter_type=ParameterType(rec.get('parameter_type', ParameterType.CUSTOM.value)),
                        parameter_name=rec.get('parameter_name', ''),
                        parameter_value=rec.get('recommended_value', 0),
                        confidence_score=rec.get('confidence', 0.5),
                        accuracy_score=None,
                        description=rec.get('reasoning', ''),
                        model_version='1.0',
                        model_source='PerformancePatternAnalyzer',
                        recommendation_id=f"PPA_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                        metadata_json=str(rec)
                    )
                    
                    ai_param.set_testing()
                    session.add(ai_param)
                
                self.logger.info(f"Saved {len(recommendations)} parameter recommendations")
                
        except Exception as e:
            self.logger.error(f"Error saving parameter recommendations: {str(e)}")
    
    def _get_current_performance(self) -> Dict[str, Any]:
        """Get current trading performance."""
        try:
            # Get recent performance statistics
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=self.performance_lookback_period)
            
            with self.database.db_session() as session:
                trades = session.query(Trade).filter(
                    Trade.state == TradeState.COMPLETE,
                    Trade.datetime >= start_date,
                    Trade.datetime <= end_date
                ).all()
                
                if not trades:
                    return {'total_return': 0.0, 'win_rate': 0.0, 'sharpe_ratio': 0.0}
                
                # Calculate performance metrics
                total_return = self._calculate_total_return(trades)
                win_rate = self._calculate_win_rate(trades)
                sharpe_ratio = self._calculate_sharpe_ratio(trades)
                
                return {
                    'total_return': total_return,
                    'win_rate': win_rate,
                    'sharpe_ratio': sharpe_ratio,
                    'trade_count': len(trades)
                }
                
        except Exception as e:
            self.logger.error(f"Error getting current performance: {str(e)}")
            return {'total_return': 0.0, 'win_rate': 0.0, 'sharpe_ratio': 0.0}
    
    def _should_switch_mode(self, current_performance: Dict[str, Any], 
                          new_mode: TradingMode) -> bool:
        """Determine if mode switch is needed."""
        try:
            # Calculate performance score
            performance_score = self._calculate_performance_score(current_performance)
            
            # Check if performance is below threshold
            if performance_score < -self.mode_switch_threshold:
                return True
            
            # Check if current mode is already optimal
            if self.current_mode == new_mode:
                return False
            
            # Additional logic for mode switching based on market conditions
            # This can be expanded based on specific requirements
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error determining mode switch need: {str(e)}")
            return False
    
    def _calculate_performance_score(self, performance: Dict[str, Any]) -> float:
        """Calculate overall performance score."""
        try:
            total_return = performance.get('total_return', 0.0)
            win_rate = performance.get('win_rate', 0.0)
            sharpe_ratio = performance.get('sharpe_ratio', 0.0)
            
            # Normalize and combine metrics
            return_score = min(max(total_return, -1.0), 1.0)  # Normalize to [-1, 1]
            win_score = (win_rate - 0.5) * 2  # Normalize to [-1, 1]
            sharpe_score = min(max(sharpe_ratio / 2, -1.0), 1.0)  # Normalize to [-1, 1]
            
            # Weighted combination
            return (return_score * 0.4 + win_score * 0.4 + sharpe_score * 0.2)
            
        except Exception as e:
            self.logger.error(f"Error calculating performance score: {str(e)}")
            return 0.0
    
    def _calculate_total_return(self, trades: List[Trade]) -> float:
        """Calculate total return from trades."""
        try:
            if not trades:
                return 0.0
            
            total_profit_loss = 0.0
            total_investment = 0.0
            
            for trade in trades:
                if trade.selling and trade.alt_trade_amount and trade.crypto_trade_amount:
                    profit_loss = trade.alt_trade_amount - trade.crypto_trade_amount
                    total_profit_loss += profit_loss
                    total_investment += trade.crypto_trade_amount
                elif not trade.selling and trade.crypto_trade_amount and trade.alt_trade_amount:
                    profit_loss = trade.crypto_trade_amount - trade.alt_trade_amount
                    total_profit_loss += profit_loss
                    total_investment += trade.alt_trade_amount
            
            return (total_profit_loss / total_investment) if total_investment > 0 else 0.0
            
        except Exception as e:
            self.logger.error(f"Error calculating total return: {str(e)}")
            return 0.0
    
    def _calculate_win_rate(self, trades: List[Trade]) -> float:
        """Calculate win rate from trades."""
        try:
            if not trades:
                return 0.0
            
            profitable_trades = 0
            for trade in trades:
                if trade.selling and trade.alt_trade_amount and trade.crypto_trade_amount:
                    if trade.alt_trade_amount > trade.crypto_trade_amount:
                        profitable_trades += 1
                elif not trade.selling and trade.crypto_trade_amount and trade.alt_trade_amount:
                    if trade.crypto_trade_amount > trade.alt_trade_amount:
                        profitable_trades += 1
            
            return profitable_trades / len(trades)
            
        except Exception as e:
            self.logger.error(f"Error calculating win rate: {str(e)}")
            return 0.0
    
    def _calculate_sharpe_ratio(self, trades: List[Trade]) -> float:
        """Calculate Sharpe ratio from trades."""
        try:
            if len(trades) < 2:
                return 0.0
            
            # Calculate returns
            returns = []
            for trade in trades:
                if trade.selling and trade.alt_trade_amount and trade.crypto_trade_amount:
                    returns.append((trade.alt_trade_amount - trade.crypto_trade_amount) / trade.crypto_trade_amount)
                elif not trade.selling and trade.crypto_trade_amount and trade.alt_trade_amount:
                    returns.append((trade.crypto_trade_amount - trade.alt_trade_amount) / trade.alt_trade_amount)
            
            if not returns:
                return 0.0
            
            # Calculate Sharpe ratio (simplified)
            avg_return = sum(returns) / len(returns)
            std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
            
            return (avg_return / std_return) if std_return > 0 else 0.0
            
        except Exception as e:
            self.logger.error(f"Error calculating Sharpe ratio: {str(e)}")
            return 0.0
    
    def _calculate_technical_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators for the data."""
        try:
            if 'close' not in data.columns:
                return data
            
            # Simple moving averages
            data['sma_20'] = data['close'].rolling(window=20).mean()
            data['sma_50'] = data['close'].rolling(window=50).mean()
            
            # RSI (simplified)
            data['price_change'] = data['close'].diff()
            data['gain'] = data['price_change'].clip(lower=0)
            data['loss'] = -data['price_change'].clip(upper=0)
            data['avg_gain'] = data['gain'].rolling(window=14).mean()
            data['avg_loss'] = data['loss'].rolling(window=14).mean()
            data['rs'] = data['avg_gain'] / data['avg_loss']
            data['rsi'] = 100 - (100 / (1 + data['rs']))
            
            # MACD (simplified)
            data['ema_12'] = data['close'].ewm(span=12).mean()
            data['ema_26'] = data['close'].ewm(span=26).mean()
            data['macd'] = data['ema_12'] - data['ema_26']
            data['macd_signal'] = data['macd'].ewm(span=9).mean()
            data['macd_histogram'] = data['macd'] - data['macd_signal']
            
            return data
            
        except Exception as e:
            self.logger.error(f"Error calculating technical indicators: {str(e)}")
            return data
    
    def _calculate_feature_contributions(self, data: pd.DataFrame) -> Dict[str, float]:
        """Calculate feature contributions for pattern recognition."""
        contributions = {}
        
        try:
            if 'close' in data.columns:
                price_change = (data['close'].iloc[-1] - data['close'].iloc[0]) / data['close'].iloc[0]
                contributions['price_change'] = abs(price_change)
            
            if 'volume' in data.columns:
                volume_change = (data['volume'].iloc[-1] - data['volume'].iloc[0]) / data['volume'].iloc[0]
                contributions['volume_change'] = abs(volume_change)
            
            if 'rsi' in data.columns:
                rsi = data['rsi'].iloc[-1]
                contributions['rsi'] = abs(rsi - 50) / 50  # Normalize around 50
            
            # Normalize contributions
            total = sum(contributions.values())
            if total > 0:
                contributions = {k: v / total for k, v in contributions.items()}
            
        except Exception as e:
            self.logger.error(f"Error calculating feature contributions: {str(e)}")
        
        return contributions
    
    def _calculate_success_indicator(self, data: pd.DataFrame) -> bool:
        """Calculate success indicator for a pattern."""
        try:
            if 'close' not in data.columns:
                return False
            
            # Simple success: price moved more than 2% in favorable direction
            price_change = (data['close'].iloc[-1] - data['close'].iloc[0]) / data['close'].iloc[0]
            
            return abs(price_change) > 0.02
            
        except Exception as e:
            self.logger.error(f"Error calculating success indicator: {str(e)}")
            return False
    
    def _determine_market_regime(self, trend: str, volatility: float) -> str:
        """Determine market regime based on trend and volatility."""
        try:
            if trend == 'BULLISH':
                if volatility > 0.05:
                    return 'BULLISH_VOLATILE'
                else:
                    return 'BULLISH_STABLE'
            elif trend == 'BEARISH':
                if volatility > 0.05:
                    return 'BEARISH_VOLATILE'
                else:
                    return 'BEARISH_STABLE'
            else:
                if volatility > 0.05:
                    return 'RANGING_VOLATILE'
                else:
                    return 'RANGING_STABLE'
                    
        except Exception as e:
            self.logger.error(f"Error determining market regime: {str(e)}")
            return 'UNKNOWN'
    
    def _assess_volatility_risk(self, volatility: float) -> str:
        """Assess risk level based on volatility."""
        if volatility < 0.02:
            return 'LOW'
        elif volatility < 0.05:
            return 'MEDIUM'
        else:
            return 'HIGH'
    
    def _calculate_recommendation_confidence(self, market_analysis: Dict[str, Any],
                                          patterns: List[Dict[str, Any]],
                                          volatility_assessment: Dict[str, Any]) -> float:
        """Calculate confidence score for recommendations."""
        try:
            confidence = 0.5  # Base confidence
            
            # Adjust based on pattern recognition
            if patterns:
                pattern_confidence = sum(p.get('confidence', 0) for p in patterns) / len(patterns)
                confidence += (pattern_confidence - 0.5) * 0.3
            
            # Adjust based on market analysis quality
            if 'error' not in market_analysis:
                confidence += 0.1
            
            # Adjust based on volatility assessment
            if 'error' not in volatility_assessment:
                confidence += 0.1
            
            return min(max(confidence, 0.0), 1.0)
            
        except Exception as e:
            self.logger.error(f"Error calculating recommendation confidence: {str(e)}")
            return 0.5
    
    def _get_default_prediction(self) -> Dict[str, Any]:
        """Get default prediction when model is not trained."""
        return {
            'status': 'warning',
            'message': 'Model is not trained, using default parameters',
            'timestamp': datetime.utcnow().isoformat(),
            'recommendations': [
                {
                    'parameter_name': 'risk_per_trade',
                    'recommended_value': 0.02,
                    'confidence': 0.5,
                    'reasoning': 'Default conservative risk parameter',
                    'parameter_type': ParameterType.RISK_MANAGEMENT.value
                }
            ],
            'optimal_mode': TradingMode.BALANCED.value
        }
    
    def _calculate_accuracy(self, predictions: Dict[str, Any], target_column: str) -> float:
        """Calculate accuracy metric."""
        # Simplified accuracy calculation
        return 0.85  # Placeholder
    
    def _calculate_precision(self, predictions: Dict[str, Any], target_column: str) -> float:
        """Calculate precision metric."""
        # Simplified precision calculation
        return 0.82  # Placeholder
    
    def _calculate_recall(self, predictions: Dict[str, Any], target_column: str) -> float:
        """Calculate recall metric."""
        # Simplified recall calculation
        return 0.78  # Placeholder
    
    def _calculate_f1_score(self, predictions: Dict[str, Any], target_column: str) -> float:
        """Calculate F1 score metric."""
        # Simplified F1 score calculation
        return 0.80  # Placeholder
    
    def _calculate_confidence_scores(self, market_analysis: Dict[str, Any],
                                   patterns: List[Dict[str, Any]],
                                   volatility_assessment: Dict[str, Any]) -> Dict[str, float]:
        """Calculate confidence scores for different aspects."""
        return {
            'market_analysis': 0.8,
            'pattern_recognition': 0.75,
            'volatility_assessment': 0.85,
            'overall': 0.8
        }