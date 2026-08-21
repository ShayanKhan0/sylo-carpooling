"""
Prompt 11D-2 — Analytics Schemas

Read-only admin analytics schemas backed by daily_aggregates.

Author: Smart Carpooling Backend Team
Date: January 23, 2026
"""

from datetime import date as Date
from decimal import Decimal

from pydantic import BaseModel, Field


class DailyRideCount(BaseModel):
	"""Daily ride count item."""

	date: Date = Field(..., description="Aggregation date")
	rides_count: int = Field(..., ge=0, description="Total rides for the day")


class DailyRevenue(BaseModel):
	"""Daily revenue item."""

	date: Date = Field(..., description="Aggregation date")
	gross_revenue: Decimal = Field(..., ge=0, description="Gross revenue for the day")
	commission_revenue: Decimal = Field(..., ge=0, description="Commission revenue for the day")


class DailyVerificationFailures(BaseModel):
	"""Daily verification failures item."""

	date: Date = Field(..., description="Aggregation date")
	verification_failures: int = Field(..., ge=0, description="Failed verifications for the day")


class ActiveDriversByRegion(BaseModel):
	"""Active drivers grouped by region/city."""

	region: str = Field(..., description="Region/city label")
	driver_count: int = Field(..., ge=0, description="Active drivers in region")


class OverviewToday(BaseModel):
	"""Today's KPI summary."""

	rides_count: int = Field(..., ge=0, description="Total rides today")
	gross_revenue: Decimal = Field(..., ge=0, description="Gross revenue today")
	commission_revenue: Decimal = Field(..., ge=0, description="Commission revenue today")
	active_drivers: int = Field(..., ge=0, description="Active drivers today")


class OverviewLast7Days(BaseModel):
	"""Last 7 days KPI summary."""

	total_rides: int = Field(..., ge=0, description="Total rides in last 7 days")
	total_revenue: Decimal = Field(..., ge=0, description="Total gross revenue in last 7 days")
	total_commission: Decimal = Field(..., ge=0, description="Total commission revenue in last 7 days")


class OverviewLifetime(BaseModel):
	"""Lifetime KPI summary."""

	total_rides: int = Field(..., ge=0, description="All-time total rides")
	total_revenue: Decimal = Field(..., ge=0, description="All-time gross revenue")
	total_commission: Decimal = Field(..., ge=0, description="All-time commission revenue")


class OverviewResponse(BaseModel):
	"""Admin analytics overview response."""

	today: OverviewToday
	last_7_days: OverviewLast7Days
	lifetime: OverviewLifetime
