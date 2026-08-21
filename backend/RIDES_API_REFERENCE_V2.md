# Rides & Scheduling API Reference (Prompt 5)

Quick reference for testing all Prompt 5 endpoints via Swagger UI or curl.

## Base URL
```
http://localhost:8000
```

## Authentication
All endpoints require JWT token in Authorization header:
```
Authorization: Bearer <your_jwt_token>
```

---

## 1. Create Ride (Driver)

**Endpoint:** `POST /api/v2/rides`

**Request Body:**
```json
{
  "start_point": {
    "lat": 31.4697,
    "lng": 74.2728,
    "address": "FAST NUCES, Lahore"
  },
  "end_point": {
    "lat": 31.5204,
    "lng": 74.3587,
    "address": "Liberty Market, Gulberg"
  },
  "start_time": "2025-12-09T08:00:00+05:00",
  "polyline_main": "u~o{Aq~{rMoB_@mC...",
  "seats_offered": 4,
  "buffer_seats": 1,
  "base_price": 150.00
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "driver_id": "...",
  "start_point": {...},
  "end_point": {...},
  "seats_available": 3,
  "status": "OPEN"
}
```

---

## 2. Update Ride (Driver)

**Endpoint:** `PATCH /api/v2/rides/{ride_id}`

**Request Body:**
```json
{
  "seats_offered": 5,
  "buffer_seats": 2,
  "base_price": 200.00,
  "start_time": "2025-12-09T09:00:00+05:00"
}
```

---

## 3. Get Driver Upcoming Rides

**Endpoint:** `GET /api/v2/rides/driver/upcoming?limit=50`

**Response:**
```json
[
  {
    "id": "...",
    "start_time": "2025-12-09T08:00:00+05:00",
    "seats_available": 3,
    "status": "OPEN"
  }
]
```

---

## 4. Search Rides (Geo-Radius) ⭐ CORE FEATURE

**Endpoint:** `POST /api/v2/rides/search`

**Request Body:**
```json
{
  "origin": {
    "lat": 31.4697,
    "lng": 74.2728
  },
  "destination": {
    "lat": 31.5204,
    "lng": 74.3587
  },
  "radius_km": 5.0,
  "date": "2025-12-09",
  "min_seats": 2,
  "max_price": 200.00
}
```

**Response:**
```json
[
  {
    "id": "...",
    "driver_id": "...",
    "start_point": {"lat": 31.4700, "lng": 74.2730, "address": "..."},
    "seats_available": 3,
    "base_price": 150.00,
    "distance_from_origin_km": 0.5,
    "distance_from_destination_km": 0.3
  }
]
```

**Search Algorithm:**
- Uses Haversine formula to calculate distances
- Filters rides within radius of BOTH origin and destination
- Only returns OPEN rides with min_seats available

---

## 5. Book Seat Atomically ⭐ CORE FEATURE

**Endpoint:** `POST /api/v2/rides/{ride_id}/book`

**Request Body:**
```json
{
  "seats_reserved": 2,
  "expected_fare": 300.00
}
```

**Response:**
```json
{
  "id": "booking-uuid",
  "ride_id": "...",
  "passenger_id": "...",
  "seats_reserved": 2,
  "fare": 300.00,
  "status": "RESERVED",
  "version": 0,
  "created_at": "2025-12-08T10:30:00Z"
}
```

**Error Responses:**
- **409 Conflict:** Not enough seats available
- **400 Bad Request:** Already have booking for this ride
- **404 Not Found:** Ride doesn't exist

---

## 6. Cancel Booking

**Endpoint:** `POST /api/v2/rides/bookings/{booking_id}/cancel`

**Request Body:**
```json
{
  "reason": "Change of plans"
}
```

**Response:**
```json
{
  "id": "booking-uuid",
  "status": "CANCELLED",
  "version": 1
}
```

---

## 7. Create Recurring Schedule ⭐ CORE FEATURE

**Endpoint:** `POST /api/v2/rides/schedule`

**Request Body:**
```json
{
  "days_of_week": ["Mon", "Wed", "Fri"],
  "time": "08:00:00",
  "start_point": {
    "lat": 31.4697,
    "lng": 74.2728,
    "address": "FAST NUCES, Lahore"
  },
  "end_point": {
    "lat": 31.5204,
    "lng": 74.3587,
    "address": "Liberty Market"
  },
  "seats_offered": 4,
  "buffer_seats": 1,
  "base_price": 150.00,
  "start_date": "2025-12-09",
  "end_date": "2026-06-30",
  "polyline_main": "u~o{Aq~{rMoB_@..."
}
```

**Response:**
```json
{
  "id": "schedule-uuid",
  "user_id": "...",
  "days_of_week": ["Mon", "Wed", "Fri"],
  "time": "08:00:00",
  "is_active": true,
  "created_at": "2025-12-08T10:00:00Z"
}
```

**Notes:**
- Celery task will materialize this schedule into actual rides daily
- Runs at midnight UTC for next 7 days
- Rides will be created automatically on matching days

---

## 8. Get My Schedules

**Endpoint:** `GET /api/v2/rides/schedule/my-schedules?active_only=true`

**Response:**
```json
[
  {
    "id": "...",
    "days_of_week": ["Mon", "Wed", "Fri"],
    "time": "08:00:00",
    "start_date": "2025-12-09",
    "end_date": "2026-06-30",
    "is_active": true
  }
]
```

---

## 9. Get Ride Details

**Endpoint:** `GET /api/v2/rides/{ride_id}`

**Response:**
```json
{
  "id": "...",
  "driver_id": "...",
  "start_point": {...},
  "end_point": {...},
  "start_time": "2025-12-09T08:00:00+05:00",
  "seats_offered": 4,
  "seats_booked": 1,
  "buffer_seats": 1,
  "seats_available": 2,
  "base_price": 150.00,
  "status": "OPEN",
  "polyline_main": "..."
}
```

---

## 10. Check Available Seats

**Endpoint:** `GET /api/v2/rides/{ride_id}/available-seats`

**Response:**
```json
{
  "ride_id": "...",
  "seats_offered": 4,
  "seats_booked": 1,
  "buffer_seats": 1,
  "seats_available": 2
}
```

**Calculation:**
```
seats_available = seats_offered - seats_booked - buffer_seats
```

---

## Testing Scenarios

### Scenario 1: Basic Ride Booking Flow
1. Driver creates ride → `POST /api/v2/rides`
2. Passenger searches for rides → `POST /api/v2/rides/search`
3. Passenger books seat → `POST /api/v2/rides/{ride_id}/book`
4. Check updated availability → `GET /api/v2/rides/{ride_id}/available-seats`

### Scenario 2: Recurring Schedule
1. Driver creates schedule → `POST /api/v2/rides/schedule`
2. Wait for Celery task (or trigger manually)
3. Check upcoming rides → `GET /api/v2/rides/driver/upcoming`
4. Passengers can now search and book these rides

### Scenario 3: Race Condition Test
1. Create ride with 4 seats, 1 buffer (3 available)
2. Have 3 users try to book 2 seats each simultaneously
3. Only 1 should succeed, others get 409 Conflict

### Scenario 4: Geo-Radius Search
1. Create multiple rides at different locations
2. Search with small radius (2 km)
3. Search with large radius (10 km)
4. Verify only nearby rides are returned

---

## Error Codes

| Code | Meaning | Common Causes |
|------|---------|---------------|
| 400  | Bad Request | Invalid data, duplicate booking |
| 401  | Unauthorized | Missing/invalid JWT token |
| 403  | Forbidden | Not the driver of this ride |
| 404  | Not Found | Ride/booking doesn't exist |
| 409  | Conflict | Not enough seats, race condition |
| 422  | Validation Error | Invalid schema fields |
| 500  | Server Error | Database/internal error |

---

## Swagger UI Testing

1. Navigate to: `http://localhost:8000/docs`
2. Click **Authorize** button (top right)
3. Enter JWT token: `Bearer <your_token>`
4. Expand endpoint → Click **Try it out**
5. Fill request body → Click **Execute**
6. View response below

---

## Curl Examples

### Create Ride
```bash
curl -X POST "http://localhost:8000/api/v2/rides" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "start_point": {"lat": 31.4697, "lng": 74.2728, "address": "FAST NUCES"},
    "end_point": {"lat": 31.5204, "lng": 74.3587, "address": "Liberty Market"},
    "start_time": "2025-12-09T08:00:00+05:00",
    "seats_offered": 4,
    "buffer_seats": 1,
    "base_price": 150.00
  }'
```

### Search Rides
```bash
curl -X POST "http://localhost:8000/api/v2/rides/search" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": {"lat": 31.4697, "lng": 74.2728},
    "destination": {"lat": 31.5204, "lng": 74.3587},
    "radius_km": 5.0,
    "min_seats": 2
  }'
```

### Book Seat
```bash
curl -X POST "http://localhost:8000/api/v2/rides/RIDE_ID/book" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"seats_reserved": 2}'
```

---

## Database Migration

Before testing, run the migration:

```bash
cd backend
alembic upgrade head
```

This will:
- Add `buffer_seats` column to `rides` table
- Add `version` column to `bookings` table
- Create `recurring_schedules` table
- Create all necessary indexes

---

## Celery Task (Schedule Materialization)

### Start Celery Worker
```bash
celery -A app.tasks worker --loglevel=info
```

### Start Celery Beat (Scheduler)
```bash
celery -A app.tasks beat --loglevel=info
```

### Manual Trigger (via Python)
```python
from app.tasks.schedule_materialization import materialize_specific_date_task
from datetime import date

# Materialize for specific date
task = materialize_specific_date_task.delay("2025-12-09")
print(f"Task ID: {task.id}")
```

---

## Performance Notes

- **Atomic Booking:** Uses database-level locking (SELECT FOR UPDATE)
- **Geo-Search:** In-memory Haversine calculation (fast for < 10k rides)
- **Indexes:** Spatial indexes on lat/lng for faster queries
- **Concurrent Bookings:** Handled atomically, no race conditions

---

## Support

For issues or questions:
- Check Swagger UI: `http://localhost:8000/docs`
- Review logs: `backend/logs/app.log`
- Run tests: `pytest tests/test_rides_v2_prompt5.py -v`

---

**Last Updated:** December 8, 2025  
**Authors:** M. Mobeen Shoukat Ch & M. Shayan Khan
