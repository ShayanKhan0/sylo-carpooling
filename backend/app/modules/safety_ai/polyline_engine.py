"""
Polyline Engine for Safety AI

Computes main and alternate route polylines using Google Directions API.
Stores results in database for real-time route validation.
"""

import logging
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import asyncio

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from app.core.config import settings
from app.models.ride import Ride

logger = logging.getLogger(__name__)


class PolylineEngine:
    """
    Manages polyline computation and storage for ride routes.
    
    Uses Google Directions API to compute main and alternate routes.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize polyline engine.
        
        Args:
            api_key: Google Maps API key (default: from settings)
        """
        self.api_key = api_key or settings.GOOGLE_MAPS_KEY
        self.base_url = "https://maps.googleapis.com/maps/api/directions/json"
    
    async def compute_main_polyline(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float
    ) -> Optional[str]:
        """
        Compute main (fastest) route polyline.
        
        Args:
            start_lat, start_lng: Starting coordinates
            end_lat, end_lng: Ending coordinates
            
        Returns:
            Encoded polyline string or None if failed
        """
        if not self.api_key:
            logger.warning("Google Maps API key not configured, skipping polyline computation")
            return None
        
        try:
            params = {
                "origin": f"{start_lat},{start_lng}",
                "destination": f"{end_lat},{end_lng}",
                "mode": "driving",
                "alternatives": "false",
                "key": self.api_key
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
            
            if data.get("status") != "OK":
                logger.error(f"Google Directions API error: {data.get('status')}")
                return None
            
            routes = data.get("routes", [])
            if not routes:
                logger.warning("No routes returned from Google Directions API")
                return None
            
            # Get first route's overview polyline
            polyline = routes[0].get("overview_polyline", {}).get("points")
            
            if polyline:
                logger.info(f"✅ Computed main polyline: {len(polyline)} chars")
                return polyline
            else:
                logger.warning("No polyline in route response")
                return None
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling Google Directions API: {e}")
            return None
        
        except Exception as e:
            logger.error(f"Failed to compute main polyline: {e}", exc_info=True)
            return None
    
    async def compute_alternate_polylines(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
        max_routes: int = 5
    ) -> List[str]:
        """
        Compute alternate route polylines.
        
        Args:
            start_lat, start_lng: Starting coordinates
            end_lat, end_lng: Ending coordinates
            max_routes: Maximum alternate routes to compute
            
        Returns:
            List of encoded polyline strings (may be empty)
        """
        if not self.api_key:
            logger.warning("Google Maps API key not configured, skipping alternates")
            return []
        
        try:
            params = {
                "origin": f"{start_lat},{start_lng}",
                "destination": f"{end_lat},{end_lng}",
                "mode": "driving",
                "alternatives": "true",  # Request alternate routes
                "key": self.api_key
            }
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
            
            if data.get("status") != "OK":
                logger.error(f"Google Directions API error: {data.get('status')}")
                return []
            
            routes = data.get("routes", [])
            if len(routes) <= 1:
                logger.info("No alternate routes available")
                return []
            
            # Extract polylines from alternate routes (skip first which is main)
            alternates = []
            for route in routes[1:max_routes]:
                polyline = route.get("overview_polyline", {}).get("points")
                if polyline:
                    alternates.append(polyline)
            
            logger.info(f"✅ Computed {len(alternates)} alternate polylines")
            return alternates
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling Google Directions API: {e}")
            return []
        
        except Exception as e:
            logger.error(f"Failed to compute alternate polylines: {e}", exc_info=True)
            return []
    
    async def compute_all_polylines(
        self,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
        max_alternates: int = 5
    ) -> Tuple[Optional[str], List[str]]:
        """
        Compute main and alternate polylines in parallel.
        
        Args:
            start_lat, start_lng: Starting coordinates
            end_lat, end_lng: Ending coordinates
            max_alternates: Maximum alternate routes
            
        Returns:
            Tuple of (main_polyline, list_of_alternates)
        """
        # Run both API calls in parallel
        results = await asyncio.gather(
            self.compute_main_polyline(start_lat, start_lng, end_lat, end_lng),
            self.compute_alternate_polylines(start_lat, start_lng, end_lat, end_lng, max_alternates),
            return_exceptions=True
        )
        
        main_polyline = results[0] if not isinstance(results[0], Exception) else None
        alternates = results[1] if not isinstance(results[1], Exception) else []
        
        return main_polyline, alternates
    
    async def store_polylines_in_db(
        self,
        db: AsyncSession,
        ride_id: UUID,
        main_polyline: Optional[str],
        alternates: List[str]
    ) -> bool:
        """
        Store computed polylines in database.
        
        Args:
            db: Database session
            ride_id: Ride UUID
            main_polyline: Main route polyline
            alternates: List of alternate polylines
            
        Returns:
            True if stored successfully
        """
        try:
            # Convert alternates list to JSON-serializable format
            alternates_json = alternates if alternates else []
            
            # Update ride record
            stmt = (
                update(Ride)
                .where(Ride.id == ride_id)
                .values(
                    polyline_main=main_polyline,
                    polyline_alternates=alternates_json
                )
            )
            
            await db.execute(stmt)
            await db.commit()
            
            logger.info(f"✅ Stored polylines for ride {ride_id}: main={bool(main_polyline)}, alternates={len(alternates_json)}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store polylines for ride {ride_id}: {e}", exc_info=True)
            await db.rollback()
            return False
    
    async def compute_and_store_polylines(
        self,
        db: AsyncSession,
        ride_id: UUID,
        start_lat: float,
        start_lng: float,
        end_lat: float,
        end_lng: float,
        max_alternates: int = 5
    ) -> bool:
        """
        Full workflow: compute and store polylines for a ride.
        
        Args:
            db: Database session
            ride_id: Ride UUID
            start_lat, start_lng: Starting coordinates
            end_lat, end_lng: Ending coordinates
            max_alternates: Maximum alternate routes
            
        Returns:
            True if successful
        """
        logger.info(f"🗺️ Computing polylines for ride {ride_id}")
        
        # Compute polylines
        main_polyline, alternates = await self.compute_all_polylines(
            start_lat, start_lng, end_lat, end_lng, max_alternates
        )
        
        # Store in database
        success = await self.store_polylines_in_db(db, ride_id, main_polyline, alternates)
        
        if success:
            logger.info(f"✅ Polyline computation complete for ride {ride_id}")
        else:
            logger.warning(f"⚠️ Failed to store polylines for ride {ride_id}")
        
        return success


# Global polyline engine instance
_polyline_engine_instance: Optional[PolylineEngine] = None


def get_polyline_engine() -> PolylineEngine:
    """
    Get global polyline engine instance (singleton).
    
    Returns:
        PolylineEngine instance
    """
    global _polyline_engine_instance
    
    if _polyline_engine_instance is None:
        _polyline_engine_instance = PolylineEngine()
    
    return _polyline_engine_instance
