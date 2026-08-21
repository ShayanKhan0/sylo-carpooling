"""
ML Adapter for Safety AI

Provides machine learning models for anomaly detection.
Supports IsolationForest (default) and LSTM (placeholder).
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class MLDetector:
    """
    Base class for ML-based anomaly detectors.
    """
    
    def fit(self, data: np.ndarray):
        """
        Train the model on normal telemetry data.
        
        Args:
            data: Training data array (n_samples, n_features)
        """
        raise NotImplementedError
    
    def predict(self, point: Dict) -> Tuple[bool, float]:
        """
        Predict if a telemetry point is anomalous.
        
        Args:
            point: Telemetry point dictionary
            
        Returns:
            Tuple of (is_anomaly, confidence_score)
        """
        raise NotImplementedError
    
    def is_trained(self) -> bool:
        """Check if model is trained"""
        raise NotImplementedError


class IsolationForestDetector(MLDetector):
    """
    Isolation Forest based anomaly detector.
    
    Uses sklearn's IsolationForest for unsupervised anomaly detection.
    """
    
    def __init__(self, contamination: float = 0.1, random_state: int = 42):
        """
        Initialize Isolation Forest detector.
        
        Args:
            contamination: Expected proportion of outliers
            random_state: Random seed for reproducibility
        """
        try:
            from sklearn.ensemble import IsolationForest
            self.model = IsolationForest(
                contamination=contamination,
                random_state=random_state,
                n_estimators=100
            )
            self._trained = False
            logger.info("✅ IsolationForest detector initialized")
            
        except ImportError:
            logger.warning("⚠️ scikit-learn not installed, IsolationForest unavailable")
            self.model = None
            self._trained = False
    
    def fit(self, data: np.ndarray):
        """
        Train Isolation Forest on normal telemetry data.
        
        Args:
            data: Training data array (n_samples, n_features)
                  Features: [lat, lng, speed, bearing, accuracy]
        """
        if self.model is None:
            logger.warning("IsolationForest model not available")
            return
        
        try:
            self.model.fit(data)
            self._trained = True
            logger.info(f"✅ IsolationForest trained on {len(data)} samples")
            
        except Exception as e:
            logger.error(f"Failed to train IsolationForest: {e}", exc_info=True)
            self._trained = False
    
    def predict(self, point: Dict) -> Tuple[bool, float]:
        """
        Predict if telemetry point is anomalous.
        
        Args:
            point: Telemetry point with lat, lng, speed, bearing, accuracy
            
        Returns:
            Tuple of (is_anomaly, anomaly_score)
        """
        if self.model is None or not self._trained:
            logger.debug("IsolationForest not trained, returning no anomaly")
            return False, 0.0
        
        try:
            # Extract features
            features = np.array([[
                point.get('lat', 0.0),
                point.get('lng', 0.0),
                point.get('speed', 0.0),
                point.get('bearing', 0.0),
                point.get('accuracy', 10.0)
            ]])
            
            # Predict: -1 for anomalies, 1 for normal points
            prediction = self.model.predict(features)[0]
            
            # Get anomaly score (negative = more anomalous)
            score = self.model.score_samples(features)[0]
            
            is_anomaly = (prediction == -1)
            
            # Convert score to confidence (0-1 range)
            # IsolationForest scores are typically in [-0.5, 0.5]
            confidence = abs(score)
            
            return is_anomaly, confidence
            
        except Exception as e:
            logger.error(f"Error in IsolationForest prediction: {e}", exc_info=True)
            return False, 0.0
    
    def is_trained(self) -> bool:
        """Check if model is trained"""
        return self._trained


class LSTMDetector(MLDetector):
    """
    LSTM-based anomaly detector (placeholder).
    
    Uses sequence modeling for temporal pattern detection.
    Requires TensorFlow/PyTorch for full implementation.
    """
    
    def __init__(self, sequence_length: int = 10, threshold: float = 0.7):
        """
        Initialize LSTM detector.
        
        Args:
            sequence_length: Number of historical points to use
            threshold: Anomaly threshold
        """
        self.sequence_length = sequence_length
        self.threshold = threshold
        self._trained = False
        self.model = None
        
        logger.warning("⚠️ LSTM detector is a placeholder - requires TensorFlow/PyTorch")
    
    def fit(self, data: np.ndarray):
        """
        Train LSTM on sequential telemetry data.
        
        Args:
            data: Sequential training data (n_sequences, sequence_length, n_features)
        """
        # Placeholder implementation
        logger.warning("LSTM training not implemented - using placeholder")
        self._trained = False
    
    def predict(self, point: Dict) -> Tuple[bool, float]:
        """
        Predict using LSTM (placeholder).
        
        Args:
            point: Telemetry point
            
        Returns:
            Tuple of (is_anomaly, confidence)
        """
        # Placeholder: always return no anomaly
        logger.debug("LSTM prediction placeholder - returning no anomaly")
        return False, 0.0
    
    def is_trained(self) -> bool:
        """Check if model is trained"""
        return self._trained


def create_ml_detector(model_type: str = "isolation_forest", **kwargs) -> MLDetector:
    """
    Factory function to create ML detector instance.
    
    Args:
        model_type: Type of detector ("isolation_forest" or "lstm")
        **kwargs: Additional arguments for detector
        
    Returns:
        MLDetector instance
    """
    if model_type.lower() == "isolation_forest":
        return IsolationForestDetector(**kwargs)
    
    elif model_type.lower() == "lstm":
        return LSTMDetector(**kwargs)
    
    else:
        logger.warning(f"Unknown model type: {model_type}, defaulting to IsolationForest")
        return IsolationForestDetector(**kwargs)


def generate_training_data(n_samples: int = 1000) -> np.ndarray:
    """
    Generate synthetic training data for ML model.
    
    Simulates normal telemetry patterns for model training.
    
    Args:
        n_samples: Number of samples to generate
        
    Returns:
        Training data array (n_samples, 5)
    """
    # Simulate normal driving patterns
    # Features: [lat, lng, speed, bearing, accuracy]
    
    # Base location: around a typical city center
    base_lat = 40.7128
    base_lng = -74.0060
    
    # Generate samples with realistic distributions
    lats = np.random.normal(base_lat, 0.01, n_samples)  # ~1km variance
    lngs = np.random.normal(base_lng, 0.01, n_samples)
    speeds = np.random.gamma(3, 15, n_samples)  # Most speeds 20-60 km/h
    speeds = np.clip(speeds, 0, 100)  # Cap at 100 km/h
    bearings = np.random.uniform(0, 360, n_samples)
    accuracy = np.random.gamma(2, 2.5, n_samples)  # Most 3-8 meters
    accuracy = np.clip(accuracy, 1, 50)
    
    data = np.column_stack([lats, lngs, speeds, bearings, accuracy])
    
    logger.info(f"Generated {n_samples} synthetic training samples")
    return data
