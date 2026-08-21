"""
Module: Users
Purpose: Database models for user profiles, saved addresses, and identity management.
         Extends the authentication module with rich user data.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 7, 2025
Notes: Models inherit from Base and use async SQLAlchemy patterns.
       UserProfile stores role-specific data (CNIC for drivers, org info for students).
       SavedAddress enables fast ride matching via geospatial indexing.
"""

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Float, Date, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid
import enum

from app.db.base import Base


class GenderEnum(str, enum.Enum):
    """
    Gender enumeration for user profiles.
    
    Values:
        - male: Male gender
        - female: Female gender
        - other: Non-binary or prefer not to say
    """
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class OrganizationTypeEnum(str, enum.Enum):
    """
    Organization type enumeration for institutional affiliations.
    
    Values:
        - university: University student/faculty
        - college: College student/faculty
        - school: School student/teacher
        - office: Corporate office employee
    """
    UNIVERSITY = "university"
    COLLEGE = "college"
    SCHOOL = "school"
    OFFICE = "office"


class UserProfile(Base):
    """
    User profile model storing extended user information.
    
    Automatically created when a user registers (via auth service).
    Contains role-specific fields that may be required/optional based on user.role:
    
    - Students: organization_name, organization_type
    - Drivers: cnic, driving_license, car_registration, address_verification
    - All: profile_photo, gender, date_of_birth
    
    Attributes:
        id (UUID): Primary key, auto-generated UUID
        user_id (UUID): Foreign key to users table (CASCADE delete)
        profile_photo (str): URL or base64 encoded photo (max 255 chars)
        gender (GenderEnum): User's gender (optional)
        date_of_birth (date): User's date of birth for age verification
        organization_name (str): Name of university/college/office (max 255 chars)
        organization_type (OrganizationTypeEnum): Type of organization
        cnic (str): National ID card number (Pakistan CNIC format: 12345-1234567-1)
        driving_license (str): Driver's license number (max 50 chars)
        car_registration (str): Vehicle registration number (max 50 chars)
        address_verification (bool): Whether home address has been verified
        created_at (datetime): Profile creation timestamp
        updated_at (datetime): Last profile update timestamp
    
    Relationships:
        user: One-to-one relationship with User model
    
    Indexes:
        - user_id: For fast profile lookups by user
    
    Notes:
        - CASCADE delete ensures profile is removed when user is deleted
        - Most fields are nullable to support gradual profile completion
        - CNIC/license only required for drivers (enforced at service layer)
    """
    __tablename__ = "user_profiles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False, 
        unique=True,  # One profile per user
        index=True
    )
    
    # Personal Information
    profile_photo = Column(String(255), nullable=True)  # URL or base64 string
    gender = Column(
        SQLEnum(GenderEnum, name="gender_enum", create_type=True),
        nullable=True
    )
    date_of_birth = Column(Date, nullable=True)
    
    # Organization Information (for students/employees)
    organization_name = Column(String(255), nullable=True)  # e.g., "Bahria University"
    organization_type = Column(
        SQLEnum(OrganizationTypeEnum, name="org_type_enum", create_type=True),
        nullable=True
    )
    
    # Identity Documents (for drivers)
    cnic = Column(String(20), nullable=True)  # Format: 12345-1234567-1
    driving_license = Column(String(50), nullable=True)
    car_registration = Column(String(50), nullable=True)
    
    # Verification Status
    address_verification = Column(Boolean, default=False, nullable=False)
    push_notifications_enabled = Column(Boolean, default=True, nullable=False)
    share_location_enabled = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    # Note: Relationship to User is defined in auth/models.py to avoid circular imports
    # user = relationship("User", back_populates="profile")
    
    def __repr__(self):
        return f"<UserProfile(user_id={self.user_id}, organization={self.organization_name})>"


class SavedAddress(Base):
    """
    Saved address model for storing user's frequent locations.
    
    Users can save multiple addresses (home, office, university, custom) for:
    - Quick ride request from favorite locations
    - Faster geospatial matching with nearby rides
    - Personalized ride suggestions
    
    Maximum addresses per user: Configurable via MAX_SAVED_ADDRESSES in settings
    Default limit: 5 addresses per user
    
    Attributes:
        id (UUID): Primary key, auto-generated UUID
        user_id (UUID): Foreign key to users table (CASCADE delete)
        label (str): Human-readable label (e.g., "Home", "Office", "University")
        address (str): Full address string (max 255 chars)
        latitude (float): Latitude coordinate for geospatial queries
        longitude (float): Longitude coordinate for geospatial queries
        created_at (datetime): Address creation timestamp
    
    Relationships:
        user: Many-to-one relationship with User model
    
    Indexes:
        - user_id: For fetching all addresses for a user
        - (latitude, longitude): For geospatial proximity queries
    
    Notes:
        - Coordinates should be validated before storage (valid lat/lng ranges)
        - Consider adding PostGIS GEOMETRY type for advanced spatial queries
        - Label should be unique per user (enforced at service layer)
        - CASCADE delete ensures addresses are removed when user is deleted
    
    TODO:
        - Add composite unique constraint on (user_id, label)
        - Add CHECK constraint for lat (-90 to 90) and lng (-180 to 180)
        - Consider adding 'is_primary' flag for default address
    """
    __tablename__ = "saved_addresses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    
    # Address Information
    label = Column(String(50), nullable=False)  # e.g., 'Home', 'Office', 'University'
    address = Column(String(255), nullable=False)  # Full address string
    
    # Geospatial Coordinates
    latitude = Column(Float, nullable=False)  # Range: -90 to 90
    longitude = Column(Float, nullable=False)  # Range: -180 to 180
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    # Note: Relationship to User is defined in auth/models.py to avoid circular imports
    # user = relationship("User", back_populates="saved_addresses")
    
    def __repr__(self):
        return f"<SavedAddress(label={self.label}, user_id={self.user_id})>"
