"""
Module: Google Maps Client
Purpose: Centralized Google Maps API client for route calculation, distance, and ETA.
Author: Generated for SmartCarpoolingApp
Date: March 2026
"""

import logging
from typing import Dict, Any, Optional, Tuple, List
import googlemaps
from app.core.config import settings

logger = logging.getLogger(__name__)


class GoogleMapsClient:
    """
    Centralized client for Google Maps API operations.
    Handles routes, distances, and traffic-aware ETAs.
    """

    def __init__(self):
        """Initialize Google Maps client with API key from config."""
        key = settings.resolved_google_maps_key()
        if not key:
            logger.error("GOOGLE_MAPS_KEY / GOOGLE_MAPS_API_KEY not configured")
            self.client = None
        else:
            self.client = googlemaps.Client(key=key)

    def get_directions(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float],
        alternatives: bool = True,
        departure_time: Optional[int] = None,
        waypoints: Optional[List[Tuple[float, float]]] = None,
        optimize_waypoints: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Get route directions including polyline, distance, and duration.
        """
        if not self.client:
            return None
        try:
            # Format coords as "lat,lng" for Google Maps API
            origin_str = f"{origin[0]},{origin[1]}"
            dest_str = f"{destination[0]},{destination[1]}"
            
            kwargs = {
                'origin': origin_str,
                'destination': dest_str,
                'mode': 'driving',
                'alternatives': alternatives
            }

            if waypoints:
                kwargs['waypoints'] = [f"{w[0]},{w[1]}" for w in waypoints]
                kwargs['optimize_waypoints'] = bool(optimize_waypoints)
            
            if departure_time:
                kwargs['departure_time'] = departure_time
            
            response = self.client.directions(**kwargs)
            
            if not response or len(response) == 0:
                logger.warning(f"No route found from {origin_str} to {dest_str}")
                return None
            
            # Extract main route
            main_route = response[0]
            if not main_route.get('legs'):
                return None

            legs = main_route['legs']
            total_distance_m = 0
            total_duration_s = 0
            for leg in legs:
                try:
                    total_distance_m += int((leg.get('distance') or {}).get('value') or 0)
                except Exception:
                    pass
                try:
                    total_duration_s += int((leg.get('duration') or {}).get('value') or 0)
                except Exception:
                    pass
            
            result = {
                'polyline': main_route['overview_polyline']['points'],
                'distance_km': (total_distance_m / 1000.0) if total_distance_m > 0 else 0.0,
                'duration_minutes': round(total_duration_s / 60.0) if total_duration_s > 0 else 0,
                'steps': [step for leg in legs for step in leg.get('steps', [])],
                'summary': (main_route.get('summary') or '').strip(),
                'alternative_routes': []
            }
            
            # Extract alternative routes if available
            if alternatives and len(response) > 1:
                for alt_route in response[1:]:
                    if not alt_route.get('legs'):
                        continue
                    alt_distance_m = 0
                    alt_duration_s = 0
                    for alt_leg in alt_route['legs']:
                        try:
                            alt_distance_m += int((alt_leg.get('distance') or {}).get('value') or 0)
                        except Exception:
                            pass
                        try:
                            alt_duration_s += int((alt_leg.get('duration') or {}).get('value') or 0)
                        except Exception:
                            pass
                    result['alternative_routes'].append({
                        'polyline': alt_route['overview_polyline']['points'],
                        'distance_km': (alt_distance_m / 1000.0) if alt_distance_m > 0 else 0.0,
                        'duration_minutes': round(alt_duration_s / 60.0) if alt_duration_s > 0 else 0,
                        'summary': (alt_route.get('summary') or '').strip(),
                    })
            
            logger.info(
                f"Directions found: {result['distance_km']:.2f}km, "
                f"ETA {result['duration_minutes']} min"
            )
            return result
            
        except Exception as e:
            logger.error(f"Error fetching directions: {str(e)}")
            return None

    def calculate_distance(
        self,
        origin: Tuple[float, float],
        destination: Tuple[float, float]
    ) -> Optional[float]:
        """
        Calculate actual road network distance in kilometers.
        """
        try:
            result = self.get_directions(origin, destination, alternatives=False)
            if result:
                return round(result['distance_km'], 2)
            return None
        except Exception as e:
            logger.error(f"Error calculating distance: {str(e)}")
            return None

    def estimate_pickup_time(
        self,
        driver_location: Tuple[float, float],
        pickup_location: Tuple[float, float],
        departure_time: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Estimate driver arrival time at pickup location with traffic awareness.
        """
        try:
            result = self.get_directions(
                origin=driver_location,
                destination=pickup_location,
                alternatives=False,
                departure_time=departure_time
            )
            
            if result:
                # Add 20% buffer for stops and congestion
                buffered_eta = max(5, round(result['duration_minutes'] * 1.2))
                return {
                    'eta_minutes': buffered_eta,
                    'distance_km': result['distance_km'],
                    'steps': result['steps']
                }
            return None
            
        except Exception as e:
            logger.error(f"Error estimating pickup time: {str(e)}")
            return None

    def get_distance_matrix(
        self,
        origins: List[Tuple[float, float]],
        destinations: List[Tuple[float, float]]
    ) -> Optional[Dict[str, Any]]:
        """
        Get distance matrix for multiple origins and destinations.
        """
        if not self.client:
            return None
        try:
            origins_str = [f"{o[0]},{o[1]}" for o in origins]
            dests_str = [f"{d[0]},{d[1]}" for d in destinations]
            
            response = self.client.distance_matrix(
                origins=origins_str,
                destinations=dests_str,
                mode='driving'
            )
            
            if response.get('status') == 'OK':
                return response
            else:
                logger.error(f"Distance matrix API error: {response.get('status')}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting distance matrix: {str(e)}")
            return None


# Singleton instance
_gmaps_client: Optional[GoogleMapsClient] = None


def get_google_maps_client() -> GoogleMapsClient:
    """Get or create the singleton Google Maps client."""
    global _gmaps_client
    if _gmaps_client is None:
        _gmaps_client = GoogleMapsClient()
    return _gmaps_client
