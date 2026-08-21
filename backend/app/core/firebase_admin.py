"""Firebase Admin SDK helpers."""

from __future__ import annotations

import asyncio
import os
from typing import Optional, Dict, Any

# Fix SSL certificate verification on Windows (proxy / corporate CA)
# Must be called BEFORE any HTTPS requests from firebase_admin / google-auth
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# firebase_admin is optional until configured
try:  # pragma: no cover - handled at runtime
    import firebase_admin
    from firebase_admin import App, auth, credentials
except ImportError as exc:  # pragma: no cover
    firebase_admin = None
    App = None  # type: ignore
    auth = None  # type: ignore
    credentials = None  # type: ignore
    logger.warning(
        "Firebase Admin SDK not installed. Install 'firebase-admin' to enable Firebase auth."
    )

_firebase_app: Optional[App] = None


def _load_credentials() -> credentials.Base:
    if credentials is None:  # pragma: no cover
        raise ValueError("Firebase Admin SDK is not installed. Run 'pip install firebase-admin'.")
    raw = (settings.FCM_CREDENTIALS_PATH or "").strip().strip('"').strip("'")
    if raw:
        path = os.path.abspath(raw)
        if os.path.exists(path):
            logger.info("Using Firebase credentials from %s", path)
            return credentials.Certificate(path)
        logger.warning("Firebase credentials file not found at %s", path)
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        logger.info("Using credentials referenced by GOOGLE_APPLICATION_CREDENTIALS")
        return credentials.ApplicationDefault()
    raise FileNotFoundError("Firebase credentials not configured. Set FCM_CREDENTIALS_PATH or GOOGLE_APPLICATION_CREDENTIALS.")


def initialize_firebase(force: bool = False) -> Optional[App]:
    global _firebase_app
    if _firebase_app and not force:
        return _firebase_app
    if firebase_admin is None:  # pragma: no cover
        logger.warning("Cannot initialize Firebase because firebase-admin is missing.")
        return None
    try:
        cred = _load_credentials()
        project_id = settings.FIREBASE_PROJECT_ID or None
        options = {"projectId": project_id} if project_id else None
        _firebase_app = firebase_admin.initialize_app(cred, options)
        logger.info("Firebase Admin SDK initialized")
        return _firebase_app
    except Exception as exc:
        logger.warning("Firebase initialization failed: %s", exc)
        _firebase_app = None
        return None


def _ensure_initialized() -> App:
    app = initialize_firebase()
    if not app:
        raise ValueError("Firebase Admin SDK is not configured. Provide service account credentials.")
    return app


async def verify_firebase_token(id_token: str) -> Dict[str, Any]:
    app = _ensure_initialized()
    loop = asyncio.get_running_loop()

    def _verify() -> Dict[str, Any]:
        # Simple auth mode: verify token signature/claims only.
        # Revocation check requires an extra Admin API call that can fail
        # in local setups with broken service-account signing.
        decoded = auth.verify_id_token(id_token, app=app, check_revoked=False)
        return {
            "firebase_uid": decoded.get("uid"),
            "email": decoded.get("email"),
            "email_verified": decoded.get("email_verified", False),
            "auth_time": decoded.get("auth_time"),
        }

    return await loop.run_in_executor(None, _verify)
