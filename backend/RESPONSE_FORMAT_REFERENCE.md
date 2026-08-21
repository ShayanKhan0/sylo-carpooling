# 📖 API Response Format Reference

## Standardized Response Formats

All API endpoints follow a consistent response format using the helpers from `app/core/responses.py`.

---

## ✅ Success Responses

### 1. Generic Success (200 OK)

```python
from app.core.responses import success_response

return success_response(
    data={"user_id": user.id, "email": user.email},
    message="User retrieved successfully"
)
```

**Response:**
```json
{
  "status": "ok",
  "data": {
    "user_id": "123e4567-e89b-12d3-a456-426614174000",
    "email": "user@example.com"
  },
  "message": "User retrieved successfully"
}
```

---

### 2. Created (201)

```python
from app.core.responses import created_response

return created_response(
    data={"ride_id": ride.id},
    message="Ride created successfully"
)
```

**Response:**
```json
{
  "status": "ok",
  "data": {
    "ride_id": "987e6543-e89b-12d3-a456-426614174000"
  },
  "message": "Ride created successfully"
}
```

---

### 3. Paginated Response (200 OK)

```python
from app.core.responses import paginated_response

return paginated_response(
    items=users_list,
    total=150,
    page=2,
    page_size=20
)
```

**Response:**
```json
{
  "status": "ok",
  "data": {
    "items": [
      {"id": "...", "name": "User 1"},
      {"id": "...", "name": "User 2"}
    ],
    "pagination": {
      "total": 150,
      "page": 2,
      "page_size": 20,
      "total_pages": 8,
      "has_next": true,
      "has_previous": true
    }
  }
}
```

---

### 4. No Content (204)

```python
from app.core.responses import no_content_response

return no_content_response()
```

**Response:** Empty body with 204 status

---

## ❌ Error Responses

### 1. Generic Error (400 Bad Request)

```python
from app.core.responses import error_response

return error_response(
    message="Invalid request parameters",
    error_code="INVALID_PARAMETERS",
    details={"field": "email", "issue": "invalid format"}
)
```

**Response:**
```json
{
  "status": "error",
  "error": {
    "detail": "Invalid request parameters",
    "code": "INVALID_PARAMETERS",
    "details": {
      "field": "email",
      "issue": "invalid format"
    }
  }
}
```

---

### 2. Unauthorized (401)

```python
from app.core.responses import unauthorized_response

return unauthorized_response(message="Invalid credentials")
```

**Response:**
```json
{
  "status": "error",
  "error": {
    "detail": "Invalid credentials",
    "code": "UNAUTHORIZED"
  }
}
```

---

### 3. Forbidden (403)

```python
from app.core.responses import forbidden_response

return forbidden_response(message="Admin access required")
```

**Response:**
```json
{
  "status": "error",
  "error": {
    "detail": "Admin access required",
    "code": "FORBIDDEN"
  }
}
```

---

### 4. Not Found (404)

```python
from app.core.responses import not_found_response

return not_found_response(
    resource="User",
    resource_id=user_id
)
```

**Response:**
```json
{
  "status": "error",
  "error": {
    "detail": "User not found",
    "code": "NOT_FOUND",
    "details": {
      "resource_id": "123e4567-e89b-12d3-a456-426614174000"
    }
  }
}
```

---

### 5. Conflict (409)

```python
from app.core.responses import conflict_response

return conflict_response(
    message="Email already exists",
    details={"email": "user@example.com"}
)
```

**Response:**
```json
{
  "status": "error",
  "error": {
    "detail": "Email already exists",
    "code": "CONFLICT",
    "details": {
      "email": "user@example.com"
    }
  }
}
```

---

### 6. Validation Error (422)

```python
from app.core.responses import validation_error_response

return validation_error_response(
    errors=[
        {"field": "email", "message": "Invalid email format", "type": "value_error.email"},
        {"field": "password", "message": "Password too short", "type": "value_error.any_str.min_length"}
    ]
)
```

**Response:**
```json
{
  "status": "error",
  "error": {
    "detail": "Validation failed",
    "code": "VALIDATION_ERROR",
    "details": {
      "errors": [
        {
          "field": "email",
          "message": "Invalid email format",
          "type": "value_error.email"
        },
        {
          "field": "password",
          "message": "Password too short",
          "type": "value_error.any_str.min_length"
        }
      ]
    }
  }
}
```

---

### 7. Internal Server Error (500)

```python
from app.core.responses import internal_server_error_response

return internal_server_error_response(
    message="Database connection failed",
    trace_id=request_id
)
```

**Response:**
```json
{
  "status": "error",
  "error": {
    "detail": "Database connection failed",
    "code": "INTERNAL_SERVER_ERROR",
    "details": {
      "trace_id": "abc12345-6789-0def-ghij-klmnopqrstuv"
    }
  }
}
```

---

## 🔄 Usage in Routers

### Example: User Creation Endpoint

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.core.responses import created_response, error_response, conflict_response
from app.modules.users import schemas, service

router = APIRouter()

@router.post("/users", status_code=201)
async def create_user(
    user_data: schemas.UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new user.
    
    Returns:
        201: User created successfully
        400: Invalid user data
        409: Email already exists
        500: Internal server error
    """
    try:
        # Check if email exists
        existing_user = await service.get_user_by_email(db, user_data.email)
        if existing_user:
            return conflict_response(
                message="Email already exists",
                details={"email": user_data.email}
            )
        
        # Create user
        user = await service.create_user(db, user_data)
        
        # Return success response
        return created_response(
            data={
                "user_id": str(user.id),
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at.isoformat()
            },
            message="User created successfully"
        )
        
    except ValueError as e:
        return error_response(
            message=str(e),
            status_code=400,
            error_code="VALIDATION_ERROR"
        )
    except Exception as e:
        logger.error(f"Error creating user: {e}", exc_info=True)
        return internal_server_error_response(
            message="Failed to create user"
        )
```

---

## 📋 Response Format Summary

| Status Code | Helper Function | Use Case |
|-------------|----------------|----------|
| 200 OK | `success_response()` | Generic success |
| 200 OK | `paginated_response()` | Paginated data |
| 201 Created | `created_response()` | Resource created |
| 204 No Content | `no_content_response()` | Successful deletion |
| 400 Bad Request | `error_response()` | Invalid input |
| 401 Unauthorized | `unauthorized_response()` | Authentication required |
| 403 Forbidden | `forbidden_response()` | Insufficient permissions |
| 404 Not Found | `not_found_response()` | Resource not found |
| 409 Conflict | `conflict_response()` | Resource conflict |
| 422 Unprocessable Entity | `validation_error_response()` | Validation failed |
| 500 Internal Server Error | `internal_server_error_response()` | Server error |

---

## 🎯 Best Practices

1. **Always use response helpers** - Don't return raw dicts
2. **Include meaningful messages** - Help clients understand what happened
3. **Provide error codes** - Enable client-side error handling
4. **Add details when useful** - Include relevant context
5. **Log errors appropriately** - Use logger for server errors
6. **Be consistent** - All endpoints should follow this format

---

## 🔗 Related Files

- `app/core/responses.py` - Response helper functions
- `app/core/middleware.py` - Exception handlers
- `app/core/logger.py` - Logging configuration

---

**Author:** M. Mobeen Shoukat Ch  
**Partner:** M. Shayan Khan  
**Date:** November 8, 2025  
**Project:** SmartCarpoolingApp Backend
