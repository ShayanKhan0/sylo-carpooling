"""
Module: Custom Exceptions
Purpose: Application-specific exception classes for better error handling.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Date: November 8, 2025
"""

from typing import Any, Optional, Dict
from fastapi import status


class AppException(Exception):
    """
    Base application exception.
    All custom exceptions should inherit from this.
    """
    
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class AuthException(AppException):
    """Authentication/authorization related exceptions."""
    
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details
        )


class PermissionDeniedException(AppException):
    """Permission/authorization exceptions."""
    
    def __init__(self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details
        )


class NotFoundException(AppException):
    """Resource not found exceptions."""
    
    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details
        )


class ConflictException(AppException):
    """Resource conflict exceptions (e.g., duplicate email)."""
    
    def __init__(self, message: str = "Resource conflict", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details=details
        )


class ValidationException(AppException):
    """Data validation exceptions."""
    
    def __init__(self, message: str = "Validation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details
        )


class DatabaseException(AppException):
    """Database operation exceptions."""
    
    def __init__(self, message: str = "Database operation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class ExternalServiceException(AppException):
    """External service (payment gateway, FCM, etc.) exceptions."""
    
    def __init__(self, message: str = "External service error", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details
        )


class RateLimitException(AppException):
    """Rate limit exceeded exceptions."""
    
    def __init__(self, message: str = "Rate limit exceeded", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details=details
        )


class PaymentException(AppException):
    """Payment processing exceptions."""
    
    def __init__(self, message: str = "Payment processing failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            details=details
        )


class VerificationException(AppException):
    """Document verification exceptions."""
    
    def __init__(self, message: str = "Verification failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class BusinessLogicException(AppException):
    """Business logic violation exceptions."""
    
    def __init__(self, message: str = "Business logic violation", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


# BadRequestException class (same as BusinessLogicException)
class BadRequestException(AppException):
    """Bad request exceptions."""
    
    def __init__(self, message: str = "Bad request", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


# Forbidden exception (alias for PermissionDeniedException)
class ForbiddenException(AppException):
    """Forbidden access exceptions."""
    
    def __init__(self, message: str = "Forbidden", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details
        )


# Aliases for backward compatibility
NotFoundError = NotFoundException
ConflictError = ConflictException
ValidationError = ValidationException
ForbiddenError = PermissionDeniedException
BadRequestError = BadRequestException
