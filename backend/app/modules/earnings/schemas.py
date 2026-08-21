"""
Prompt 11C — Earnings Schemas

Pydantic models for driver earnings endpoints.

Author: Smart Carpooling Backend Team
Date: December 20, 2025
"""

from datetime import date as DateType, datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class MonthlyEarningsResponse(BaseModel):
    """
    Monthly earnings summary for drivers.
    
    Represents earnings for a specific month including:
    - Total rides completed
    - Gross earnings (total fare collected)
    - Platform commission deducted
    - Net earnings (after commission)
    - Payout status
    """
    
    year: int = Field(..., description="Year (e.g., 2025)")
    month: int = Field(..., ge=1, le=12, description="Month (1-12)")
    total_rides: int = Field(..., ge=0, description="Number of completed rides")
    gross_earnings: Decimal = Field(..., ge=0, description="Total fare from all rides (PKR)")
    commission_deducted: Decimal = Field(..., ge=0, description="Platform commission (PKR)")
    net_earnings: Decimal = Field(..., ge=0, description="Earnings after commission (PKR)")
    payout_status: str = Field(..., description="Payout status: pending, paid, failed")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "year": 2025,
                "month": 12,
                "total_rides": 45,
                "gross_earnings": "25000.00",
                "commission_deducted": "750.00",
                "net_earnings": "24250.00",
                "payout_status": "paid"
            }
        }
    )


class LifetimeEarningsResponse(BaseModel):
    """
    Lifetime earnings summary for drivers.
    
    Aggregates all-time earnings including:
    - Total rides completed
    - Lifetime gross/net earnings
    - Total withdrawals
    - Current wallet balance
    """
    
    total_rides: int = Field(..., ge=0, description="Total completed rides")
    lifetime_gross: Decimal = Field(..., ge=0, description="Total gross earnings (PKR)")
    lifetime_commission: Decimal = Field(..., ge=0, description="Total commission deducted (PKR)")
    lifetime_net: Decimal = Field(..., ge=0, description="Total net earnings (PKR)")
    total_withdrawn: Decimal = Field(..., ge=0, description="Total amount withdrawn (PKR)")
    current_wallet_balance: Decimal = Field(..., ge=0, description="Current wallet balance (PKR)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_rides": 523,
                "lifetime_gross": "350000.00",
                "lifetime_commission": "10500.00",
                "lifetime_net": "339500.00",
                "total_withdrawn": "300000.00",
                "current_wallet_balance": "39500.00"
            }
        }
    )


class DailyEarningsData(BaseModel):
    """
    Single day earnings data point for chart visualization.
    """
    
    date: DateType = Field(..., description="Date (YYYY-MM-DD)")
    rides: int = Field(..., ge=0, description="Number of rides on this day")
    earnings: Decimal = Field(..., ge=0, description="Net earnings for this day (PKR)")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2025-12-20",
                "rides": 3,
                "earnings": "1850.00"
            }
        }
    )


class EarningsChartResponse(BaseModel):
    """
    Daily earnings chart data for the last 30 days.
    
    Used for visualizing earnings trends over time.
    """
    
    period_start: DateType = Field(..., description="Start date of chart period")
    period_end: DateType = Field(..., description="End date of chart period")
    daily_data: List[DailyEarningsData] = Field(..., description="Daily earnings breakdown")
    total_earnings: Decimal = Field(..., ge=0, description="Total earnings in period (PKR)")
    total_rides: int = Field(..., ge=0, description="Total rides in period")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "period_start": "2025-11-20",
                "period_end": "2025-12-20",
                "daily_data": [
                    {
                        "date": "2025-12-20",
                        "rides": 3,
                        "earnings": "1850.00"
                    },
                    {
                        "date": "2025-12-19",
                        "rides": 5,
                        "earnings": "2500.00"
                    }
                ],
                "total_earnings": "45000.00",
                "total_rides": 98
            }
        }
    )


class RideEarningDetail(BaseModel):
    """
    Individual ride earning details for CSV export.
    
    Contains all relevant information about a single ride's earnings.
    """
    
    ride_id: UUID = Field(..., description="Ride unique identifier")
    date: datetime = Field(..., description="Ride date and time")
    from_location: str = Field(..., description="Starting point address")
    to_location: str = Field(..., description="Destination address")
    seats_booked: int = Field(..., ge=0, description="Number of seats booked")
    base_fare: Decimal = Field(..., ge=0, description="Total base fare (PKR)")
    commission: Decimal = Field(..., ge=0, description="Platform commission (PKR)")
    net_earning: Decimal = Field(..., ge=0, description="Net earning after commission (PKR)")
    payout_status: str = Field(..., description="Payout status: pending, paid, failed")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "ride_id": "550e8400-e29b-41d4-a716-446655440000",
                "date": "2025-12-20T08:30:00",
                "from_location": "Bahria Town, Lahore",
                "to_location": "Johar Town, Lahore",
                "seats_booked": 3,
                "base_fare": "900.00",
                "commission": "27.00",
                "net_earning": "873.00",
                "payout_status": "paid"
            }
        }
    )


class EarningsExportFilters(BaseModel):
    """
    Filter parameters for earnings CSV export.
    """
    
    from_date: Optional[DateType] = Field(None, description="Start date (YYYY-MM-DD)")
    to_date: Optional[DateType] = Field(None, description="End date (YYYY-MM-DD)")
    payout_status: Optional[str] = Field(None, description="Filter by payout status")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "from_date": "2025-01-01",
                "to_date": "2025-12-31",
                "payout_status": "paid"
            }
        }
    )
