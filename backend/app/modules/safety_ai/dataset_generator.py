"""
Dataset Generator for Safety AI Testing

Generates synthetic telemetry data for:
- Normal route following
- Off-route deviations
- Long stops
- Erratic motion patterns
- Overspeed events
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from uuid import uuid4
import math
import csv

import numpy as np

from app.modules.telemetry.anomaly import encode_polyline, decode_polyline

logger = logging.getLogger(__name__)


class DatasetGenerator:
    """
    Generate synthetic telemetry datasets for testing and ML training.
    
    Provides realistic patterns including normal driving and various anomalies.
    """
    
    def __init__(self, seed: int = 42):
        """
        Initialize dataset generator.
        
        Args:
            seed: Random seed for reproducibility
        """
        random.seed(seed)
        np.random.seed(seed)
        
        logger.info("✅ DatasetGenerator initialized")
    
    def generate_normal_route(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
        num_points: int = 100,
        start_time: datetime = None
    ) -> List[Dict]:
        """
        Generate normal route-following telemetry.
        
        Args:
            start_lat, start_lng: Starting coordinates
            end_lat, end_lng: Ending coordinates
            num_points: Number of telemetry points
            start_time: Starting timestamp
            
        Returns:
            List of telemetry points
        """
        if start_time is None:
            start_time = datetime.utcnow()
        
        points = []
        
        # Generate smooth interpolated path
        for i in range(num_points):
            t = i / (num_points - 1)  # 0 to 1
            
            # Smooth interpolation with slight curves
            lat = start_lat + (end_lat - start_lat) * t + np.random.normal(0, 0.0001)
            lng = start_lng + (end_lng - start_lng) * t + np.random.normal(0, 0.0001)
            
            # Realistic speed (40-70 km/h with variation)
            speed = 40 + 30 * math.sin(t * math.pi) + np.random.normal(0, 5)
            speed = max(0, min(speed, 80))
            
            # Calculate bearing
            if i > 0:
                bearing = self._calculate_bearing(
                    points[-1]['lat'], points[-1]['lng'],
                    lat, lng
                )
            else:
                bearing = self._calculate_bearing(start_lat, start_lng, end_lat, end_lng)
            
            # Increment timestamp (2-5 seconds between points)
            timestamp = start_time + timedelta(seconds=i * random.uniform(2, 5))
            
            points.append({
                "ride_id": str(uuid4()),
                "lat": lat,
                "lng": lng,
                "speed": speed,
                "bearing": bearing,
                "accuracy": random.uniform(5, 15),
                "timestamp": timestamp
            })
        
        logger.info(f"Generated {num_points} normal route points")
        return points
    
    def generate_off_route(
        self,
        polyline_coords: List[Tuple[float, float]],
        deviation_start_idx: int = None,
        deviation_distance_m: float = 100,
        num_points: int = 100,
        start_time: datetime = None
    ) -> List[Dict]:
        """
        Generate off-route deviation telemetry.
        
        Args:
            polyline_coords: Expected route coordinates
            deviation_start_idx: Index where deviation starts
            deviation_distance_m: Maximum deviation distance
            num_points: Number of telemetry points
            start_time: Starting timestamp
            
        Returns:
            List of telemetry points with off-route section
        """
        if start_time is None:
            start_time = datetime.utcnow()
        
        if deviation_start_idx is None:
            deviation_start_idx = num_points // 2
        
        points = []
        
        for i in range(num_points):
            # Get position on polyline
            polyline_idx = int((i / num_points) * (len(polyline_coords) - 1))
            base_lat, base_lng = polyline_coords[polyline_idx]
            
            # Add deviation after deviation_start_idx
            if i >= deviation_start_idx:
                # Gradual deviation
                deviation_factor = (i - deviation_start_idx) / 20.0
                deviation_factor = min(deviation_factor, 1.0)
                
                # Convert meters to degrees (approximate)
                deviation_degrees = (deviation_distance_m / 111000) * deviation_factor
                
                lat = base_lat + np.random.normal(0, deviation_degrees)
                lng = base_lng + np.random.normal(0, deviation_degrees)
            else:
                lat = base_lat + np.random.normal(0, 0.00005)
                lng = base_lng + np.random.normal(0, 0.00005)
            
            # Normal speed
            speed = random.uniform(40, 70)
            
            # Calculate bearing
            if i > 0:
                bearing = self._calculate_bearing(
                    points[-1]['lat'], points[-1]['lng'],
                    lat, lng
                )
            else:
                bearing = random.uniform(0, 360)
            
            timestamp = start_time + timedelta(seconds=i * random.uniform(2, 5))
            
            points.append({
                "ride_id": str(uuid4()),
                "lat": lat,
                "lng": lng,
                "speed": speed,
                "bearing": bearing,
                "accuracy": random.uniform(5, 15),
                "timestamp": timestamp
            })
        
        logger.info(f"Generated {num_points} off-route points (deviation at index {deviation_start_idx})")
        return points
    
    def generate_long_stop(
        self,
        stop_lat: float,
        stop_lng: float,
        stop_duration_minutes: float = 5,
        num_points: int = 60,
        start_time: datetime = None
    ) -> List[Dict]:
        """
        Generate prolonged stop telemetry.
        
        Args:
            stop_lat, stop_lng: Stop location
            stop_duration_minutes: Duration of stop
            num_points: Number of telemetry points
            start_time: Starting timestamp
            
        Returns:
            List of telemetry points with prolonged stop
        """
        if start_time is None:
            start_time = datetime.utcnow()
        
        points = []
        interval_seconds = (stop_duration_minutes * 60) / num_points
        
        for i in range(num_points):
            # Stationary position with GPS jitter
            lat = stop_lat + np.random.normal(0, 0.00002)
            lng = stop_lng + np.random.normal(0, 0.00002)
            
            # Zero or near-zero speed
            speed = abs(np.random.normal(0, 0.5))
            
            # Random bearing (stationary)
            bearing = random.uniform(0, 360)
            
            timestamp = start_time + timedelta(seconds=i * interval_seconds)
            
            points.append({
                "ride_id": str(uuid4()),
                "lat": lat,
                "lng": lng,
                "speed": speed,
                "bearing": bearing,
                "accuracy": random.uniform(5, 20),
                "timestamp": timestamp
            })
        
        logger.info(f"Generated {num_points} long stop points ({stop_duration_minutes} minutes)")
        return points
    
    def generate_erratic_motion(
        self,
        center_lat: float,
        center_lng: float,
        radius_m: float = 200,
        num_points: int = 100,
        start_time: datetime = None
    ) -> List[Dict]:
        """
        Generate erratic/zigzag motion pattern.
        
        Args:
            center_lat, center_lng: Center coordinates
            radius_m: Radius of erratic motion
            num_points: Number of telemetry points
            start_time: Starting timestamp
            
        Returns:
            List of telemetry points with erratic pattern
        """
        if start_time is None:
            start_time = datetime.utcnow()
        
        points = []
        radius_degrees = radius_m / 111000
        
        for i in range(num_points):
            # Random walk pattern
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(0, radius_degrees)
            
            lat = center_lat + distance * math.cos(angle)
            lng = center_lng + distance * math.sin(angle)
            
            # Variable speed
            speed = random.uniform(10, 60)
            
            # Erratic bearing changes
            if i > 0:
                bearing = self._calculate_bearing(
                    points[-1]['lat'], points[-1]['lng'],
                    lat, lng
                )
                # Add random bearing offset
                bearing = (bearing + random.uniform(-90, 90)) % 360
            else:
                bearing = random.uniform(0, 360)
            
            timestamp = start_time + timedelta(seconds=i * random.uniform(1, 4))
            
            points.append({
                "ride_id": str(uuid4()),
                "lat": lat,
                "lng": lng,
                "speed": speed,
                "bearing": bearing,
                "accuracy": random.uniform(10, 30),
                "timestamp": timestamp
            })
        
        logger.info(f"Generated {num_points} erratic motion points")
        return points
    
    def generate_overspeed(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
        overspeed_kmh: float = 140,
        num_points: int = 50,
        start_time: datetime = None
    ) -> List[Dict]:
        """
        Generate overspeed event telemetry.
        
        Args:
            start_lat, start_lng: Starting coordinates
            end_lat, end_lng: Ending coordinates
            overspeed_kmh: Speed during overspeed event
            num_points: Number of telemetry points
            start_time: Starting timestamp
            
        Returns:
            List of telemetry points with overspeed
        """
        if start_time is None:
            start_time = datetime.utcnow()
        
        points = []
        
        for i in range(num_points):
            t = i / (num_points - 1)
            
            lat = start_lat + (end_lat - start_lat) * t + np.random.normal(0, 0.00005)
            lng = start_lng + (end_lng - start_lng) * t + np.random.normal(0, 0.00005)
            
            # High speed with slight variation
            speed = overspeed_kmh + np.random.normal(0, 5)
            
            # Calculate bearing
            if i > 0:
                bearing = self._calculate_bearing(
                    points[-1]['lat'], points[-1]['lng'],
                    lat, lng
                )
            else:
                bearing = self._calculate_bearing(start_lat, start_lng, end_lat, end_lng)
            
            # Shorter intervals due to high speed
            timestamp = start_time + timedelta(seconds=i * random.uniform(1, 2))
            
            points.append({
                "ride_id": str(uuid4()),
                "lat": lat,
                "lng": lng,
                "speed": speed,
                "bearing": bearing,
                "accuracy": random.uniform(5, 15),
                "timestamp": timestamp
            })
        
        logger.info(f"Generated {num_points} overspeed points ({overspeed_kmh} km/h)")
        return points
    
    def export_to_csv(
        self,
        datasets: List[Tuple[str, List[Dict]]],
        output_path: str
    ):
        """
        Export datasets to CSV file.
        
        Args:
            datasets: List of (label, points) tuples
            output_path: Output CSV file path
        """
        with open(output_path, 'w', newline='') as csvfile:
            fieldnames = ['label', 'ride_id', 'lat', 'lng', 'speed', 'bearing', 'accuracy', 'timestamp']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            
            for label, points in datasets:
                for point in points:
                    row = {'label': label, **point}
                    row['timestamp'] = row['timestamp'].isoformat()
                    writer.writerow(row)
        
        total_points = sum(len(points) for _, points in datasets)
        logger.info(f"✅ Exported {total_points} points to {output_path}")
    
    def _calculate_bearing(
        self,
        lat1: float, lng1: float,
        lat2: float, lng2: float
    ) -> float:
        """Calculate bearing between two points"""
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        lng_diff = math.radians(lng2 - lng1)
        
        x = math.sin(lng_diff) * math.cos(lat2_rad)
        y = math.cos(lat1_rad) * math.sin(lat2_rad) - \
            math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(lng_diff)
        
        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360) % 360


# Example usage
def generate_complete_dataset(output_path: str = "safety_ai_dataset.csv"):
    """
    Generate a complete dataset with all anomaly types.
    
    Args:
        output_path: Output CSV file path
    """
    generator = DatasetGenerator()
    
    # Example coordinates (adjust to your region)
    start_lat, start_lng = 37.7749, -122.4194  # San Francisco
    end_lat, end_lng = 37.8044, -122.2712      # Oakland
    
    datasets = []
    
    # 1. Normal routes (200 points)
    normal_points = generator.generate_normal_route(
        start_lat, start_lng, end_lat, end_lng, num_points=200
    )
    datasets.append(("normal", normal_points))
    
    # 2. Off-route deviations (100 points)
    from app.modules.telemetry.anomaly import encode_polyline
    # Create simple polyline
    polyline_coords = [
        (start_lat + i * (end_lat - start_lat) / 50, 
         start_lng + i * (end_lng - start_lng) / 50)
        for i in range(50)
    ]
    off_route_points = generator.generate_off_route(
        polyline_coords, deviation_distance_m=150, num_points=100
    )
    datasets.append(("off_route", off_route_points))
    
    # 3. Long stops (60 points)
    stop_points = generator.generate_long_stop(
        37.7849, -122.4094, stop_duration_minutes=7, num_points=60
    )
    datasets.append(("long_stop", stop_points))
    
    # 4. Erratic motion (100 points)
    erratic_points = generator.generate_erratic_motion(
        37.7949, -122.3994, radius_m=250, num_points=100
    )
    datasets.append(("erratic_motion", erratic_points))
    
    # 5. Overspeed (50 points)
    overspeed_points = generator.generate_overspeed(
        start_lat, start_lng, end_lat, end_lng, overspeed_kmh=150, num_points=50
    )
    datasets.append(("overspeed", overspeed_points))
    
    # Export to CSV
    generator.export_to_csv(datasets, output_path)
    
    logger.info(f"✅ Complete dataset generated: {output_path}")


if __name__ == "__main__":
    # Generate dataset when run directly
    logging.basicConfig(level=logging.INFO)
    generate_complete_dataset()
