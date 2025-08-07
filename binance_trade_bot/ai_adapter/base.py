"""
Base abstract class for AI adapter implementations.
"""

from abc import ABC, abstractmethod
import pandas as pd


class AIAdapterBase(ABC):
    """
    Abstract base class for AI adapter implementations.
    
    This class defines the interface that all AI adapter implementations
    must follow, ensuring consistent functionality across different AI/ML
    models and machine learning frameworks.
    """
    
    def __init__(self, config):
        """
        Initialize the AI adapter with configuration.
        
        @param {dict} config - Configuration dictionary containing AI settings
        """
        self.config = config
        self.model = None
        self.is_trained = False
    
    @abstractmethod
    def train_model(self, training_data, target_column):
        """
        Train the AI model with provided training data.
        
        @param {pd.DataFrame} training_data - DataFrame containing training features
        @param {str} target_column - Name of the target column to predict
        @returns {bool} True if training completed successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def predict(self, input_data):
        """
        Make predictions using the trained AI model.
        
        @param {pd.DataFrame} input_data - DataFrame containing input features
        @returns {dict} Dictionary containing prediction results
        """
        pass
    
    @abstractmethod
    def get_feature_importance(self):
        """
        Get feature importance scores from the trained model.
        
        @returns {dict} Dictionary with feature importance scores
        """
        pass
    
    @abstractmethod
    def save_model(self, filepath):
        """
        Save the trained model to a file.
        
        @param {str} filepath - Path where the model should be saved
        @returns {bool} True if model saved successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def load_model(self, filepath):
        """
        Load a trained model from a file.
        
        @param {str} filepath - Path to the saved model file
        @returns {bool} True if model loaded successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def evaluate_model(self, test_data, target_column):
        """
        Evaluate the model performance on test data.
        
        @param {pd.DataFrame} test_data - DataFrame containing test features
        @param {str} target_column - Name of the target column
        @returns {dict} Dictionary containing evaluation metrics
        """
        pass
    
    @abstractmethod
    def preprocess_data(self, raw_data):
        """
        Preprocess raw data for model training or prediction.
        
        @param {pd.DataFrame} raw_data - Raw input data
        @returns {pd.DataFrame} Preprocessed data ready for model use
        """
        pass
    
    @abstractmethod
    def get_model_info(self):
        """
        Get information about the current model.
        
        @returns {dict} Dictionary containing model information and metadata
        """
        pass