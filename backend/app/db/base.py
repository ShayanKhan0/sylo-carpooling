"""
Purpose: SQLAlchemy declarative base for all database models.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 7, 2025
Notes: All database models should inherit from Base.
       Provides common functionality and metadata for all tables.
"""

from sqlalchemy.orm import declarative_base

# Create declarative base class for all models
Base = declarative_base()
