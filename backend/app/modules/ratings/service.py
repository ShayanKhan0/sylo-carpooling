"""
Ratings Service Layer (Prompt 11)

Business logic for rating system with weighted average algorithm.

Three-tier weighting system:
- Recent rides (≤90 days): weight = 1.0
- Old rides (>90 days): weight = 0.6  
- Outliers (<2 or >4.8): weight = 0.3

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy import func, and_, select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.rating import Rating
from app.models.ride import Ride
from app.modules.rides.models import RideBooking
from app.modules.auth.models import User
from app.modules.users.models import UserProfile
from app.core.config import settings
from app.core.exceptions import BadRequestException, NotFoundException, ForbiddenException

# Weighting constants
RECENT_WEIGHT = getattr(settings, "RATINGS_RECENT_WEIGHT", 1.0)
OLD_WEIGHT = getattr(settings, "RATINGS_OLD_WEIGHT", 0.6)
OUTLIER_WEIGHT = getattr(settings, "RATINGS_OUTLIER_WEIGHT", 0.3)
RECENT_DAYS = getattr(settings, "RATINGS_RECENT_DAYS", 90)
OUTLIER_LOW = getattr(settings, "RATINGS_OUTLIER_LOW", 2.0)
OUTLIER_HIGH = getattr(settings, "RATINGS_OUTLIER_HIGH", 4.8)


class RatingService:
    """Service for managing ratings with weighted averages (async)."""

    def __init__(self, db: AsyncSession):
        """Initialize service with async database session."""
        self.db = db

    @staticmethod
    def _normalize_status(value: object) -> str:
        raw = str(getattr(value, "value", value) or "").strip().lower()
        if "." in raw:
            raw = raw.split(".")[-1]
        aliases = {
            "scheduled": "open",
            "ongoing": "in_progress",
            "in-progress": "in_progress",
            "inprogress": "in_progress",
        }
        return aliases.get(raw, raw)

    @classmethod
    def _is_booking_dropoff_completed(cls, booking: RideBooking) -> bool:
        booking_status = cls._normalize_status(getattr(booking, "status", None))
        return (
            booking_status == "completed"
            or getattr(booking, "actual_dropoff_time", None) is not None
        )

    async def submit_rating(
        self,
        ride_id: UUID,
        from_user_id: UUID,
        rating_value: float,
        target_user_id: Optional[UUID] = None,
        booking_id: Optional[UUID] = None,
        comment: Optional[str] = None,
    ) -> Rating:
        """
        Submit a rating for a ride.

        Validation:
        - Ride must exist
        - User must be passenger or driver of the ride
        - Passenger dropoff must be completed (or ride completed)
        - Cannot rate yourself
        - Cannot rate same counterpart twice for the same ride
        """
        # Fetch ride
        result = await self.db.execute(select(Ride).where(Ride.id == ride_id))
        ride = result.scalar_one_or_none()
        if not ride:
            raise NotFoundException(f"Ride {ride_id} not found")

        ride_status = self._normalize_status(getattr(ride, "status", None))
        target_booking: Optional[RideBooking] = None

        # Determine who is being rated
        if from_user_id == ride.driver_id:
            # Driver rates passenger. Prefer explicit target (to_user_id/booking_id).
            booking_result = await self.db.execute(
                select(RideBooking).where(
                    and_(
                        RideBooking.ride_id == ride_id,
                        RideBooking.passenger_id != from_user_id,
                    )
                )
                .where(
                    RideBooking.passenger_id == target_user_id
                    if target_user_id is not None
                    else True
                )
                .where(
                    RideBooking.id == booking_id
                    if booking_id is not None
                    else True
                )
                .order_by(
                    desc(RideBooking.actual_dropoff_time),
                    desc(RideBooking.booking_time),
                )
                .limit(1)
            )
            target_booking = booking_result.scalar_one_or_none()
            if not target_booking:
                if target_user_id is not None or booking_id is not None:
                    raise BadRequestException(
                        "Target passenger booking not found for this ride"
                    )
                raise BadRequestException("No passenger found for this ride")

            to_user_id = target_booking.passenger_id
        else:
            # Passenger rates driver and must belong to this ride.
            booking_result = await self.db.execute(
                select(RideBooking)
                .where(
                    and_(
                        RideBooking.ride_id == ride_id,
                        RideBooking.passenger_id == from_user_id,
                    )
                )
                .where(
                    RideBooking.id == booking_id
                    if booking_id is not None
                    else True
                )
                .order_by(desc(RideBooking.booking_time))
                .limit(1)
            )
            target_booking = booking_result.scalar_one_or_none()
            if not target_booking:
                raise ForbiddenException("You are not part of this ride")

            if target_user_id is not None and target_user_id != ride.driver_id:
                raise BadRequestException("Passengers can only rate the ride driver")

            to_user_id = ride.driver_id

        if target_user_id is not None and to_user_id != target_user_id:
            raise BadRequestException("Rating target does not match ride participation")

        if target_booking is None:
            raise BadRequestException("Unable to resolve rating booking context")

        if (
            not self._is_booking_dropoff_completed(target_booking)
            and ride_status != "completed"
        ):
            raise BadRequestException("Rating is allowed after dropoff is completed")

        # Self-rating check
        if from_user_id == to_user_id:
            raise BadRequestException("Cannot rate yourself")

        # Check for duplicate rating
        existing_result = await self.db.execute(
            select(Rating).where(
                and_(
                    Rating.ride_id == ride_id,
                    Rating.rater_id == from_user_id,
                    Rating.ratee_id == to_user_id,
                )
            )
        )
        if existing_result.scalar_one_or_none():
            raise BadRequestException("You have already rated this user for this ride")

        # Create rating
        rating = Rating(
            ride_id=ride_id,
            rater_id=from_user_id,
            ratee_id=to_user_id,
            score=int(rating_value),
            comment=comment,
        )
        self.db.add(rating)

        try:
            await self.db.commit()
            await self.db.refresh(rating)
            return rating
        except IntegrityError as exc:
            await self.db.rollback()
            error_text = str(getattr(exc, "orig", exc)).lower()
            if (
                "uq_rating_ride_rater" in error_text
                or "uq_rating_ride_from_user" in error_text
            ):
                raise BadRequestException(
                    "Ratings database migration is required before multiple passenger ratings can be stored"
                )
            raise BadRequestException("Failed to create rating (duplicate)")

    async def update_rating(
        self,
        rating_id: UUID,
        user_id: UUID,
        rating_value: Optional[float] = None,
        comment: Optional[str] = None,
    ) -> Rating:
        """Update an existing rating."""
        result = await self.db.execute(select(Rating).where(Rating.id == rating_id))
        rating = result.scalar_one_or_none()
        if not rating:
            raise NotFoundException(f"Rating {rating_id} not found")

        if rating.rater_id != user_id:
            raise ForbiddenException("Cannot update another user's rating")

        if rating_value is not None:
            rating.score = int(rating_value)
        if comment is not None:
            rating.comment = comment

        rating.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(rating)
        return rating

    async def get_weighted_average(self, user_id: UUID) -> dict:
        """
        Calculate weighted average rating for a user.

        Weighting algorithm:
        1. Recent rides (≤90 days): weight = 1.0
        2. Old rides (>90 days): weight = 0.6
        3. Outliers (<2 or >4.8): weight = 0.3
        """
        result = await self.db.execute(
            select(Rating).where(Rating.ratee_id == user_id)
        )
        ratings = result.scalars().all()

        if not ratings:
            return {
                "user_id": str(user_id),
                "weighted_average": 0.0,
                "total_ratings": 0,
                "recent_ratings": 0,
                "rating_distribution": {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0},
            }

        recent_date = datetime.utcnow() - timedelta(days=RECENT_DAYS)
        weighted_sum = 0.0
        weight_sum = 0.0
        recent_count = 0

        for r in ratings:
            weight = self._calculate_weight(r, recent_date)
            weighted_sum += r.score * weight
            weight_sum += weight
            if r.created_at >= recent_date:
                recent_count += 1

        weighted_average = weighted_sum / weight_sum if weight_sum > 0 else 0.0

        distribution = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
        for r in ratings:
            star = str(int(round(r.score)))
            if star in distribution:
                distribution[star] += 1

        return {
            "user_id": str(user_id),
            "weighted_average": round(weighted_average, 2),
            "total_ratings": len(ratings),
            "recent_ratings": recent_count,
            "rating_distribution": distribution,
        }

    def _calculate_weight(self, rating: Rating, recent_date: datetime) -> float:
        """Calculate weight for a single rating."""
        if rating.score < OUTLIER_LOW or rating.score > OUTLIER_HIGH:
            return OUTLIER_WEIGHT
        if rating.created_at >= recent_date:
            return RECENT_WEIGHT
        return OLD_WEIGHT

    async def _calculate_percentile(
        self, user_id: UUID, weighted_average: float
    ) -> Optional[float]:
        """Calculate user's percentile rank among all rated users."""
        stmt = (
            select(Rating.ratee_id, func.avg(Rating.score).label("avg_rating"))
            .group_by(Rating.ratee_id)
            .having(func.count(Rating.id) >= 5)
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        if len(rows) < 10:
            return None

        averages = sorted(row.avg_rating for row in rows)
        rank = sum(1 for avg in averages if avg < weighted_average)
        return round((rank / len(averages)) * 100, 1)

    async def get_user_ratings(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        as_rater: bool = False,
    ) -> dict:
        """Get paginated list of ratings for a user."""
        col = Rating.rater_id if as_rater else Rating.ratee_id

        # Total count
        count_result = await self.db.execute(
            select(func.count(Rating.id)).where(col == user_id)
        )
        total = count_result.scalar() or 0

        # Paginated data
        offset = (page - 1) * page_size
        data_result = await self.db.execute(
            select(Rating)
            .where(col == user_id)
            .order_by(Rating.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        ratings = data_result.scalars().all()
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        user_ids = {
            rating.rater_id for rating in ratings
        } | {
            rating.ratee_id for rating in ratings
        }

        user_name_map: dict[UUID, str] = {}
        profile_photo_map: dict[UUID, str] = {}

        if user_ids:
            users_result = await self.db.execute(
                select(User.id, User.full_name).where(User.id.in_(list(user_ids)))
            )
            user_name_map = {
                row.id: row.full_name for row in users_result
            }

            profiles_result = await self.db.execute(
                select(UserProfile.user_id, UserProfile.profile_photo).where(
                    UserProfile.user_id.in_(list(user_ids))
                )
            )
            profile_photo_map = {
                row.user_id: row.profile_photo
                for row in profiles_result
                if row.profile_photo
            }

        serialized_ratings = [
            {
                "id": rating.id,
                "ride_id": rating.ride_id,
                "from_user_id": rating.rater_id,
                "to_user_id": rating.ratee_id,
                "rating": int(round(rating.score)),
                "comment": rating.comment,
                "created_at": rating.created_at,
                "from_user_name": user_name_map.get(rating.rater_id),
                "to_user_name": user_name_map.get(rating.ratee_id),
                "from_user_profile_photo": profile_photo_map.get(rating.rater_id),
                "to_user_profile_photo": profile_photo_map.get(rating.ratee_id),
            }
            for rating in ratings
        ]

        return {
            "ratings": serialized_ratings,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def get_ride_rating(
        self,
        ride_id: UUID,
        user_id: UUID,
        to_user_id: Optional[UUID] = None,
    ) -> Optional[Rating]:
        """Get rating for a specific ride by a specific user."""
        query = select(Rating).where(
            and_(Rating.ride_id == ride_id, Rating.rater_id == user_id)
        )

        if to_user_id is not None:
            query = query.where(Rating.ratee_id == to_user_id)

        query = query.order_by(desc(Rating.created_at)).limit(1)
        result = await self.db.execute(
            query
        )
        return result.scalar_one_or_none()

    async def get_rating_stats(self, user_id: UUID) -> dict:
        """Get comprehensive rating statistics for a user."""
        result = await self.db.execute(
            select(Rating).where(Rating.ratee_id == user_id)
        )
        ratings = result.scalars().all()

        if not ratings:
            return {
                "user_id": user_id,
                "total_ratings": 0,
                "average_rating": 0.0,
                "weighted_average": 0.0,
                "5_star": 0,
                "4_star": 0,
                "3_star": 0,
                "2_star": 0,
                "1_star": 0,
                "most_recent_rating": None,
            }

        average = sum(r.score for r in ratings) / len(ratings)
        weighted_data = await self.get_weighted_average(user_id)

        star_counts = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
        for r in ratings:
            star = int(round(r.score))
            star_counts[star] = star_counts.get(star, 0) + 1

        most_recent = max(ratings, key=lambda r: r.created_at)

        return {
            "user_id": user_id,
            "total_ratings": len(ratings),
            "average_rating": round(average, 2),
            "weighted_average": weighted_data["weighted_average"],
            "5_star": star_counts[5],
            "4_star": star_counts[4],
            "3_star": star_counts[3],
            "2_star": star_counts[2],
            "1_star": star_counts[1],
            "most_recent_rating": most_recent.score,
        }

    async def delete_rating(self, rating_id: UUID, user_id: UUID) -> None:
        """Delete a rating."""
        result = await self.db.execute(select(Rating).where(Rating.id == rating_id))
        rating = result.scalar_one_or_none()
        if not rating:
            raise NotFoundException(f"Rating {rating_id} not found")

        if rating.rater_id != user_id:
            raise ForbiddenException("Cannot delete another user's rating")

        await self.db.delete(rating)
        await self.db.commit()

    async def get_weighted_average_prompt11a(self, user_id: UUID) -> dict:
        """
        Calculate weighted average rating for a user (PROMPT 11A EXACT SPECIFICATION).

        Prompt 11A Algorithm:
        - Last 20 ratings: 70% weight
        - Remaining older ratings: 30% weight

        Formula: weighted_avg = (avg_last_20 * 0.7) + (avg_older * 0.3)
        """
        result = await self.db.execute(
            select(Rating)
            .where(Rating.ratee_id == user_id)
            .order_by(Rating.created_at.desc())
        )
        ratings = result.scalars().all()

        if not ratings:
            return {
                "user_id": str(user_id),
                "weighted_average": 0.0,
                "total_ratings": 0,
                "recent_ratings": 0,
                "rating_distribution": {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0},
            }

        total_count = len(ratings)
        last_20 = ratings[:20] if total_count >= 20 else ratings
        older = ratings[20:] if total_count > 20 else []

        avg_last_20 = sum(r.score for r in last_20) / len(last_20) if last_20 else 0.0
        avg_older = sum(r.score for r in older) / len(older) if older else 0.0

        if total_count <= 20:
            weighted_average = avg_last_20
        else:
            weighted_average = (avg_last_20 * 0.7) + (avg_older * 0.3)

        distribution = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
        for r in ratings:
            star = str(int(round(r.score)))
            if star in distribution:
                distribution[star] += 1

        return {
            "user_id": str(user_id),
            "weighted_average": round(weighted_average, 2),
            "total_ratings": total_count,
            "recent_ratings": len(last_20),
            "rating_distribution": distribution,
        }
