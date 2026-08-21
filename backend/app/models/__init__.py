"""
Purpose: Models package - exports all database models.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: This package contains all database models and enums.
       ALL models must be imported here so SQLAlchemy can resolve relationship() strings.
       Model imports for Alembic are handled in alembic/env.py to avoid circular imports.
"""

# Export Base for convenience
from app.db.base import Base

# Export all enums
from app.models.enums import (
    UserRole,
    DriverVerificationStatus,
    RideStatus,
    BookingStatus,
    TransactionType,
    TransactionStatus,
    VerificationStatus,
    FlagSeverity,
    FlagStatus,
)

# ---------------------------------------------------------------------------
# Import ALL model classes so SQLAlchemy mappers can resolve every
# relationship() string reference on the User model (and others).
# Without these imports, creating a User() object triggers mapper
# configuration that fails with "expression 'Xyz' failed to locate a name".
# ---------------------------------------------------------------------------

# -- app/models/ (standalone models) --
from app.models.admin_flag import AdminFlag  # noqa: F401
from app.models.system_config import SystemConfig  # noqa: F401
from app.models.booking import Booking  # noqa: F401
from app.models.driver import Driver  # noqa: F401
from app.models.rating import Rating  # noqa: F401
from app.models.recurring_schedule import RecurringSchedule  # noqa: F401
from app.models.recurring_schedule_subscription import RecurringScheduleSubscription  # noqa: F401
from app.models.ride import Ride  # noqa: F401
from app.models.ride_request import RideRequest, RideRequestStatus  # noqa: F401
from app.models.telemetry_point import TelemetryPoint  # noqa: F401
from app.models.vehicle import Vehicle  # noqa: F401
from app.models.verification import Verification  # noqa: F401
from app.models.wallet import Wallet  # noqa: F401
from app.models.wallet_transaction import WalletTransaction  # noqa: F401

# -- app/modules/*/models.py (module models) --
from app.modules.auth.models import User, RefreshToken  # noqa: F401
from app.modules.users.models import UserProfile, SavedAddress  # noqa: F401
from app.modules.drivers.models import DriverProfile  # noqa: F401
from app.modules.rides.models import RideBooking  # noqa: F401
from app.modules.payments.models import Transaction, Payout, PaymentIntent, IdempotencyRecord  # noqa: F401
from app.modules.verification.models import UserVerification, VerificationAttempt  # noqa: F401
from app.modules.matching.models import MatchRecord, MatchPreference  # noqa: F401
from app.modules.notifications.models import Notification, NotificationToken  # noqa: F401
from app.modules.admin.models import SystemStats, LogEntry, Alert  # noqa: F401
from app.modules.admin_moderation.models import Dispute, DisputeAttachment  # noqa: F401
from app.modules.admin_audit.models import AdminAuditLog  # noqa: F401

# Optional modules (may not exist in all setups)
try:
    from app.modules.safety_ai.models import TelemetryData, IncidentReport  # noqa: F401
except ImportError:
    pass

try:
    from app.modules.analytics.models import DailyAggregate  # noqa: F401
except ImportError:
    pass

__all__ = [
    # Base
    "Base",
    # Enums
    "UserRole",
    "DriverVerificationStatus",
    "RideStatus",
    "BookingStatus",
    "TransactionType",
    "TransactionStatus",
    "VerificationStatus",
    "FlagSeverity",
    "FlagStatus",
]
