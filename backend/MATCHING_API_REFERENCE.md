# Matching Engine API Quick Reference

## 🎯 Core Matching Endpoints

### 1. Find Matched Drivers (AI-Powered)
```http
POST /api/v1/match/find
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "ride_id": "uuid-here",
  "pickup_latitude": 31.5204,
  "pickup_longitude": 74.3587,
  "destination_latitude": 31.4697,
  "destination_longitude": 74.2728,
  "requested_seats": 2,
  "preferred_pickup_time": "2025-11-08T09:00:00+05:00",
  "max_results": 10
}
```

**Algorithm:**
- Distance Score (35%): Haversine formula, linear decay
- Time Score (25%): Gaussian decay from preferred time
- Preference Score (30%): Verified, rating, gender, vehicle type
- Route Similarity (10%): Direction vector cosine similarity

**Response:**
```json
{
  "status": "ok",
  "data": {
    "matches": [
      {
        "match_id": "uuid",
        "driver_id": "uuid",
        "driver_name": "Ahmed Khan",
        "driver_rating": 4.7,
        "vehicle_type": "sedan",
        "vehicle_model": "Honda Civic 2020",
        "available_seats": 3,
        "match_score": 87.5,
        "distance_score": 90.0,
        "time_score": 85.0,
        "preference_score": 100.0,
        "distance_km": 2.5,
        "estimated_pickup_time": 7,
        "status": "proposed",
        "expires_at": "2025-11-07T15:45:00"
      }
    ],
    "total_matches": 1
  }
}
```

---

### 2. Assign Driver to Ride
```http
POST /api/v1/match/assign
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "match_id": "uuid-here"
}
```

**Requirements:**
- User must be the passenger
- Match status must be "proposed"
- Match must not be expired

**Response:**
```json
{
  "status": "ok",
  "data": {
    "match_id": "uuid",
    "ride_id": "uuid",
    "driver_id": "uuid",
    "passenger_id": "uuid",
    "status": "assigned",
    "assigned_at": "2025-11-07T15:35:00+05:00"
  }
}
```

---

### 3. Get Match History
```http
GET /api/v1/match/history/{user_id}?as_driver=false&limit=20
Authorization: Bearer <jwt_token>
```

**Query Params:**
- `as_driver` (boolean): Get driver matches instead of passenger matches
- `limit` (integer, 1-500): Maximum records to return

**Response:**
```json
{
  "status": "ok",
  "data": {
    "matches": [
      {
        "match_id": "uuid",
        "ride_id": "uuid",
        "driver_id": "uuid",
        "passenger_id": "uuid",
        "match_score": 87.5,
        "distance_km": 2.5,
        "status": "assigned",
        "created_at": "2025-11-07T15:30:00",
        "updated_at": "2025-11-07T15:35:00"
      }
    ],
    "total_count": 1
  }
}
```

---

## 🎛️ Preference Management

### 4. Create Match Preferences
```http
POST /api/v1/match/preferences
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "prefer_verified_drivers": true,
  "prefer_same_gender": false,
  "prefer_non_smoking": true,
  "max_pickup_distance_km": 10.0,
  "max_pickup_time_minutes": 15,
  "min_driver_rating": 4.0,
  "prefer_vehicle_types": "sedan,suv"
}
```

**Preference Options:**

| Preference | Type | Range | Default | Description |
|------------|------|-------|---------|-------------|
| prefer_verified_drivers | boolean | - | true | Only match verified drivers |
| prefer_same_gender | boolean | - | false | Prefer same gender drivers |
| prefer_non_smoking | boolean | - | false | Prefer non-smoking drivers |
| max_pickup_distance_km | float | 1-50 | 10.0 | Maximum distance (km) |
| max_pickup_time_minutes | integer | 1-60 | 15 | Maximum time (minutes) |
| min_driver_rating | float | 0-5 | 3.0 | Minimum driver rating |
| prefer_vehicle_types | string | - | null | "sedan,suv,hatchback" |

**Effect on Matching:**
- **Hard Constraints** (score = 0 if violated):
  - prefer_verified_drivers: Filters out unverified drivers
  - min_driver_rating: Filters out low-rated drivers
- **Soft Preferences** (score penalties):
  - prefer_same_gender: -20 points if mismatched
  - prefer_vehicle_types: -15 points if not in list
- **Distance/Time Constraints**:
  - Used in score calculation (not hard filters)

---

### 5. Get Current Preferences
```http
GET /api/v1/match/preferences
Authorization: Bearer <jwt_token>
```

**Response:**
```json
{
  "status": "ok",
  "data": {
    "id": "uuid",
    "user_id": "uuid",
    "prefer_verified_drivers": true,
    "prefer_same_gender": false,
    "prefer_non_smoking": true,
    "max_pickup_distance_km": 10.0,
    "max_pickup_time_minutes": 15,
    "min_driver_rating": 4.0,
    "prefer_vehicle_types": "sedan,suv",
    "created_at": "2025-11-05T10:00:00",
    "updated_at": "2025-11-07T15:00:00"
  }
}
```

---

### 6. Update Preferences (Partial)
```http
PUT /api/v1/match/preferences
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "max_pickup_distance_km": 15.0,
  "min_driver_rating": 4.5
}
```

**Note:** All fields are optional - only provided fields updated.

---

### 7. Delete Preferences
```http
DELETE /api/v1/match/preferences
Authorization: Bearer <jwt_token>
```

**Response:**
```json
{
  "status": "ok",
  "data": {
    "message": "Preferences deleted successfully"
  }
}
```

---

## 🧮 Scoring Algorithm Details

### Distance Score Calculation
```python
def calculate_distance_score(distance_km, max_distance_km=10.0):
    if distance_km >= max_distance_km:
        return 0.0
    return 100.0 * (1.0 - (distance_km / max_distance_km))
```

**Examples:**
- 0 km → 100 score (at pickup location)
- 2.5 km → 75 score (25% of max distance)
- 5 km → 50 score (halfway)
- 10 km → 0 score (at max distance)
- 12 km → 0 score (beyond max distance)

---

### Time Score Calculation
```python
def calculate_time_score(request_time, driver_eta_minutes, tolerance_minutes=10):
    driver_arrival = now + timedelta(minutes=driver_eta_minutes)
    time_diff_minutes = abs((driver_arrival - request_time).total_seconds() / 60)
    
    if time_diff_minutes <= 5:
        return 100.0  # Perfect
    elif time_diff_minutes <= tolerance_minutes:
        return 100.0 - (20.0 * (time_diff_minutes - 5) / (tolerance_minutes - 5))
    else:
        excess = time_diff_minutes - tolerance_minutes
        return 80.0 * exp(-0.1 * excess)
```

**Examples:**
- 2 min diff → 100 score (perfect timing)
- 7 min diff → 92 score (within tolerance)
- 10 min diff → 80 score (at tolerance limit)
- 15 min diff → 48 score (beyond tolerance)
- 20 min diff → 29 score (significantly late)

---

### Preference Score Calculation
```python
score = 100.0

# Hard Constraints (deal breakers)
if prefer_verified and not driver_verified:
    return 0.0
if driver_rating < min_rating:
    return 0.0

# Soft Preferences (penalties)
if prefer_same_gender and gender_mismatch:
    score -= 20.0
if vehicle_type not in prefer_vehicle_types:
    score -= 15.0

# Bonuses
if driver_rating >= 4.5:
    score += 5.0

return max(0.0, min(100.0, score))
```

---

### Route Similarity Score
```python
# Calculate bearing angles
route_bearing = atan2(sin(dest_lon - pickup_lon), ...)
driver_bearing = atan2(sin(pickup_lon - driver_lon), ...)

# Angle difference
angle_diff = abs(route_bearing - driver_bearing)

# Cosine similarity
similarity = (1 + cos(angle_diff)) / 2
score = similarity * 100.0
```

**Examples:**
- Same direction (0°) → 100 score
- 45° difference → 85 score
- Perpendicular (90°) → 50 score
- Opposite (180°) → 0 score

---

### Overall Match Score
```python
match_score = (
    distance_score * 0.35 +
    time_score * 0.25 +
    preference_score * 0.30 +
    route_similarity * 0.10
)
```

**Example Calculation:**
```
distance_score = 90 (2.5km from 10km max)
time_score = 85 (7 min ETA for 9:00 AM request)
preference_score = 100 (all preferences met)
route_similarity = 80 (similar direction)

match_score = 90*0.35 + 85*0.25 + 100*0.30 + 80*0.10
            = 31.5 + 21.25 + 30 + 8
            = 90.75
```

---

## 🚨 Error Codes

| Code | Error | Cause |
|------|-------|-------|
| 400 | Bad Request | Invalid coordinates, match expired, already assigned |
| 401 | Unauthorized | Missing/invalid JWT token |
| 403 | Forbidden | Not authorized to assign this match |
| 404 | Not Found | Ride/match not found |
| 500 | Server Error | Database/algorithm failure |

---

## 🔄 Match Status Lifecycle

```
┌───────────┐
│ PROPOSED  │ ──────┐
└───────────┘       │
      │             │
      │(assign)     │(expire/reject)
      ▼             ▼
┌───────────┐   ┌───────────┐
│ ASSIGNED  │   │ EXPIRED/  │
└───────────┘   │ REJECTED  │
                └───────────┘
```

**Status Meanings:**
- `PROPOSED`: Match generated, waiting for action (15 min expiry)
- `ACCEPTED`: Driver accepted (future feature)
- `REJECTED`: Driver/passenger rejected
- `ASSIGNED`: Match confirmed, ride created
- `EXPIRED`: Match expired after 15 minutes
- `CANCELLED`: Match cancelled before assignment

---

## 🧪 Testing with cURL

### Find Matches
```bash
curl -X POST http://localhost:8000/api/v1/match/find \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "ride_id": "uuid-here",
    "pickup_latitude": 31.5204,
    "pickup_longitude": 74.3587,
    "destination_latitude": 31.4697,
    "destination_longitude": 74.2728,
    "requested_seats": 2,
    "max_results": 10
  }'
```

### Assign Match
```bash
curl -X POST http://localhost:8000/api/v1/match/assign \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "match_id": "uuid-here"
  }'
```

### Create Preferences
```bash
curl -X POST http://localhost:8000/api/v1/match/preferences \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prefer_verified_drivers": true,
    "max_pickup_distance_km": 10.0,
    "min_driver_rating": 4.0
  }'
```

---

## 📊 Performance Metrics

### Current (Database-based)
- Average response time: 200-500ms
- Concurrent requests: 10-50
- Driver search: Full table scan
- Scalability: Vertical only

### Future (Redis-based)
- Average response time: 50-100ms
- Concurrent requests: 1000+
- Driver search: Geospatial index (sub-millisecond)
- Scalability: Horizontal ready

---

## 🎯 Best Practices

1. **Always set preferences** - Better match quality
2. **Use realistic coordinates** - Valid lat/lon values
3. **Set appropriate max_results** - Balance between choice and performance
4. **Check match expiration** - Matches expire after 15 minutes
5. **Handle errors gracefully** - Check "status" field in response
6. **Monitor match scores** - Low scores indicate poor matches

---

## 📚 Swagger Documentation

Access interactive API docs at:
```
http://localhost:8000/docs
```

Test all endpoints with built-in request/response examples!

---

**Last Updated**: November 7, 2025  
**API Version**: v1  
**Base URL**: `http://localhost:8000/api/v1`
