from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TripStartResponse(BaseModel):
    ride_id: UUID
    status: str
    telemetry_ws_url_template: str
    started_at: datetime


class SettlementItem(BaseModel):
    booking_id: UUID
    passenger_id: UUID
    fare: Decimal
    settled: bool
    error: Optional[str] = None


class TripCompleteResponse(BaseModel):
    ride_id: UUID
    status: str
    completed_at: datetime
    settlement_attempted: bool = True
    settled_count: int = 0
    failed_count: int = 0
    settlement: List[SettlementItem] = Field(default_factory=list)
    next_rating_endpoint: str


class TripSettleResponse(BaseModel):
    ride_id: UUID
    settled_count: int
    failed_count: int
    settlement: List[SettlementItem] = Field(default_factory=list)


class TripSummaryResponse(BaseModel):
    ride_id: UUID
    ride_status: str
    driver_id: UUID
    bookings_total: int
    bookings_active: int
    telemetry_points_total: int
    safety_telemetry_total: int
    incidents_total: int
    incidents_critical: int
