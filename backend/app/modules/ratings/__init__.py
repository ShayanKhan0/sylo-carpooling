"""
Ratings Module

Exports for ratings module components.
"""

from app.modules.ratings.service import RatingService
from app.modules.ratings import schemas
from app.modules.ratings.routers import router

__all__ = ["RatingService", "schemas", "router"]
