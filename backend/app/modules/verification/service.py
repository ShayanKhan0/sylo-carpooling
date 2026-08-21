"""
Business logic for Verification Module.

Services for document upload, AI verification, and admin review.

Author: Smart Carpooling Development Team
Created: 2025-11-08
"""

# === VERIFICATION FUNCTIONALITY START ===
import json
import math
import re
import struct
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Any, Optional, List
from uuid import UUID

from fastapi import UploadFile, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import crud
from .models import DocumentTypeEnum, VerificationStatusEnum
from .utils import (
    validate_document_file,
    generate_doc_filename,
    extract_document_number
)
from .ocr_adapter import get_ocr_adapter
from .face_match_adapter import get_face_match_adapter
from .decision_engine import get_decision_engine
import logging

logger = logging.getLogger(__name__)
from app.core.config import settings


# Upload directory configuration
BACKEND_DIR = Path(__file__).resolve().parents[3]
UPLOAD_DIR = BACKEND_DIR / "static" / "uploads" / "verification"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

_VERIFICATION_PROVIDER_HINT_RE = re.compile(
    r"(google|google\s+vision|cloud\s+vision|gcp|aws|textract|rekognition|azure|computer\s+vision|ocr|api|endpoint|service\s+account|subscription\s*key|boto3|credential)",
    re.IGNORECASE,
)

_VERIFICATION_PROVIDER_KEY_RE = re.compile(
    r"(provider|api|ocr_raw|face_result|face_detection|credential|endpoint|subscription|service_account)",
    re.IGNORECASE,
)


def sanitize_verification_client_text(message: Optional[str]) -> Optional[str]:
    """Remove provider hints from verification-facing messages without changing flow."""
    if message is None:
        return None
    text = str(message).strip()
    if not text:
        return text

    lowered = text.lower()
    has_failure_signal = any(
        token in lowered
        for token in (
            "failed",
            "error",
            "unavailable",
            "unable",
            "not configured",
            "timed out",
            "could not",
            "exception",
        )
    )
    has_provider_hint = _VERIFICATION_PROVIDER_HINT_RE.search(text) is not None

    if has_failure_signal and "face" in lowered:
        return (
            "Face verification could not be completed right now. "
            "Upload a brighter, uncropped image with full document visible and try again."
        )
    if has_failure_signal and (
        has_provider_hint or "document" in lowered or "identity" in lowered
    ):
        return (
            "Document could not be read clearly. "
            "Upload a brighter, uncropped image with full document visible and try again."
        )

    # Non-failure strings: scrub provider-identifying terms while keeping meaning.
    scrubbed = text
    scrubbed = re.sub(
        r"google\s+vision|cloud\s+vision|gcp",
        "document scan service",
        scrubbed,
        flags=re.IGNORECASE,
    )
    scrubbed = re.sub(
        r"aws\s+rekognition|rekognition|azure\s+face|computer\s+vision",
        "face verification service",
        scrubbed,
        flags=re.IGNORECASE,
    )
    scrubbed = re.sub(r"\bocr\b", "document scan", scrubbed, flags=re.IGNORECASE)
    scrubbed = re.sub(r"\bapi\b", "service", scrubbed, flags=re.IGNORECASE)
    return scrubbed


def sanitize_verification_client_payload(payload: Any) -> Any:
    """Recursively sanitize verification responses so provider names never reach clients."""
    if isinstance(payload, dict):
        sanitized: Dict[str, Any] = {}
        for key, value in payload.items():
            key_str = str(key)
            if _VERIFICATION_PROVIDER_KEY_RE.search(key_str):
                # Hide provider-specific internals from client responses.
                continue
            sanitized[key] = sanitize_verification_client_payload(value)
        return sanitized
    if isinstance(payload, list):
        return [sanitize_verification_client_payload(item) for item in payload]
    if isinstance(payload, str):
        return sanitize_verification_client_text(payload)
    return payload


def sanitized_verification_http_exception(exc: HTTPException) -> HTTPException:
    """Return a copy of HTTPException with provider-hint-free detail."""
    detail = exc.detail
    if isinstance(detail, (dict, list)):
        sanitized_detail = sanitize_verification_client_payload(detail)
    else:
        sanitized_detail = sanitize_verification_client_text(str(detail))
    return HTTPException(
        status_code=exc.status_code,
        detail=sanitized_detail,
        headers=exc.headers,
    )

PASSENGER_REQUIRED_VERIFICATION_DOCS = [
    DocumentTypeEnum.CNIC.value,
    DocumentTypeEnum.SELFIE.value,
]

DRIVER_REQUIRED_VERIFICATION_DOCS = [
    DocumentTypeEnum.CNIC.value,
    DocumentTypeEnum.DRIVING_LICENSE.value,
    DocumentTypeEnum.SELFIE.value,
]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _resolve_google_ocr_credentials_path() -> str:
    primary = _first_non_empty(settings.GOOGLE_APPLICATION_CREDENTIALS)
    fallback = _first_non_empty(settings.FCM_CREDENTIALS_PATH)

    # Allow quoted values in .env while preserving Windows paths.
    for raw in (primary, fallback):
        if not raw:
            continue
        normalized = str(raw).strip().strip('"').strip("'")
        if normalized:
            return normalized

    return ""


def _normalize_identifier(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _normalize_ocr_digit_confusions(value: Optional[str]) -> str:
    """
    Replace common OCR confusions for numeric identifiers.
    """
    text = str(value or "").upper()
    if not text:
        return ""

    replacements = str.maketrans(
        {
            "O": "0",
            "Q": "0",
            "D": "0",
            "I": "1",
            "L": "1",
            "Z": "2",
            "S": "5",
            "B": "8",
            "G": "6",
            "T": "7",
        }
    )
    return text.translate(replacements)


def _compact_preview(value: Any, max_length: int = 96) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _extract_image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    """
    Best-effort width/height parsing for PNG/JPEG bytes.
    """
    if not image_bytes or len(image_bytes) < 24:
        return 0, 0

    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
        width = struct.unpack(">I", image_bytes[16:20])[0]
        height = struct.unpack(">I", image_bytes[20:24])[0]
        return int(width), int(height)

    if image_bytes[0:2] == b"\xFF\xD8":
        idx = 2
        length = len(image_bytes)
        while idx + 9 < length:
            if image_bytes[idx] != 0xFF:
                idx += 1
                continue

            marker = image_bytes[idx + 1]
            idx += 2

            if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
                continue

            if idx + 1 >= length:
                break
            segment_length = struct.unpack(">H", image_bytes[idx:idx + 2])[0]
            if segment_length < 2 or idx + segment_length > length:
                break

            if marker in {
                0xC0, 0xC1, 0xC2, 0xC3,
                0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB,
                0xCD, 0xCE, 0xCF,
            }:
                if idx + 7 <= length:
                    height = struct.unpack(">H", image_bytes[idx + 3:idx + 5])[0]
                    width = struct.unpack(">H", image_bytes[idx + 5:idx + 7])[0]
                    return int(width), int(height)
                break

            idx += segment_length

    return 0, 0


def _extract_loose_document_number_from_text(text: str, doc_type: Any) -> str:
    source_text = str(text or "")
    if not source_text:
        return ""

    doc_type_value = str(getattr(doc_type, "value", doc_type) or "").strip().lower()

    if doc_type_value == "cnic":
        match = re.search(r"\b(\d{5})[-\s]?(\d{7})[-\s]?(\d)\b", source_text)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

        dense_match = re.search(r"\b\d{13}\b", source_text)
        if dense_match:
            digits = dense_match.group(0)
            return f"{digits[:5]}-{digits[5:12]}-{digits[12]}"

        # Retry with OCR-confusion normalization (e.g., O->0, I->1, S->5).
        normalized_text = _normalize_ocr_digit_confusions(source_text)
        match = re.search(r"\b(\d{5})[-\s]?(\d{7})[-\s]?(\d)\b", normalized_text)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

        dense_match = re.search(r"\b\d{13}\b", normalized_text)
        if dense_match:
            digits = dense_match.group(0)
            return f"{digits[:5]}-{digits[5:12]}-{digits[12]}"

    if doc_type_value in {"driving_license", "license", "driver_license"}:
        mixed_match = re.search(
            r"\b([A-Z]{2,5})[-\s]?(\d{3,6})[-\s]?([A-Z]{1,4})[-\s]?(\d{2,6})\b",
            source_text,
            flags=re.IGNORECASE,
        )
        if mixed_match:
            return (
                f"{mixed_match.group(1).upper()}"
                f"{mixed_match.group(2)}"
                f"{mixed_match.group(3).upper()}"
                f"{mixed_match.group(4)}"
            )

        prefixed_match = re.search(
            r"\b(\d{1,4})[-\s]?([A-Z]{1,4})[-\s]?(\d{2,10})\b",
            source_text,
            flags=re.IGNORECASE,
        )
        if prefixed_match:
            return (
                f"{prefixed_match.group(1)}"
                f"{prefixed_match.group(2).upper()}"
                f"{prefixed_match.group(3)}"
            )

        match = re.search(r"\b([A-Z]{2,5})[-\s]?(\d{4,10})\b", source_text, flags=re.IGNORECASE)
        if match:
            return f"{match.group(1).upper()}{match.group(2)}"

    return ""


def _extract_identity_display_number(
    ocr_result: Dict[str, Any],
    doc_type: Any,
    profile_field: str,
    include_preview: bool = True,
) -> str:
    raw_fields = ocr_result.get("fields")
    fields = raw_fields if isinstance(raw_fields, dict) else {}
    ocr_text = _first_non_empty(ocr_result.get("text"), ocr_result.get("raw_text"))
    doc_type_value = str(getattr(doc_type, "value", doc_type) or "").strip().lower()

    if doc_type_value == "cnic":
        preferred_keys = [
            "cnic_number",
            "cnic_no",
            "cnic",
            "national_id",
            "id_number",
            "document_number",
            profile_field,
        ]
    elif doc_type_value in {"driving_license", "license", "driver_license"}:
        preferred_keys = [
            "license_number",
            "license_no",
            "license",
            "driver_license_number",
            "dl_number",
            "document_number",
            profile_field,
        ]
    else:
        preferred_keys = [profile_field, "document_number", "id_number"]

    key_candidates: List[str] = []
    for key in preferred_keys:
        candidate = str(fields.get(key) or "").strip()
        if candidate:
            key_candidates.append(candidate)

    numeric_field_candidate = ""
    for value in fields.values():
        value_text = str(value or "").strip()
        if value_text and re.search(r"\d", value_text):
            numeric_field_candidate = value_text
            break

    loose_number = _extract_loose_document_number_from_text(ocr_text, doc_type_value)
    if not include_preview:
        return _first_non_empty(*key_candidates, numeric_field_candidate, loose_number)

    preview = _compact_preview(ocr_text)
    return _first_non_empty(*key_candidates, numeric_field_candidate, loose_number, preview)


def _format_identity_display_number(doc_type: Any, extracted_value: Any) -> str:
    value = str(extracted_value or "").strip()
    if not value:
        return ""

    doc_type_value = str(getattr(doc_type, "value", doc_type) or "").strip().lower()
    compact = re.sub(r"[^A-Z0-9]", "", value.upper())

    if doc_type_value == "cnic":
        match = re.fullmatch(r"(\d{5})(\d{7})(\d)", compact)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        return value

    if doc_type_value in {"driving_license", "license", "driver_license"}:
        mixed_match = re.fullmatch(r"([A-Z]{2,5})(\d{3,6})([A-Z]{1,4})(\d{2,6})", compact)
        if mixed_match:
            return (
                f"{mixed_match.group(1)}-"
                f"{mixed_match.group(2)}{mixed_match.group(3)}{mixed_match.group(4)}"
            )

        prefixed_match = re.fullmatch(r"(\d{1,4})([A-Z]{1,4})(\d{2,10})", compact)
        if prefixed_match:
            return (
                f"{prefixed_match.group(1)}-"
                f"{prefixed_match.group(2)}-"
                f"{prefixed_match.group(3)}"
            )

        match = re.fullmatch(r"([A-Z]{2,5})(\d{4,10})", compact)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return value

    return value


def _align_with_profile_format(extracted_value: Any, profile_value: Any) -> str:
    extracted = str(extracted_value or "").strip()
    profile = str(profile_value or "").strip()

    if not extracted or not profile:
        return extracted

    extracted_compact = re.sub(r"[^A-Z0-9]", "", extracted.upper())
    profile_compact = re.sub(r"[^A-Z0-9]", "", profile.upper())

    # Reformat only when both identifiers carry the same alphanumeric length.
    if not extracted_compact or len(extracted_compact) != len(profile_compact):
        return extracted

    aligned_chars: List[str] = []
    value_index = 0
    for ch in profile:
        if ch.isalnum():
            token = extracted_compact[value_index]
            value_index += 1
            if ch.isalpha() and ch.islower():
                aligned_chars.append(token.lower())
            elif ch.isalpha():
                aligned_chars.append(token.upper())
            else:
                aligned_chars.append(token)
        else:
            aligned_chars.append(ch)

    return "".join(aligned_chars).strip()


def _extract_by_profile_template(ocr_result: Dict[str, Any], profile_value: Any) -> str:
    expected = str(profile_value or "").strip()
    if not expected:
        return ""

    ocr_text = _first_non_empty(ocr_result.get("text"), ocr_result.get("raw_text"))
    if not ocr_text:
        return ""

    expected_upper = expected.upper()
    tokens = [token for token in re.split(r"[^A-Z0-9]+", expected_upper) if token]
    if not tokens:
        return ""

    separator_pattern = r"[\s\-\._:/\\]*"
    pattern = separator_pattern.join(re.escape(token) for token in tokens)
    match = re.search(pattern, ocr_text.upper())
    if not match:
        return ""

    return _align_with_profile_format(match.group(0), expected)


def _detect_identity_document_type(ocr_result: Dict[str, Any]) -> str:
    raw_fields = ocr_result.get("fields")
    fields = raw_fields if isinstance(raw_fields, dict) else {}
    text = _first_non_empty(ocr_result.get("text"), ocr_result.get("raw_text")).lower()

    cnic_score = 0
    license_score = 0

    if str(fields.get("cnic_number") or "").strip():
        cnic_score += 3
    if str(fields.get("license_number") or "").strip():
        license_score += 3

    cnic_patterns = [
        r"computerized\s+national\s+identity\s+card",
        r"national\s+identity\s+card",
        r"\bcnic\b",
        r"\bidentity\s+card\b",
    ]
    license_patterns = [
        r"\bdriving\s+licen[cs]e\b",
        r"\blicen[cs]e\s*(?:no|number)\b",
        r"\bdl\s*no\b",
        r"\bdriver\b",
        r"\bcategory\b",
    ]

    for pattern in cnic_patterns:
        if re.search(pattern, text):
            cnic_score += 1

    for pattern in license_patterns:
        if re.search(pattern, text):
            license_score += 1

    if cnic_score == 0 and license_score == 0:
        return "unknown"
    if cnic_score > license_score:
        return "cnic"
    if license_score > cnic_score:
        return "driving_license"
    return "unknown"


def _normalize_name(value: Optional[str]) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^a-z\s]", "", str(value).lower())
    return " ".join(normalized.split())


def _names_match(expected_name: str, extracted_name: str, threshold: float = 0.80) -> bool:
    expected = _normalize_name(expected_name)
    extracted = _normalize_name(extracted_name)

    if not expected or not extracted:
        return False

    similarity = SequenceMatcher(None, expected, extracted).ratio()
    return similarity >= threshold


def _resolve_ocr_provider(configured_provider: Optional[str]) -> str:
    """Force OCR provider policy: Google Vision in production, local only when explicitly requested."""
    normalized = (configured_provider or "google").strip().lower()

    if normalized in {"google", "google_vision", "gcp"}:
        return "google"
    if normalized in {"local", "stub", "mock"}:
        return "local"

    logger.warning(
        "Unsupported OCR provider '%s'. Falling back to Google Vision OCR.",
        configured_provider,
    )
    return "google"


def _is_ocr_service_failure(error_message: Optional[str]) -> bool:
    """
    Detect OCR provider/runtime failures that are not caused by image quality.
    """
    raw = (error_message or "").strip().lower()
    if not raw:
        return False

    service_markers = (
        "permission denied",
        "authentication",
        "credentials",
        "quota",
        "billing",
        "api has not been used",
        "service unavailable",
        "deadline exceeded",
        "timeout",
        "timed out",
        "network",
        "connection",
        "dns",
        "unavailable",
        "rate limit",
        "429",
        "500",
        "503",
    )
    return any(marker in raw for marker in service_markers)


def _resolve_face_provider(configured_provider: Optional[str]) -> str:
    """Resolve face provider: AWS Rekognition or Azure Face, local only when explicitly requested."""
    normalized = (configured_provider or "aws").strip().lower()

    if normalized in {"aws", "rekognition", "aws_rekognition"}:
        return "aws"
    if normalized in {"azure", "azure_face", "azure-face"}:
        return "azure"
    if normalized in {"local", "stub", "mock"}:
        return "local"

    logger.warning(
        "Unsupported face provider '%s'. Falling back to AWS Rekognition.",
        configured_provider,
    )
    return "aws"


def _is_face_only_mode() -> bool:
    return bool(getattr(settings, "VERIFICATION_FACE_ONLY_MODE", False))


def _normalize_user_role(user_role: Any) -> str:
    if user_role is None:
        return "passenger"

    if hasattr(user_role, "value"):
        role_text = str(user_role.value).strip().lower()
    else:
        role_text = str(user_role).strip().lower()

    if role_text == "student":
        return "passenger"
    if role_text:
        return role_text
    return "passenger"


def _is_driver_role(user_role: Any) -> bool:
    return _normalize_user_role(user_role) == "driver"


def _is_face_only_mode_for_role(user_role: Any) -> bool:
    # Passenger flow: CNIC + selfie. Driver flow uses CNIC + license + selfie.
    return not _is_driver_role(user_role)


def _requires_binary_final_decision_for_role(user_role: Any) -> bool:
    return (
        _is_face_only_mode_for_role(user_role)
        or _is_driver_role(user_role)
        or not _is_manual_review_enabled()
    )


def _get_required_verification_docs_for_role(user_role: Any) -> List[str]:
    if _is_driver_role(user_role):
        return DRIVER_REQUIRED_VERIFICATION_DOCS
    return PASSENGER_REQUIRED_VERIFICATION_DOCS


async def _get_user_role_for_user(db: AsyncSession, user_id: UUID) -> str:
    try:
        from app.modules.auth.models import User

        role_value = (
            await db.execute(select(User.role).where(User.id == user_id))
        ).scalar_one_or_none()
        return _normalize_user_role(role_value)
    except Exception as exc:
        logger.warning("Could not resolve verification role for user %s: %s", user_id, exc)
        return "passenger"


def _is_manual_review_enabled() -> bool:
    return bool(getattr(settings, "VERIFICATION_MANUAL_REVIEW_ENABLED", True))


def _manual_review_outcome() -> tuple[str, str]:
    if _is_manual_review_enabled():
        return "flagged", "under_review"
    return "rejected", "rejected"


def _requires_binary_final_decision() -> bool:
    return _requires_binary_final_decision_for_role("passenger")


def _get_required_verification_docs() -> List[str]:
    return _get_required_verification_docs_for_role("passenger")


def _normalize_public_verification_status(status_value: Optional[str]) -> str:
    """Normalize status aliases to a stable public set used by frontend state logic."""
    normalized = (status_value or "").strip().lower()

    if normalized in {"approved", "verified"}:
        return "verified"
    if normalized in {"in_review", "reviewing", "under-review", "under_review"}:
        return "under_review"
    if normalized in {"pending", "processing", "rejected", "expired", "not_uploaded"}:
        return normalized

    return normalized or "pending"


def _build_face_adapter(provider: str):
    kwargs: Dict[str, Any] = {
        "match_threshold": settings.VERIFICATION_FACE_MATCH_THRESHOLD,
    }

    if provider == "aws":
        kwargs.update(
            {
                "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                "region_name": settings.AWS_REGION,
            }
        )
    elif provider == "azure":
        kwargs.update(
            {
                "endpoint": settings.AZURE_FACE_ENDPOINT or settings.AZURE_VISION_ENDPOINT,
                "subscription_key": settings.AZURE_FACE_API_KEY or settings.AZURE_VISION_API_KEY,
            }
        )

    return get_face_match_adapter(provider, **kwargs)


async def _get_user_identity_snapshot(db: AsyncSession, user_id: UUID) -> Dict[str, str]:
    """Collect user-entered identity values used to cross-check OCR output."""
    try:
        from app.modules.auth.models import User
        from app.modules.users.models import UserProfile
        from app.modules.drivers.models import DriverProfile

        user_full_name = (
            await db.execute(select(User.full_name).where(User.id == user_id))
        ).scalar_one_or_none()

        profile_row = (
            await db.execute(
                select(
                    UserProfile.cnic,
                    UserProfile.driving_license,
                    UserProfile.car_registration,
                ).where(UserProfile.user_id == user_id)
            )
        ).first()

        driver_row = (
            await db.execute(
                select(
                    DriverProfile.cnic_number,
                    DriverProfile.license_number,
                ).where(DriverProfile.user_id == user_id)
            )
        ).first()

        profile_cnic = profile_row[0] if profile_row else ""
        profile_license = profile_row[1] if profile_row else ""
        profile_registration = profile_row[2] if profile_row else ""

        driver_cnic = driver_row[0] if driver_row else ""
        driver_license = driver_row[1] if driver_row else ""

        return {
            "full_name": _first_non_empty(user_full_name),
            "cnic_number": _first_non_empty(profile_cnic, driver_cnic),
            "license_number": _first_non_empty(profile_license, driver_license),
            "registration_number": _first_non_empty(profile_registration),
        }
    except Exception as exc:
        logger.warning("Could not load identity snapshot for OCR cross-check: %s", exc)
        return {
            "full_name": "",
            "cnic_number": "",
            "license_number": "",
            "registration_number": "",
        }


def _build_identity_cross_check(
    document_type: str,
    expected_identity: Dict[str, str],
    ocr_fields: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare user-entered values with OCR output for the uploaded document type."""
    doc_type = (document_type or "").lower()
    checks: List[Dict[str, Any]] = []

    def add_check(field: str, expected_value: str, extracted_value: str, strict: bool) -> None:
        expected_text = (expected_value or "").strip()
        if not expected_text:
            return

        extracted_text = (extracted_value or "").strip()
        severity = "hard" if strict else "soft"

        if not extracted_text:
            checks.append(
                {
                    "field": field,
                    "severity": severity,
                    "status": "missing_in_ocr",
                    "expected": expected_text,
                    "extracted": "",
                }
            )
            return

        if field == "name":
            matched = _names_match(expected_text, extracted_text)
        else:
            matched = _normalize_identifier(expected_text) == _normalize_identifier(extracted_text)

        checks.append(
            {
                "field": field,
                "severity": severity,
                "status": "match" if matched else "mismatch",
                "expected": expected_text,
                "extracted": extracted_text,
            }
        )

    if doc_type == "cnic":
        add_check(
            "cnic_number",
            expected_identity.get("cnic_number", ""),
            str(ocr_fields.get("cnic_number") or ""),
            strict=True,
        )
        add_check(
            "name",
            expected_identity.get("full_name", ""),
            str(ocr_fields.get("name") or ""),
            strict=False,
        )
    elif doc_type in {"driving_license", "license", "driver_license"}:
        add_check(
            "license_number",
            expected_identity.get("license_number", ""),
            str(ocr_fields.get("license_number") or ""),
            strict=True,
        )
        add_check(
            "name",
            expected_identity.get("full_name", ""),
            str(ocr_fields.get("name") or ""),
            strict=False,
        )
    elif doc_type in {"vehicle_registration", "vehicle_reg", "registration"}:
        add_check(
            "registration_number",
            expected_identity.get("registration_number", ""),
            str(ocr_fields.get("registration_number") or ""),
            strict=True,
        )

    hard_fail = any(
        c["severity"] == "hard" and c["status"] in {"mismatch", "missing_in_ocr"}
        for c in checks
    )
    soft_fail = any(
        c["severity"] == "soft" and c["status"] in {"mismatch", "missing_in_ocr"}
        for c in checks
    )

    if hard_fail:
        status_str = "hard_fail"
    elif soft_fail:
        status_str = "soft_fail"
    elif checks:
        status_str = "pass"
    else:
        status_str = "not_applicable"

    mismatch_fields = [c["field"] for c in checks if c["status"] != "match"]

    return {
        "status": status_str,
        "checks": checks,
        "mismatch_fields": mismatch_fields,
    }


def _resolve_document_path(path_value: Optional[str]) -> Optional[Path]:
    """Resolve stored verification path to an existing absolute path."""
    if not path_value or path_value.startswith("hash:"):
        return None

    raw = Path(path_value)
    candidates = []

    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(BACKEND_DIR / raw)
        candidates.append(Path.cwd() / raw)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def _to_stored_relative_path(path_obj: Path) -> str:
    """Store upload paths as backend-relative paths for portability."""
    try:
        return str(path_obj.relative_to(BACKEND_DIR)).replace("\\", "/")
    except ValueError:
        return str(path_obj)


def _safe_parse_metadata(metadata_raw: Optional[str]) -> Dict[str, Any]:
    if not metadata_raw:
        return {}

    try:
        parsed = json.loads(metadata_raw)
    except (TypeError, ValueError):
        return {}

    if isinstance(parsed, dict):
        return parsed
    return {}


def _normalize_identity_check_status(status_value: Any) -> str:
    normalized = str(status_value or "").strip().lower()
    if normalized in {"passed", "pass", "verified", "approved", "success", "match"}:
        return "passed"
    if normalized in {"failed", "rejected", "mismatch", "not_matched", "hard_fail"}:
        return "failed"
    if normalized in {"processing", "pending", "under_review", "in_review"}:
        return "processing"
    return "not_run"


def _extract_identity_check_snapshot(verification: Optional[Any]) -> Dict[str, Any]:
    if verification is None:
        return {
            "check_status": "not_uploaded",
            "reason": "document_not_uploaded",
            "checked_at": None,
        }

    metadata = _safe_parse_metadata(getattr(verification, "meta_data", None))
    identity_meta = metadata.get("identity_data_verification")
    if not isinstance(identity_meta, dict):
        return {
            "check_status": "not_run",
            "reason": "identity_check_not_run",
            "checked_at": None,
        }

    stored_doc_path = _first_non_empty(identity_meta.get("document_path"))
    verification_doc_path = _first_non_empty(getattr(verification, "doc_path", None))
    if (
        stored_doc_path
        and verification_doc_path
        and stored_doc_path != verification_doc_path
    ):
        return {
            "check_status": "not_run",
            "reason": "identity_check_stale",
            "checked_at": identity_meta.get("checked_at"),
        }

    return {
        "check_status": _normalize_identity_check_status(
            identity_meta.get("check_status")
        ),
        "reason": _first_non_empty(
            identity_meta.get("reason"),
            "identity_check_not_run",
        ),
        "checked_at": identity_meta.get("checked_at"),
    }


async def _persist_identity_data_result(
    db: AsyncSession,
    verification: Any,
    result_data: Dict[str, Any],
) -> None:
    try:
        metadata = _safe_parse_metadata(getattr(verification, "meta_data", None))
        metadata["identity_data_verification"] = {
            "document_type": result_data.get("document_type"),
            "verification_step": result_data.get("verification_step"),
            "check_status": result_data.get("check_status"),
            "match": bool(result_data.get("match")),
            "reason": result_data.get("reason"),
            "message": result_data.get("message"),
            "profile_number": result_data.get("profile_number"),
            "extracted_number": result_data.get("extracted_number"),
            "ocr_confidence": _to_float(result_data.get("ocr_confidence"), 0.0),
            "ocr_provider": result_data.get("ocr_provider"),
            "document_path": verification.doc_path,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

        verification.meta_data = json.dumps(metadata)
        verification.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(verification)
    except Exception as exc:
        await db.rollback()
        logger.warning(
            "Failed to persist identity-data verification result for verification %s: %s",
            getattr(verification, "id", "unknown"),
            exc,
        )


def _collect_verification_file_paths(doc_path: Optional[str], metadata_raw: Optional[str]) -> List[Path]:
    paths: List[Path] = []

    primary_path = _resolve_document_path(doc_path)
    if primary_path:
        paths.append(primary_path)

    metadata = _safe_parse_metadata(metadata_raw)
    for key in ["back_document_path", "document_back_path", "document_path", "selfie_path"]:
        value = metadata.get(key)
        if not isinstance(value, str):
            continue

        resolved = _resolve_document_path(value)
        if resolved:
            paths.append(resolved)

    deduped: List[Path] = []
    seen: set[str] = set()
    for path_obj in paths:
        path_key = str(path_obj)
        if path_key in seen:
            continue
        seen.add(path_key)
        deduped.append(path_obj)

    return deduped


def _delete_file_if_exists(path_obj: Path) -> None:
    try:
        if path_obj.exists():
            path_obj.unlink()
    except Exception as exc:
        logger.warning("Failed to delete verification file %s: %s", path_obj, exc)


async def _find_latest_selfie_path(db: AsyncSession, user_id: UUID) -> Optional[str]:
    selfies = await crud.get_user_verifications(db, user_id, doc_type=DocumentTypeEnum.SELFIE)
    if not selfies:
        return None

    selfie_doc_path = selfies[0].doc_path
    resolved = _resolve_document_path(selfie_doc_path)
    return str(resolved) if resolved else None


async def _sync_driver_profile_photo_from_verified_selfie(
    db: AsyncSession,
    user_id: UUID,
    selfie_doc_path: Optional[str],
) -> None:
    normalized_selfie_path = str(selfie_doc_path or "").strip().replace("\\", "/")
    if not normalized_selfie_path:
        return

    try:
        from app.modules.users import crud as users_crud

        profile = await users_crud.get_user_profile(db, user_id)
        current_profile_photo = (
            str(getattr(profile, "profile_photo", "") or "")
            .strip()
            .replace("\\", "/")
        )

        if current_profile_photo == normalized_selfie_path:
            return

        await users_crud.update_profile_photo(db, user_id, normalized_selfie_path)
        logger.info(
            "Synced verified driver selfie as profile photo for user %s",
            user_id,
        )
    except Exception as exc:
        logger.warning(
            "Could not sync driver selfie profile photo for user %s: %s",
            user_id,
            exc,
        )


async def _create_verification_with_attempt(
    db: AsyncSession,
    user_id: UUID,
    doc_type: DocumentTypeEnum,
    doc_path: str,
    ai_result: Dict[str, Any],
    extra_metadata: Optional[Dict[str, Any]] = None,
):
    """Persist one verification row and one attempt row from an AI result payload."""
    verification_metadata = ai_result.get("metadata", {})
    if not isinstance(verification_metadata, dict):
        verification_metadata = {"raw": verification_metadata}

    if extra_metadata:
        verification_metadata.update(extra_metadata)

    verification = await crud.create_verification(
        db=db,
        user_id=user_id,
        doc_type=doc_type,
        doc_path=doc_path,
        doc_number=ai_result.get("doc_number"),
        ai_confidence=ai_result.get("confidence"),
        ai_remarks=ai_result.get("remarks"),
        verification_status=VerificationStatusEnum(ai_result.get("status")),
        metadata=json.dumps(verification_metadata),
    )

    await crud.create_verification_attempt(
        db=db,
        verification_id=verification.id,
        attempt_type="ai_analysis",
        decision=ai_result.get("decision"),
        ai_score=ai_result.get("confidence"),
        face_match_score=ai_result.get("face_match_score"),
        remarks=ai_result.get("remarks"),
        ocr_data=json.dumps(ai_result.get("ocr_data", {})),
        metadata=json.dumps(verification_metadata),
    )

    return verification


async def _reverify_latest_cnic_after_selfie_upload(
    db: AsyncSession,
    user_id: UUID,
    selfie_path: Optional[str],
    user_role: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Re-run face checks after selfie upload so upload order does not affect final outcome."""
    resolved_user_role = (
        _normalize_user_role(user_role)
        if user_role is not None
        else await _get_user_role_for_user(db, user_id)
    )

    if not selfie_path:
        return []

    if _is_driver_role(resolved_user_role):
        target_doc_types = [DocumentTypeEnum.CNIC, DocumentTypeEnum.DRIVING_LICENSE]
    elif _is_face_only_mode_for_role(resolved_user_role):
        target_doc_types = [DocumentTypeEnum.CNIC]
    else:
        return []

    reprocessed_documents: List[Dict[str, Any]] = []

    for target_doc_type in target_doc_types:
        target_verifications = await crud.get_user_verifications(
            db,
            user_id,
            doc_type=target_doc_type,
        )
        if not target_verifications:
            continue

        source_verification = None
        source_doc_abs_path: Optional[Path] = None
        for verification in target_verifications:
            resolved = _resolve_document_path(verification.doc_path)
            if resolved:
                source_verification = verification
                source_doc_abs_path = resolved
                break

        if source_verification is None or source_doc_abs_path is None:
            continue

        ai_result = await perform_ai_verification_service(
            db=db,
            file_path=str(source_doc_abs_path),
            doc_type=target_doc_type,
            selfie_path=selfie_path,
            user_id=user_id,
            user_role=resolved_user_role,
        )

        refreshed = await _create_verification_with_attempt(
            db=db,
            user_id=user_id,
            doc_type=target_doc_type,
            doc_path=source_verification.doc_path,
            ai_result=ai_result,
            extra_metadata={
                "reverified_after_selfie_upload": True,
                "reverification_source_id": str(source_verification.id),
            },
        )

        reprocessed_documents.append(
            {
                "verification_id": str(refreshed.id),
                "doc_type": target_doc_type.value,
                "status": refreshed.status.value,
                "decision": ai_result.get("decision"),
                "ai_confidence": refreshed.ai_confidence,
                "remarks": ai_result.get("remarks"),
            }
        )

    if reprocessed_documents:
        logger.info(
            "Selfie-triggered re-verification completed for user %s (docs=%s)",
            user_id,
            ",".join(doc.get("doc_type", "") for doc in reprocessed_documents),
        )

    return reprocessed_documents


async def upload_document_service(
    db: AsyncSession,
    user_id: UUID,
    doc_type: DocumentTypeEnum,
    file: UploadFile,
    document_back_file: Optional[UploadFile] = None,
    selfie_file: Optional[UploadFile] = None,
    user_role: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Handle document upload and trigger AI verification.
    
    Process:
    1. Validate file (type, size, format)
    2. Save file to secure location
    3. Extract text using OCR (mock)
    4. Compare faces if applicable (mock)
    5. Calculate AI confidence score
    6. Create verification record
    7. Create verification attempt record
    8. Return result
    
    Args:
        db: Database session
        user_id: User ID
        doc_type: Document type
        file: Uploaded document file
        document_back_file: Optional document back image
        selfie_file: Optional selfie for face matching
    
    Returns:
        Dictionary with status, verification details, and AI decision
    
    Raises:
        HTTPException: If validation fails or upload error occurs
    """
    try:
        resolved_user_role = (
            _normalize_user_role(user_role)
            if user_role is not None
            else await _get_user_role_for_user(db, user_id)
        )

        content = await file.read()

        # Validate file
        is_valid, error_msg = validate_document_file(
            filename=file.filename,
            content_type=file.content_type,
            file_size=len(content)
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg
            )

        # Generate secure filename
        secure_filename = generate_doc_filename(
            user_id=str(user_id),
            doc_type=doc_type.value,
            original_filename=file.filename
        )
        
        # Save file
        file_path = UPLOAD_DIR / secure_filename
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        logger.info(f"Document saved: {file_path}")

        back_document_rel_path = None
        if document_back_file is not None:
            back_content = await document_back_file.read()
            back_valid, back_error = validate_document_file(
                filename=document_back_file.filename,
                content_type=document_back_file.content_type,
                file_size=len(back_content),
            )
            if not back_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid back document: {back_error}"
                )

            back_filename = generate_doc_filename(
                user_id=str(user_id),
                doc_type=f"{doc_type.value}_back",
                original_filename=document_back_file.filename,
            )
            back_file_path = UPLOAD_DIR / back_filename
            with open(back_file_path, "wb") as f:
                f.write(back_content)

            back_document_rel_path = _to_stored_relative_path(back_file_path)
            logger.info(f"Back document saved: {back_file_path}")

        selfie_path = None
        if doc_type in [DocumentTypeEnum.CNIC, DocumentTypeEnum.DRIVING_LICENSE]:
            if selfie_file is not None:
                selfie_content = await selfie_file.read()
                selfie_valid, selfie_error = validate_document_file(
                    filename=selfie_file.filename,
                    content_type=selfie_file.content_type,
                    file_size=len(selfie_content),
                )
                if selfie_valid:
                    selfie_filename = generate_doc_filename(
                        user_id=str(user_id),
                        doc_type=DocumentTypeEnum.SELFIE.value,
                        original_filename=selfie_file.filename,
                    )
                    selfie_file_path = UPLOAD_DIR / selfie_filename
                    with open(selfie_file_path, "wb") as f:
                        f.write(selfie_content)
                    selfie_path = str(selfie_file_path)
                else:
                    logger.warning("Skipping provided selfie because it failed validation: %s", selfie_error)
            else:
                selfie_path = await _find_latest_selfie_path(db, user_id)
        
        # Perform AI verification
        ai_result = await perform_ai_verification_service(
            db=db,
            file_path=str(file_path),
            doc_type=doc_type,
            selfie_path=selfie_path,
            user_id=user_id,
            user_role=resolved_user_role,
        )

        stored_file_path = _to_stored_relative_path(file_path)
        metadata_extra: Dict[str, Any] = {}
        if back_document_rel_path:
            metadata_extra["back_document_path"] = back_document_rel_path

        verification = await _create_verification_with_attempt(
            db=db,
            user_id=user_id,
            doc_type=doc_type,
            doc_path=stored_file_path,
            ai_result=ai_result,
            extra_metadata=metadata_extra or None,
        )

        reprocessed_documents: List[Dict[str, Any]] = []
        if doc_type == DocumentTypeEnum.SELFIE:
            reprocessed_documents = await _reverify_latest_cnic_after_selfie_upload(
                db=db,
                user_id=user_id,
                selfie_path=str(file_path),
                user_role=resolved_user_role,
            )
        
        logger.info(f"Verification created: {verification.id} with status {verification.status}")
        
        return {
            "status": "ok",
            "data": {
                "verification_id": str(verification.id),
                "doc_type": doc_type.value,
                "status": verification.status.value,
                "ai_confidence": verification.ai_confidence,
                "decision": ai_result.get("decision"),
                "message": ai_result.get("remarks"),
                "reprocessed_documents": reprocessed_documents,
            },
            "error": None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload document"
        )


async def perform_ai_verification_service(
    db: AsyncSession,
    file_path: str,
    doc_type: DocumentTypeEnum,
    selfie_path: Optional[str] = None,
    user_id: Optional[UUID] = None,
    user_role: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Perform AI verification on uploaded document.
    
    Steps:
    1. Extract text using OCR
    2. Extract document number
    3. Compare faces if applicable
    4. Calculate overall confidence score
    5. Determine verification decision
    
    Args:
        db: Database session
        file_path: Path to document file
        doc_type: Document type
        selfie_path: Optional path to selfie for face matching
    
    Returns:
        Dictionary with AI analysis results
    """
    try:
        doc_path_obj = _resolve_document_path(file_path)
        if not doc_path_obj:
            raise FileNotFoundError(f"Verification document not found: {file_path}")

        document_bytes = doc_path_obj.read_bytes()
        fallback_decision, fallback_status = _manual_review_outcome()
        if user_role is not None:
            resolved_user_role = _normalize_user_role(user_role)
        elif user_id is not None:
            resolved_user_role = await _get_user_role_for_user(db, user_id)
        else:
            resolved_user_role = "passenger"

        face_only_mode = _is_face_only_mode_for_role(resolved_user_role)

        # Selfie verification uses face detection only (no OCR requirement).
        if doc_type == DocumentTypeEnum.SELFIE:
            face_provider = _resolve_face_provider(settings.VERIFICATION_FACE_PROVIDER)
            try:
                face_adapter = _build_face_adapter(face_provider)
            except Exception as exc:
                logger.error("Failed to initialize face adapter for selfie verification: %s", exc)
                return {
                    "confidence": 0.0,
                    "decision": fallback_decision,
                    "status": fallback_status,
                    "doc_number": None,
                    "ocr_confidence": None,
                    "face_match_score": None,
                    "ocr_data": {},
                    "remarks": f"Selfie uploaded. Face verification pending: {str(exc)}",
                    "metadata": {
                        "face_provider": face_provider,
                        "selfie_used": True,
                    },
                }

            detect_result = await face_adapter.detect_face(document_bytes)
            if detect_result.get("success") and detect_result.get("face_detected"):
                selfie_confidence = _to_float(detect_result.get("quality_score"), 0.85)
                selfie_confidence = round(max(0.75, min(0.99, selfie_confidence)), 3)
                return {
                    "confidence": selfie_confidence,
                    "decision": "approved",
                    "status": "verified",
                    "doc_number": None,
                    "ocr_confidence": None,
                    "face_match_score": selfie_confidence,
                    "ocr_data": {},
                    "remarks": "Selfie verified successfully.",
                    "metadata": {
                        "face_provider": face_provider,
                        "selfie_used": True,
                        "face_detection": detect_result,
                        "mock": detect_result.get("mock", False),
                    },
                }

            return {
                "confidence": 0.0,
                "decision": fallback_decision,
                "status": fallback_status,
                "doc_number": None,
                "ocr_confidence": None,
                "face_match_score": 0.0,
                "ocr_data": {},
                "remarks": f"Selfie uploaded but face detection needs manual review: {detect_result.get('error', 'Face not clearly detected')}",
                "metadata": {
                    "face_provider": face_provider,
                    "selfie_used": True,
                    "face_detection": detect_result,
                    "mock": detect_result.get("mock", False),
                },
            }

        if face_only_mode and doc_type == DocumentTypeEnum.CNIC:
            face_provider = _resolve_face_provider(settings.VERIFICATION_FACE_PROVIDER)
            resolved_selfie_path = _resolve_document_path(selfie_path) if selfie_path else None

            if not resolved_selfie_path and user_id is not None:
                latest_selfie_path = await _find_latest_selfie_path(db, user_id)
                resolved_selfie_path = _resolve_document_path(latest_selfie_path)

            if not resolved_selfie_path:
                return {
                    "confidence": 0.0,
                    "decision": "flagged",
                    "status": "pending",
                    "doc_number": None,
                    "ocr_confidence": None,
                    "face_match_score": None,
                    "ocr_data": {},
                    "remarks": "CNIC uploaded. Waiting for selfie upload before face match.",
                    "metadata": {
                        "face_provider": face_provider,
                        "selfie_used": False,
                        "face_only_mode": face_only_mode,
                        "waiting_for_selfie": True,
                    },
                }

            try:
                face_adapter = _build_face_adapter(face_provider)
            except Exception as exc:
                logger.error("Failed to initialize face adapter (%s): %s", face_provider, exc)
                return {
                    "confidence": 0.0,
                    "decision": "rejected",
                    "status": "rejected",
                    "doc_number": None,
                    "ocr_confidence": None,
                    "face_match_score": None,
                    "ocr_data": {},
                    "remarks": f"Face service initialization failed: {str(exc)}",
                    "metadata": {
                        "face_provider": face_provider,
                        "selfie_used": True,
                        "face_only_mode": face_only_mode,
                    },
                }

            selfie_bytes = resolved_selfie_path.read_bytes()
            face_result = await face_adapter.match(selfie_bytes, document_bytes)
            face_score = _to_float(
                face_result.get("similarity"),
                _to_float(face_result.get("confidence"), 0.0),
            )
            score_confidence = round(max(0.0, min(1.0, face_score)), 3)
            face_threshold = max(0.0, min(1.0, float(settings.VERIFICATION_FACE_MATCH_THRESHOLD)))

            is_match = bool(face_result.get("success")) and (
                bool(face_result.get("match")) or face_score >= face_threshold
            )

            if is_match:
                return {
                    "confidence": score_confidence,
                    "decision": "approved",
                    "status": "verified",
                    "doc_number": None,
                    "ocr_confidence": None,
                    "face_match_score": score_confidence,
                    "ocr_data": {},
                    "remarks": "Face match successful. CNIC verified.",
                    "metadata": {
                        "face_provider": face_provider,
                        "selfie_used": True,
                        "face_only_mode": face_only_mode,
                        "face_result": face_result,
                        "mock": face_result.get("mock", False),
                    },
                }

            fail_reason = face_result.get("error") or "Selfie and CNIC face did not match."
            return {
                "confidence": score_confidence,
                "decision": "rejected",
                "status": "rejected",
                "doc_number": None,
                "ocr_confidence": None,
                "face_match_score": score_confidence,
                "ocr_data": {},
                "remarks": f"Face match failed: {fail_reason}",
                "metadata": {
                    "face_provider": face_provider,
                    "selfie_used": True,
                    "face_only_mode": face_only_mode,
                    "face_result": face_result,
                    "mock": face_result.get("mock", False),
                },
            }

        if face_only_mode and doc_type != DocumentTypeEnum.CNIC:
            return {
                "confidence": 0.0,
                "decision": "rejected",
                "status": "rejected",
                "doc_number": None,
                "ocr_confidence": None,
                "face_match_score": None,
                "ocr_data": {},
                "remarks": "Only CNIC and selfie uploads are enabled in face-only mode.",
                "metadata": {
                    "face_only_mode": face_only_mode,
                },
            }

        if _is_driver_role(resolved_user_role) and doc_type in {
            DocumentTypeEnum.CNIC,
            DocumentTypeEnum.DRIVING_LICENSE,
        }:
            # Driver flow uses two independent AWS Rekognition checks:
            # selfie<->CNIC and selfie<->driving license.
            face_provider = "aws"
            resolved_selfie_path = _resolve_document_path(selfie_path) if selfie_path else None

            if not resolved_selfie_path and user_id is not None:
                latest_selfie_path = await _find_latest_selfie_path(db, user_id)
                resolved_selfie_path = _resolve_document_path(latest_selfie_path)

            if not resolved_selfie_path:
                doc_label = "CNIC" if doc_type == DocumentTypeEnum.CNIC else "Driving License"
                return {
                    "confidence": 0.0,
                    "decision": "flagged",
                    "status": "pending",
                    "doc_number": None,
                    "ocr_confidence": None,
                    "face_match_score": None,
                    "ocr_data": {},
                    "remarks": f"{doc_label} uploaded. Waiting for selfie upload before face match.",
                    "metadata": {
                        "face_provider": face_provider,
                        "selfie_used": False,
                        "driver_dual_face_mode": True,
                        "waiting_for_selfie": True,
                        "target_document": doc_type.value,
                    },
                }

            try:
                face_adapter = _build_face_adapter(face_provider)
            except Exception as exc:
                logger.error("Failed to initialize AWS face adapter for driver flow: %s", exc)
                return {
                    "confidence": 0.0,
                    "decision": "rejected",
                    "status": "rejected",
                    "doc_number": None,
                    "ocr_confidence": None,
                    "face_match_score": None,
                    "ocr_data": {},
                    "remarks": f"Driver face service initialization failed: {str(exc)}",
                    "metadata": {
                        "face_provider": face_provider,
                        "selfie_used": True,
                        "driver_dual_face_mode": True,
                        "target_document": doc_type.value,
                    },
                }

            selfie_bytes = resolved_selfie_path.read_bytes()
            face_result = await face_adapter.match(selfie_bytes, document_bytes)
            face_score = _to_float(
                face_result.get("similarity"),
                _to_float(face_result.get("confidence"), 0.0),
            )
            score_confidence = round(max(0.0, min(1.0, face_score)), 3)
            face_threshold = max(0.0, min(1.0, float(settings.VERIFICATION_FACE_MATCH_THRESHOLD)))
            doc_label = "CNIC" if doc_type == DocumentTypeEnum.CNIC else "Driving License"

            is_match = bool(face_result.get("success")) and (
                bool(face_result.get("match")) or face_score >= face_threshold
            )

            if is_match:
                return {
                    "confidence": score_confidence,
                    "decision": "approved",
                    "status": "verified",
                    "doc_number": None,
                    "ocr_confidence": None,
                    "face_match_score": score_confidence,
                    "ocr_data": {},
                    "remarks": f"Driver face match successful for {doc_label}.",
                    "metadata": {
                        "face_provider": face_provider,
                        "selfie_used": True,
                        "driver_dual_face_mode": True,
                        "target_document": doc_type.value,
                        "face_result": face_result,
                        "mock": face_result.get("mock", False),
                    },
                }

            fail_reason = face_result.get("error") or "Selfie and document face did not match."
            return {
                "confidence": score_confidence,
                "decision": "rejected",
                "status": "rejected",
                "doc_number": None,
                "ocr_confidence": None,
                "face_match_score": score_confidence,
                "ocr_data": {},
                "remarks": f"Driver face match failed for {doc_label}: {fail_reason}",
                "metadata": {
                    "face_provider": face_provider,
                    "selfie_used": True,
                    "driver_dual_face_mode": True,
                    "target_document": doc_type.value,
                    "failure_document": doc_type.value,
                    "face_result": face_result,
                    "mock": face_result.get("mock", False),
                },
            }

        # OCR extraction using configured provider
        ocr_provider = _resolve_ocr_provider(settings.VERIFICATION_OCR_PROVIDER)
        try:
            ocr_adapter = get_ocr_adapter(
                ocr_provider,
                credentials_path=_resolve_google_ocr_credentials_path(),
                project_id=settings.GOOGLE_CLOUD_PROJECT,
            )
        except Exception as exc:
            logger.error("Failed to initialize OCR adapter (%s): %s", ocr_provider, exc)
            return {
                "confidence": 0.0,
                "decision": fallback_decision,
                "status": fallback_status,
                "doc_number": None,
                "ocr_confidence": 0.0,
                "face_match_score": None,
                "ocr_data": {},
                "remarks": f"OCR service initialization failed: {str(exc)}",
                "metadata": {
                    "ocr_provider": ocr_provider,
                    "selfie_used": False,
                },
            }

        ocr_result = await ocr_adapter.extract_text(document_bytes, doc_type.value)
        if not ocr_result.get("success"):
            return {
                "confidence": 0.0,
                "decision": fallback_decision,
                "status": fallback_status,
                "doc_number": None,
                "ocr_confidence": 0.0,
                "face_match_score": None,
                "ocr_data": {},
                "remarks": f"OCR extraction failed: {ocr_result.get('error') or 'Unknown OCR error'}",
                "metadata": {
                    "ocr_provider": ocr_provider,
                    "ocr_raw": ocr_result,
                    "selfie_used": False,
                    "mock": ocr_result.get("mock", False),
                },
            }

        ocr_confidence = ocr_result.get("confidence", 0.0)

        # Extract document number
        doc_number = extract_document_number(ocr_result, doc_type.value)

        # Profile cross-check: compare OCR values with user-entered identity fields
        identity_cross_check = {
            "status": "not_run",
            "checks": [],
            "mismatch_fields": [],
        }
        if user_id is not None:
            expected_identity = await _get_user_identity_snapshot(db, user_id)
            identity_cross_check = _build_identity_cross_check(
                document_type=doc_type.value,
                expected_identity=expected_identity,
                ocr_fields=ocr_result.get("fields", {}),
            )

        # Face matching (if applicable)
        face_match_score = None
        face_provider = _resolve_face_provider(settings.VERIFICATION_FACE_PROVIDER)
        selfie_used = False
        face_error = None

        if doc_type in [DocumentTypeEnum.CNIC, DocumentTypeEnum.DRIVING_LICENSE]:
            resolved_selfie_path = _resolve_document_path(selfie_path) if selfie_path else None

            if resolved_selfie_path:
                selfie_used = True
                selfie_bytes = resolved_selfie_path.read_bytes()

                try:
                    face_adapter = _build_face_adapter(face_provider)
                except Exception as exc:
                    logger.error("Failed to initialize face adapter (%s): %s", face_provider, exc)
                    face_error = str(exc)
                    face_match_score = None
                else:
                    face_result = await face_adapter.match(selfie_bytes, document_bytes)
                    if face_result.get("success"):
                        face_match_score = _to_float(
                            face_result.get("similarity"),
                            _to_float(face_result.get("confidence"), 0.0),
                        )
                    else:
                        face_error = face_result.get("error") or "Face match failed"
                        face_match_score = None
            else:
                if settings.VERIFICATION_REQUIRE_SELFIE_FOR_FACE_MATCH:
                    overall_confidence = round(max(0.0, min(0.99, ocr_confidence * 0.8)), 3)
                    return {
                        "confidence": overall_confidence,
                        "decision": fallback_decision,
                        "status": fallback_status,
                        "doc_number": doc_number,
                        "ocr_confidence": ocr_confidence,
                        "face_match_score": None,
                        "ocr_data": ocr_result.get("fields", {}),
                        "remarks": "Selfie not found for face comparison. Sent for manual review.",
                        "metadata": {
                            "ocr_text": ocr_result.get("text", ""),
                            "ocr_provider": ocr_provider,
                            "face_provider": face_provider,
                            "selfie_used": False,
                            "mock": ocr_result.get("mock", False),
                        },
                    }
                face_match_score = 0.85

        if doc_type in [DocumentTypeEnum.CNIC, DocumentTypeEnum.DRIVING_LICENSE] and face_match_score is None:
            overall_confidence = round(max(0.0, min(0.79, ocr_confidence * 0.85)), 3)
            return {
                "confidence": overall_confidence,
                "decision": fallback_decision,
                "status": fallback_status,
                "doc_number": doc_number,
                "ocr_confidence": ocr_confidence,
                "face_match_score": None,
                "ocr_data": ocr_result.get("fields", {}),
                "remarks": f"Document uploaded. Face verification pending manual review: {face_error or 'Face service unavailable'}",
                "metadata": {
                    "ocr_text": ocr_result.get("text", ""),
                    "ocr_provider": ocr_provider,
                    "face_provider": face_provider,
                    "selfie_used": selfie_used,
                    "identity_cross_check": identity_cross_check,
                    "face_error": face_error,
                    "mock": ocr_result.get("mock", False),
                },
            }

        # Determine decision using the rule engine
        decision_engine = get_decision_engine()
        face_required = doc_type in [DocumentTypeEnum.CNIC, DocumentTypeEnum.DRIVING_LICENSE]
        decision_enum, reason, overall_confidence = await decision_engine.evaluate(
            ocr_score=ocr_confidence,
            face_score=face_match_score if face_required else 1.0,
            document_type=doc_type.value,
            has_face=face_required,
        )

        if decision_enum.value == "approved":
            decision = "approved"
            status_str = "verified"
        elif decision_enum.value == "manual_review":
            if _is_manual_review_enabled():
                decision = "flagged"
                status_str = "under_review"
            else:
                decision = "rejected"
                status_str = "rejected"
                reason = f"{reason} Manual review is currently disabled."
        else:
            decision = "rejected"
            status_str = "rejected"

        remarks = reason
        if face_error:
            remarks = f"{remarks} (Face service warning: {face_error})"

        # Enforce profile-vs-OCR consistency rules
        identity_status = identity_cross_check.get("status")
        mismatch_fields = identity_cross_check.get("mismatch_fields", [])
        enforce_identity_match = bool(
            getattr(settings, "VERIFICATION_ENFORCE_PROFILE_OCR_MATCH", False)
        )

        if enforce_identity_match:
            if identity_status == "hard_fail":
                decision = "rejected"
                status_str = "rejected"
                overall_confidence = round(min(overall_confidence, 0.49), 3)
                remarks = (
                    f"{remarks} Identity mismatch with profile data for fields: "
                    f"{', '.join(mismatch_fields)}."
                )
            elif identity_status == "soft_fail" and decision != "rejected":
                if _is_manual_review_enabled():
                    decision = "flagged"
                    status_str = "under_review"
                    overall_confidence = round(min(overall_confidence, 0.74), 3)
                    remarks = (
                        f"{remarks} Profile comparison requires manual review for fields: "
                        f"{', '.join(mismatch_fields)}."
                    )
                else:
                    decision = "rejected"
                    status_str = "rejected"
                    overall_confidence = round(min(overall_confidence, 0.49), 3)
                    remarks = (
                        f"{remarks} Profile mismatch for fields: "
                        f"{', '.join(mismatch_fields)}."
                    )
        elif identity_status in {"hard_fail", "soft_fail"} and mismatch_fields:
            remarks = (
                f"{remarks} Profile data mismatch noted for fields: "
                f"{', '.join(mismatch_fields)}."
            )

        return {
            "confidence": overall_confidence,
            "decision": decision,
            "status": status_str,
            "doc_number": doc_number,
            "ocr_confidence": ocr_confidence,
            "face_match_score": face_match_score,
            "ocr_data": ocr_result.get("fields", {}),
            "remarks": remarks,
            "metadata": {
                "ocr_text": ocr_result.get("text", ""),
                "ocr_provider": ocr_provider,
                "face_provider": face_provider,
                "selfie_used": selfie_used,
                "identity_cross_check": identity_cross_check,
                "mock": ocr_result.get("mock", False),
            },
        }
        
    except Exception as e:
        logger.error(f"Error in AI verification: {str(e)}")
        return {
            "confidence": 0.0,
            "decision": "flagged",
            "status": "under_review",
            "doc_number": None,
            "remarks": f"AI verification pending manual review: {str(e)}",
            "metadata": {}
        }


async def delete_uploaded_document_service(
    db: AsyncSession,
    user_id: UUID,
    doc_type: DocumentTypeEnum,
    user_role: Optional[Any] = None,
    allow_driver_selfie_delete: bool = False,
) -> Dict[str, Any]:
    """
    Delete all uploaded verification records/files for one document type.

    This supports testing flows where users repeatedly upload/delete images.
    """
    try:
        resolved_user_role = (
            _normalize_user_role(user_role)
            if user_role is not None
            else await _get_user_role_for_user(db, user_id)
        )

        if (
            doc_type == DocumentTypeEnum.SELFIE
            and _is_driver_role(resolved_user_role)
            and not allow_driver_selfie_delete
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Driver selfie cannot be removed directly. "
                    "Use the Profile camera action to start selfie re-verification."
                ),
            )

        verifications = await crud.get_user_verifications(db, user_id, doc_type=doc_type)

        if not verifications:
            return {
                "status": "ok",
                "data": {
                    "doc_type": doc_type.value,
                    "deleted": False,
                    "deleted_count": 0,
                    "message": "No uploaded document found for this type.",
                },
                "error": None,
            }

        files_to_delete: List[Path] = []
        deleted_count = 0

        for verification in verifications:
            files_to_delete.extend(
                _collect_verification_file_paths(verification.doc_path, verification.meta_data)
            )
            if await crud.delete_verification(db, verification.id):
                deleted_count += 1

        if deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete uploaded document",
            )

        for path_obj in files_to_delete:
            _delete_file_if_exists(path_obj)

        await _demote_driver_verification_on_document_delete(
            db=db,
            user_id=user_id,
            doc_type=doc_type,
        )

        return {
            "status": "ok",
            "data": {
                "doc_type": doc_type.value,
                "deleted": True,
                "deleted_count": deleted_count,
                "message": "Uploaded document deleted successfully.",
            },
            "error": None,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error deleting uploaded document for user %s, type %s: %s", user_id, doc_type.value, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete uploaded document",
        )


async def start_driver_selfie_reverification_service(
    db: AsyncSession,
    user_id: UUID,
    user_role: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Start driver selfie re-verification.

    Flow:
    1. Delete current selfie verification record(s) and files.
    2. Demote driver to unverified/pending state.
    3. Ask driver to upload a new selfie in Verification screen.
    """
    resolved_user_role = (
        _normalize_user_role(user_role)
        if user_role is not None
        else await _get_user_role_for_user(db, user_id)
    )

    if not _is_driver_role(resolved_user_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Selfie re-verification intent is available for driver accounts only.",
        )

    deletion_result = await delete_uploaded_document_service(
        db=db,
        user_id=user_id,
        doc_type=DocumentTypeEnum.SELFIE,
        user_role=resolved_user_role,
        allow_driver_selfie_delete=True,
    )

    payload = deletion_result.get("data") if isinstance(deletion_result, dict) else {}
    deleted = bool((payload or {}).get("deleted", False))
    deleted_count = int((payload or {}).get("deleted_count") or 0)

    if not deleted:
        # Even if no selfie record exists, force driver into pending state to
        # ensure the next selfie upload goes through full verification flow.
        await _demote_driver_verification_on_document_delete(
            db=db,
            user_id=user_id,
            doc_type=DocumentTypeEnum.SELFIE,
        )

    return {
        "status": "ok",
        "data": {
            "deleted_selfie": deleted,
            "deleted_count": deleted_count,
            "message": (
                "Selfie re-verification started. Upload a new selfie in Verification to become verified again."
            ),
        },
        "error": None,
    }


async def _demote_driver_verification_on_document_delete(
    db: AsyncSession,
    user_id: UUID,
    doc_type: DocumentTypeEnum,
) -> None:
    """Force driver profile back to unverified after any document removal."""
    try:
        from app.modules.drivers import crud as driver_crud

        driver = await driver_crud.get_driver_profile(db, user_id)
        if not driver:
            return

        touched = False

        if doc_type == DocumentTypeEnum.CNIC and getattr(driver, "cnic_verified", False):
            driver.cnic_verified = False
            touched = True

        status_value = str(getattr(driver, "status", "") or "").strip().lower()
        if getattr(driver, "is_verified", False):
            driver.is_verified = False
            touched = True
        if status_value in {"", "active", "verified"}:
            driver.status = "pending"
            touched = True

        if touched:
            await db.commit()
            await db.refresh(driver)
            logger.info(
                "Driver demoted after document delete for user %s (doc_type=%s)",
                user_id,
                doc_type.value,
            )
    except Exception as exc:
        await db.rollback()
        logger.warning(
            "Could not demote driver after document delete for user %s: %s",
            user_id,
            exc,
        )


async def verify_identity_data_service(
    db: AsyncSession,
    user_id: UUID,
    doc_type: DocumentTypeEnum,
    user_role: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Run on-demand Google OCR identity-data match for driver verification.

    Uses already uploaded document image as OCR input and compares the extracted
    document number against the number stored in profile/personal info.
    """
    try:
        resolved_user_role = (
            _normalize_user_role(user_role)
            if user_role is not None
            else await _get_user_role_for_user(db, user_id)
        )

        is_driver_user = _is_driver_role(resolved_user_role)
        allowed_doc_types = (
            {DocumentTypeEnum.CNIC, DocumentTypeEnum.DRIVING_LICENSE}
            if is_driver_user
            else {DocumentTypeEnum.CNIC}
        )

        if doc_type not in allowed_doc_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Identity Data Verification supports only CNIC and Driving License."
                    if is_driver_user
                    else "Identity Data Verification supports CNIC only for passenger dashboard."
                ),
            )

        profile_field = (
            "cnic_number" if doc_type == DocumentTypeEnum.CNIC else "license_number"
        )
        verification_step = (
            "cnic_number_match"
            if doc_type == DocumentTypeEnum.CNIC
            else "driving_license_number_match"
        )

        source_verification: Optional[Any] = None

        async def _build_identity_response(
            *,
            check_status: str,
            match: bool,
            reason: str,
            message: str,
            profile_number: str,
            extracted_number: str,
            ocr_confidence: float,
            ocr_provider: str,
            document_path: Optional[str],
            fields: Dict[str, Any],
            detected_document_type: Optional[str] = None,
        ) -> Dict[str, Any]:
            payload: Dict[str, Any] = {
                "document_type": doc_type.value,
                "verification_step": verification_step,
                "check_status": check_status,
                "match": match,
                "reason": reason,
                "message": message,
                "profile_number": profile_number,
                "extracted_number": extracted_number,
                "ocr_confidence": _to_float(ocr_confidence, 0.0),
                "ocr_provider": ocr_provider,
                "document_path": document_path,
                "fields": fields if isinstance(fields, dict) else {},
            }

            if detected_document_type:
                payload["detected_document_type"] = detected_document_type

            if source_verification is not None:
                await _persist_identity_data_result(db, source_verification, payload)

            return {
                "status": "ok",
                "data": payload,
                "error": None,
            }

        verifications = await crud.get_user_verifications(db, user_id, doc_type=doc_type)

        source_doc_abs_path: Optional[Path] = None
        for verification in verifications:
            resolved = _resolve_document_path(verification.doc_path)
            if resolved:
                source_verification = verification
                source_doc_abs_path = resolved
                break

        if source_verification is None or source_doc_abs_path is None:
            return await _build_identity_response(
                check_status="failed",
                match=False,
                reason="document_not_uploaded",
                message=f"Please upload {_doc_label_from_type(doc_type)} first.",
                profile_number="",
                extracted_number="",
                ocr_confidence=0.0,
                ocr_provider="google",
                document_path=None,
                fields={},
            )

        expected_identity = await _get_user_identity_snapshot(db, user_id)
        expected_number = _first_non_empty(expected_identity.get(profile_field, ""))

        if not expected_number:
            return await _build_identity_response(
                check_status="failed",
                match=False,
                reason="profile_number_missing",
                message=(
                    f"No {_doc_label_from_type(doc_type)} number found in Personal Info. "
                    "Please update your profile first."
                ),
                profile_number="",
                extracted_number="",
                ocr_confidence=0.0,
                ocr_provider="google",
                document_path=source_verification.doc_path,
                fields={},
            )

        document_bytes = source_doc_abs_path.read_bytes()
        ocr_provider = _resolve_ocr_provider("google")

        try:
            ocr_adapter = get_ocr_adapter(
                ocr_provider,
                credentials_path=_resolve_google_ocr_credentials_path(),
                project_id=settings.GOOGLE_CLOUD_PROJECT,
            )
        except Exception as exc:
            logger.error("Failed to initialize OCR adapter for identity verification: %s", exc)
            return await _build_identity_response(
                check_status="failed",
                match=False,
                reason="ocr_service_unavailable",
                message=f"Identity Data Verification OCR service is unavailable: {str(exc)}",
                profile_number=expected_number,
                extracted_number="",
                ocr_confidence=0.0,
                ocr_provider=ocr_provider,
                document_path=source_verification.doc_path,
                fields={},
            )

        ocr_result = await ocr_adapter.extract_text(document_bytes, doc_type.value)
        if not ocr_result.get("success"):
            ocr_error_message = str(ocr_result.get("error") or "").strip()
            image_width, image_height = _extract_image_dimensions(document_bytes)
            failed_extracted_number = _first_non_empty(
                _extract_identity_display_number(
                    ocr_result,
                    doc_type,
                    profile_field,
                    include_preview=False,
                ),
                _extract_by_profile_template(ocr_result, expected_number),
            )
            failed_extracted_number = _format_identity_display_number(
                doc_type,
                failed_extracted_number,
            )
            failed_extracted_number = _align_with_profile_format(
                failed_extracted_number,
                expected_number,
            )
            if _is_ocr_service_failure(ocr_error_message):
                response_message = (
                    "Google OCR is temporarily unavailable. "
                    "Please try again in a few minutes."
                )
                reason = "ocr_service_unavailable"
            elif (
                not ocr_error_message
                and image_width > 0
                and image_height > 0
                and (image_width < 500 or image_height < 300)
            ):
                response_message = (
                    f"Uploaded {_doc_label_from_type(doc_type)} image is too small/cropped for OCR. "
                    "Please upload a full, clear photo of the original document (not a screenshot card)."
                )
                reason = "document_image_too_small"
            else:
                response_message = (
                    f"Google OCR could not read {_doc_label_from_type(doc_type)}. "
                    "Please re-upload a clearer image."
                )
                reason = "ocr_extraction_failed"

            return await _build_identity_response(
                check_status="failed",
                match=False,
                reason=reason,
                message=response_message,
                profile_number=expected_number,
                extracted_number=failed_extracted_number,
                ocr_confidence=_to_float(ocr_result.get("confidence"), 0.0),
                ocr_provider=ocr_provider,
                document_path=source_verification.doc_path,
                fields=ocr_result.get("fields", {}),
            )

        expected_doc_type = (
            "cnic" if doc_type == DocumentTypeEnum.CNIC else "driving_license"
        )
        detected_doc_type = _detect_identity_document_type(ocr_result)
        if detected_doc_type != "unknown" and detected_doc_type != expected_doc_type:
            mismatch_extracted_number = _first_non_empty(
                _extract_identity_display_number(
                    ocr_result,
                    doc_type,
                    profile_field,
                    include_preview=False,
                ),
                _extract_by_profile_template(ocr_result, expected_number),
            )
            mismatch_extracted_number = _format_identity_display_number(
                doc_type,
                mismatch_extracted_number,
            )
            mismatch_extracted_number = _align_with_profile_format(
                mismatch_extracted_number,
                expected_number,
            )
            expected_label = _doc_label_from_type(doc_type)
            detected_label = "CNIC" if detected_doc_type == "cnic" else "Driving License"

            return await _build_identity_response(
                check_status="failed",
                match=False,
                reason="document_type_mismatch",
                message=(
                    f"Uploaded document appears to be {detected_label}, not {expected_label}. "
                    f"Please upload a valid {expected_label} image for this step."
                ),
                profile_number=expected_number,
                extracted_number=mismatch_extracted_number,
                ocr_confidence=_to_float(ocr_result.get("confidence"), 0.0),
                ocr_provider=ocr_provider,
                document_path=source_verification.doc_path,
                fields=ocr_result.get("fields", {}),
                detected_document_type=detected_doc_type,
            )

        strict_extracted_number = _first_non_empty(
            extract_document_number(ocr_result, doc_type.value),
            str((ocr_result.get("fields") or {}).get(profile_field) or ""),
            _extract_by_profile_template(ocr_result, expected_number),
            _extract_identity_display_number(
                ocr_result,
                doc_type,
                profile_field,
                include_preview=False,
            ),
        )
        display_extracted_number = strict_extracted_number
        display_extracted_number = _format_identity_display_number(
            doc_type,
            display_extracted_number,
        )
        display_extracted_number = _align_with_profile_format(
            display_extracted_number,
            expected_number,
        )

        normalized_expected = _normalize_identifier(expected_number)
        normalized_extracted = _normalize_identifier(strict_extracted_number)
        is_match = bool(normalized_expected and normalized_extracted and normalized_expected == normalized_extracted)

        if is_match:
            message = (
                f"{_doc_label_from_type(doc_type)} number matches Personal Info successfully."
            )
            reason = "match"
            check_status = "passed"
        elif not normalized_extracted:
            message = (
                f"Google OCR did not find a valid {_doc_label_from_type(doc_type)} number. "
                "Please re-upload a clearer image."
            )
            reason = "number_not_found"
            check_status = "failed"
        else:
            message = (
                f"{_doc_label_from_type(doc_type)} number does not match Personal Info."
            )
            reason = "mismatch_with_profile"
            check_status = "failed"

        return await _build_identity_response(
            check_status=check_status,
            match=is_match,
            reason=reason,
            message=message,
            profile_number=expected_number,
            extracted_number=display_extracted_number,
            ocr_confidence=_to_float(ocr_result.get("confidence"), 0.0),
            ocr_provider=ocr_provider,
            document_path=source_verification.doc_path,
            fields=ocr_result.get("fields", {}),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error in identity data verification for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to run Identity Data Verification",
        )


def _doc_label_from_type(doc_type: DocumentTypeEnum) -> str:
    if doc_type == DocumentTypeEnum.CNIC:
        return "CNIC"
    if doc_type == DocumentTypeEnum.DRIVING_LICENSE:
        return "Driving License"
    return doc_type.value.replace("_", " ").title()


async def get_verification_status_service(
    db: AsyncSession,
    user_id: UUID,
    user_role: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Get verification status for user.
    
    Returns status of all document verifications.
    
    Args:
        db: Database session
        user_id: User ID
    
    Returns:
        Dictionary with verification status
    """
    try:
        resolved_user_role = (
            _normalize_user_role(user_role)
            if user_role is not None
            else await _get_user_role_for_user(db, user_id)
        )

        verifications = await crud.get_user_verifications(db, user_id)

        # Newest-first query: keep first status and created_at per document type.
        actual_status_map: Dict[str, str] = {}
        raw_status_map: Dict[str, str] = {}
        latest_created_at_map: Dict[str, datetime] = {}
        latest_doc_path_map: Dict[str, Optional[str]] = {}
        latest_verification_map: Dict[str, Any] = {}
        for verification in verifications:
            doc_key = verification.doc_type.value
            raw_status = str(verification.status.value)
            raw_status_map.setdefault(doc_key, raw_status)
            actual_status_map.setdefault(doc_key, _normalize_public_verification_status(raw_status))
            latest_created_at_map.setdefault(doc_key, verification.created_at)
            latest_doc_path_map.setdefault(doc_key, verification.doc_path)
            latest_verification_map.setdefault(doc_key, verification)

        required_docs = _get_required_verification_docs_for_role(resolved_user_role)
        missing_docs = [doc for doc in required_docs if doc not in actual_status_map]
        all_required_uploaded = len(missing_docs) == 0

        latest_required_upload_at: Optional[datetime] = None
        if all_required_uploaded:
            required_created_at = [
                latest_created_at_map.get(doc)
                for doc in required_docs
                if latest_created_at_map.get(doc) is not None
            ]
            if required_created_at:
                latest_required_upload_at = max(required_created_at)

        status_delay_seconds = max(0, int(getattr(settings, "VERIFICATION_RESULT_DELAY_SECONDS", 30)))
        analysis_ready_in_seconds = 0
        if latest_required_upload_at is not None and status_delay_seconds > 0:
            # Normalize to UTC-aware datetimes to avoid naive/aware subtraction errors.
            upload_time_utc = latest_required_upload_at
            if upload_time_utc.tzinfo is None:
                upload_time_utc = upload_time_utc.replace(tzinfo=timezone.utc)
            else:
                upload_time_utc = upload_time_utc.astimezone(timezone.utc)

            elapsed_seconds = (datetime.now(timezone.utc) - upload_time_utc).total_seconds()
            remaining_seconds = status_delay_seconds - elapsed_seconds
            analysis_ready_in_seconds = max(0, int(math.ceil(remaining_seconds)))

        if not all_required_uploaded:
            uploaded_required_docs = [
                doc for doc in required_docs if doc in actual_status_map
            ]
            status_map = {
                doc: ("processing" if doc in uploaded_required_docs else "not_uploaded")
                for doc in required_docs
            }
            # If nothing required is uploaded, show a clean "not submitted" state.
            overall_status = "processing" if uploaded_required_docs else "not_uploaded"
            overall_verified = False
        elif analysis_ready_in_seconds > 0:
            # Hold final status briefly to avoid instant rejection/approval flash.
            status_map = {doc: "processing" for doc in required_docs}
            overall_status = "processing"
            overall_verified = False
        else:
            status_map = {doc: actual_status_map.get(doc, "not_uploaded") for doc in required_docs}
            if _requires_binary_final_decision_for_role(resolved_user_role):
                decision_docs = required_docs
                if _is_driver_role(resolved_user_role):
                    # Driver final decision is based strictly on two AWS outputs:
                    # selfie<->CNIC and selfie<->driving license.
                    decision_docs = [
                        DocumentTypeEnum.CNIC.value,
                        DocumentTypeEnum.DRIVING_LICENSE.value,
                    ]

                for doc in decision_docs:
                    status_map[doc] = (
                        "verified" if status_map.get(doc) == "verified" else "rejected"
                    )

                overall_verified = all(status_map.get(doc) == "verified" for doc in decision_docs)
                overall_status = "verified" if overall_verified else "rejected"
            else:
                overall_verified = all(status_map.get(doc) == "verified" for doc in required_docs)

                if overall_verified:
                    overall_status = "verified"
                elif any(status_map.get(doc) == "rejected" for doc in required_docs):
                    overall_status = "rejected"
                elif any(status_map.get(doc) in {"pending", "under_review", "processing", "in_review"} for doc in required_docs):
                    overall_status = "under_review"
                else:
                    overall_status = "processing"

        identity_required_docs: List[str] = []
        if _is_driver_role(resolved_user_role):
            identity_required_docs = [
                DocumentTypeEnum.CNIC.value,
                DocumentTypeEnum.DRIVING_LICENSE.value,
            ]
        elif DocumentTypeEnum.CNIC.value in required_docs:
            identity_required_docs = [DocumentTypeEnum.CNIC.value]

        identity_status_map: Dict[str, str] = {}
        identity_reason_map: Dict[str, str] = {}
        identity_checked_at_map: Dict[str, Optional[str]] = {}
        for doc in identity_required_docs:
            snapshot = _extract_identity_check_snapshot(latest_verification_map.get(doc))
            identity_status_map[doc] = str(snapshot.get("check_status") or "not_run")
            identity_reason_map[doc] = str(snapshot.get("reason") or "identity_check_not_run")
            identity_checked_at_map[doc] = snapshot.get("checked_at")

        identity_failed_documents = [
            doc for doc in identity_required_docs
            if identity_status_map.get(doc) == "failed"
        ]
        identity_pending_documents = [
            doc for doc in identity_required_docs
            if identity_status_map.get(doc) not in {"passed", "failed"}
        ]
        identity_overall_verified = bool(identity_required_docs) and all(
            identity_status_map.get(doc) == "passed"
            for doc in identity_required_docs
        )

        if not identity_required_docs:
            identity_overall_status = "not_required"
        elif identity_overall_verified:
            identity_overall_status = "verified"
        elif identity_failed_documents:
            identity_overall_status = "rejected"
        elif all(identity_status_map.get(doc) == "not_uploaded" for doc in identity_required_docs):
            identity_overall_status = "not_uploaded"
        else:
            identity_overall_status = "under_review"

        if (
            _is_driver_role(resolved_user_role)
            and all_required_uploaded
            and analysis_ready_in_seconds == 0
        ):
            driver_decision_docs = [
                DocumentTypeEnum.CNIC.value,
                DocumentTypeEnum.DRIVING_LICENSE.value,
            ]
            face_verified = all(status_map.get(doc) == "verified" for doc in driver_decision_docs)
            identity_verified_for_driver = all(
                identity_status_map.get(doc) == "passed"
                for doc in driver_decision_docs
            )

            overall_verified = face_verified and identity_verified_for_driver
            if overall_verified:
                overall_status = "verified"
            elif not face_verified:
                overall_status = "rejected"
            elif any(identity_status_map.get(doc) == "failed" for doc in driver_decision_docs):
                overall_status = "rejected"
            else:
                overall_status = "under_review"

        failed_documents = [doc for doc in required_docs if status_map.get(doc) == "rejected"]
        if _is_driver_role(resolved_user_role):
            for doc in identity_failed_documents:
                if doc not in failed_documents:
                    failed_documents.append(doc)

        driver_failed_documents: List[str] = []
        driver_failed_identity_documents: List[str] = []
        if _is_driver_role(resolved_user_role):
            driver_face_docs = [
                DocumentTypeEnum.CNIC.value,
                DocumentTypeEnum.DRIVING_LICENSE.value,
            ]
            rejected_driver_face_docs = [
                doc for doc in driver_face_docs
                if status_map.get(doc) == "rejected"
            ]

            # If both selfie-to-document face checks fail, treat selfie as the root issue.
            if len(rejected_driver_face_docs) == len(driver_face_docs):
                driver_failed_documents = [DocumentTypeEnum.SELFIE.value]
            else:
                driver_failed_documents = rejected_driver_face_docs

            driver_failed_identity_documents = [
                doc for doc in driver_face_docs
                if identity_status_map.get(doc) == "failed"
            ]

        if _is_driver_role(resolved_user_role) and overall_verified:
            selfie_doc = DocumentTypeEnum.SELFIE.value
            selfie_status = status_map.get(selfie_doc)
            selfie_doc_path = latest_doc_path_map.get(selfie_doc)
            if selfie_status == "verified" and selfie_doc_path:
                await _sync_driver_profile_photo_from_verified_selfie(
                    db=db,
                    user_id=user_id,
                    selfie_doc_path=selfie_doc_path,
                )

        return {
            "status": "ok",
            "data": {
                "user_id": str(user_id),
                "verifications": status_map,
                "raw_verifications": raw_status_map,
                "required_documents": required_docs,
                "overall_status": overall_status,
                "overall_verified": overall_verified,
                "missing_documents": missing_docs,
                "latest_document_paths": {
                    doc: latest_doc_path_map.get(doc)
                    for doc in required_docs
                },
                "failed_documents": failed_documents,
                "driver_failed_documents": driver_failed_documents,
                "driver_failed_identity_documents": driver_failed_identity_documents,
                "identity_data_verification": {
                    "required_documents": identity_required_docs,
                    "status_by_document": identity_status_map,
                    "reason_by_document": identity_reason_map,
                    "last_checked_at_by_document": identity_checked_at_map,
                    "failed_documents": identity_failed_documents,
                    "pending_documents": identity_pending_documents,
                    "overall_status": identity_overall_status,
                    "overall_verified": identity_overall_verified,
                },
                "analysis_ready_in_seconds": analysis_ready_in_seconds,
                "last_upload_at": latest_required_upload_at.isoformat() if latest_required_upload_at else None,
                "mode": {
                    "face_only": _is_face_only_mode_for_role(resolved_user_role),
                    "user_role": resolved_user_role,
                    "driver_dual_face_match": _is_driver_role(resolved_user_role),
                    "manual_review_enabled": _is_manual_review_enabled(),
                    "allow_reupload_always": bool(getattr(settings, "VERIFICATION_ALLOW_REUPLOAD_ALWAYS", False)),
                },
            },
            "error": None
        }
        
    except Exception as e:
        logger.error(f"Error fetching verification status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch verification status"
        )


async def admin_review_verification_service(
    db: AsyncSession,
    verification_id: UUID,
    admin_user_id: UUID,
    decision: str,
    remarks: Optional[str] = None
) -> Dict[str, Any]:
    """
    Admin manual review of verification.
    
    Args:
        db: Database session
        verification_id: Verification ID
        admin_user_id: Admin user ID
        decision: "approved" or "rejected"
        remarks: Admin review notes
    
    Returns:
        Dictionary with updated verification
    """
    try:
        # Validate decision
        if decision not in ["approved", "rejected"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid decision. Must be 'approved' or 'rejected'"
            )
        
        # Get verification
        verification = await crud.get_verification_by_id(db, verification_id)
        
        if not verification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification not found"
            )
        
        # Update status
        new_status = VerificationStatusEnum.VERIFIED if decision == "approved" else VerificationStatusEnum.REJECTED
        
        updated = await crud.update_verification_status(
            db=db,
            verification_id=verification_id,
            new_status=new_status,
            admin_remarks=remarks,
            reviewed_by=admin_user_id
        )
        
        # Create verification attempt
        await crud.create_verification_attempt(
            db=db,
            verification_id=verification_id,
            attempt_type="admin_review",
            decision=decision,
            remarks=remarks or f"Admin {decision} verification",
            reviewed_by=admin_user_id
        )
        
        logger.info(f"Admin {admin_user_id} {decision} verification {verification_id}")
        
        return {
            "status": "ok",
            "data": {
                "verification_id": str(verification_id),
                "decision": decision,
                "status": updated.status.value,
                "reviewed_by": str(admin_user_id),
                "message": f"Verification {decision} successfully"
            },
            "error": None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in admin review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process admin review"
        )


async def trigger_ai_verification_service(
    db: AsyncSession,
    verification_id: UUID,
    force_reprocess: bool = False
) -> Dict[str, Any]:
    """
    Manually trigger AI verification (test mode).
    
    Args:
        db: Database session
        verification_id: Verification ID
        force_reprocess: Force reprocessing even if already analyzed
    
    Returns:
        Dictionary with AI analysis results
    """
    try:
        # Get verification
        verification = await crud.get_verification_by_id(db, verification_id)
        
        if not verification:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Verification not found"
            )
        
        # Check if already verified
        if verification.status == VerificationStatusEnum.VERIFIED and not force_reprocess:
            return {
                "status": "ok",
                "data": {
                    "message": "Verification already completed",
                    "verification_id": str(verification_id),
                    "status": verification.status.value,
                    "confidence": verification.ai_confidence
                },
                "error": None
            }
        
        # Perform AI verification
        ai_result = await perform_ai_verification_service(
            db=db,
            file_path=verification.doc_path,
            doc_type=verification.doc_type,
            user_id=verification.user_id,
        )
        
        # Update verification
        new_status = VerificationStatusEnum(ai_result.get("status"))
        updated = await crud.update_verification_status(
            db=db,
            verification_id=verification_id,
            new_status=new_status
        )
        
        # Update AI confidence and remarks
        updated.ai_confidence = ai_result.get("confidence")
        updated.ai_remarks = ai_result.get("remarks")
        updated.doc_number = ai_result.get("doc_number")
        await db.commit()
        
        # Create verification attempt
        await crud.create_verification_attempt(
            db=db,
            verification_id=verification_id,
            attempt_type="ai_analysis",
            decision=ai_result.get("decision"),
            ai_score=ai_result.get("confidence"),
            face_match_score=ai_result.get("face_match_score"),
            remarks=ai_result.get("remarks"),
            ocr_data=json.dumps(ai_result.get("ocr_data", {}))
        )
        
        return {
            "status": "ok",
            "data": {
                "verification_id": str(verification_id),
                "decision": ai_result.get("decision"),
                "confidence": ai_result.get("confidence"),
                "ocr_confidence": ai_result.get("ocr_confidence"),
                "face_match_score": ai_result.get("face_match_score"),
                "extracted_data": ai_result.get("ocr_data"),
                "remarks": ai_result.get("remarks")
            },
            "error": None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering AI verification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger AI verification"
        )


async def process_verification(
    db: AsyncSession,
    user_id: UUID,
    document_file: UploadFile,
    document_back_file: Optional[UploadFile],
    selfie_file: Optional[UploadFile],
    document_type: str
) -> Dict[str, Any]:
    """
    Orchestration function for complete verification workflow using new adapters.
    
    This function implements the full Prompt 4 specification:
    1. Validate and save uploaded files
    2. Extract text using OCR adapter
    3. Perform face matching using face match adapter
    4. Run decision engine for auto-approval
    5. Save verification record
    6. Log audit events
    7. Create admin flag if manual review needed
    
    Args:
        db: Database session
        user_id: User ID
        document_file: Primary document image (front)
        document_back_file: Back of document (optional)
        selfie_file: User selfie for face matching (optional)
        document_type: Type of document (cnic, license, vehicle_registration)
    
    Returns:
        Dictionary with verification results including status, scores, and decision
    
    Raises:
        HTTPException: If validation fails or processing error occurs
    """
    try:
        # Compatibility wrapper: route all processing through the active upload flow.
        try:
            doc_type_enum = DocumentTypeEnum(document_type.strip().lower())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported document type: {document_type}"
            ) from exc

        upload_result = await upload_document_service(
            db=db,
            user_id=user_id,
            doc_type=doc_type_enum,
            file=document_file,
            document_back_file=document_back_file,
            selfie_file=selfie_file,
        )

        data = upload_result.get("data", {})
        verification_id = data.get("verification_id")

        ocr_fields: Dict[str, Any] = {}
        face_match_score = None
        if verification_id:
            try:
                attempts = await crud.get_verification_attempts(db, UUID(str(verification_id)))
                if attempts:
                    latest_attempt = attempts[0]
                    face_match_score = latest_attempt.face_match_score
                    if latest_attempt.ocr_data:
                        ocr_fields = json.loads(latest_attempt.ocr_data)
            except Exception as exc:
                logger.warning("Could not enrich process_verification response: %s", exc)

        return {
            "status": data.get("status", "under_review"),
            "confidence_score": _to_float(data.get("ai_confidence"), 0.0),
            "face_match_score": face_match_score,
            "ocr_fields": ocr_fields,
            "message": data.get("message", "Verification processed"),
            "verification_id": verification_id,
            "decision": data.get("decision", "flagged"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing verification: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification processing failed: {str(e)}"
        )

# === VERIFICATION FUNCTIONALITY END ===
