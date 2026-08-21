"""
Purpose: Application configuration management using Pydantic Settings.
         Reads environment variables with validation and default fallbacks.
Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: November 7, 2025
Notes: All configuration is centralized here for easy management and security.
       Environment variables should be set in .env file for local development.
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env — must not depend on process cwd (uvicorn is often started from repo root).
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_BACKEND_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Uses Pydantic for validation and type checking.
    """

    # Application Settings
    APP_NAME: str = "SmartCarpoolingApp"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "local"  # local, staging, production
    DEBUG: bool = True
    ALLOWED_HOSTS: List[str] = ["*"]
    
    # Database Configuration
    DB_URL: str = "postgresql+asyncpg://sylo_user:Admin%40123@localhost:5432/sylo_carpool"


    # Example: postgresql+asyncpg://user:pass@localhost:5432/dbname
    DB_POOL_SIZE: int = 20  # Connection pool size for high concurrency
    DB_MAX_OVERFLOW: int = 10  # Additional connections beyond pool_size

    # JWT Authentication
    JWT_SECRET: str = "change-this-to-a-secure-random-secret-key-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Caching (in-memory, no external service required)
    CACHE_EXPIRE_SECONDS: int = 300  # 5 minutes default cache expiry

    # External APIs — Google Maps (Places, Directions, Geocoding, Distance Matrix)
    # Set GOOGLE_MAPS_KEY or GOOGLE_MAPS_API_KEY in .env (both supported).
    GOOGLE_MAPS_KEY: str = ""
    GOOGLE_MAPS_API_KEY: str = ""  # Alias; if set, overrides empty GOOGLE_MAPS_KEY
    FCM_CREDENTIALS_PATH: str = ""  # Firebase Cloud Messaging credentials JSON
    FIREBASE_PROJECT_ID: str = "sylo-e895e"  # Firebase project ID for Admin SDK

    # === VERIFICATION FUNCTIONALITY START ===
    # Verification AI providers
    VERIFICATION_OCR_PROVIDER: str = "google"  # google, local
    VERIFICATION_FACE_PROVIDER: str = "aws"  # aws, azure, local
    VERIFICATION_REQUIRE_SELFIE_FOR_FACE_MATCH: bool = True
    VERIFICATION_FACE_MATCH_THRESHOLD: float = 0.80  # 0.0 - 1.0
    VERIFICATION_RESULT_DELAY_SECONDS: int = 5
    VERIFICATION_ENFORCE_PROFILE_OCR_MATCH: bool = False
    VERIFICATION_FACE_ONLY_MODE: bool = True
    VERIFICATION_MANUAL_REVIEW_ENABLED: bool = False
    VERIFICATION_ALLOW_REUPLOAD_ALWAYS: bool = True

    # Google Vision OCR
    GOOGLE_APPLICATION_CREDENTIALS: str = ""  # Service account JSON path
    GOOGLE_CLOUD_PROJECT: str = ""

    # AWS Rekognition
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "ap-south-1"

    # Azure AI Vision + Face API
    AZURE_VISION_ENDPOINT: str = ""  # e.g. https://<resource>.cognitiveservices.azure.com
    AZURE_VISION_API_KEY: str = ""
    AZURE_FACE_ENDPOINT: str = ""  # Optional override; defaults to AZURE_VISION_ENDPOINT in service
    AZURE_FACE_API_KEY: str = ""  # Optional override; defaults to AZURE_VISION_API_KEY in service
    # === VERIFICATION FUNCTIONALITY END ===

    # Payment Gateway
    PAYMENT_SANDBOX_KEY: str = ""  # Test environment payment key
    PAYMENT_PRODUCTION_KEY: str = ""  # Production payment key
    PAYMENT_PROVIDER: str = "stripe"  # stripe, razorpay, etc.

    # Email/SMS Configuration
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    FROM_EMAIL: str = "noreply@smartcarpooling.com"

    # Admin Configuration
    ADMIN_EMAIL: str = "admin@smartcarpooling.com"
    ADMIN_PASSWORD: str = "change-this-in-production"
    ADMIN_IP_ALLOWLIST: List[str] = ["127.0.0.1", "10.0.0.0/24"]

    # CORS Settings (Development: allow all localhost, Production: specify exact origins)
    CORS_ORIGINS: List[str] = []  # Empty for regex matching in development
    CORS_ORIGIN_REGEX: str = r"http://(localhost|127\.0\.0\.1)(:\d+)?"  # Allow any localhost port
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 5
    UPLOAD_DIR: str = "uploads"

    # Logging
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_FORMAT: str = "json"  # json or pretty

    # AI/ML Settings (for ride matching and anomaly detection)
    ML_MODEL_PATH: Optional[str] = None
    ENABLE_AI_MATCHING: bool = True
    ANOMALY_DETECTION_THRESHOLD: float = 0.75

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100

    # Matching Engine Settings
    MATCHING_PREFILTER_RADIUS_DEFAULT_KM: float = 10.0
    MATCHING_MAX_CANDIDATES: int = 50
    MATCHING_WEIGHT_DETOUR: float = 0.5
    MATCHING_WEIGHT_DRIVER: float = 0.3
    MATCHING_WEIGHT_PREFERENCE: float = 0.2
    CLUSTER_CACHE_TTL_SECONDS: int = 300  # 5 minutes
    CLUSTER_REFRESH_INTERVAL_MINUTES: int = 5

    # Telemetry Settings
    TELEMETRY_MAX_STOP_MINUTES: float = 3.0  # Unexpected stop threshold
    TELEMETRY_MAX_LATERAL_DEVIATION_METERS: float = 25.0  # Lateral deviation threshold
    TELEMETRY_EXPECTED_POLYLINE_SIMPLIFICATION: float = 0.0001  # Douglas-Peucker tolerance
    TELEMETRY_MAX_BATCH_SIZE: int = 500  # Maximum points per batch upload

    # Safety AI Microservice Settings (Prompt 8)
    SAFETY_AI_OFF_ROUTE_M: float = 60.0  # Off-route detection threshold in meters
    SAFETY_AI_STOP_MINUTES: float = 3.0  # Unexpected stop duration in minutes
    SAFETY_AI_OVERSPEED_KMH: float = 120.0  # Overspeed threshold in km/h
    SAFETY_AI_ML_SENSITIVITY: float = 0.7  # ML anomaly detection sensitivity (0-1)
    SAFETY_AI_FALSE_POSITIVE_SECONDS: float = 15.0  # Minimum duration for anomaly confirmation
    SAFETY_AI_POLYLINE_MAX_ALTERNATES: int = 5  # Maximum alternate routes to compute
    SAFETY_AI_ESCALATION_STAGE1_TIMEOUT: int = 60  # Stage 1 timeout in seconds
    SAFETY_AI_ESCALATION_STAGE2_TIMEOUT: int = 300  # Stage 2 timeout in seconds

    # Notifications & Real-Time WebSocket Settings (Prompt 9)
    NOTIFICATIONS_CHANNEL_PREFIX: str = "notifications"  # Channel prefix for in-memory pub/sub
    NOTIFICATIONS_RETRY_MAX: int = 5  # Maximum retry attempts for failed deliveries
    NOTIFICATIONS_RETRY_BACKOFF: float = 2.0  # Exponential backoff multiplier (1s, 2s, 4s, 8s, 16s)
    NOTIFICATIONS_HEARTBEAT_INTERVAL: int = 30  # WebSocket heartbeat/ping interval in seconds
    NOTIFICATIONS_DLQ_KEY: str = "dlq:notifications"  # Dead-letter queue key (in-memory)
    
    # SMS Settings (Twilio/Easypaisa)
    SMS_ACCOUNT_SID: str = ""  # Twilio Account SID or Easypaisa API key
    SMS_AUTH_TOKEN: str = ""  # Twilio Auth Token or Easypaisa API secret
    SMS_FROM_NUMBER: str = ""  # Sender phone number (E.164 format: +923001234567)
    SMS_PROVIDER: str = "twilio"  # SMS provider: twilio or easypaisa
    
    # Email Settings (SMTP)
    SMTP_HOST: str = "smtp.gmail.com"  # SMTP server hostname
    SMTP_PORT: int = 587  # SMTP port (587 for TLS, 465 for SSL)
    SMTP_USER: str = ""  # SMTP username (email address)
    SMTP_PASSWORD: str = ""  # SMTP password or app password
    SMTP_FROM_EMAIL: str = ""  # Sender email address
    SMTP_FROM_NAME: str = "SmartCarpoolingApp"  # Sender display name

    # Payments & Wallets Settings (Prompt 10)
    PAYMENTS_SANDBOX_MODE: bool = True  # Use sandbox environment for all providers
    PAYMENTS_TOPUP_COMMISSION_PERCENT: float = 5.0  # Top-up commission percentage (5% = 0.05)
    PAYMENTS_PAYOUT_COMMISSION_PERCENT: float = 3.0  # Payout commission percentage (3% = 0.03)
    PAYMENTS_IDEMPOTENCY_TTL: int = 3600  # Idempotency record TTL in seconds (1 hour)
    PAYMENTS_MIN_COMMISSION: float = 0.0  # Minimum commission amount in PKR
    PAYMENTS_MAX_COMMISSION: Optional[float] = None  # Maximum commission amount in PKR (None = unlimited)
    
    # Easypaisa Adapter Settings
    EASYPAISA_API_KEY: str = "sandbox_api_key_123"  # Easypaisa API key
    EASYPAISA_SECRET_KEY: str = "sandbox_secret_key_456"  # HMAC secret key
    EASYPAISA_MERCHANT_ID: str = "MERCHANT_001"  # Easypaisa Merchant ID
    
    # JazzCash Adapter Settings
    JAZZCASH_MERCHANT_ID: str = "MC12345"  # JazzCash Merchant ID
    JAZZCASH_PASSWORD: str = "sandbox_password_123"  # Merchant password
    JAZZCASH_INTEGRITY_SALT: str = "sandbox_salt_456"  # Integrity salt for signature
    
    # Card Gateway Adapter Settings
    CARD_GATEWAY_KEY: str = "sandbox_gateway_key_123"  # Payment gateway API key
    CARD_GATEWAY_SECRET: str = "sandbox_gateway_secret_456"  # Gateway secret for signature

    # Ratings & Analytics Settings (Prompt 11)
    RATINGS_RECENT_WEIGHT: float = 1.0  # Weight for recent ratings (≤90 days)
    RATINGS_OLD_WEIGHT: float = 0.6  # Weight for old ratings (>90 days)
    RATINGS_OUTLIER_WEIGHT: float = 0.3  # Weight for outlier ratings (<2 or >4.8)
    RATINGS_RECENT_DAYS: int = 90  # Days to consider "recent"
    RATINGS_OUTLIER_LOW: float = 2.0  # Low outlier threshold
    RATINGS_OUTLIER_HIGH: float = 4.8  # High outlier threshold
    
    # Analytics & Reporting Settings
    ANALYTICS_CACHE_TTL_SECONDS: int = 300  # Analytics cache expiry (5 minutes)
    ANALYTICS_DAILY_AGGREGATION_TIME: str = "23:55"  # Daily aggregation task time (HH:MM)
    ANALYTICS_MONTHLY_EARNINGS_TIME: str = "00:00"  # Monthly earnings computation time
    ANALYTICS_TOP_DRIVERS_LIMIT: int = 50  # Maximum top drivers to show
    
    # CSV Export Settings
    EARNINGS_CSV_EXPORT_PATH: str = "./exports/"  # Path for CSV exports
    EARNINGS_CSV_MAX_MONTHS: int = 24  # Maximum months for CSV export

    model_config = SettingsConfigDict(
        env_file=[str(_BACKEND_ENV_FILE)] if _BACKEND_ENV_FILE.is_file() else [],
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    def resolved_google_maps_key(self) -> str:
        """Single key used by maps proxy, clustering ETAs, and route tools."""
        return (self.GOOGLE_MAPS_API_KEY or self.GOOGLE_MAPS_KEY or "").strip()


# Singleton instance of settings
settings = Settings()


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return settings
