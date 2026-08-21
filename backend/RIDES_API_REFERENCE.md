# Rides API Quick Reference Guide

## 🚗 Driver Endpoints

### 1. Create New Ride
```http
POST /api/v1/rides/create
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "origin": "FAST NUCES, Lahore",
  "destination": "Liberty Market, Gulberg",
  "departure_time": "2025-11-08T09:00:00+05:00",
  "available_seats": 3,
  "price_per_seat": 150.0,
  "vehicle_id": "uuid-here",
  "estimated_duration": 30,
  "route_distance_km": 12.5
}
```
**Requirements**: Verified driver, active verified vehicle, future departure time  
**Response**: 201 Created with ride details

---

### 2. Get My Rides (Driver)
```http
GET /api/v1/rides/my/driver?status=scheduled
Authorization: Bearer <jwt_token>
```
**Query Params**: `status` (optional) - scheduled/ongoing/completed/cancelled  
**Response**: List of driver's rides ordered by departure time

---

### 3. Update Ride Details
```http
PUT /api/v1/rides/{ride_id}
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "departure_time": "2025-11-08T10:00:00+05:00",
  "price_per_seat": 200.0,
  "available_seats": 4
}
```
**Requirements**: Must be ride owner, ride not started  
**Response**: Updated ride details

---

### 4. Update Ride Status
```http
PUT /api/v1/rides/{ride_id}/status
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "status": "ongoing"
}
```
**Valid Transitions**:
- `scheduled` → `ongoing` (start trip)
- `ongoing` → `completed` (end trip)
- `scheduled` → `cancelled` (cancel before start)

**Side Effects on Completion**:
- All bookings marked "completed"
- Driver stats updated (total_rides, total_earnings)

---

### 5. Delete Ride
```http
DELETE /api/v1/rides/{ride_id}
Authorization: Bearer <jwt_token>
```
**Requirements**: Must be ride owner, no active bookings  
**Response**: Deletion confirmation

---

### 6. Get Driver Statistics
```http
GET /api/v1/rides/my/stats/driver
Authorization: Bearer <jwt_token>
```
**Response**:
```json
{
  "status": "ok",
  "data": {
    "total_rides_created": 25,
    "total_rides_completed": 20,
    "total_rides_cancelled": 2,
    "total_earnings": 15000.0,
    "average_occupancy_rate": 0.75
  }
}
```

---

## 👥 Passenger Endpoints

### 7. List Available Rides
```http
GET /api/v1/rides/available?origin=FAST&destination=Liberty&min_seats=2&max_price=200&departure_after=2025-11-08T08:00:00
Authorization: Bearer <jwt_token>
```
**Query Params** (all optional):
- `origin` - Partial match on origin location
- `destination` - Partial match on destination
- `min_seats` - Minimum available seats (1-8)
- `max_price` - Maximum price per seat
- `departure_after` - ISO datetime filter

**Auto-Filters**:
- Only `scheduled` status rides
- Only rides with `available_seats > 0`
- Only future rides (`departure_time > now`)

**Response**: List ordered by departure time (earliest first)

---

### 8. Get Ride Details
```http
GET /api/v1/rides/{ride_id}
Authorization: Bearer <jwt_token>
```
**Response**: Complete ride info with all bookings and booked_seats_count

---

### 9. Book a Ride
```http
POST /api/v1/rides/book
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "ride_id": "uuid-here",
  "booked_seats": 2
}
```
**Requirements**:
- Ride status must be "scheduled"
- Sufficient seats available
- No existing active booking for this ride

**Automatic Calculations**:
- `total_price = booked_seats × ride.price_per_seat`
- `ride.available_seats -= booked_seats`
- `ride.total_earnings += total_price`

**Response**: 201 Created with booking details

---

### 10. Get My Bookings
```http
GET /api/v1/rides/my/bookings?status=booked
Authorization: Bearer <jwt_token>
```
**Query Params**: `status` (optional) - booked/cancelled/completed  
**Response**: List with full ride details for each booking

---

### 11. Cancel Booking
```http
PUT /api/v1/rides/bookings/{booking_id}/cancel
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "reason": "Change of plans"
}
```
**Requirements**:
- Must be booking owner
- Ride must not have started (status != "ongoing")

**Automatic Adjustments**:
- `ride.available_seats += booked_seats`
- `ride.total_earnings -= total_price`
- Cancellation time recorded
- Payment status marked for refund

**Response**: Updated booking with cancellation details

---

### 12. Get Passenger Statistics
```http
GET /api/v1/rides/my/stats/passenger
Authorization: Bearer <jwt_token>
```
**Response**:
```json
{
  "status": "ok",
  "data": {
    "total_bookings": 15,
    "total_spent": 4500.0,
    "active_bookings": 2,
    "completed_rides": 12,
    "cancelled_bookings": 1
  }
}
```

---

## 📊 Response Format

All endpoints return standardized response:

### Success Response
```json
{
  "status": "ok",
  "data": { /* response data */ },
  "error": null
}
```

### Error Response
```json
{
  "status": "error",
  "data": null,
  "error": "Error message here"
}
```

---

## 🔒 Authentication

All endpoints require JWT authentication via `Authorization: Bearer <token>` header.

Get token from:
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

---

## 🚨 Common Error Codes

| Code | Meaning | Example |
|------|---------|---------|
| 400 | Bad Request | Invalid data, insufficient seats |
| 401 | Unauthorized | Missing/invalid JWT token |
| 403 | Forbidden | Unverified driver, not ride owner |
| 404 | Not Found | Ride/booking doesn't exist |
| 500 | Server Error | Database connection issue |

---

## 🧪 Testing with cURL

### Create Ride
```bash
curl -X POST http://localhost:8000/api/v1/rides/create \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "FAST NUCES",
    "destination": "Liberty Market",
    "departure_time": "2025-11-08T09:00:00+05:00",
    "available_seats": 3,
    "price_per_seat": 150.0,
    "vehicle_id": "uuid-here",
    "estimated_duration": 30,
    "route_distance_km": 12.5
  }'
```

### List Available Rides
```bash
curl -X GET "http://localhost:8000/api/v1/rides/available?origin=FAST&min_seats=2" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Book Ride
```bash
curl -X POST http://localhost:8000/api/v1/rides/book \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "ride_id": "uuid-here",
    "booked_seats": 2
  }'
```

---

## 📝 Validation Rules

### Ride Creation
- `departure_time`: Must be in the future
- `price_per_seat`: 50 to 10,000 PKR
- `available_seats`: 1 to 8 passengers
- `estimated_duration`: 5 to 720 minutes
- `route_distance_km`: 0 to 1000 km

### Booking
- `booked_seats`: 1 to 8 passengers
- Must not exceed `ride.available_seats`
- Cannot book same ride twice

---

## 🔄 Status Lifecycle

```
┌─────────────┐
│  scheduled  │ ──────┐
└─────────────┘       │
      │               │
      │ (start)       │ (cancel)
      ▼               ▼
┌─────────────┐   ┌─────────────┐
│   ongoing   │   │  cancelled  │
└─────────────┘   └─────────────┘
      │
      │ (complete)
      ▼
┌─────────────┐
│  completed  │
└─────────────┘
```

---

## 🎯 Quick Tips

1. **Always filter available rides** - Use query params to get relevant results
2. **Check seat availability** - Before booking, verify `available_seats >= booked_seats`
3. **Update status properly** - Follow the status lifecycle diagram
4. **Cancel early** - Cannot cancel after ride starts
5. **Verify driver** - Only verified drivers can create rides
6. **Use statistics** - Track performance with stats endpoints

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
