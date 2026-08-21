"""
Purpose: Shared enums for database models.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: All enum types used across database models.
"""

import enum


class UserRole(str, enum.Enum):
    """User role types"""
    PASSENGER = "passenger"
    STUDENT = "passenger"  # Backward-compatible alias
    DRIVER = "driver"
    ADMIN = "admin"
    ORGANIZATION = "organization"


class DriverVerificationStatus(str, enum.Enum):
    """Driver verification status"""
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class RideStatus(str, enum.Enum):
    """Ride status types"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BookingStatus(str, enum.Enum):
    """Booking status types"""
    RESERVED = "reserved"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class TransactionType(str, enum.Enum):
    """Wallet transaction types"""
    TOPUP = "topup"
    PAYOUT = "payout"
    RIDE = "ride"


class TransactionStatus(str, enum.Enum):
    """Transaction status types"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationStatus(str, enum.Enum):
    """Document verification status"""
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


class FlagSeverity(str, enum.Enum):
    """Admin flag severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FlagStatus(str, enum.Enum):
    """Admin flag status"""
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
