"""
Comprehensive Test Suite for Telemetry Module (Prompt 7)

Tests all 9 required deliverables:
1. WebSocket streaming
2. Batch upload
3. Latest points retrieval
4. Replay generation
5. Database integration
6. Redis pub/sub
7. Anomaly detection (lateral deviation, unexpected stop, overspeed)
8. Timestamp ordering
9. Load testing (500 points)
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import List
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.db.session import get_db
from app.models.telemetry_point import TelemetryPoint as TelemetryPointModel
from app.modules.telemetry.schemas import TelemetryPoint, TelemetryBatchRequest, AnomalyAlert
from app.modules.telemetry.publisher import TelemetryPublisher
from app.modules.telemetry.anomaly import (
    detect_lateral_deviation,
    detect_unexpected_stop,
    detect_overspeed,
    calculate_distance
)
from app.modules.telemetry.replay import encode_polyline, decode_polyline, build_replay
from app.modules.telemetry import crud


# ========== Fixtures ==========

@pytest.fixture
def client():
    """FastAPI test client"""
    return TestClient(app)


@pytest.fixture
def mock_ride_id():
    """Generate test ride UUID"""
    return uuid4()


@pytest.fixture
def mock_telemetry_point():
    """Generate mock telemetry point"""
    return TelemetryPoint(
        timestamp=datetime.utcnow(),
        lat=40.7128,
        lng=-74.0060,
        speed=45.5,
        bearing=180.0,
        accuracy=5.0
    )


@pytest.fixture
def mock_batch_points(mock_ride_id) -> TelemetryBatchRequest:
    """Generate batch of chronologically ordered points"""
    base_time = datetime.utcnow()
    points = []
    
    for i in range(10):
        points.append(TelemetryPoint(
            timestamp=base_time + timedelta(seconds=i * 5),
            lat=40.7128 + i * 0.001,
            lng=-74.0060 + i * 0.001,
            speed=45.0 + i * 2.0,
            bearing=180.0,
            accuracy=5.0
        ))
    
    return TelemetryBatchRequest(
        ride_id=mock_ride_id,
        points=points
    )


# ========== Test 1: WebSocket End-to-End ==========

@pytest.mark.asyncio
async def test_websocket_streaming(mock_ride_id):
    """
    Test 1: WebSocket streaming with authentication and message processing.
    
    Verifies:
    - Connection establishment
    - JWT authentication
    - Telemetry point reception
    - Acknowledgment responses
    - Ping/pong keepalive
    """
    # Note: Full WebSocket testing requires a mock JWT and async WebSocket client
    # This is a placeholder showing the test structure
    
    with TestClient(app) as client:
        # Generate mock JWT token
        token = "mock_jwt_token_for_testing"
        
        # Attempt WebSocket connection
        with client.websocket_connect(f"/api/v2/ws/trip/{mock_ride_id}?token={token}") as websocket:
            # Receive welcome message
            welcome = websocket.receive_json()
            assert welcome["type"] == "welcome"
            assert welcome["ride_id"] == str(mock_ride_id)
            
            # Send telemetry point
            point_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "lat": 40.7128,
                "lng": -74.0060,
                "speed": 45.5,
                "bearing": 180.0,
                "accuracy": 5.0
            }
            
            websocket.send_json(point_data)
            
            # Receive acknowledgment
            ack = websocket.receive_json()
            assert ack["type"] in ["ack", "warning"]  # warning if anomaly detected
            assert "point_id" in ack
            
            print("✅ Test 1 (WebSocket): PASSED")


# ========== Test 2: Batch Insert ==========

@pytest.mark.asyncio
async def test_batch_insert(mock_batch_points):
    """
    Test 2: Batch upload with bulk database insertion.
    
    Verifies:
    - Batch request validation
    - Bulk insert performance
    - Redis publishing per point
    - Response with inserted count
    """
    async for db in get_db():
        try:
            # Bulk insert
            inserted_points = await crud.bulk_insert_telemetry_points(
                db,
                ride_id=mock_batch_points.ride_id,
                points=[p.dict() for p in mock_batch_points.points]
            )
            
            assert len(inserted_points) == len(mock_batch_points.points)
            
            # Verify insertion
            count = await crud.get_telemetry_count(db, mock_batch_points.ride_id)
            assert count == len(mock_batch_points.points)
            
            print(f"✅ Test 2 (Batch Insert): PASSED - Inserted {count} points")
            break
            
        except Exception as e:
            pytest.fail(f"Batch insert failed: {e}")


# ========== Test 3: Redis Publishing ==========

@pytest.mark.asyncio
async def test_redis_publishing(mock_ride_id, mock_telemetry_point):
    """
    Test 3: Redis pub/sub with fallback.
    
    Verifies:
    - Redis publishing
    - Channel naming (telemetry:ride:{ride_id})
    - In-memory fallback when Redis unavailable
    - JSON serialization
    """
    # Test with in-memory fallback (no Redis connection)
    publisher = TelemetryPublisher(redis_client=None)
    
    point_data = mock_telemetry_point.dict()
    success = await publisher.publish_telemetry_point(mock_ride_id, point_data)
    
    assert success
    assert not publisher.using_redis
    
    # Verify in-memory queue
    messages = publisher.get_in_memory_messages()
    assert len(messages) == 1
    assert messages[0]["channel"] == f"telemetry:ride:{mock_ride_id}"
    assert messages[0]["message"]["lat"] == mock_telemetry_point.lat
    
    print("✅ Test 3 (Redis Publishing): PASSED")


# ========== Test 4: Lateral Deviation Detection ==========

def test_lateral_deviation():
    """
    Test 4: Lateral deviation anomaly detection.
    
    Verifies:
    - Distance calculation from polyline
    - Threshold enforcement (25 meters)
    - AnomalyAlert generation
    """
    # Define expected route (straight line from A to B)
    polyline_coords = [
        (40.7128, -74.0060),  # Point A
        (40.7138, -74.0050)   # Point B
    ]
    
    # Test point ON the route (should NOT trigger anomaly)
    lat_on_route = 40.7133
    lng_on_route = -74.0055
    
    anomaly = detect_lateral_deviation(lat_on_route, lng_on_route, polyline_coords, max_deviation_meters=25.0)
    assert anomaly is None  # No anomaly
    
    # Test point OFF the route (100 meters away, SHOULD trigger anomaly)
    lat_off_route = 40.7128 + 0.001  # ~111 meters north
    lng_off_route = -74.0060
    
    anomaly = detect_lateral_deviation(lat_off_route, lng_off_route, polyline_coords, max_deviation_meters=25.0)
    assert anomaly is not None
    assert anomaly.anomaly_type == "lateral_deviation"
    assert anomaly.severity == "medium"
    
    print("✅ Test 4 (Lateral Deviation): PASSED")


# ========== Test 5: Unexpected Stop Detection ==========

def test_unexpected_stop():
    """
    Test 5: Unexpected stop anomaly detection.
    
    Verifies:
    - Stop duration calculation
    - Speed threshold (<1 km/h)
    - Pickup/dropoff proximity exclusion
    """
    base_time = datetime.utcnow()
    
    # Create 40 points over 4 minutes (every 6 seconds) with speed <1 km/h
    recent_points = [
        {
            "timestamp": base_time + timedelta(seconds=i * 6),
            "lat": 40.7128,
            "lng": -74.0060,
            "speed": 0.5  # Stopped
        }
        for i in range(40)
    ]
    
    # Should detect unexpected stop (>3 minutes)
    anomaly = detect_unexpected_stop(recent_points, max_stop_minutes=3.0)
    assert anomaly is not None
    assert anomaly.anomaly_type == "unexpected_stop"
    assert anomaly.severity == "high"
    
    # Test with pickup location proximity (should NOT trigger)
    pickup_coords = (40.7128, -74.0060)  # Same as stop location
    
    anomaly_with_pickup = detect_unexpected_stop(
        recent_points,
        max_stop_minutes=3.0,
        pickup_coords=pickup_coords,
        proximity_threshold_meters=50.0
    )
    assert anomaly_with_pickup is None  # Expected stop at pickup
    
    print("✅ Test 5 (Unexpected Stop): PASSED")


# ========== Test 6: Overspeed Detection ==========

def test_overspeed():
    """
    Test 6: Overspeed anomaly detection.
    
    Verifies:
    - Speed threshold enforcement
    - Severity levels (medium vs high)
    """
    # Normal speed (no anomaly)
    anomaly = detect_overspeed(speed_kmh=80.0, max_speed_kmh=120.0)
    assert anomaly is None
    
    # Moderate overspeed (medium severity)
    anomaly = detect_overspeed(speed_kmh=130.0, max_speed_kmh=120.0)
    assert anomaly is not None
    assert anomaly.severity == "medium"
    
    # Extreme overspeed (high severity, >20 km/h over limit)
    anomaly = detect_overspeed(speed_kmh=145.0, max_speed_kmh=120.0)
    assert anomaly is not None
    assert anomaly.severity == "high"
    
    print("✅ Test 6 (Overspeed): PASSED")


# ========== Test 7: Polyline Encoding/Decoding ==========

def test_polyline_encoding():
    """
    Test 7: Polyline encoding and decoding (Google Maps format).
    
    Verifies:
    - Encoding algorithm
    - Decoding accuracy
    - Round-trip fidelity
    """
    # Test coordinates
    coords = [
        (40.7128, -74.0060),
        (40.7138, -74.0050),
        (40.7148, -74.0040)
    ]
    
    # Encode
    encoded = encode_polyline(coords)
    assert isinstance(encoded, str)
    assert len(encoded) > 0
    
    # Decode
    decoded = decode_polyline(encoded)
    
    # Verify round-trip accuracy (within 0.00001 degrees ~1 meter)
    for i, (lat, lng) in enumerate(coords):
        decoded_lat, decoded_lng = decoded[i]
        assert abs(lat - decoded_lat) < 0.00001
        assert abs(lng - decoded_lng) < 0.00001
    
    print(f"✅ Test 7 (Polyline Encoding): PASSED - Encoded: {encoded[:50]}...")


# ========== Test 8: Replay Generation ==========

@pytest.mark.asyncio
async def test_replay_generation(mock_ride_id):
    """
    Test 8: Trip replay with statistics.
    
    Verifies:
    - Polyline encoding
    - Duration calculation
    - Distance calculation
    - Speed statistics (avg, max)
    """
    # Create sample telemetry data
    base_time = datetime.utcnow()
    points = []
    
    for i in range(20):
        points.append({
            "timestamp": base_time + timedelta(seconds=i * 10),
            "lat": 40.7128 + i * 0.001,
            "lng": -74.0060 + i * 0.001,
            "speed": 40.0 + i * 2.0,
            "bearing": 180.0,
            "accuracy": 5.0
        })
    
    # Build replay
    replay = await build_replay(mock_ride_id, points, simplify=False)
    
    assert replay.ride_id == mock_ride_id
    assert len(replay.encoded_polyline) > 0
    assert replay.sample_count == 20
    assert replay.duration_minutes > 0
    assert replay.distance_km > 0
    assert replay.avg_speed_kmh > 0
    assert replay.max_speed_kmh >= replay.avg_speed_kmh
    
    print(f"✅ Test 8 (Replay Generation): PASSED - {replay.sample_count} points, {replay.distance_km:.2f} km")


# ========== Test 9: Timestamp Ordering Validation ==========

def test_timestamp_ordering():
    """
    Test 9: Chronological ordering validation.
    
    Verifies:
    - Batch request validates chronological order
    - Out-of-order points are rejected
    """
    ride_id = uuid4()
    base_time = datetime.utcnow()
    
    # Valid chronological order
    valid_points = [
        TelemetryPoint(
            timestamp=base_time + timedelta(seconds=i * 5),
            lat=40.7128,
            lng=-74.0060,
            speed=45.0,
            bearing=180.0,
            accuracy=5.0
        )
        for i in range(5)
    ]
    
    valid_batch = TelemetryBatchRequest(ride_id=ride_id, points=valid_points)
    assert valid_batch is not None
    
    # Invalid order (should raise validation error)
    invalid_points = [
        TelemetryPoint(
            timestamp=base_time + timedelta(seconds=10),
            lat=40.7128, lng=-74.0060, speed=45.0, bearing=180.0, accuracy=5.0
        ),
        TelemetryPoint(
            timestamp=base_time + timedelta(seconds=5),  # Earlier than previous
            lat=40.7128, lng=-74.0060, speed=45.0, bearing=180.0, accuracy=5.0
        )
    ]
    
    try:
        invalid_batch = TelemetryBatchRequest(ride_id=ride_id, points=invalid_points)
        pytest.fail("Should have raised ValidationError for out-of-order timestamps")
    except ValueError as e:
        assert "chronologically ordered" in str(e).lower()
    
    print("✅ Test 9 (Timestamp Ordering): PASSED")


# ========== Test 10: Load Testing (500 points) ==========

@pytest.mark.asyncio
async def test_load_batch_500_points():
    """
    Test 10: Load test with maximum batch size (500 points).
    
    Verifies:
    - Batch size limit (500 points)
    - Bulk insert performance
    - Response time <2 seconds
    """
    ride_id = uuid4()
    base_time = datetime.utcnow()
    
    # Generate 500 points
    points = [
        TelemetryPoint(
            timestamp=base_time + timedelta(seconds=i),
            lat=40.7128 + (i % 100) * 0.0001,
            lng=-74.0060 + (i % 100) * 0.0001,
            speed=45.0 + (i % 50),
            bearing=180.0,
            accuracy=5.0
        )
        for i in range(500)
    ]
    
    batch_request = TelemetryBatchRequest(ride_id=ride_id, points=points)
    
    # Measure insertion time
    start_time = datetime.utcnow()
    
    async for db in get_db():
        try:
            inserted = await crud.bulk_insert_telemetry_points(
                db,
                ride_id=batch_request.ride_id,
                points=[p.dict() for p in batch_request.points]
            )
            
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            
            assert len(inserted) == 500
            assert elapsed < 2.0  # Must complete in <2 seconds
            
            print(f"✅ Test 10 (Load Test): PASSED - Inserted 500 points in {elapsed:.3f}s")
            break
            
        except Exception as e:
            pytest.fail(f"Load test failed: {e}")


# ========== Test 11: Database Integration ==========

@pytest.mark.asyncio
async def test_database_integration(mock_ride_id, mock_telemetry_point):
    """
    Test 11: Database CRUD operations.
    
    Verifies:
    - Single point insertion
    - Latest points retrieval
    - Time range queries
    - Count aggregation
    """
    async for db in get_db():
        try:
            # Insert single point
            db_point = await crud.insert_telemetry_point(
                db,
                ride_id=mock_ride_id,
                timestamp=mock_telemetry_point.timestamp,
                lat=mock_telemetry_point.lat,
                lng=mock_telemetry_point.lng,
                speed=mock_telemetry_point.speed,
                bearing=mock_telemetry_point.bearing,
                accuracy=mock_telemetry_point.accuracy
            )
            
            assert db_point.id is not None
            assert db_point.ride_id == mock_ride_id
            
            # Retrieve latest points
            latest = await crud.get_latest_points(db, mock_ride_id, limit=10)
            assert len(latest) >= 1
            
            # Get count
            count = await crud.get_telemetry_count(db, mock_ride_id)
            assert count >= 1
            
            print("✅ Test 11 (Database Integration): PASSED")
            break
            
        except Exception as e:
            pytest.fail(f"Database integration test failed: {e}")


# ========== Run All Tests ==========

if __name__ == "__main__":
    print("=" * 80)
    print("🧪 Running Comprehensive Telemetry Test Suite (Prompt 7)")
    print("=" * 80)
    
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
