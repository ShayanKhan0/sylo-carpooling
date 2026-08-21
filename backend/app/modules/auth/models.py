"""
Module: Authentication
Purpose: Database models for authentication-related tables.
         Defines User and RefreshToken SQLAlchemy models.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 8, 2025
Notes: This module is foundational for secure access to all SmartCarpoolingApp features.
       Uses UUID primary keys, bcrypt password hashing, and role-based access control.
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

from app.db.base import Base
from app.models.enums import UserRole


class User(Base):
    """
    User model representing registered users in the system.
    Supports multiple roles with email and phone verification.

    Attributes:
        id (UUID): Primary key, auto-generated UUID
        full_name (str): User's full name (max 120 chars)
        email (str): Unique email address, indexed for fast lookups
        password_hash (str): Bcrypt hashed password
        phone (str): Unique phone number with country code
        role (UserRole): User role (passenger, driver, admin, organization)
        is_active (bool): Account active status, default True
        is_verified (bool): Email verification status, default False
        created_at (datetime): Account creation timestamp
        updated_at (datetime): Last update timestamp

    Relationships:
        refresh_tokens: One-to-many relationship with RefreshToken (CASCADE delete)

    Example:
        >>> user = User(
        >>>     full_name="John Doe",
        >>>     email="john.doe@university.edu",
        >>>     password_hash=get_password_hash("SecurePass123!"),
        >>>     phone="+1234567890",
        >>>     role=UserRole.PASSENGER
        >>> )
    """
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    firebase_uid = Column(String(255), unique=True, nullable=True, index=True)  # Firebase UID
    password_hash = Column(String(255), nullable=False)  # Bcrypt hashed password
    phone = Column(String(20), unique=True, nullable=False)
    role = Column(
        SQLEnum(
            UserRole,
            name="user_role",
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        default=UserRole.PASSENGER,
        nullable=False,
    )
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    wallet = relationship("Wallet", back_populates="user", uselist=False)
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    verifications = relationship(
        "UserVerification",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="UserVerification.user_id",
    )
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    notification_tokens = relationship("NotificationToken", back_populates="user", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="owner", cascade="all, delete-orphan")
    driver = relationship("Driver", back_populates="user", uselist=False)
    bookings = relationship(
        "Booking",
        back_populates="passenger",
        cascade="all, delete-orphan",
        foreign_keys="Booking.passenger_id",
    )
    ratings_given = relationship(
        "Rating",
        back_populates="rater",
        cascade="all, delete-orphan",
        foreign_keys="Rating.rater_id",
    )
    ratings_received = relationship(
        "Rating",
        back_populates="ratee",
        cascade="all, delete-orphan",
        foreign_keys="Rating.ratee_id",
    )
    recurring_schedules = relationship(
        "RecurringSchedule",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"


class RefreshToken(Base):
    """
    Refresh token model for managing JWT refresh tokens.
    Allows long-lived sessions while maintaining security through token rotation.

    Attributes:
        id (UUID): Primary key, auto-generated UUID
        user_id (UUID): Foreign key to users table with CASCADE delete
        token (str): Unique refresh token string (512 chars max)
        created_at (datetime): Token creation timestamp
        expires_at (datetime): Token expiration timestamp
        revoked_at (datetime): Token revocation timestamp (if revoked)
        is_revoked (bool): Whether token has been revoked

    Relationships:
        user: Many-to-one relationship with User

    Security Notes:
        - Tokens are stored hashed for additional security
        - Expired tokens should be cleaned up periodically
        - Revoked tokens cannot be used for authentication
        - CASCADE delete ensures tokens are removed when user is deleted

    Example:
        >>> from datetime import datetime, timedelta
        >>> expires = datetime.utcnow() + timedelta(days=7)
        >>> token = RefreshToken(
        >>>     user_id=user.id,
        >>>     token="unique_token_string",
        >>>     expires_at=expires
        >>> )
    """
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(512), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    is_revoked = Column(Boolean, default=False, nullable=False)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, is_revoked={self.is_revoked})>"
