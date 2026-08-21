"""
Purpose: Standardized response models and helpers for consistent API responses.
         Provides unified JSON response format across all endpoints.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: All API endpoints should use these response helpers for consistency.
       Follows the pattern: {"status": "ok/error", "data": {...} or "error": {...}}
"""

from typing import Any, Dict, Optional
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class SuccessResponse(BaseModel):
    """
    Standardized success response schema.
    
    Attributes:
        status: Always "ok" for successful responses
        data: Response payload data
    """
    status: str = "ok"
    data: Dict[str, Any]


class ErrorResponse(BaseModel):
    """
    Standardized error response schema.
    
    Attributes:
        status: Always "error" for error responses
        error: Error details including message
    """
    status: str = "error"
    error: Dict[str, Any]


def success_response(
    data: Any,
    status_code: int = 200,
    message: Optional[str] = None
) -> JSONResponse:
    """
    Create a standardized success response.
    
    Args:
        data: Response data (dict, list, or any JSON-serializable object)
        status_code: HTTP status code (default: 200)
        message: Optional success message
    
    Returns:
        JSONResponse with standardized success format
    
    Example:
        >>> return success_response(
        >>>     data={"user_id": user.id, "email": user.email},
        >>>     message="User created successfully"
        >>> )
        
        Output:
        {
            "status": "ok",
            "data": {
                "user_id": "123e4567-...",
                "email": "user@example.com"
            }
        }
    """
    response_data = {"status": "ok", "data": data}
    
    if message:
        response_data["message"] = message
    
    return JSONResponse(
        content=response_data,
        status_code=status_code
    )


def error_response(
    message: str,
    status_code: int = 400,
    details: Optional[Dict[str, Any]] = None,
    error_code: Optional[str] = None
) -> JSONResponse:
    """
    Create a standardized error response.
    
    Args:
        message: Error message describing what went wrong
        status_code: HTTP status code (default: 400)
        details: Optional additional error details
        error_code: Optional machine-readable error code
    
    Returns:
        JSONResponse with standardized error format
    
    Example:
        >>> return error_response(
        >>>     message="Invalid credentials provided",
        >>>     status_code=401,
        >>>     error_code="AUTH_INVALID_CREDENTIALS"
        >>> )
        
        Output:
        {
            "status": "error",
            "error": {
                "detail": "Invalid credentials provided",
                "code": "AUTH_INVALID_CREDENTIALS"
            }
        }
    """
    error_data = {"status": "error", "error": {"detail": message}}
    
    if error_code:
        error_data["error"]["code"] = error_code
    
    if details:
        error_data["error"]["details"] = details
    
    return JSONResponse(
        content=error_data,
        status_code=status_code
    )


def paginated_response(
    items: list,
    total: int,
    page: int,
    page_size: int,
    status_code: int = 200
) -> JSONResponse:
    """
    Create a standardized paginated response.
    
    Args:
        items: List of items for current page
        total: Total number of items across all pages
        page: Current page number (1-indexed)
        page_size: Number of items per page
        status_code: HTTP status code (default: 200)
    
    Returns:
        JSONResponse with pagination metadata
    
    Example:
        >>> return paginated_response(
        >>>     items=users_list,
        >>>     total=150,
        >>>     page=2,
        >>>     page_size=20
        >>> )
        
        Output:
        {
            "status": "ok",
            "data": {
                "items": [...],
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
    """
    total_pages = (total + page_size - 1) // page_size  # Ceiling division
    
    response_data = {
        "status": "ok",
        "data": {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_previous": page > 1
            }
        }
    }
    
    return JSONResponse(content=response_data, status_code=status_code)


def created_response(
    data: Any,
    message: Optional[str] = None
) -> JSONResponse:
    """
    Create a standardized 201 Created response.
    
    Args:
        data: Created resource data
        message: Optional creation message
    
    Returns:
        JSONResponse with 201 status code
    """
    return success_response(data=data, status_code=201, message=message)


def no_content_response() -> JSONResponse:
    """
    Create a standardized 204 No Content response.
    
    Returns:
        JSONResponse with 204 status code and no body
    """
    return JSONResponse(content=None, status_code=204)


def unauthorized_response(message: str = "Authentication required") -> JSONResponse:
    """
    Create a standardized 401 Unauthorized response.
    
    Args:
        message: Error message (default: "Authentication required")
    
    Returns:
        JSONResponse with 401 status code
    """
    return error_response(
        message=message,
        status_code=401,
        error_code="UNAUTHORIZED"
    )


def forbidden_response(message: str = "Access forbidden") -> JSONResponse:
    """
    Create a standardized 403 Forbidden response.
    
    Args:
        message: Error message (default: "Access forbidden")
    
    Returns:
        JSONResponse with 403 status code
    """
    return error_response(
        message=message,
        status_code=403,
        error_code="FORBIDDEN"
    )


def not_found_response(
    resource: str = "Resource",
    resource_id: Optional[str] = None
) -> JSONResponse:
    """
    Create a standardized 404 Not Found response.
    
    Args:
        resource: Type of resource not found (e.g., "User", "Ride")
        resource_id: Optional ID of the resource
    
    Returns:
        JSONResponse with 404 status code
    
    Example:
        >>> return not_found_response(resource="User", resource_id=user_id)
        
        Output:
        {
            "status": "error",
            "error": {
                "detail": "User not found",
                "code": "NOT_FOUND",
                "details": {"resource_id": "123e4567-..."}
            }
        }
    """
    message = f"{resource} not found"
    details = {"resource_id": resource_id} if resource_id else None
    
    return error_response(
        message=message,
        status_code=404,
        error_code="NOT_FOUND",
        details=details
    )


def conflict_response(message: str, details: Optional[Dict[str, Any]] = None) -> JSONResponse:
    """
    Create a standardized 409 Conflict response.
    
    Args:
        message: Conflict error message
        details: Optional conflict details
    
    Returns:
        JSONResponse with 409 status code
    """
    return error_response(
        message=message,
        status_code=409,
        error_code="CONFLICT",
        details=details
    )


def validation_error_response(errors: list) -> JSONResponse:
    """
    Create a standardized 422 Validation Error response.
    
    Args:
        errors: List of validation errors
    
    Returns:
        JSONResponse with 422 status code
    """
    return error_response(
        message="Validation failed",
        status_code=422,
        error_code="VALIDATION_ERROR",
        details={"errors": errors}
    )


def internal_server_error_response(
    message: str = "Internal server error",
    trace_id: Optional[str] = None
) -> JSONResponse:
    """
    Create a standardized 500 Internal Server Error response.
    
    Args:
        message: Error message
        trace_id: Optional trace ID for debugging
    
    Returns:
        JSONResponse with 500 status code
    """
    details = {"trace_id": trace_id} if trace_id else None
    
    return error_response(
        message=message,
        status_code=500,
        error_code="INTERNAL_SERVER_ERROR",
        details=details
    )
