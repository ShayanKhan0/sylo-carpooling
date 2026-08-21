"""
History Module Utilities (Prompt 11)

CSV export and formatting utilities for earnings reports.

Author: Smart Carpooling Backend Team
Date: December 8, 2025
"""

import csv
import io
from datetime import datetime
from typing import List, Dict, Any
from uuid import UUID


def generate_earnings_csv(earnings_data: List[Dict[str, Any]]) -> str:
    """
    Generate CSV content from earnings data.
    
    Args:
        earnings_data: List of monthly earnings dictionaries
    
    Returns:
        CSV content as string
    
    Example Input:
        [
            {
                "month": "2025-12",
                "total_earnings": 5000.00,
                "commissions_paid": 1000.00,
                "net_earnings": 4000.00,
                "completed_rides": 50
            }
        ]
    
    Example Output:
        "Month,Gross Earnings,Commissions,Net Earnings,Rides\\n2025-12,5000.00,1000.00,4000.00,50"
    """
    output = io.StringIO()
    
    # Define CSV headers
    fieldnames = [
        "Month",
        "Gross Earnings",
        "Platform Commissions",
        "Net Earnings",
        "Completed Rides",
        "Total Distance (km)",
        "Total Duration (min)",
        "Average Rating",
        "Tips Received",
        "Bonuses"
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    # Write rows
    for item in earnings_data:
        writer.writerow({
            "Month": item.get("month", ""),
            "Gross Earnings": f"{item.get('total_earnings', 0.0):.2f}",
            "Platform Commissions": f"{item.get('commissions_paid', 0.0):.2f}",
            "Net Earnings": f"{item.get('net_earnings', 0.0):.2f}",
            "Completed Rides": item.get("completed_rides", 0),
            "Total Distance (km)": f"{item.get('total_distance_km', 0.0):.2f}",
            "Total Duration (min)": item.get("total_duration_minutes", 0),
            "Average Rating": f"{item.get('average_rating', 0.0):.2f}" if item.get('average_rating') else "N/A",
            "Tips Received": f"{item.get('tips_received', 0.0):.2f}",
            "Bonuses": f"{item.get('bonuses', 0.0):.2f}"
        })
    
    csv_content = output.getvalue()
    output.close()
    
    return csv_content


def generate_ride_history_csv(rides: List[Dict[str, Any]]) -> str:
    """
    Generate CSV content from ride history data.
    
    Args:
        rides: List of ride dictionaries
    
    Returns:
        CSV content as string
    """
    output = io.StringIO()
    
    # Define CSV headers
    fieldnames = [
        "Date",
        "Ride ID",
        "Pickup Location",
        "Dropoff Location",
        "Distance (km)",
        "Duration (min)",
        "Fare Total",
        "Status",
        "Driver",
        "Passenger",
        "Rating"
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    # Write rows
    for ride in rides:
        date = ride.get("date")
        if isinstance(date, datetime):
            date_str = date.strftime("%Y-%m-%d %H:%M:%S")
        else:
            date_str = str(date)
        
        writer.writerow({
            "Date": date_str,
            "Ride ID": str(ride.get("ride_id", "")),
            "Pickup Location": ride.get("pickup_location", ""),
            "Dropoff Location": ride.get("dropoff_location", ""),
            "Distance (km)": f"{ride.get('distance_km', 0.0):.2f}",
            "Duration (min)": ride.get("duration_minutes", 0),
            "Fare Total": f"{ride.get('fare', 0.0):.2f}",
            "Status": ride.get("status", ""),
            "Driver": ride.get("driver_name", ""),
            "Passenger": ", ".join(ride.get("passenger_names", []) or []),
            "Rating": f"{ride.get('rating', 0.0):.1f}" if ride.get('rating') else "N/A"
        })
    
    csv_content = output.getvalue()
    output.close()
    
    return csv_content


def format_currency(amount: float, currency: str = "PKR") -> str:
    """
    Format currency amount.
    
    Args:
        amount: Amount to format
        currency: Currency code
    
    Returns:
        Formatted string (e.g., "PKR 5,000.00")
    """
    return f"{currency} {amount:,.2f}"


def format_duration(minutes: int) -> str:
    """
    Format duration in human-readable format.
    
    Args:
        minutes: Duration in minutes
    
    Returns:
        Formatted string (e.g., "2h 30m")
    """
    hours = minutes // 60
    mins = minutes % 60
    
    if hours > 0:
        return f"{hours}h {mins}m"
    else:
        return f"{mins}m"


def format_distance(km: float) -> str:
    """
    Format distance in human-readable format.
    
    Args:
        km: Distance in kilometers
    
    Returns:
        Formatted string (e.g., "15.5 km")
    """
    return f"{km:.2f} km"


def generate_summary_stats(earnings_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate summary statistics from earnings data.
    
    Args:
        earnings_data: List of monthly earnings
    
    Returns:
        Dictionary with summary stats
    """
    if not earnings_data:
        return {
            "total_earnings": 0.0,
            "total_rides": 0,
            "avg_monthly_earnings": 0.0,
            "avg_monthly_rides": 0,
            "best_month": None,
            "total_distance": 0.0
        }
    
    total_earnings = sum(item.get("total_earnings", 0.0) for item in earnings_data)
    total_rides = sum(item.get("completed_rides", 0) for item in earnings_data)
    total_distance = sum(item.get("total_distance_km", 0.0) for item in earnings_data)
    
    avg_monthly_earnings = total_earnings / len(earnings_data)
    avg_monthly_rides = total_rides // len(earnings_data)
    
    # Find best month
    best_month = max(earnings_data, key=lambda x: x.get("total_earnings", 0.0))
    
    return {
        "total_earnings": round(total_earnings, 2),
        "total_rides": total_rides,
        "avg_monthly_earnings": round(avg_monthly_earnings, 2),
        "avg_monthly_rides": avg_monthly_rides,
        "best_month": best_month.get("month"),
        "best_month_earnings": best_month.get("total_earnings", 0.0),
        "total_distance": round(total_distance, 2)
    }
