"""
Anomaly Detector for Safety AI

Hybrid detection system combining deterministic rules and ML-based analysis.
Includes false-positive suppression and multi-stage alert generation.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from uuid import UUID
from collections import deque

import numpy as np

from app.modules.safety_ai.ml_adapter import create_ml_detector, MLDetector
from app.modules.safety_ai.rule_engine import get_rule_engine
from app.modules.telemetry.anomaly import calculate_distance

logger = logging.getLogger(__name__)


class AnomalyResult:
    """Result of anomaly detection"""
    
    def __init__(
        self,
        anomaly_type: str,
        confidence: float,
        severity: str,
        details: Dict
    ):
        self.anomaly_type = anomaly_type
        self.confidence = confidence  # 0.0 - 1.0
        self.severity = severity  # low, medium, high
        self.details = details
        self.detected_at = datetime.utcnow()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "anomaly_type": self.anomaly_type,
            "confidence": self.confidence,
            "severity": self.severity,
            "details": self.details,
            "detected_at": self.detected_at.isoformat()
        }


class AnomalyDetector:
    """
    Hybrid anomaly detector with deterministic rules and ML models.
    
    Provides:
    - Off-route deviation detection
    - Unexpected stop detection
    - Overspeed detection
    - Rapid direction change detection
    - Driver offline detection
    - ML-based pattern anomalies
    - False-positive suppression
    """
    
    def __init__(self, ml_enabled: bool = True):
        """
        Initialize anomaly detector.
        
        Args:
            ml_enabled: Enable ML-based detection
        """
        self.rule_engine = get_rule_engine()
        self.ml_enabled = ml_enabled
        self.ml_detector: Optional[MLDetector] = None
        
        if ml_enabled:
            model_type = self.rule_engine.get_rule_value("ml_model_type", "isolation_forest")
            sensitivity = self.rule_engine.get_rule_value("ml_sensitivity", 0.7)
            
            self.ml_detector = create_ml_detector(
                model_type=model_type,
                contamination=1.0 - sensitivity
            )
            
            # Train with synthetic data (placeholder)
            from app.modules.safety_ai.ml_adapter import generate_training_data
            training_data = generate_training_data(1000)
            self.ml_detector.fit(training_data)
        
        # Anomaly history for false-positive suppression
        self.anomaly_history: Dict[UUID, deque] = {}
        self.last_telemetry: Dict[UUID, Dict] = {}
        
        logger.info(f"✅ AnomalyDetector initialized (ML={'enabled' if ml_enabled else 'disabled'})")
    
    def detect_off_route(
        self,
        lat: float,
        lng: float,
        polyline_coords: List[Tuple[float, float]]
    ) -> Optional[AnomalyResult]:
        """
        Detect off-route deviation using polyline distance.
        
        Args:
            lat, lng: Current position
            polyline_coords: Expected route coordinates
            
        Returns:
            AnomalyResult if off-route, else None
        """
        if not polyline_coords or len(polyline_coords) < 2:
            return None
        
        threshold_m = self.rule_engine.get_rule_value("off_route_threshold_m", 60)
        
        # Find minimum distance to polyline
        min_distance = float('inf')
        
        for i in range(len(polyline_coords) - 1):
            lat1, lng1 = polyline_coords[i]
            lat2, lng2 = polyline_coords[i + 1]
            
            # Point-to-segment distance
            distance = self._point_to_segment_distance(lat, lng, lat1, lng1, lat2, lng2)
            min_distance = min(min_distance, distance)
        
        if min_distance > threshold_m:
            severity = "high" if min_distance > threshold_m * 2 else "medium"
            
            return AnomalyResult(
                anomaly_type="off_route",
                confidence=min(0.9, min_distance / (threshold_m * 2)),
                severity=severity,
                details={
                    "distance_m": round(min_distance, 2),
                    "threshold_m": threshold_m,
                    "description": f"Vehicle {min_distance:.1f}m off expected route"
                }
            )
        
        return None
    
    def detect_unexpected_stop(
        self,
        ride_id: UUID,
        current_point: Dict,
        recent_points: List[Dict],
        pickup_coords: Optional[Tuple[float, float]] = None,
        dropoff_coords: Optional[Tuple[float, float]] = None
    ) -> Optional[AnomalyResult]:
        """
        Detect unexpected prolonged stops.
        
        Args:
            ride_id: Ride UUID
            current_point: Current telemetry point
            recent_points: Recent historical points
            pickup_coords: Pickup location (to exclude)
            dropoff_coords: Dropoff location (to exclude)
            
        Returns:
            AnomalyResult if unexpected stop, else None
        """
        stop_minutes = self.rule_engine.get_rule_value("stop_minutes", 3)
        speed_threshold = self.rule_engine.get_rule_value("stop_speed_threshold_kmh", 1.0)
        
        if len(recent_points) < 5:
            return None
        
        # Check if currently stopped
        if current_point.get('speed', 10) >= speed_threshold:
            return None
        
        # Find continuous stop duration
        stop_start = None
        for point in sorted(recent_points, key=lambda p: p['timestamp']):
            if point.get('speed', 10) < speed_threshold:
                if stop_start is None:
                    stop_start = point['timestamp']
            else:
                stop_start = None
        
        if stop_start is None:
            return None
        
        stop_duration_minutes = (current_point['timestamp'] - stop_start).total_seconds() / 60.0
        
        if stop_duration_minutes < stop_minutes:
            return None
        
        # Check if stopped at pickup or dropoff
        current_lat = current_point['lat']
        current_lng = current_point['lng']
        
        if pickup_coords:
            dist_to_pickup = calculate_distance(current_lat, current_lng, *pickup_coords)
            if dist_to_pickup < 100:  # 100m proximity
                return None
        
        if dropoff_coords:
            dist_to_dropoff = calculate_distance(current_lat, current_lng, *dropoff_coords)
            if dist_to_dropoff < 100:
                return None
        
        return AnomalyResult(
            anomaly_type="unexpected_stop",
            confidence=min(0.95, stop_duration_minutes / (stop_minutes * 2)),
            severity="high",
            details={
                "duration_minutes": round(stop_duration_minutes, 1),
                "threshold_minutes": stop_minutes,
                "description": f"Vehicle stopped for {stop_duration_minutes:.1f} minutes at unexpected location"
            }
        )
    
    def detect_overspeed(
        self,
        speed_kmh: float
    ) -> Optional[AnomalyResult]:
        """
        Detect overspeed violations.
        
        Args:
            speed_kmh: Current speed
            
        Returns:
            AnomalyResult if overspeed, else None
        """
        overspeed_threshold = self.rule_engine.get_rule_value("overspeed_kmh", 120)
        high_threshold = self.rule_engine.get_rule_value("overspeed_high_kmh", 140)
        
        if speed_kmh > high_threshold:
            return AnomalyResult(
                anomaly_type="overspeed",
                confidence=0.95,
                severity="high",
                details={
                    "speed_kmh": speed_kmh,
                    "threshold_kmh": overspeed_threshold,
                    "description": f"Extreme overspeed: {speed_kmh:.1f} km/h"
                }
            )
        
        elif speed_kmh > overspeed_threshold:
            return AnomalyResult(
                anomaly_type="overspeed",
                confidence=0.85,
                severity="medium",
                details={
                    "speed_kmh": speed_kmh,
                    "threshold_kmh": overspeed_threshold,
                    "description": f"Overspeed detected: {speed_kmh:.1f} km/h"
                }
            )
        
        return None
    
    def detect_rapid_direction_change(
        self,
        ride_id: UUID,
        current_bearing: Optional[float],
        recent_points: List[Dict]
    ) -> Optional[AnomalyResult]:
        """
        Detect rapid direction changes (potential erratic driving).
        
        Args:
            ride_id: Ride UUID
            current_bearing: Current bearing in degrees
            recent_points: Recent historical points
            
        Returns:
            AnomalyResult if rapid change, else None
        """
        if current_bearing is None or len(recent_points) < 2:
            return None
        
        threshold_degrees = self.rule_engine.get_rule_value("rapid_direction_change_degrees", 45)
        threshold_seconds = self.rule_engine.get_rule_value("rapid_direction_change_seconds", 5)
        
        # Get recent bearings within time window
        now = datetime.utcnow()
        recent_bearings = []
        
        for point in sorted(recent_points, key=lambda p: p['timestamp'], reverse=True):
            if (now - point['timestamp']).total_seconds() > threshold_seconds:
                break
            
            if point.get('bearing') is not None:
                recent_bearings.append(point['bearing'])
        
        if len(recent_bearings) < 2:
            return None
        
        # Calculate bearing changes
        for prev_bearing in recent_bearings:
            # Normalize bearing difference (-180 to 180)
            diff = abs(current_bearing - prev_bearing)
            if diff > 180:
                diff = 360 - diff
            
            if diff > threshold_degrees:
                return AnomalyResult(
                    anomaly_type="rapid_direction_change",
                    confidence=0.75,
                    severity="medium",
                    details={
                        "bearing_change": round(diff, 1),
                        "threshold_degrees": threshold_degrees,
                        "time_window_seconds": threshold_seconds,
                        "description": f"Rapid {diff:.1f}° direction change"
                    }
                )
        
        return None
    
    def detect_driver_offline(
        self,
        ride_id: UUID,
        last_telemetry_time: datetime
    ) -> Optional[AnomalyResult]:
        """
        Detect driver offline (no telemetry for extended period).
        
        Args:
            ride_id: Ride UUID
            last_telemetry_time: Timestamp of last telemetry point
            
        Returns:
            AnomalyResult if offline, else None
        """
        threshold_seconds = self.rule_engine.get_rule_value("driver_offline_seconds", 180)
        
        elapsed = (datetime.utcnow() - last_telemetry_time).total_seconds()
        
        if elapsed > threshold_seconds:
            return AnomalyResult(
                anomaly_type="driver_offline",
                confidence=0.9,
                severity="high",
                details={
                    "offline_seconds": round(elapsed, 1),
                    "threshold_seconds": threshold_seconds,
                    "description": f"No telemetry for {elapsed:.0f} seconds"
                }
            )
        
        return None
    
    def detect_ml_anomaly(
        self,
        point: Dict
    ) -> Optional[AnomalyResult]:
        """
        Detect anomalies using ML model.
        
        Args:
            point: Telemetry point
            
        Returns:
            AnomalyResult if ML detects anomaly, else None
        """
        if not self.ml_enabled or not self.ml_detector or not self.ml_detector.is_trained():
            return None
        
        try:
            is_anomaly, confidence = self.ml_detector.predict(point)
            
            if is_anomaly:
                # Determine severity based on confidence
                if confidence > 0.8:
                    severity = "high"
                elif confidence > 0.5:
                    severity = "medium"
                else:
                    severity = "low"
                
                return AnomalyResult(
                    anomaly_type="ml_anomaly",
                    confidence=confidence,
                    severity=severity,
                    details={
                        "ml_confidence": round(confidence, 3),
                        "description": "ML model detected anomalous pattern"
                    }
                )
        
        except Exception as e:
            logger.error(f"ML anomaly detection failed: {e}", exc_info=True)
        
        return None
    
    def suppress_false_positives(
        self,
        ride_id: UUID,
        anomaly: AnomalyResult
    ) -> bool:
        """
        Suppress false positives using temporal consistency.
        
        Args:
            ride_id: Ride UUID
            anomaly: Detected anomaly
            
        Returns:
            True if anomaly should be reported, False if suppressed
        """
        min_seconds = self.rule_engine.get_rule_value("false_positive_min_seconds", 15)
        min_consecutive = self.rule_engine.get_rule_value("false_positive_min_consecutive", 3)
        
        # Initialize history for ride
        if ride_id not in self.anomaly_history:
            self.anomaly_history[ride_id] = deque(maxlen=10)
        
        history = self.anomaly_history[ride_id]
        history.append((anomaly.anomaly_type, anomaly.detected_at))
        
        # Count consecutive anomalies of same type
        consecutive_count = 0
        for anom_type, _ in reversed(history):
            if anom_type == anomaly.anomaly_type:
                consecutive_count += 1
            else:
                break
        
        # Check if meets minimum consecutive threshold
        if consecutive_count < min_consecutive:
            logger.debug(f"Suppressing anomaly {anomaly.anomaly_type} (only {consecutive_count} consecutive)")
            return False
        
        # Check if meets minimum duration threshold
        first_detection = history[-consecutive_count][1]
        duration = (anomaly.detected_at - first_detection).total_seconds()
        
        if duration < min_seconds:
            logger.debug(f"Suppressing anomaly {anomaly.anomaly_type} (only {duration:.1f}s duration)")
            return False
        
        return True
    
    def analyze_point(
        self,
        ride_id: UUID,
        point: Dict,
        polyline_coords: Optional[List[Tuple[float, float]]] = None,
        recent_points: Optional[List[Dict]] = None,
        pickup_coords: Optional[Tuple[float, float]] = None,
        dropoff_coords: Optional[Tuple[float, float]] = None
    ) -> List[AnomalyResult]:
        """
        Comprehensive anomaly analysis for a telemetry point.
        
        Args:
            ride_id: Ride UUID
            point: Current telemetry point
            polyline_coords: Expected route coordinates
            recent_points: Recent historical points
            pickup_coords: Pickup location
            dropoff_coords: Dropoff location
            
        Returns:
            List of detected anomalies (after false-positive suppression)
        """
        anomalies = []
        
        # 1. Off-route detection
        if polyline_coords:
            off_route = self.detect_off_route(point['lat'], point['lng'], polyline_coords)
            if off_route:
                anomalies.append(off_route)
        
        # 2. Unexpected stop
        if recent_points:
            stop = self.detect_unexpected_stop(ride_id, point, recent_points, pickup_coords, dropoff_coords)
            if stop:
                anomalies.append(stop)
        
        # 3. Overspeed
        overspeed = self.detect_overspeed(point.get('speed', 0))
        if overspeed:
            anomalies.append(overspeed)
        
        # 4. Rapid direction change
        if recent_points:
            rapid_change = self.detect_rapid_direction_change(ride_id, point.get('bearing'), recent_points)
            if rapid_change:
                anomalies.append(rapid_change)
        
        # 5. ML-based detection
        ml_anomaly = self.detect_ml_anomaly(point)
        if ml_anomaly:
            anomalies.append(ml_anomaly)
        
        # Apply false-positive suppression
        confirmed_anomalies = []
        for anomaly in anomalies:
            if self.suppress_false_positives(ride_id, anomaly):
                confirmed_anomalies.append(anomaly)
                logger.warning(f"🚨 Anomaly detected for ride {ride_id}: {anomaly.anomaly_type} ({anomaly.severity})")
        
        # Update last telemetry
        self.last_telemetry[ride_id] = point
        
        return confirmed_anomalies
    
    def _point_to_segment_distance(
        self,
        px: float, py: float,
        ax: float, ay: float,
        bx: float, by: float
    ) -> float:
        """Calculate minimum distance from point to line segment"""
        # Vector AB
        ab_x = bx - ax
        ab_y = by - ay
        
        # Vector AP
        ap_x = px - ax
        ap_y = py - ay
        
        # AB length squared
        ab_len_sq = ab_x**2 + ab_y**2
        
        if ab_len_sq == 0:
            return calculate_distance(px, py, ax, ay)
        
        # Projection
        t = max(0, min(1, (ap_x * ab_x + ap_y * ab_y) / ab_len_sq))
        
        # Closest point
        closest_x = ax + t * ab_x
        closest_y = ay + t * ab_y
        
        return calculate_distance(px, py, closest_x, closest_y)


# Global detector instance
_anomaly_detector_instance: Optional[AnomalyDetector] = None


def get_anomaly_detector() -> AnomalyDetector:
    """Get global anomaly detector instance (singleton)"""
    global _anomaly_detector_instance
    
    if _anomaly_detector_instance is None:
        _anomaly_detector_instance = AnomalyDetector()
    
    return _anomaly_detector_instance
