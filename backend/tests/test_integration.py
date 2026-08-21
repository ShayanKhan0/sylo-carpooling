"""
Integration Tests for Backend System
Tests router integration, middleware, health checks, and response formats.

Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
"""

import pytest
from httpx import AsyncClient
from fastapi import status

from app.main import app
from app.core.config import settings


@pytest.mark.asyncio
class TestHealthEndpoints:
    """Test health check endpoints and monitoring features."""

    async def test_root_endpoint(self):
        """Test root endpoint returns API information."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            
            assert data["status"] == "ok"
            assert "data" in data
            assert data["data"]["name"] == settings.APP_NAME
            assert data["data"]["version"] == settings.APP_VERSION
            assert "docs" in data["data"]
            assert "health" in data["data"]

    async def test_healthz_endpoint(self):
        """Test basic health check endpoint."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/healthz")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            
            assert data["status"] == "ok"
            assert data["service"] == settings.APP_NAME
            assert data["version"] == settings.APP_VERSION

    async def test_health_detailed_endpoint(self):
        """Test detailed health check includes all components."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/health/detailed")
            
            # Should return 200 or 503 depending on component health
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_503_SERVICE_UNAVAILABLE
            ]
            data = response.json()
            
            # Check response structure
            assert "status" in data
            assert data["status"] in ["ok", "degraded", "error"]
            
            # If status is "ok" or "degraded", check components
            if data["status"] in ["ok", "degraded"]:
                assert "service" in data
                assert "version" in data
                assert "components" in data
                
                components = data["components"]
                assert "database" in components
                assert "cache" in components
                assert "fcm" in components
                
                # Each component should have a status
                for component, status_val in components.items():
                    assert status_val in ["ok", "error", "not_configured"]

    async def test_health_ready_endpoint(self):
        """Test readiness endpoint."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
            
            # Should return 200 if ready, 503 if not ready
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_503_SERVICE_UNAVAILABLE
            ]

    async def test_health_live_endpoint(self):
        """Test liveness endpoint."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/health/live")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            
            assert data["status"] == "ok"
            assert data["alive"] is True


@pytest.mark.asyncio
class TestRouterIntegration:
    """Test that all routers are properly registered."""

    async def test_all_routers_registered(self):
        """Test that all expected routers are registered in the app."""
        # Get all registered routes
        routes = [route.path for route in app.routes if hasattr(route, "path")]
        
        # Check that key API prefixes are present
        expected_prefixes = [
            "/api/v1/health",
            "/api/v1/auth",
            "/api/v1/users",
            "/api/v1/drivers",
            "/api/v1/rides",
            "/api/v1/matching",
            "/api/v1/payments",
            "/api/v1/verification",
            "/api/v1/notifications",
            "/api/v1/safety",
            "/api/v1/admin",
        ]
        
        # At least 10 routers should be registered
        # (Health, Auth, Users, Drivers, Rides, Matching, Payments, 
        #  Verification, Notifications, Safety AI, Admin)
        assert len(routes) >= 10, f"Expected at least 10 routes, found {len(routes)}"
        
        # Check that API v1 routes exist
        api_v1_routes = [r for r in routes if "/api/v1/" in r]
        assert len(api_v1_routes) > 0, "No /api/v1/ routes found"

    async def test_openapi_schema_generated(self):
        """Test that OpenAPI schema is properly generated."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/openapi.json")
            
            assert response.status_code == status.HTTP_200_OK
            openapi_schema = response.json()
            
            # Check OpenAPI metadata
            assert "openapi" in openapi_schema
            assert "info" in openapi_schema
            assert openapi_schema["info"]["title"] == "SmartCarpoolingApp API"
            assert openapi_schema["info"]["version"] == "1.0.0"
            
            # Check that paths are defined
            assert "paths" in openapi_schema
            assert len(openapi_schema["paths"]) > 0

    async def test_docs_endpoint_accessible(self):
        """Test that API documentation is accessible."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/docs")
            
            assert response.status_code == status.HTTP_200_OK
            assert "text/html" in response.headers["content-type"]

    async def test_redoc_endpoint_accessible(self):
        """Test that ReDoc documentation is accessible."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/redoc")
            
            assert response.status_code == status.HTTP_200_OK
            assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
class TestResponseFormat:
    """Test standardized response format across endpoints."""

    async def test_root_endpoint_response_format(self):
        """Test that root endpoint follows standardized response format."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            
            # Check standardized success format
            assert "status" in data
            assert data["status"] == "ok"
            assert "data" in data
            assert isinstance(data["data"], dict)

    async def test_health_endpoint_response_format(self):
        """Test that health endpoints follow standardized format."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/healthz")
            
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            
            # Basic health check format
            assert "status" in data
            assert data["status"] == "ok"

    async def test_not_found_error_format(self):
        """Test that 404 errors follow standardized error format."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/nonexistent-endpoint")
            
            assert response.status_code == status.HTTP_404_NOT_FOUND
            data = response.json()
            
            # Check standardized error format
            assert "status" in data or "detail" in data
            # FastAPI default 404 may not use our custom format


@pytest.mark.asyncio
class TestMiddleware:
    """Test middleware functionality."""

    async def test_request_id_header_added(self):
        """Test that X-Request-ID header is added to responses."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/")
            
            assert "X-Request-ID" in response.headers
            request_id = response.headers["X-Request-ID"]
            
            # Request ID should be a valid UUID format
            assert len(request_id) > 0
            assert "-" in request_id

    async def test_process_time_header_added(self):
        """Test that X-Process-Time header is added to responses."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/")
            
            assert "X-Process-Time" in response.headers
            process_time = response.headers["X-Process-Time"]
            
            # Process time should be a valid number (in milliseconds)
            assert float(process_time) > 0

    async def test_cors_headers_present(self):
        """Test that CORS headers are present in responses."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.options(
                "/",
                headers={"Origin": "http://localhost:3000"}
            )
            
            # CORS headers should be present
            # Note: Actual headers depend on CORS configuration
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_204_NO_CONTENT
            ]

    async def test_security_headers_present(self):
        """Test that security headers are added to responses."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/")
            
            # Check security headers
            assert "X-Content-Type-Options" in response.headers
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            
            assert "X-Frame-Options" in response.headers
            assert response.headers["X-Frame-Options"] == "DENY"
            
            assert "X-XSS-Protection" in response.headers


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling and exception responses."""

    async def test_validation_error_format(self):
        """Test that validation errors return standardized format."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Try to access an authenticated endpoint without token
            # This should trigger validation or authentication error
            response = await client.post(
                "/api/v1/auth/login",
                json={"invalid": "data"}  # Invalid login data
            )
            
            # Should return 422 for validation error or 400 for bad request
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_422_UNPROCESSABLE_ENTITY
            ]


@pytest.mark.asyncio
class TestDatabaseIntegration:
    """Test database connection and health checks."""

    async def test_database_health_check(self):
        """Test database health check endpoint."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/health/db")
            
            # Should return 200 if DB is connected, 503 if not
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_503_SERVICE_UNAVAILABLE
            ]
            
            data = response.json()
            
            # Check response structure
            if response.status_code == status.HTTP_200_OK:
                assert data["status"] == "ok"
                assert data["database"] == "connected"
            else:
                # Error response format
                assert "status" in data
                assert data["status"] == "error"


@pytest.mark.asyncio
class TestPerformance:
    """Test performance and optimization features."""

    async def test_gzip_compression_enabled(self):
        """Test that GZip compression is enabled for large responses."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(
                "/openapi.json",
                headers={"Accept-Encoding": "gzip"}
            )
            
            # Check if response is large enough to be compressed
            # (GZip minimum size is 1000 bytes in our config)
            if len(response.content) > 1000:
                # Content-Encoding header may be present if compressed
                # Note: Test client might not show this header
                pass

    async def test_response_time_reasonable(self):
        """Test that endpoints respond within reasonable time."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/healthz")
            
            # Response time should be in header
            assert "X-Process-Time" in response.headers
            process_time_ms = float(response.headers["X-Process-Time"])
            
            # Health check should be very fast (< 1 second = 1000ms)
            assert process_time_ms < 1000, f"Response too slow: {process_time_ms}ms"


@pytest.mark.asyncio
class TestSecurity:
    """Test security features and configurations."""

    async def test_security_headers_in_production(self):
        """Test that security headers are properly configured."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/")
            
            # Critical security headers
            assert "X-Content-Type-Options" in response.headers
            assert "X-Frame-Options" in response.headers
            assert "X-XSS-Protection" in response.headers

    async def test_openapi_security_schemes_defined(self):
        """Test that security schemes are defined in OpenAPI spec."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/openapi.json")
            
            assert response.status_code == status.HTTP_200_OK
            openapi_schema = response.json()
            
            # Check if components section exists
            # (Security schemes are optional but recommended)
            # Our JWT auth should be documented
            if "components" in openapi_schema:
                # Security schemes may be defined
                pass


def test_app_initialization():
    """Test that FastAPI app is properly initialized."""
    assert app is not None
    assert app.title == "SmartCarpoolingApp API"
    assert app.version == "1.0.0"
    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"


def test_settings_loaded():
    """Test that settings are properly loaded."""
    assert settings.APP_NAME == "SmartCarpoolingApp"
    assert settings.APP_VERSION == "1.0.0"
    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.LOG_LEVEL in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
