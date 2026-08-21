"""
Purpose: Custom middleware for request/response processing, security, and monitoring.
         Includes CORS, compression, trusted hosts, request logging, and rate limiting.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: Middleware is executed in order for each request/response cycle.
       Order matters: security middleware should come before application logic.
"""

import time
import logging
from typing import Callable
from uuid import uuid4

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.core.responses import error_response

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all incoming requests and responses.
    Includes request ID, method, path, status code, and response time.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and log details.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            Response from route handler
        """
        # Generate unique request ID for tracing
        request_id = str(uuid4())
        request.state.request_id = request_id

        # Record start time
        start_time = time.time()

        # Log incoming request
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} - Client: {request.client.host if request.client else 'unknown'}",
            extra={
                "extra_fields": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client_host": request.client.host if request.client else None,
                }
            },
        )

        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log exception
            logger.error(
                f"[{request_id}] Request failed with exception: {str(e)}",
                exc_info=True,
                extra={"extra_fields": {"request_id": request_id}},
            )
            # Return error response (include exception detail in debug mode)
            detail = "Internal server error"
            if settings.DEBUG:
                detail = f"Internal server error: {str(e)}"

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "status": "error",
                    "error": {
                        "detail": detail,
                        "request_id": request_id,
                    },
                },
            )

        # Calculate response time
        process_time = time.time() - start_time
        response_time_ms = round(process_time * 1000, 2)

        # Add custom headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(response_time_ms)

        # Log response
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} - Status: {response.status_code} - Time: {response_time_ms}ms",
            extra={
                "extra_fields": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "response_time_ms": response_time_ms,
                }
            },
        )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    In-memory rate limiting middleware.
    Implements per-IP rate limiting with configurable limits and windows.
    
    Configuration:
        - Default limit: 100 requests per minute (configurable per endpoint)
        - Uses in-memory cache for rate limiting
        - Adds rate limit headers to responses (X-RateLimit-*)
    
    Notes:
        - Excludes health check endpoints from rate limiting
        - Can be extended to support per-user rate limits
        - For more advanced rate limiting, consider slowapi or fastapi-limiter
    """

    # Exempt paths from rate limiting
    EXEMPT_PATHS = ["/healthz", "/health", "/live", "/ready", "/healthz/detailed", "/healthz/db"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Check rate limits for incoming request using in-memory cache.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            Response or rate limit error (429)
        """
        # Skip rate limiting for exempt paths
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        # Get client identifier (IP address)
        client_ip = request.client.host if request.client else "unknown"
        identifier = f"rate_limit:{client_ip}:{request.url.path}"

        # Import cache here to avoid circular imports
        from app.core.cache import cache

        try:
            # Check if cache is connected
            if not cache.is_connected:
                logger.warning("Cache not connected, skipping rate limiting")
                return await call_next(request)

            # Check rate limit (default: 100 requests per minute)
            allowed, remaining = await cache.check_rate_limit(
                identifier=identifier,
                limit=100,  # TODO: Make configurable per endpoint
                window=60,  # 60 seconds
            )

            if not allowed:
                request_id = getattr(request.state, "request_id", "unknown")
                logger.warning(
                    f"[{request_id}] Rate limit exceeded for {client_ip} on {request.url.path}",
                    extra={
                        "extra_fields": {
                            "request_id": request_id,
                            "client_ip": client_ip,
                            "path": request.url.path,
                        }
                    },
                )

                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "status": "error",
                        "error": {
                            "detail": "Rate limit exceeded. Please try again later.",
                            "code": "RATE_LIMIT_EXCEEDED",
                            "retry_after": 60,  # seconds
                        },
                    },
                    headers={
                        "X-RateLimit-Limit": "100",
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(60),
                        "Retry-After": "60",
                    },
                )

            # Process request
            response = await call_next(request)

            # Add rate limit headers to response
            response.headers["X-RateLimit-Limit"] = "100"
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = "60"

            return response

        except Exception as e:
            logger.error(f"Error in rate limiting middleware: {str(e)}", exc_info=True)
            # On error, allow request to proceed (fail open)
            return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.
    Implements OWASP recommended security headers.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add security headers to response.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            Response with security headers
        """
        response = await call_next(request)

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(self), microphone=()"

        # Content Security Policy (basic, adjust as needed)
        if settings.APP_ENV == "production":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )

        return response


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    Middleware to redirect HTTP requests to HTTPS in production.
    Only active when APP_ENV is set to 'production'.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Redirect HTTP to HTTPS if in production environment.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            Redirect response or normal response
        """
        # Only enforce HTTPS in production
        if settings.APP_ENV == "production":
            # Check if request is using HTTP (not HTTPS)
            if request.url.scheme == "http":
                # Build HTTPS URL
                https_url = request.url.replace(scheme="https")
                
                logger.info(
                    f"Redirecting HTTP request to HTTPS: {request.url} -> {https_url}",
                    extra={
                        "extra_fields": {
                            "original_url": str(request.url),
                            "redirect_url": str(https_url),
                        }
                    },
                )
                
                # Return 301 Permanent Redirect
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url=str(https_url), status_code=301)

        # Process request normally
        return await call_next(request)


def setup_middleware(app) -> None:
    """
    Configure all middleware for the FastAPI application.
    Order matters: middleware is executed in reverse order of addition.

    Args:
        app: FastAPI application instance

    Returns:
        None

    Middleware Order (execution order):
        1. SecurityHeadersMiddleware (last added, first executed)
        2. HTTPSRedirectMiddleware (production only)
        3. RequestLoggingMiddleware
        4. RateLimitMiddleware (Redis-based)
        5. GZipMiddleware
        6. CORSMiddleware
        7. TrustedHostMiddleware (first added, last executed, production only)
    """
    # 1. Trusted Host Middleware - Validate Host header (production only)
    if settings.APP_ENV == "production":
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.ALLOWED_HOSTS,
        )

    # 2. CORS Middleware - Cross-Origin Resource Sharing
    _cors_origins = settings.CORS_ORIGINS if settings.CORS_ORIGINS else [
        "http://localhost:9100",
        "http://localhost:9101",
        "http://localhost:3000",
        "http://localhost:5000",
        "http://127.0.0.1:9100",
        "http://127.0.0.1:9101",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
        expose_headers=["X-Request-ID", "X-Process-Time", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )

    # 3. GZip Middleware - Response compression
    app.add_middleware(
        GZipMiddleware,
        minimum_size=1000,  # Only compress responses larger than 1KB
        compresslevel=5,  # Compression level (1-9, higher = more compression)
    )

    # 4. Rate Limit Middleware - In-memory API rate limiting
    app.add_middleware(RateLimitMiddleware)

    # 5. Request Logging Middleware - Log all requests/responses with request ID
    app.add_middleware(RequestLoggingMiddleware)

    # 6. HTTPS Redirect Middleware - Force HTTPS in production
    if settings.APP_ENV == "production":
        app.add_middleware(HTTPSRedirectMiddleware)

    # 7. Security Headers Middleware - Add OWASP security headers
    app.add_middleware(SecurityHeadersMiddleware)

    logger.info("✅ Middleware configured successfully (7 layers including in-memory rate limiting)")


def setup_exception_handlers(app) -> None:
    """
    Configure custom exception handlers for the FastAPI application.
    Includes handlers for custom app exceptions, HTTP exceptions, validation errors,
    and unexpected exceptions.

    Args:
        app: FastAPI application instance

    Returns:
        None
    """
    from fastapi.exceptions import RequestValidationError
    from fastapi import HTTPException
    from app.core.exceptions import (
        AppException,
        AuthException,
        PermissionDeniedException,
        NotFoundException,
        ConflictException,
        ValidationException,
        DatabaseException,
        ExternalServiceException,
        RateLimitException,
        PaymentException,
        VerificationException,
        BusinessLogicException,
    )

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """
        Handle custom AppException and all its subclasses.

        Args:
            request: HTTP request that caused the exception
            exc: AppException instance

        Returns:
            Standardized error response
        """
        request_id = getattr(request.state, "request_id", "unknown")
        
        # Log based on severity (4xx vs 5xx)
        if exc.status_code >= 500:
            logger.error(
                f"[{request_id}] {type(exc).__name__}: {exc.message}",
                exc_info=True,
                extra={
                    "extra_fields": {
                        "request_id": request_id,
                        "exception_type": type(exc).__name__,
                        "status_code": exc.status_code,
                        "details": exc.details,
                    }
                },
            )
        else:
            logger.warning(
                f"[{request_id}] {type(exc).__name__}: {exc.message}",
                extra={
                    "extra_fields": {
                        "request_id": request_id,
                        "exception_type": type(exc).__name__,
                        "status_code": exc.status_code,
                        "details": exc.details,
                    }
                },
            )

        # Add request_id to details
        details = exc.details or {}
        details["request_id"] = request_id

        return error_response(
            message=exc.message,
            status_code=exc.status_code,
            details=details,
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """
        Handle HTTPException with standardized error response.

        Args:
            request: HTTP request that caused the exception
            exc: HTTPException instance

        Returns:
            Standardized error response
        """
        request_id = getattr(request.state, "request_id", "unknown")
        
        logger.warning(
            f"[{request_id}] HTTPException: {exc.status_code} - {exc.detail}",
            extra={
                "extra_fields": {
                    "request_id": request_id,
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            },
        )

        return error_response(
            message=exc.detail,
            status_code=exc.status_code,
            details={"request_id": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """
        Handle request validation errors with detailed error messages.

        Args:
            request: HTTP request that caused the validation error
            exc: RequestValidationError instance

        Returns:
            Standardized validation error response
        """
        request_id = getattr(request.state, "request_id", "unknown")
        
        # Format validation errors
        errors = []
        for error in exc.errors():
            errors.append({
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            })

        logger.warning(
            f"[{request_id}] Validation error: {len(errors)} field(s) failed validation",
            extra={
                "extra_fields": {
                    "request_id": request_id,
                    "errors": errors,
                }
            },
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "status": "error",
                "error": {
                    "detail": "Request validation failed",
                    "code": "VALIDATION_ERROR",
                    "errors": errors,
                    "request_id": request_id,
                },
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """
        Handle unexpected exceptions with generic error response.
        This is the catch-all handler for any unhandled exceptions.

        Args:
            request: HTTP request that caused the exception
            exc: Exception instance

        Returns:
            Generic error response
        """
        request_id = getattr(request.state, "request_id", "unknown")
        
        logger.error(
            f"[{request_id}] Unhandled exception: {str(exc)}",
            exc_info=True,
            extra={
                "extra_fields": {
                    "request_id": request_id,
                    "exception_type": type(exc).__name__,
                }
            },
        )

        detail = "Internal server error. Please contact support if the issue persists."
        if settings.DEBUG:
            detail = f"Internal server error: {str(exc)}"

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "error": {
                    "detail": detail,
                    "code": "INTERNAL_SERVER_ERROR",
                    "request_id": request_id,
                },
            },
        )

    logger.info("✅ Exception handlers configured successfully (including custom app exceptions)")
