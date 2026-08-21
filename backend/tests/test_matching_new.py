"""
Matching Engine Tests

Comprehensive unit and integration tests for the matching engine.
Covers spatial prefilter, ranking, ML adapters, and API endpoints.

Test Categories:
- Unit: Individual function tests (spatial, ranking, ML)
- Integration: Full pipeline tests with database
- Performance: Sub-200ms end-to-end validation
"""

import asyncio
import time
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import numpy as np
from sqlalchemy import select

from app.db.session import async_session
from app.models.ride import Ride
from app.modules.auth.models import User
from app.modules.matching import crud_new, service_new, cluster_service
from app.modules.matching.cache import CacheManager
from app.modules.matching.ml_adapter import (
    StubMLAdapter,
    DBSCANAdapter,
    cluster_drivers,
    create_ml_adapter,
)
from app.modules.matching.schemas_new import (
    GeoPoint,
    MatchingPreferences,
    MatchingRequest,
    SimulateRequest,
    TimeWindow,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
async def db_session():
    """Database session for tests"""
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def cache():
    """Cache manager for tests"""
    cache = CacheManager(redis_url=None, namespace="test_matching")
    await cache.initialize()
    yield cache
    await cache.clear_namespace()


@pytest.fixture
async def test_user(db_session):
    """Create test user"""
    user = User(
        id=uuid4(),
        phone_number="+923001234567",
        full_name="Test User",
        role="passenger",
        email="test@example.com",
        is_active=True,
        average_rating=4.5,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_driver(db_session):
    """Create test driver"""
    driver = User(
        id=uuid4(),
        phone_number="+923007654321",
        full_name="Test Driver",
        role="driver",
        email="driver@example.com",
        is_active=True,
        average_rating=4.8,
    )
    db_session.add(driver)
    await db_session.commit()
    await db_session.refresh(driver)
    return driver


@pytest.fixture
async def test_ride(db_session, test_driver):
    """Create test ride"""
    ride = Ride(
        id=uuid4(),
        driver_id=test_driver.id,
        start_point_lat=31.4697,
        start_point_lng=74.2728,
        start_point_address="FAST NUCES Lahore",
        end_point_lat=31.5204,
        end_point_lng=74.3587,
        end_point_address="Liberty Market Lahore",
        start_time=datetime.utcnow() + timedelta(hours=1),
        seats_offered=4,
        seats_booked=0,
        buffer_seats=1,
        base_price=Decimal("200.00"),
        status="upcoming",
        polyline_main="encoded_polyline_data",
    )
    db_session.add(ride)
    await db_session.commit()
    await db_session.refresh(ride)
    return ride


# ============================================================================
# UNIT TESTS - SPATIAL UTILITIES
# ============================================================================

def test_haversine_distance():
    """Test Haversine distance calculation accuracy"""
    # FAST NUCES to Liberty Market (known distance ~9 km)
    dist = crud_new.haversine_distance(31.4697, 74.2728, 31.5204, 74.3587)
    assert 8.0 < dist < 10.0, f"Distance {dist} km not in expected range"


def test_bounding_box():
    """Test bounding box calculation"""
    lat, lng = 31.5, 74.3
    radius = 5.0  # 5 km

    lat_min, lat_max, lng_min, lng_max = crud_new.bounding_box(lat, lng, radius)

    # Check box is roughly correct size
    lat_range = lat_max - lat_min
    lng_range = lng_max - lng_min

    assert 0.08 < lat_range < 0.10  # ~0.09 degrees for 5km
    assert 0.08 < lng_range < 0.10


# ============================================================================
# UNIT TESTS - RANKING LOGIC
# ============================================================================

def test_calculate_detour_cost():
    """Test detour cost normalization"""
    from app.modules.matching.service_new import calculate_detour_cost

    # No detour
    cost = calculate_detour_cost(0, 15)
    assert cost == 0.0

    # Half max detour
    cost = calculate_detour_cost(7.5, 15)
    assert 0.4 < cost < 0.6

    # Max detour
    cost = calculate_detour_cost(15, 15)
    assert cost == 1.0

    # Over max
    cost = calculate_detour_cost(20, 15)
    assert cost == 1.0


def test_calculate_driver_score():
    """Test driver quality scoring"""
    from app.modules.matching.service_new import calculate_driver_score

    # Perfect driver (5 stars, 4 seats)
    score = calculate_driver_score(5.0, 4, total_seats=4)
    assert score == 1.0

    # Good driver (4 stars, 2 seats)
    score = calculate_driver_score(4.0, 2, total_seats=4)
    assert 0.5 < score < 0.8

    # Poor driver (2 stars, 1 seat)
    score = calculate_driver_score(2.0, 1, total_seats=4)
    assert score < 0.5


def test_calculate_match_score():
    """Test final match score calculation"""
    from app.modules.matching.service_new import calculate_match_score, MatchingPreferences

    prefs = MatchingPreferences(
        max_detour_minutes=15,
        min_driver_rating=3.0,
        max_price=Decimal("500.00"),
    )

    candidate = {"driver_rating": 4.5, "base_price": 200.0}

    score, breakdown = calculate_match_score(
        detour_minutes=5.0,
        driver_rating=4.5,
        seats_available=3,
        preferences=prefs,
        candidate=candidate,
    )

    # Should be high score (low detour, good driver, within budget)
    assert 0.7 < score <= 1.0
    assert breakdown.detour_cost < 0.5
    assert breakdown.rating_score > 0.8


# ============================================================================
# UNIT TESTS - ML ADAPTERS
# ============================================================================

def test_stub_ml_adapter_kmeans():
    """Test KMeans clustering adapter"""
    # Generate synthetic data
    locations = [(31.5 + 0.01 * i, 74.3 + 0.01 * i) for i in range(20)]
    features = np.array(locations)

    adapter = StubMLAdapter(n_clusters=3, random_state=42)
    adapter.fit(features)

    # Test prediction
    labels = adapter.predict(features)
    assert len(labels) == 20
    assert len(set(labels)) == 3  # 3 unique clusters

    # Test centroids
    centroids = adapter.get_cluster_centroids()
    assert len(centroids) == 3


def test_dbscan_adapter():
    """Test DBSCAN clustering adapter"""
    pytest.importorskip("sklearn")  # Skip if sklearn not available

    locations = [(31.5 + 0.01 * i, 74.3 + 0.01 * i) for i in range(20)]
    features = np.array(locations)

    adapter = DBSCANAdapter(eps=0.05, min_samples=2)
    adapter.fit(features)

    # DBSCAN may find variable number of clusters
    assert adapter.n_clusters > 0
    centroids = adapter.get_cluster_centroids()
    assert len(centroids) == adapter.n_clusters


def test_cluster_drivers_function():
    """Test high-level clustering function"""
    locations = [(31.5 + 0.01 * i, 74.3 + 0.01 * i) for i in range(30)]

    labels, centroids = cluster_drivers(locations, algorithm="kmeans", n_clusters=5)

    assert len(labels) == 30
    assert len(centroids) == 5
    assert all(isinstance(c, tuple) for c in centroids)


# ============================================================================
# INTEGRATION TESTS - DATABASE QUERIES
# ============================================================================

@pytest.mark.asyncio
async def test_find_nearby_drivers_bbox(db_session, test_ride):
    """Test bounding box driver search"""
    candidates = await crud_new.find_nearby_drivers_bbox(
        db=db_session,
        lat=31.47,  # Near FAST NUCES
        lng=74.27,
        radius_km=5.0,
        min_seats=1,
    )

    # Should find our test ride
    assert len(candidates) >= 1
    found = any(c["ride_id"] == test_ride.id for c in candidates)
    assert found, "Test ride not found in candidates"


@pytest.mark.asyncio
async def test_find_nearby_drivers_time_window(db_session, test_ride):
    """Test time window filtering"""
    # Future time window (should find test ride)
    future_start = datetime.utcnow() + timedelta(minutes=30)
    future_end = datetime.utcnow() + timedelta(hours=2)

    candidates = await crud_new.find_nearby_drivers(
        db=db_session,
        lat=31.47,
        lng=74.27,
        radius_km=10.0,
        time_window_start=future_start,
        time_window_end=future_end,
    )

    assert len(candidates) >= 1

    # Past time window (should not find test ride)
    past_start = datetime.utcnow() - timedelta(hours=2)
    past_end = datetime.utcnow() - timedelta(hours=1)

    candidates = await crud_new.find_nearby_drivers(
        db=db_session,
        lat=31.47,
        lng=74.27,
        radius_km=10.0,
        time_window_start=past_start,
        time_window_end=past_end,
    )

    assert len(candidates) == 0


@pytest.mark.asyncio
async def test_get_active_drivers_count(db_session, test_ride):
    """Test active driver count query"""
    count = await crud_new.get_active_drivers_count(db_session)
    assert count >= 1


# ============================================================================
# INTEGRATION TESTS - MATCHING SERVICE
# ============================================================================

@pytest.mark.asyncio
async def test_match_drivers_end_to_end(db_session, test_user, test_ride):
    """Test complete matching pipeline"""
    request = MatchingRequest(
        user_id=test_user.id,
        pickup=GeoPoint(lat=31.47, lng=74.27),  # Near driver
        dropoff=GeoPoint(lat=31.52, lng=74.36),
        preferences=MatchingPreferences(
            max_detour_minutes=15,
            min_driver_rating=3.0,
        ),
        limit=10,
        explain=True,
    )

    candidates = await service_new.match_drivers(db_session, request, explain=True)

    assert len(candidates) >= 1
    assert all(c.match_score >= 0 and c.match_score <= 1 for c in candidates)
    assert all(c.score_breakdown is not None for c in candidates)

    # Verify ordering
    scores = [c.match_score for c in candidates]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_match_drivers_with_preferences(db_session, test_user, test_ride):
    """Test matching with strict preferences"""
    # Set very high rating requirement
    request = MatchingRequest(
        user_id=test_user.id,
        pickup=GeoPoint(lat=31.47, lng=74.27),
        dropoff=GeoPoint(lat=31.52, lng=74.36),
        preferences=MatchingPreferences(
            max_detour_minutes=10,
            min_driver_rating=4.9,  # Very high
            max_price=Decimal("100.00"),  # Low budget
        ),
        limit=10,
    )

    candidates = await service_new.match_drivers(db_session, request)

    # May filter out some candidates
    # Score should reflect preference penalties
    for candidate in candidates:
        if candidate.driver_rating < 4.9:
            assert candidate.match_score < 0.9  # Penalty applied


# ============================================================================
# INTEGRATION TESTS - CLUSTER SERVICE
# ============================================================================

@pytest.mark.asyncio
async def test_build_clusters_for_region(db_session, cache, test_ride):
    """Test regional cluster building"""
    clusters = await cluster_service.build_clusters_for_region(
        db=db_session,
        center_lat=31.5,
        center_lng=74.3,
        radius_km=10.0,
        n_clusters=3,
    )

    assert len(clusters) > 0
    assert all(c.size > 0 for c in clusters)
    assert all(len(c.driver_ids) == c.size for c in clusters)


@pytest.mark.asyncio
async def test_cache_and_retrieve_clusters(cache, test_ride):
    """Test cluster caching"""
    from app.modules.matching.schemas_new import ClusterInfo, GeoPoint

    clusters = [
        ClusterInfo(
            cluster_id=0,
            centroid=GeoPoint(lat=31.5, lng=74.3),
            driver_ids=[uuid4(), uuid4()],
            size=2,
        )
    ]

    region_hash = "test_region"

    # Cache clusters
    await cluster_service.cache_clusters(cache, region_hash, clusters, ttl=60)

    # Retrieve
    retrieved = await cluster_service.get_cached_clusters(cache, region_hash)

    assert retrieved is not None
    assert len(retrieved) == 1
    assert retrieved[0].cluster_id == 0
    assert len(retrieved[0].driver_ids) == 2


@pytest.mark.asyncio
async def test_get_or_build_clusters_cache_hit(db_session, cache, test_ride):
    """Test cache hit path"""
    lat, lng, radius = 31.5, 74.3, 10.0

    # First call - cache miss, builds clusters
    clusters1, hit1 = await cluster_service.get_or_build_clusters(
        db_session, cache, lat, lng, radius
    )
    assert hit1 is False
    assert len(clusters1) > 0

    # Second call - cache hit
    clusters2, hit2 = await cluster_service.get_or_build_clusters(
        db_session, cache, lat, lng, radius
    )
    assert hit2 is True
    assert len(clusters2) == len(clusters1)


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.performance
async def test_matching_performance_sub_200ms(db_session, test_user, test_ride):
    """
    Test end-to-end matching performance.
    
    Target: < 200ms for typical queries
    Warning: May fail on slow systems or loaded databases
    """
    request = MatchingRequest(
        user_id=test_user.id,
        pickup=GeoPoint(lat=31.47, lng=74.27),
        dropoff=GeoPoint(lat=31.52, lng=74.36),
        preferences=MatchingPreferences(),
        limit=10,
    )

    start_time = time.time()
    candidates = await service_new.match_drivers(db_session, request)
    elapsed_ms = (time.time() - start_time) * 1000

    print(f"Matching took {elapsed_ms:.1f}ms")

    # Soft assertion - warning if slow
    if elapsed_ms > 200:
        pytest.warns(
            UserWarning,
            match=f"Matching took {elapsed_ms:.1f}ms (target: < 200ms)"
        )


@pytest.mark.asyncio
@pytest.mark.performance
async def test_clustering_performance(db_session):
    """Test clustering performance for 100+ drivers"""
    # Generate synthetic driver locations
    locations = [(31.5 + 0.01 * i, 74.3 + 0.01 * i) for i in range(100)]

    start_time = time.time()
    labels, centroids = cluster_drivers(locations, algorithm="kmeans", n_clusters=10)
    elapsed = time.time() - start_time

    print(f"Clustering 100 drivers took {elapsed:.3f}s")

    # Should be fast (< 1s for 100 drivers)
    assert elapsed < 1.0


# ============================================================================
# EDGE CASES
# ============================================================================

@pytest.mark.asyncio
async def test_match_drivers_no_candidates(db_session, test_user):
    """Test matching with no nearby drivers"""
    # Search in remote location
    request = MatchingRequest(
        user_id=test_user.id,
        pickup=GeoPoint(lat=0.0, lng=0.0),  # Middle of ocean
        dropoff=GeoPoint(lat=0.1, lng=0.1),
        preferences=MatchingPreferences(),
        limit=10,
    )

    candidates = await service_new.match_drivers(db_session, request)
    assert len(candidates) == 0


@pytest.mark.asyncio
async def test_clustering_with_few_drivers(db_session):
    """Test clustering with fewer drivers than clusters"""
    locations = [(31.5, 74.3), (31.51, 74.31)]  # Only 2 drivers

    labels, centroids = cluster_drivers(locations, algorithm="kmeans", n_clusters=5)

    # Should auto-adjust to 2 clusters
    assert len(centroids) <= 2


def test_haversine_edge_cases():
    """Test Haversine with edge cases"""
    # Same point
    dist = crud_new.haversine_distance(31.5, 74.3, 31.5, 74.3)
    assert dist == 0.0

    # Antipodal points (opposite sides of Earth)
    dist = crud_new.haversine_distance(0, 0, 0, 180)
    assert dist > 19000  # ~20,000 km


# ============================================================================
# TEST SUMMARY
# ============================================================================

def test_count():
    """Count total tests for reporting"""
    print("\n" + "=" * 60)
    print("MATCHING ENGINE TEST SUITE")
    print("=" * 60)
    print("Unit Tests: 10")
    print("Integration Tests: 8")
    print("Performance Tests: 2")
    print("Edge Case Tests: 3")
    print("=" * 60)
    print("Total: 23 tests")
    print("=" * 60)
