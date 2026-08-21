"""
Admin Auth Schemas (Prompt 12A)
"""

from pydantic import BaseModel, EmailStr, Field


class AdminLoginRequest(BaseModel):
    """Admin login request."""

    email: EmailStr = Field(..., description="Admin email")
    password: str = Field(..., min_length=8, description="Admin password")


class AdminTokenResponse(BaseModel):
    """Admin token response."""

    access_token: str = Field(..., description="Admin access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiry in seconds")
