"""
Basic tests for SmartCarpoolingApp API

Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Date: November 7, 2025
"""

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_healthz_endpoint():
    """
    Test the /healthz endpoint returns 200 OK.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/healthz")
        
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "SmartCarpoolingApp"


@pytest.mark.asyncio
async def test_root_endpoint():
    """
    Test the root endpoint returns API metadata.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
        
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "data" in data
    assert data["data"]["name"] == "SmartCarpoolingApp API"


@pytest.mark.asyncio
async def test_health_detailed_endpoint():
    """
    Test the detailed health check endpoint.
    """
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/health/detailed")
        
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
