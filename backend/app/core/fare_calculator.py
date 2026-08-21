"""
Sylo Shared Fare Calculator — Server-side, Yango-inspired.

Computes the total trip cost based on distance, fuel consumption,
and petrol price, then divides it among passengers (seats).

Formula:
  fuelCost     = (distanceKm / fuelAverageKmPerLitre) × petrolPricePerLitre
    timeCost     = durationMinutes × timeRatePerMinute
  platformFee  = fuelCost × platformMarkup  (e.g. 30%)
    totalFare    = baseFare + fuelCost + timeCost + platformFee
  farePerSeat  = ceil(totalFare / numberOfSeats / 10) × 10   (round UP to nearest 10 PKR)
  farePerSeat  = max(farePerSeat, minimumFarePerSeat)

Author: M. Mobeen Shoukat Ch & M. Shayan Khan
"""

import math
from dataclasses import dataclass, field
from typing import Optional


# ── Default configuration (Pakistan, mid-2025) ───────────
PETROL_PRICE_PER_LITRE: float = 268.0   # PKR — update as needed
FUEL_AVERAGE_KM_PER_LITRE: float = 12.0  # typical sedan city driving
PLATFORM_MARKUP: float = 0.30            # 30 % covers driver profit, wear & tear, commission
MINIMUM_FARE_PER_SEAT: float = 80.0      # PKR
BASE_FARE: float = 50.0                  # flat base charge per trip
TIME_RATE_PER_MINUTE: float = 1.5        # PKR per minute (traffic/time component)


@dataclass
class FareEstimate:
    """Holds the result of a fare calculation."""
    distance_km: float
    total_seats: int
    fuel_cost_raw: float
    time_cost: float
    duration_minutes: float
    base_fare: float
    platform_fee: float
    total_fare: float
    fare_per_seat: float
    petrol_price_used: float
    fuel_average_used: float
    markup_percent: float

    @property
    def summary(self) -> str:
        return (
            f"Rs {self.fare_per_seat:.0f}/seat × {self.total_seats} seats "
            f"= Rs {self.fare_per_seat * self.total_seats:.0f} total "
            f"({self.distance_km:.1f} km)"
        )

    def to_dict(self) -> dict:
        return {
            "distance_km": round(self.distance_km, 2),
            "total_seats": self.total_seats,
            "fuel_cost_raw": round(self.fuel_cost_raw, 2),
            "time_cost": round(self.time_cost, 2),
            "duration_minutes": round(self.duration_minutes, 1),
            "base_fare": round(self.base_fare, 2),
            "platform_fee": round(self.platform_fee, 2),
            "total_fare": round(self.total_fare, 2),
            "fare_per_seat": round(self.fare_per_seat, 2),
            "petrol_price_used": round(self.petrol_price_used, 2),
            "fuel_average_used": round(self.fuel_average_used, 2),
            "markup_percent": round(self.markup_percent * 100, 1),
            "summary": self.summary,
        }


def calculate_fare(
    distance_km: float,
    total_seats: int = 4,
    duration_minutes: Optional[float] = None,
    petrol_price: Optional[float] = None,
    fuel_average: Optional[float] = None,
    markup: Optional[float] = None,
    base_fare: Optional[float] = None,
    min_fare_per_seat: Optional[float] = None,
    time_rate_per_minute: Optional[float] = None,
    surge_multiplier: float = 1.0,  # Dynamic pricing multiplier
    traffic_factor: float = 1.0,     # Traffic-based adjustment
) -> FareEstimate:
    """
    Calculate the shared fare for a ride.

    Parameters
    ----------
    distance_km : float
        Route distance in kilometres.
    total_seats : int
        Number of seats to split the fare across (1-8).
    petrol_price : float, optional
        Override petrol price per litre (PKR). Defaults to 268.
    fuel_average : float, optional
        Override fuel average (km/L). Defaults to 12.
    markup : float, optional
        Override platform markup fraction (0.30 = 30 %). Defaults to 0.30.
    base_fare : float, optional
        Override base fare (PKR). Defaults to 50.
    min_fare_per_seat : float, optional
        Override minimum fare per seat (PKR). Defaults to 80.

    Returns
    -------
    FareEstimate
        Dataclass with full breakdown.
    """
    _petrol = petrol_price if petrol_price is not None else PETROL_PRICE_PER_LITRE
    _avg = fuel_average if fuel_average is not None else FUEL_AVERAGE_KM_PER_LITRE
    _mkp = markup if markup is not None else PLATFORM_MARKUP
    _base = base_fare if base_fare is not None else BASE_FARE
    _min = min_fare_per_seat if min_fare_per_seat is not None else MINIMUM_FARE_PER_SEAT
    _time_rate = (
        time_rate_per_minute
        if time_rate_per_minute is not None
        else TIME_RATE_PER_MINUTE
    )

    # Clamp seats
    seats = max(1, min(total_seats, 8))

    # Raw fuel cost
    fuel_cost = (distance_km / _avg) * _petrol

    # Time component (if not provided, use 0 for backward compatibility)
    dur_min = max(0.0, float(duration_minutes or 0.0))
    time_cost = dur_min * _time_rate * traffic_factor

    # Platform fee
    platform_fee = fuel_cost * _mkp

    # Total trip fare
    base_subtotal = _base + fuel_cost + time_cost + platform_fee
    total_fare = base_subtotal * surge_multiplier

# Per-seat, rounded UP to nearest 10 PKR
    raw_per_seat = total_fare / seats
    per_seat = max(raw_per_seat, _min)
    per_seat_rounded = math.ceil(per_seat / 10) * 10.0

    return FareEstimate(
        distance_km=distance_km,
        total_seats=seats,
        fuel_cost_raw=fuel_cost,
        time_cost=time_cost,
        duration_minutes=dur_min,
        base_fare=_base,
        platform_fee=platform_fee,
        total_fare=total_fare,
        fare_per_seat=per_seat_rounded,
        petrol_price_used=_petrol,
        fuel_average_used=_avg,
        markup_percent=_mkp,
    )


def quick_per_seat(distance_km: float, seats: int = 4) -> float:
    """Return just the fare-per-seat for a given distance."""
    return calculate_fare(distance_km=distance_km, total_seats=seats).fare_per_seat
