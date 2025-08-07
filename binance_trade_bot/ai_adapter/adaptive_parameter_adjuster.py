"""
Adaptive Parameter Adjustment System for AI Adapter.

This module implements intelligent parameter adjustment with safe bounds checking,
AI recommendation validation, learning model updates, and fallback mechanisms.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from enum import Enum
import logging
import json
from pathlib import Path

from .base import AIAdapterBase
from ..database import Database
from ..models.trade import Trade, TradeState
from ..models.coin import Coin
from ..models.pair import Pair
from ..models.ai_parameters import AiParameters, ParameterType, ParameterStatus
from ..statistics.manager import StatisticsManager
from ..logger import Logger
from ..state_persistence import StatePersistence


class ParameterBoundType(Enum):
    """Parameter bound type enumeration."""
    MIN = "MIN"
    MAX = "MAX"
    RANGE = "RANGE"
    STEP = "STEP"


class ParameterSafetyLevel(Enum):
    """Parameter safety level enumeration."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AdaptiveParameterAdjuster(AIAdapterBase):
    """
    Adaptive Parameter Adjustment System for intelligent parameter management.
    
    This system provides safe parameter bounds checking, AI recommendation validation,
    learning model updates based on trading results, and fallback mechanisms when
    insufficient data is available.
    """
    
    # Default parameter bounds for safety
    DEFAULT_PARAMETER_BOUNDS = {
        'risk_per_trade': {
            'min': 0.001,  # 0.1%
            'max': 0.1,    # 10%
            'default': 0.02,  # 2%
            'safety_level': ParameterSafetyLevel.HIGH,
            'step': 0.001
        },
        'position_size': {
            'min': 0.1,
            'max': 2.0,
            'default': 1.0,
            'safety_level': ParameterSafetyLevel.MEDIUM,
            'step': 0.1
        },
        'stop_loss_percentage': {
            'min': 0.01,   # 1%
            'max': 0.2,    # 20%
            'default': 0.05,  # 5%
            'safety_level': ParameterSafetyLevel.CRITICAL,
            'step': 0.01
        },
        'take_profit_percentage': {
            'min': 0.02,   # 2%
            'max': 0.5,    # 50%
            'default': 0.1,   # 10%
            'safety_level': ParameterSafetyLevel.HIGH,
            'step': 0.02
        },
        'sma_short_period': {
            'min': 5,
            'max': 50,
            'default': 20,
            'safety_level': ParameterSafetyLevel.LOW,
            'step': 1
        },
        'sma_long_period': {
            'min': 10,
            'max': 200,
            'default': 50,
            'safety_level': ParameterSafetyLevel.LOW,
            'step': 1
        },
        'rsi_period': {
            'min': 5,
            'max': 30,
            'default': 14,
            'safety_level': ParameterSafetyLevel.LOW,
            'step': 1
        }
    }
    
    def __init__(self, config: Dict[str, Any], database: Database,
                 statistics_manager: StatisticsManager, logger: Logger,
                 state_persistence: Optional[StatePersistence] = None):
        """
        Initialize the adaptive parameter adjuster.
        
        @param {dict} config - Configuration dictionary
        @param {Database} database - Database instance
        @param {StatisticsManager} statistics_manager - Statistics manager instance
        @param {Logger} logger - Logger instance
        """
        super().__init__(config)
        self.database = database
        self.statistics_manager = statistics_manager
        self.logger = logger

        # Optional persistence for learning parameters
        path = Path(config.get('learning_state_path', 'ai_learning_state.json'))
        self.state_persistence = state_persistence or StatePersistence(path)
        
        # Parameter bounds configuration
        self.parameter_bounds = config.get('parameter_bounds', self.DEFAULT_PARAMETER_BOUNDS)
        self.enable_bounds_validation = config.get('enable_bounds_validation', True)
        self.enable_confidence_capping = config.get('enable_confidence_capping', True)
        self.confidence_cap_threshold = config.get('confidence_cap_threshold', 0.95)
        
        # Learning configuration
        self.min_trades_for_learning = config.get('min_trades_for_learning', 10)
        self.performance_window_size = config.get('performance_window_size', 50)
        self.learning_rate = config.get('learning_rate', 0.1)
        self.enable_adaptive_learning = config.get('enable_adaptive_learning', True)
        
        # Fallback configuration
        self.enable_fallback_to_defaults = config.get('enable_fallback_to_defaults', True)
        self.min_data_points_for_recommendation = config.get('min_data_points_for_recommendation', 5)
        self.fallback_confidence_threshold = config.get('fallback_confidence_threshold', 0.3)
        
        # Validation configuration
        self.enable_parameter_correlation_checks = config.get('enable_parameter_correlation_checks', True)
        self.max_parameter_change_rate = config.get('max_parameter_change_rate', 0.5)  # 50% max change
        
        # Internal state
        self.parameter_history = []
        self.performance_tracking = {}
        self.learning_model_state = {}
        self._restore_learning_state()
        
        self.logger.info("Adaptive Parameter Adjuster initialized")
    
    def train_model(self, training_data: pd.DataFrame, target_column: str) -> bool:
        """
        Train the adaptive parameter adjustment model.
        
        @param {pd.DataFrame} training_data - Training data
        @param {str} target_column - Target column name
        @returns {bool} True if training completed successfully
        """
        try:
            self.logger.info("Starting adaptive parameter adjustment model training")
            
            # Validate input data
            if training_data.empty:
                self.logger.error("Training data is empty")
                return False
            
            if target_column not in training_data.columns:
                self.logger.error(f"Target column '{target_column}' not found in training data")
                return False
            
            # Preprocess training data
            processed_data = self.preprocess_data(training_data)
            
            # Extract parameter performance patterns
            performance_patterns = self._extract_performance_patterns(processed_data, target_column)
            
            # Build learning model state
            self._build_learning_model_state(performance_patterns)
            
            # Calculate initial parameter bounds
            self._calculate_optimal_parameter_bounds(performance_patterns)
            
            self.is_trained = True
            self.logger.info(f"Model training completed. Extracted {len(performance_patterns)} performance patterns")

            self.save_learning_state()
            return True
            
        except Exception as e:
            self.logger.error(f"Error during model training: {str(e)}")
            return False

    def _restore_learning_state(self) -> None:
        """Load any previously saved learning state."""
        data = self.state_persistence.load() if self.state_persistence else {}
        self.learning_model_state = data.get('learning_model_state', {})
        self.parameter_history = data.get('parameter_history', [])

    def save_learning_state(self) -> None:
        """Persist current learning parameters to disk."""
        if not self.state_persistence:
            return
        self.state_persistence.save({
            'learning_model_state': self.learning_model_state,
            'parameter_history': self.parameter_history,
        })
    
    def predict(self, input_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Make parameter adjustment predictions using the trained model.
        
        @param {pd.DataFrame} input_data - Input data for prediction
        @returns {dict} Prediction results with safe parameter adjustments
        """
        try:
            if not self.is_trained:
                self.logger.warning("Model is not trained, returning fallback predictions")
                return self._get_fallback_predictions()
            
            # Preprocess input data
            processed_data = self.preprocess_data(input_data)
            
            # Get AI recommendations
            ai_recommendations = self._get_ai_recommendations(processed_data)
            
            # Validate and bound recommendations
            validated_recommendations = self._validate_and_bound_recommendations(ai_recommendations)
            
            # Apply confidence capping
            if self.enable_confidence_capping:
                validated_recommendations = self._apply_confidence_capping(validated_recommendations)
            
            # Check for parameter correlations
            if self.enable_parameter_correlation_checks:
                validated_recommendations = self._check_parameter_correlations(validated_recommendations)
            
            # Apply rate limiting to parameter changes
            validated_recommendations = self._apply_rate_limiting(validated_recommendations)
            
            # Generate fallback recommendations if needed
            final_recommendations = self._generate_fallback_recommendations(validated_recommendations)
            
            return {
                'status': 'success',
                'timestamp': datetime.utcnow().isoformat(),
                'recommendations': final_recommendations,
                'validation_results': {
                    'bounds_validated': self.enable_bounds_validation,
                    'confidence_capped': self.enable_confidence_capping,
                    'correlations_checked': self.enable_parameter_correlation_checks,
                    'rate_limited': True
                },
                'model_info': self.get_model_info()
            }
            
        except Exception as e:
            self.logger.error(f"Error during prediction: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'recommendations': self._get_fallback_predictions().get('recommendations', [])
            }
    
    def get_feature_importance(self) -> Dict[str, float]:
        """
        Get feature importance scores from the trained model.
        
        @returns {dict} Feature importance scores
        """
        try:
            feature_importance = {}
            
            if self.learning_model_state:
                # Calculate importance based on parameter performance impact
                for param_name, param_state in self.learning_model_state.items():
                    if 'performance_impact' in param_state:
                        feature_importance[param_name] = param_state['performance_impact']
            
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
                'parameter_bounds': self.parameter_bounds,
                'learning_model_state': self.learning_model_state,
                'parameter_history': self.parameter_history,
                'performance_tracking': self.performance_tracking,
                'config': self.config,
                'is_trained': self.is_trained,
                'timestamp': datetime.utcnow().isoformat()
            }
            
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
            with open(filepath, 'r') as f:
                model_data = json.load(f)
            
            self.parameter_bounds = model_data.get('parameter_bounds', self.DEFAULT_PARAMETER_BOUNDS)
            self.learning_model_state = model_data.get('learning_model_state', {})
            self.parameter_history = model_data.get('parameter_history', [])
            self.performance_tracking = model_data.get('performance_tracking', {})
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
                'recommendations_count': len(predictions.get('recommendations', [])),
                'valid_recommendations': len([
                    r for r in predictions.get('recommendations', [])
                    if r.get('validation_status') == 'valid'
                ]),
                'validation_success_rate': len([
                    r for r in predictions.get('recommendations', [])
                    if r.get('validation_status') == 'valid'
                ]) / len(predictions.get('recommendations', [])) if predictions.get('recommendations') else 0,
                'average_confidence': np.mean([
                    r.get('confidence', 0) for r in predictions.get('recommendations', [])
                ]) if predictions.get('recommendations') else 0,
                'bounds_violations': len([
                    r for r in predictions.get('recommendations', [])
                    if r.get('validation_status') == 'bounds_violation'
                ]),
                'fallback_recommendations': len([
                    r for r in predictions.get('recommendations', [])
                    if r.get('source') == 'fallback'
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
            'model_type': 'AdaptiveParameterAdjuster',
            'is_trained': self.is_trained,
            'parameter_count': len(self.parameter_bounds),
            'learning_model_state_size': len(self.learning_model_state),
            'parameter_history_size': len(self.parameter_history),
            'config': {
                'enable_bounds_validation': self.enable_bounds_validation,
                'enable_confidence_capping': self.enable_confidence_capping,
                'enable_adaptive_learning': self.enable_adaptive_learning,
                'enable_fallback_to_defaults': self.enable_fallback_to_defaults,
                'enable_parameter_correlation_checks': self.enable_parameter_correlation_checks
            },
            'feature_importance': self.get_feature_importance(),
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def update_parameters_from_trading_results(self, trades: List[Trade], 
                                             performance_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update parameters based on trading results and performance metrics.
        
        @param {List[Trade]} trades - List of recent trades
        @param {Dict[str, Any]} performance_metrics - Performance metrics
        @returns {dict} Update results
        """
        try:
            if not self.is_trained:
                return {
                    'status': 'warning',
                    'message': 'Model is not trained, cannot update parameters'
                }
            
            # Validate sufficient data for learning
            if len(trades) < self.min_trades_for_learning:
                return {
                    'status': 'warning',
                    'message': f'Insufficient data for learning (need {self.min_trades_for_learning}, got {len(trades)})'
                }
            
            # Extract performance insights from trades
            performance_insights = self._extract_performance_insights(trades, performance_metrics)
            
            # Update learning model state
            self._update_learning_model_state(performance_insights)
            
            # Adjust parameter bounds based on performance
            self._adjust_parameter_bounds(performance_insights)
            
            # Generate updated recommendations
            updated_recommendations = self._generate_updated_recommendations(performance_insights)
            
            # Store parameter update history
            self._store_parameter_update_history(updated_recommendations, performance_insights)
            
            return {
                'status': 'success',
                'message': 'Parameters updated successfully based on trading results',
                'updated_recommendations': updated_recommendations,
                'performance_insights': performance_insights,
                'trades_analyzed': len(trades),
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Error updating parameters from trading results: {str(e)}")
            return {
                'status': 'error',
                'message': str(e)
            }
    
    def validate_parameter_bounds(self, parameter_name: str, value: float) -> Dict[str, Any]:
        """
        Validate a parameter value against predefined bounds.
        
        @param {str} parameter_name - Name of the parameter
        @param {float} value - Parameter value to validate
        @returns {dict} Validation results
        """
        try:
            if not self.enable_bounds_validation:
                return {
                    'is_valid': True,
                    'validation_status': 'validation_disabled',
                    'message': 'Bounds validation is disabled'
                }
            
            if parameter_name not in self.parameter_bounds:
                return {
                    'is_valid': False,
                    'validation_status': 'unknown_parameter',
                    'message': f'Unknown parameter: {parameter_name}'
                }
            
            bounds = self.parameter_bounds[parameter_name]
            min_val = bounds.get('min')
            max_val = bounds.get('max')
            default_val = bounds.get('default')
            safety_level = bounds.get('safety_level', ParameterSafetyLevel.MEDIUM)
            
            validation_result = {
                'parameter_name': parameter_name,
                'value': value,
                'bounds': bounds,
                'is_valid': True,
                'validation_status': 'valid',
                'message': 'Parameter is within bounds'
            }
            
            # Check minimum bound
            if min_val is not None and value < min_val:
                validation_result.update({
                    'is_valid': False,
                    'validation_status': 'bounds_violation',
                    'message': f'Value {value} is below minimum {min_val}',
                    'corrected_value': min_val
                })
            
            # Check maximum bound
            elif max_val is not None and value > max_val:
                validation_result.update({
                    'is_valid': False,
                    'validation_status': 'bounds_violation',
                    'message': f'Value {value} is above maximum {max_val}',
                    'corrected_value': max_val
                })
            
            # Check step size if defined
            step = bounds.get('step')
            if step is not None and validation_result['is_valid']:
                remainder = (value - default_val) % step
                if remainder > 0:
                    validation_result.update({
                        'is_valid': False,
                        'validation_status': 'step_violation',
                        'message': f'Value {value} does not respect step size {step} from default {default_val}',
                        'corrected_value': round(value / step) * step
                    })
            
            return validation_result
            
        except Exception as e:
            self.logger.error(f"Error validating parameter bounds: {str(e)}")
            return {
                'is_valid': False,
                'validation_status': 'error',
                'message': str(e)
            }
    
    def get_default_parameters(self) -> Dict[str, Any]:
        """
        Get default parameters for all configured parameters.
        
        @returns {dict} Default parameters
        """
        default_params = {}
        
        for param_name, bounds in self.parameter_bounds.items():
            default_params[param_name] = bounds.get('default', 0)
        
        return default_params
    
    def _extract_performance_patterns(self, data: pd.DataFrame, target_column: str) -> List[Dict[str, Any]]:
        """Extract performance patterns from training data."""
        patterns = []
        
        try:
            # Analyze parameter performance relationships
            for param_name in self.parameter_bounds.keys():
                if param_name in data.columns:
                    # Calculate correlation with target
                    correlation = data[param_name].corr(data[target_column])
                    
                    # Create performance pattern
                    pattern = {
                        'parameter_name': param_name,
                        'correlation': correlation,
                        'performance_impact': abs(correlation),
                        'optimal_range': self._calculate_optimal_range(data, param_name, target_column),
                        'data_quality': self._assess_data_quality(data, param_name)
                    }
                    
                    patterns.append(pattern)
            
        except Exception as e:
            self.logger.error(f"Error extracting performance patterns: {str(e)}")
        
        return patterns
    
    def _build_learning_model_state(self, performance_patterns: List[Dict[str, Any]]):
        """Build learning model state from performance patterns."""
        try:
            for pattern in performance_patterns:
                param_name = pattern['parameter_name']
                
                self.learning_model_state[param_name] = {
                    'correlation': pattern['correlation'],
                    'performance_impact': pattern['performance_impact'],
                    'optimal_range': pattern['optimal_range'],
                    'data_quality': pattern['data_quality'],
                    'adaptation_factor': 1.0,
                    'last_updated': datetime.utcnow().isoformat()
                }
            
        except Exception as e:
            self.logger.error(f"Error building learning model state: {str(e)}")
    
    def _calculate_optimal_parameter_bounds(self, performance_patterns: List[Dict[str, Any]]):
        """Calculate optimal parameter bounds based on performance patterns."""
        try:
            for pattern in performance_patterns:
                param_name = pattern['parameter_name']
                
                if param_name in self.parameter_bounds and pattern['optimal_range']:
                    # Adjust bounds based on optimal range
                    optimal_range = pattern['optimal_range']
                    current_bounds = self.parameter_bounds[param_name]
                    
                    # Expand bounds to include optimal range
                    if 'min' not in current_bounds or optimal_range['min'] < current_bounds['min']:
                        current_bounds['min'] = optimal_range['min']
                    
                    if 'max' not in current_bounds or optimal_range['max'] > current_bounds['max']:
                        current_bounds['max'] = optimal_range['max']
                    
                    self.parameter_bounds[param_name] = current_bounds
            
        except Exception as e:
            self.logger.error(f"Error calculating optimal parameter bounds: {str(e)}")
    
    def _get_ai_recommendations(self, data: pd.DataFrame) -> List[Dict[str, Any]]:
        """Get AI recommendations from the model."""
        recommendations = []
        
        try:
            # Generate recommendations based on learning model state
            for param_name, param_state in self.learning_model_state.items():
                # Calculate recommendation based on correlation and current market conditions
                correlation = param_state.get('correlation', 0)
                performance_impact = param_state.get('performance_impact', 0)
                
                # Generate base recommendation
                if correlation > 0:
                    # Positive correlation: increase parameter for better performance
                    base_adjustment = 1.0 + (performance_impact * 0.1)
                else:
                    # Negative correlation: decrease parameter for better performance
                    base_adjustment = 1.0 - (performance_impact * 0.1)
                
                # Get current default value
                current_default = self.parameter_bounds[param_name].get('default', 1.0)
                
                # Calculate recommended value
                recommended_value = current_default * base_adjustment
                
                recommendation = {
                    'parameter_name': param_name,
                    'recommended_value': recommended_value,
                    'confidence': min(abs(correlation), 1.0),
                    'reasoning': f'Based on correlation {correlation:.3f} and performance impact {performance_impact:.3f}',
                    'source': 'ai_model',
                    'validation_status': 'pending'
                }
                
                recommendations.append(recommendation)
            
        except Exception as e:
            self.logger.error(f"Error getting AI recommendations: {str(e)}")
        
        return recommendations
    
    def _validate_and_bound_recommendations(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validate and bound AI recommendations."""
        validated_recommendations = []
        
        try:
            for rec in recommendations:
                param_name = rec['parameter_name']
                recommended_value = rec['recommended_value']
                
                # Validate bounds
                validation_result = self.validate_parameter_bounds(param_name, recommended_value)
                
                # Update recommendation with validation result
                rec.update({
                    'validation_result': validation_result,
                    'validation_status': validation_result['validation_status'],
                    'original_value': recommended_value
                })
                
                # Apply correction if validation failed
                if not validation_result['is_valid'] and 'corrected_value' in validation_result:
                    rec['recommended_value'] = validation_result['corrected_value']
                    rec['correction_applied'] = True
                else:
                    rec['correction_applied'] = False
                
                validated_recommendations.append(rec)
            
        except Exception as e:
            self.logger.error(f"Error validating and bounding recommendations: {str(e)}")
        
        return validated_recommendations
    
    def _apply_confidence_capping(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply confidence capping to recommendations."""
        if not self.enable_confidence_capping:
            return recommendations
        
        capped_recommendations = []
        
        try:
            for rec in recommendations:
                confidence = rec.get('confidence', 0)
                
                # Cap confidence if it exceeds threshold
                if confidence > self.confidence_cap_threshold:
                    rec['confidence'] = self.confidence_cap_threshold
                    rec['confidence_capped'] = True
                    rec['capping_reason'] = f'Confidence capped at {self.confidence_cap_threshold}'
                else:
                    rec['confidence_capped'] = False
                
                capped_recommendations.append(rec)
            
        except Exception as e:
            self.logger.error(f"Error applying confidence capping: {str(e)}")
        
        return capped_recommendations
    
    def _check_parameter_correlations(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Check for parameter correlations and adjust recommendations."""
        if not self.enable_parameter_correlation_checks:
            return recommendations
        
        correlated_recommendations = recommendations.copy()
        
        try:
            # Check for known parameter correlations
            parameter_correlations = {
                'risk_per_trade': ['position_size', 'stop_loss_percentage'],
                'position_size': ['risk_per_trade', 'take_profit_percentage'],
                'stop_loss_percentage': ['risk_per_trade', 'take_profit_percentage']
            }
            
            for i, rec in enumerate(correlated_recommendations):
                param_name = rec['parameter_name']
                
                # Check if this parameter has correlations
                if param_name in parameter_correlations:
                    correlated_params = parameter_correlations[param_name]
                    
                    # Find correlated recommendations
                    correlated_recs = [
                        r for r in correlated_recommendations 
                        if r['parameter_name'] in correlated_params
                    ]
                    
                    if correlated_recs:
                        # Apply correlation adjustments
                        adjustment_factor = self._calculate_correlation_adjustment(
                            rec, correlated_recs, param_name
                        )
                        
                        if adjustment_factor != 1.0:
                            rec['recommended_value'] *= adjustment_factor
                            rec['correlation_adjusted'] = True
                            rec['correlation_adjustment_factor'] = adjustment_factor
                        else:
                            rec['correlation_adjusted'] = False
            
        except Exception as e:
            self.logger.error(f"Error checking parameter correlations: {str(e)}")
        
        return correlated_recommendations
    
    def _apply_rate_limiting(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply rate limiting to parameter changes."""
        rate_limited_recommendations = []
        
        try:
            for rec in recommendations:
                param_name = rec['parameter_name']
                new_value = rec['recommended_value']
                
                # Get previous value if available
                previous_value = self._get_previous_parameter_value(param_name)
                
                if previous_value is not None:
                    # Calculate change rate
                    change_rate = abs(new_value - previous_value) / previous_value
                    
                    # Apply rate limiting if change exceeds threshold
                    if change_rate > self.max_parameter_change_rate:
                        # Limit the change
                        max_change = previous_value * self.max_parameter_change_rate
                        if new_value > previous_value:
                            limited_value = previous_value + max_change
                        else:
                            limited_value = previous_value - max_change
                        
                        rec['recommended_value'] = limited_value
                        rec['rate_limited'] = True
                        rec['rate_limit_reason'] = f'Change rate {change_rate:.2%} exceeds maximum {self.max_parameter_change_rate:.2%}'
                        rec['original_value'] = new_value
                        rec['previous_value'] = previous_value
                    else:
                        rec['rate_limited'] = False
                else:
                    rec['rate_limited'] = False
                
                rate_limited_recommendations.append(rec)
            
        except Exception as e:
            self.logger.error(f"Error applying rate limiting: {str(e)}")
        
        return rate_limited_recommendations
    
    def _generate_fallback_recommendations(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate fallback recommendations if needed."""
        if not self.enable_fallback_to_defaults:
            return recommendations
        
        final_recommendations = []
        
        try:
            for rec in recommendations:
                # Check if recommendation needs fallback
                needs_fallback = (
                    rec.get('validation_status') != 'valid' or
                    rec.get('source') == 'fallback' or
                    rec.get('confidence', 0) < self.fallback_confidence_threshold
                )
                
                if needs_fallback:
                    # Get default value
                    default_value = self.parameter_bounds[rec['parameter_name']].get('default', 1.0)
                    
                    # Create fallback recommendation
                    fallback_rec = {
                        'parameter_name': rec['parameter_name'],
                        'recommended_value': default_value,
                        'confidence': 0.5,  # Default confidence for fallback
                        'reasoning': 'Fallback to default parameter due to validation or confidence issues',
                        'source': 'fallback',
                        'validation_status': 'valid',
                        'is_fallback': True,
                        'original_recommendation': rec
                    }
                    
                    final_recommendations.append(fallback_rec)
                else:
                    rec['is_fallback'] = False
                    final_recommendations.append(rec)
            
        except Exception as e:
            self.logger.error(f"Error generating fallback recommendations: {str(e)}")
            # Return original recommendations if fallback fails
            return recommendations
        
        return final_recommendations
    
    def _get_fallback_predictions(self) -> Dict[str, Any]:
        """Get fallback predictions when model is not trained."""
        try:
            default_params = self.get_default_parameters()
            
            recommendations = []
            for param_name, default_value in default_params.items():
                recommendation = {
                    'parameter_name': param_name,
                    'recommended_value': default_value,
                    'confidence': 0.5,
                    'reasoning': 'Default parameter (model not trained)',
                    'source': 'fallback',
                    'validation_status': 'valid',
                    'is_fallback': True
                }
                recommendations.append(recommendation)
            
            return {
                'status': 'warning',
                'message': 'Model is not trained, using default parameters',
                'timestamp': datetime.utcnow().isoformat(),
                'recommendations': recommendations,
                'model_info': self.get_model_info()
            }
            
        except Exception as e:
            self.logger.error(f"Error getting fallback predictions: {str(e)}")
            return {
                'status': 'error',
                'message': str(e),
                'timestamp': datetime.utcnow().isoformat(),
                'recommendations': []
            }
    
    def _calculate_optimal_range(self, data: pd.DataFrame, param_name: str, target_column: str) -> Dict[str, float]:
        """Calculate optimal range for a parameter based on target correlation."""
        try:
            if param_name not in data.columns or target_column not in data.columns:
                return {}
            
            # Calculate correlation between parameter and target
            correlation = data[param_name].corr(data[target_column])
            
            if abs(correlation) < 0.1:  # Weak correlation
                return {}
            
            # Find optimal range based on target values
            if correlation > 0:
                # Positive correlation: higher parameter values better
                optimal_data = data[data[target_column] > data[target_column].quantile(0.75)]
                optimal_range = {
                    'min': optimal_data[param_name].quantile(0.25),
                    'max': optimal_data[param_name].quantile(0.75)
                }
            else:
                # Negative correlation: lower parameter values better
                optimal_data = data[data[target_column] < data[target_column].quantile(0.25)]
                optimal_range = {
                    'min': optimal_data[param_name].quantile(0.25),
                    'max': optimal_data[param_name].quantile(0.75)
                }
            
            return optimal_range
            
        except Exception as e:
            self.logger.error(f"Error calculating optimal range: {str(e)}")
            return {}
    
    def _assess_data_quality(self, data: pd.DataFrame, param_name: str) -> Dict[str, Any]:
        """Assess data quality for a parameter."""
        try:
            if param_name not in data.columns:
                return {'quality_score': 0.0, 'missing_data_ratio': 1.0}
            
            # Calculate missing data ratio
            missing_data_ratio = data[param_name].isnull().sum() / len(data)
            
            # Calculate data quality score
            quality_score = 1.0 - missing_data_ratio
            
            # Add variance score (higher variance = more informative)
            variance_score = min(data[param_name].var() / 10.0, 1.0)  # Normalize to [0, 1]
            
            overall_quality = (quality_score * 0.7) + (variance_score * 0.3)
            
            return {
                'quality_score': overall_quality,
                'missing_data_ratio': missing_data_ratio,
                'variance_score': variance_score,
                'data_points': len(data.dropna(subset=[param_name]))
            }
            
        except Exception as e:
            self.logger.error(f"Error assessing data quality: {str(e)}")
            return {'quality_score': 0.0, 'missing_data_ratio': 1.0}
    
    def _extract_performance_insights(self, trades: List[Trade], 
                                    performance_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Extract performance insights from trading results."""
        try:
            insights = {
                'total_trades': len(trades),
                'win_rate': performance_metrics.get('win_rate', 0.0),
                'profit_factor': performance_metrics.get('profit_factor', 1.0),
                'sharpe_ratio': performance_metrics.get('sharpe_ratio', 0.0),
                'max_drawdown': performance_metrics.get('max_drawdown', 0.0),
                'total_return': performance_metrics.get('total_return', 0.0),
                'trade_duration_stats': self._calculate_trade_duration_stats(trades),
                'volume_stats': self._calculate_volume_stats(trades),
                'parameter_performance_correlation': self._calculate_parameter_performance_correlation(trades)
            }
            
            return insights
            
        except Exception as e:
            self.logger.error(f"Error extracting performance insights: {str(e)}")
            return {}
    
    def _update_learning_model_state(self, performance_insights: Dict[str, Any]):
        """Update learning model state based on performance insights."""
        try:
            # Update adaptation factors based on performance
            for param_name, param_state in self.learning_model_state.items():
                # Calculate performance score
                performance_score = self._calculate_performance_score(performance_insights)
                
                # Update adaptation factor
                if performance_score > 0:
                    # Good performance: increase adaptation
                    param_state['adaptation_factor'] = min(param_state['adaptation_factor'] * 1.1, 2.0)
                else:
                    # Poor performance: decrease adaptation
                    param_state['adaptation_factor'] = max(param_state['adaptation_factor'] * 0.9, 0.5)
                
                # Update last updated timestamp
                param_state['last_updated'] = datetime.utcnow().isoformat()
            
        except Exception as e:
            self.logger.error(f"Error updating learning model state: {str(e)}")
    
    def _adjust_parameter_bounds(self, performance_insights: Dict[str, Any]):
        """Adjust parameter bounds based on performance insights."""
        try:
            # Adjust bounds based on performance
            performance_score = self._calculate_performance_score(performance_insights)
            
            if performance_score > 0:
                # Good performance: expand bounds slightly
                expansion_factor = 1.05
            else:
                # Poor performance: contract bounds slightly
                expansion_factor = 0.95
            
            # Apply expansion/contraction to bounds
            for param_name, bounds in self.parameter_bounds.items():
                if 'min' in bounds:
                    bounds['min'] *= expansion_factor
                if 'max' in bounds:
                    bounds['max'] *= expansion_factor
            
        except Exception as e:
            self.logger.error(f"Error adjusting parameter bounds: {str(e)}")
    
    def _generate_updated_recommendations(self, performance_insights: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate updated recommendations based on performance insights."""
        recommendations = []
        
        try:
            performance_score = self._calculate_performance_score(performance_insights)
            
            for param_name, param_state in self.learning_model_state.items():
                # Generate adjusted recommendation
                base_value = self.parameter_bounds[param_name].get('default', 1.0)
                adaptation_factor = param_state.get('adaptation_factor', 1.0)
                
                # Adjust based on performance
                if performance_score > 0:
                    adjusted_value = base_value * adaptation_factor
                else:
                    adjusted_value = base_value / adaptation_factor
                
                recommendation = {
                    'parameter_name': param_name,
                    'recommended_value': adjusted_value,
                    'confidence': min(abs(param_state.get('correlation', 0)) + 0.1, 1.0),
                    'reasoning': f'Updated based on performance score {performance_score:.3f} and adaptation factor {adaptation_factor:.2f}',
                    'source': 'adaptive_learning',
                    'validation_status': 'pending'
                }
                
                recommendations.append(recommendation)
            
        except Exception as e:
            self.logger.error(f"Error generating updated recommendations: {str(e)}")
        
        return recommendations
    
    def _store_parameter_update_history(self, recommendations: List[Dict[str, Any]], 
                                      performance_insights: Dict[str, Any]):
        """Store parameter update history for tracking and analysis."""
        try:
            update_record = {
                'timestamp': datetime.utcnow().isoformat(),
                'recommendations': recommendations,
                'performance_insights': performance_insights,
                'performance_score': self._calculate_performance_score(performance_insights)
            }
            
            self.parameter_history.append(update_record)
            
            # Keep only recent history (last 100 updates)
            if len(self.parameter_history) > 100:
                self.parameter_history = self.parameter_history[-100:]
            
        except Exception as e:
            self.logger.error(f"Error storing parameter update history: {str(e)}")
    
    def _calculate_performance_score(self, performance_insights: Dict[str, Any]) -> float:
        """Calculate overall performance score from insights."""
        try:
            win_rate = performance_insights.get('win_rate', 0.0)
            profit_factor = performance_insights.get('profit_factor', 1.0)
            sharpe_ratio = performance_insights.get('sharpe_ratio', 0.0)
            total_return = performance_insights.get('total_return', 0.0)
            
            # Normalize and combine metrics
            win_score = min(max(win_rate - 0.5, 0.0) * 2, 1.0)  # 0-1 scale
            profit_score = min(max(profit_factor - 1.0, 0.0), 1.0)  # 0-1 scale
            sharpe_score = min(max(sharpe_ratio, 0.0) / 2.0, 1.0)  # 0-1 scale
            return_score = min(max(total_return, -1.0) + 1.0, 2.0) / 2.0  # 0-1 scale
            
            # Weighted combination
            return (win_score * 0.3 + profit_score * 0.3 + sharpe_score * 0.2 + return_score * 0.2)
            
        except Exception as e:
            self.logger.error(f"Error calculating performance score: {str(e)}")
            return 0.0
    
    def _calculate_trade_duration_stats(self, trades: List[Trade]) -> Dict[str, Any]:
        """Calculate trade duration statistics."""
        try:
            durations = []
            for trade in trades:
                if trade.datetime:
                    duration = (datetime.utcnow() - trade.datetime).total_seconds() / 3600  # hours
                    durations.append(duration)
            
            if not durations:
                return {}
            
            return {
                'avg_duration': sum(durations) / len(durations),
                'min_duration': min(durations),
                'max_duration': max(durations),
                'median_duration': sorted(durations)[len(durations) // 2]
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating trade duration stats: {str(e)}")
            return {}
    
    def _calculate_volume_stats(self, trades: List[Trade]) -> Dict[str, Any]:
        """Calculate volume statistics from trades."""
        try:
            volumes = []
            for trade in trades:
                if trade.selling and trade.alt_trade_amount:
                    volumes.append(trade.alt_trade_amount)
                elif not trade.selling and trade.crypto_trade_amount:
                    volumes.append(trade.crypto_trade_amount)
            
            if not volumes:
                return {}
            
            return {
                'avg_volume': sum(volumes) / len(volumes),
                'min_volume': min(volumes),
                'max_volume': max(volumes),
                'total_volume': sum(volumes)
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating volume stats: {str(e)}")
            return {}
    
    def _calculate_parameter_performance_correlation(self, trades: List[Trade]) -> Dict[str, Any]:
        """Calculate correlation between parameters and performance."""
        try:
            # This would require parameter values for each trade
            # For now, return empty dict
            return {}
            
        except Exception as e:
            self.logger.error(f"Error calculating parameter performance correlation: {str(e)}")
            return {}
    
    def _calculate_correlation_adjustment(self, primary_rec: Dict[str, Any], 
                                        correlated_recs: List[Dict[str, Any]], 
                                        param_name: str) -> float:
        """Calculate correlation adjustment factor."""
        try:
            # Simple correlation adjustment logic
            adjustment_factor = 1.0
            
            for correlated_rec in correlated_recs:
                corr_param_name = correlated_rec['parameter_name']
                corr_value = correlated_rec['recommended_value']
                
                # Apply specific correlation adjustments
                if param_name == 'risk_per_trade' and corr_param_name == 'position_size':
                    # Risk and position size should be inversely correlated
                    adjustment_factor *= 0.95
                
                elif param_name == 'position_size' and corr_param_name == 'risk_per_trade':
                    # Position size and risk should be inversely correlated
                    adjustment_factor *= 0.95
                
                elif param_name == 'stop_loss_percentage' and corr_param_name == 'take_profit_percentage':
                    # Stop loss and take profit should be positively correlated
                    adjustment_factor *= 1.05
            
            return adjustment_factor
            
        except Exception as e:
            self.logger.error(f"Error calculating correlation adjustment: {str(e)}")
            return 1.0
    
    def _get_previous_parameter_value(self, parameter_name: str) -> Optional[float]:
        """Get the previous value of a parameter from history."""
        try:
            # Look for most recent value in parameter history
            for update_record in reversed(self.parameter_history):
                for rec in update_record.get('recommendations', []):
                    if rec['parameter_name'] == parameter_name:
                        return rec.get('recommended_value')
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting previous parameter value: {str(e)}")
            return None
    
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