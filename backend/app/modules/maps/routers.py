"""
Maps proxy endpoints — relays Google Maps API requests from the Flutter web
frontend so the browser never calls maps.googleapis.com directly (avoids CORS
blocks and keeps the API key server-side).

Requires GOOGLE_MAPS_KEY or GOOGLE_MAPS_API_KEY in the backend .env file.
"""

from fastapi import APIRouter, Query
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings

router = APIRouter(prefix="/api/v1/maps", tags=["Maps Proxy"])

_BASE = "https://maps.googleapis.com/maps/api"
_ROADS_BASE = "https://roads.googleapis.com/v1"


def _maps_key() -> str:
    return settings.resolved_google_maps_key()


def _denied() -> Dict[str, Any]:
    return {
        "status": "REQUEST_DENIED",
        "error_message": (
            "Maps proxy: set GOOGLE_MAPS_KEY or GOOGLE_MAPS_API_KEY in backend .env"
        ),
    }


@router.get("/autocomplete")
async def places_autocomplete(
    input: str = Query(..., min_length=1),
    location: Optional[str] = Query(None),
    radius: int = Query(50000),
    sessiontoken: Optional[str] = Query(None),
    components: str = Query("country:pk"),
):
    """Proxy for Google Places Autocomplete."""
    gkey = _maps_key()
    if not gkey:
        return _denied()
    params: dict = {
        "input": input,
        "key": gkey,
        "components": components,
    }
    if location:
        params["location"] = location
        params["radius"] = radius
    if sessiontoken:
        params["sessiontoken"] = sessiontoken

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_BASE}/place/autocomplete/json", params=params)
        return r.json()


@router.get("/place-details")
async def place_details(
    place_id: str = Query(...),
    fields: str = Query("geometry,formatted_address,name"),
    sessiontoken: Optional[str] = Query(None),
):
    """Proxy for Google Place Details."""
    gkey = _maps_key()
    if not gkey:
        return _denied()
    params: dict = {
        "place_id": place_id,
        "fields": fields,
        "key": gkey,
    }
    if sessiontoken:
        params["sessiontoken"] = sessiontoken

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_BASE}/place/details/json", params=params)
        return r.json()


@router.get("/geocode")
async def geocode(
    latlng: Optional[str] = Query(None),
    address: Optional[str] = Query(None),
    components: Optional[str] = Query(None),
):
    """Proxy for Google Geocoding (forward & reverse)."""
    gkey = _maps_key()
    if not gkey:
        return _denied()
    params: dict = {"key": gkey}
    if latlng:
        params["latlng"] = latlng
    if address:
        params["address"] = address
    if components:
        params["components"] = components

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_BASE}/geocode/json", params=params)
        return r.json()


@router.get("/directions")
async def directions(
    origin: str = Query(...),
    destination: str = Query(...),
    origin_place_id: Optional[str] = Query(None),
    destination_place_id: Optional[str] = Query(None),
    mode: str = Query("driving"),
    alternatives: bool = Query(True),
    waypoints: Optional[str] = Query(None),
    avoid: Optional[str] = Query(None),
    departure_time: Optional[str] = Query(None),
    traffic_model: Optional[str] = Query(None),
):
    """Proxy for Google Directions."""
    gkey = _maps_key()
    if not gkey:
        return _denied()

    resolved_origin = (
        f"place_id:{origin_place_id.strip()}"
        if origin_place_id and origin_place_id.strip()
        else origin
    )
    resolved_destination = (
        f"place_id:{destination_place_id.strip()}"
        if destination_place_id and destination_place_id.strip()
        else destination
    )

    params: dict = {
        "origin": resolved_origin,
        "destination": resolved_destination,
        "mode": mode,
        "alternatives": str(alternatives).lower(),
        "key": gkey,
    }
    if waypoints:
        params["waypoints"] = waypoints
    if avoid:
        params["avoid"] = avoid
    if departure_time:
        params["departure_time"] = departure_time
        params["traffic_model"] = traffic_model or "best_guess"

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{_BASE}/directions/json", params=params)
        return r.json()


@router.get("/snap-to-road")
async def snap_to_road(
    path: str = Query(..., min_length=3),
    interpolate: bool = Query(False),
):
    """Proxy for Google Roads API snapToRoads."""
    gkey = _maps_key()
    if not gkey:
        return _denied()

    params: dict = {
        "path": path,
        "interpolate": str(interpolate).lower(),
        "key": gkey,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_ROADS_BASE}/snapToRoads", params=params)
        data = r.json()
        if "status" not in data:
            data["status"] = "OK" if data.get("snappedPoints") else "ZERO_RESULTS"
        return data


@router.get("/distance-matrix")
async def distance_matrix(
    origins: str = Query(...),
    destinations: str = Query(...),
    mode: str = Query("driving"),
):
    """Proxy for Google Distance Matrix."""
    gkey = _maps_key()
    if not gkey:
        return _denied()
    params: dict = {
        "origins": origins,
        "destinations": destinations,
        "mode": mode,
        "key": gkey,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_BASE}/distancematrix/json", params=params)
        return r.json()
