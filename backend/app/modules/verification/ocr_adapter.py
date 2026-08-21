"""
OCR Adapter - Pluggable Interface for Text Extraction

Purpose: Provides a pluggable interface for OCR services with mock implementation.
         Can be replaced with real OCR APIs (Google Vision, AWS Textract, Azure Computer Vision).

Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: December 7, 2025
"""

# === VERIFICATION FUNCTIONALITY START ===
from abc import ABC, abstractmethod
from typing import Dict, List, Any
import secrets
import asyncio
import logging
import re
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)


def _search_regex(pattern: str, text: str, group: int = 0) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return ""
    return (match.group(group) or "").strip()


def _extract_cnic_fields_from_text(text: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}

    cnic = _search_regex(r"\b\d{5}-\d{7}-\d\b", text)
    if not cnic:
        cnic = _search_regex(r"\b\d{13}\b", text)
        if cnic and len(cnic) == 13:
            cnic = f"{cnic[:5]}-{cnic[5:12]}-{cnic[12]}"
    if cnic:
        fields["cnic_number"] = cnic

    name = _search_regex(r"(?:Name|Name\s*[:\-])\s*([A-Za-z][A-Za-z\s]{2,50})", text, group=1)
    if name:
        fields["name"] = " ".join(name.split())

    dob = _search_regex(r"(?:Birth|DOB|Date\s*of\s*Birth)\s*[:\-]?\s*(\d{2}[\-/]\d{2}[\-/]\d{4})", text, group=1)
    if dob:
        fields["dob"] = dob

    expiry = _search_regex(r"(?:Expiry|Valid\s*Till|Date\s*of\s*Expiry)\s*[:\-]?\s*(\d{2}[\-/]\d{2}[\-/]\d{4})", text, group=1)
    if expiry:
        fields["expiry_date"] = expiry

    return fields


def _extract_license_fields_from_text(text: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}

    def _normalize_license_number(raw_value: str) -> str:
        compact = re.sub(r"[^A-Z0-9]", "", str(raw_value or "").upper())
        if not compact:
            return ""

        mixed = re.fullmatch(r"([A-Z]{2,5})(\d{3,6})([A-Z]{1,4})(\d{2,6})", compact)
        if mixed:
            return f"{mixed.group(1)}-{mixed.group(2)}{mixed.group(3)}{mixed.group(4)}"

        prefixed = re.fullmatch(r"(\d{1,4})([A-Z]{1,4})(\d{2,10})", compact)
        if prefixed:
            return f"{prefixed.group(1)}-{prefixed.group(2)}-{prefixed.group(3)}"

        suffix = re.fullmatch(r"([A-Z]{2,5})(\d{4,10})", compact)
        if suffix:
            return f"{suffix.group(1)}-{suffix.group(2)}"

        return ""

    labeled_match = re.search(
        r"(?:License\s*(?:No|Number)?|DL\s*No)\s*[:\-]?\s*"
        r"((?:[A-Z]{2,5}[-\s]?\d{3,6}[-\s]?[A-Z]{1,4}[-\s]?\d{2,6})|"
        r"(?:\d{1,4}[-\s]?[A-Z]{1,4}[-\s]?\d{2,10})|"
        r"(?:[A-Z]{2,5}[-\s]?\d{4,10}))\b",
        text,
        flags=re.IGNORECASE,
    )
    license_no = labeled_match.group(1) if labeled_match else ""

    if not license_no:
        mixed_match = re.search(
            r"\b([A-Z]{2,5})[-\s]?(\d{3,6})[-\s]?([A-Z]{1,4})[-\s]?(\d{2,6})\b",
            text,
            flags=re.IGNORECASE,
        )
        if mixed_match:
            license_no = (
                f"{mixed_match.group(1).upper()}-"
                f"{mixed_match.group(2)}"
                f"{mixed_match.group(3).upper()}"
                f"{mixed_match.group(4)}"
            )

    if not license_no:
        prefixed_match = re.search(
            r"\b(\d{1,4})[-\s]?([A-Z]{1,4})[-\s]?(\d{2,10})\b",
            text,
            flags=re.IGNORECASE,
        )
        if prefixed_match:
            license_no = (
                f"{prefixed_match.group(1)}-"
                f"{prefixed_match.group(2).upper()}-"
                f"{prefixed_match.group(3)}"
            )

    if not license_no:
        suffix_match = re.search(r"\b([A-Z]{2,5})[-\s]?(\d{4,10})\b", text, flags=re.IGNORECASE)
        if suffix_match:
            license_no = f"{suffix_match.group(1).upper()}-{suffix_match.group(2)}"

    license_no = _normalize_license_number(license_no)
    if license_no:
        fields["license_number"] = license_no

    name = _search_regex(r"(?:Name|Driver\s*Name)\s*[:\-]?\s*([A-Za-z][A-Za-z\s]{2,50})", text, group=1)
    if name:
        fields["name"] = " ".join(name.split())

    expiry = _search_regex(r"(?:Valid\s*Till|Expiry|Expires)\s*[:\-]?\s*(\d{2}[\-/]\d{2}[\-/]\d{4})", text, group=1)
    if expiry:
        fields["expiry_date"] = expiry

    return fields


def _extract_vehicle_fields_from_text(text: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}

    reg_no = _search_regex(r"(?:Registration\s*(?:No|Number)?|Reg\s*No)\s*[:\-]?\s*([A-Z0-9\-]{5,20})", text, group=1)
    if not reg_no:
        reg_no = _search_regex(r"\b[A-Z]{2,4}[-\s]?\d{3,4}\b", text)
    if reg_no:
        fields["registration_number"] = reg_no.replace(" ", "-")

    engine_no = _search_regex(r"(?:Engine\s*(?:No|Number)?)\s*[:\-]?\s*([A-Z0-9\-]{5,25})", text, group=1)
    if engine_no:
        fields["engine_number"] = engine_no

    chassis_no = _search_regex(r"(?:Chassis\s*(?:No|Number)?|VIN)\s*[:\-]?\s*([A-Z0-9\-]{5,25})", text, group=1)
    if chassis_no:
        fields["chassis_number"] = chassis_no

    return fields


def _extract_structured_fields(text: str, document_type: str) -> Dict[str, Any]:
    if not text:
        return {}

    doc_type = (document_type or "").lower()
    if doc_type == "cnic":
        return _extract_cnic_fields_from_text(text)
    if doc_type in {"driving_license", "license", "driver_license"}:
        return _extract_license_fields_from_text(text)
    if doc_type in {"vehicle_registration", "vehicle_reg", "registration"}:
        return _extract_vehicle_fields_from_text(text)

    return {
        "raw_text_preview": " ".join(text.split())[:200]
    }


def _calculate_validation_score(extracted: Dict[str, Any], expected_fields: List[str]) -> float:
    if not extracted.get("success"):
        return 0.0

    fields = extracted.get("fields", {})
    if not expected_fields:
        return extracted.get("confidence", 0.0)

    found_count = sum(1 for field in expected_fields if fields.get(field))
    completeness = found_count / len(expected_fields)
    ocr_confidence = extracted.get("confidence", 0.0)
    return round(min(1.0, (0.6 * completeness) + (0.4 * ocr_confidence)), 3)


def _estimate_google_confidence(response: Any, fields: Dict[str, Any], document_type: str) -> float:
    block_confidences: List[float] = []

    try:
        if response.full_text_annotation and response.full_text_annotation.pages:
            for page in response.full_text_annotation.pages:
                for block in page.blocks:
                    if block.confidence is not None:
                        block_confidences.append(float(block.confidence))
    except Exception:
        block_confidences = []

    base_conf = sum(block_confidences) / len(block_confidences) if block_confidences else 0.75

    expected_fields_map = {
        "cnic": ["cnic_number", "name", "expiry_date"],
        "driving_license": ["license_number", "name", "expiry_date"],
        "vehicle_registration": ["registration_number"],
    }
    expected = expected_fields_map.get((document_type or "").lower(), [])

    if expected:
        found = sum(1 for key in expected if fields.get(key))
        completeness = found / len(expected)
        score = (0.7 * base_conf) + (0.3 * completeness)
    else:
        score = base_conf

    return round(max(0.0, min(0.99, score)), 3)


class OCRAdapter(ABC):
    """
    Abstract base class for OCR adapters.
    
    Provides interface for text extraction from document images.
    Implementations can use different OCR services while maintaining
    consistent API.
    """
    
    @abstractmethod
    async def extract_text(self, image_bytes: bytes, document_type: str = "generic") -> Dict[str, Any]:
        """
        Extract text from image bytes.
        
        Args:
            image_bytes: Raw image data
            document_type: Type of document (cnic, license, vehicle_registration, etc.)
        
        Returns:
            Dictionary containing:
            - success: bool
            - text: Extracted raw text
            - confidence: Overall OCR confidence (0.0 - 1.0)
            - fields: Structured data extracted (dict)
            - error: Error message if failed (optional)
        """
        pass
    
    @abstractmethod
    async def validate_fields(self, extracted: Dict[str, Any], expected_fields: List[str]) -> float:
        """
        Validate that expected fields were extracted successfully.
        
        Args:
            extracted: Extracted data dictionary from extract_text()
            expected_fields: List of required field names
        
        Returns:
            Validation score (0.0 - 1.0) representing completeness
        """
        pass


class LocalOCRStubAdapter(OCRAdapter):
    """
    Mock OCR adapter for development and testing.
    
    Provides deterministic simulated OCR results based on document type.
    Replace this with real OCR service in production.
    
    Features:
    - Simulated processing delay
    - Deterministic outputs for testing
    - Confidence scoring based on "image quality"
    - Supports CNIC, driving license, vehicle registration
    """
    
    def __init__(self):
        self.processing_delay = 1.0  # Simulated processing time in seconds
    
    async def extract_text(self, image_bytes: bytes, document_type: str = "generic") -> Dict[str, Any]:
        """
        Mock text extraction with simulated results.
        
        Args:
            image_bytes: Raw image data (not actually processed in mock)
            document_type: Type of document
        
        Returns:
            Simulated OCR results with deterministic values
        """
        # Simulate processing delay
        await asyncio.sleep(self.processing_delay)
        
        # Determine quality based on image size (mock heuristic)
        image_size = len(image_bytes)
        base_confidence = 0.92  # Good quality baseline
        
        if image_size < 50000:  # Very small file
            base_confidence = 0.60
        elif image_size < 200000:  # Medium file
            base_confidence = 0.80
        
        logger.info(f"[MOCK OCR] Processing {document_type} document, size: {image_size} bytes")
        
        # Generate document-specific results
        if document_type.lower() in ["cnic", "identity_card", "national_id"]:
            return await self._extract_cnic(base_confidence)
        elif document_type.lower() in ["license", "driving_license", "driver_license"]:
            return await self._extract_license(base_confidence)
        elif document_type.lower() in ["vehicle_registration", "vehicle_reg", "registration"]:
            return await self._extract_vehicle_registration(base_confidence)
        else:
            return await self._extract_generic(base_confidence)
    
    async def _extract_cnic(self, base_confidence: float) -> Dict[str, Any]:
        """Generate mock CNIC extraction results."""
        mock_cnic = f"{35200 + secrets.randbelow(300)}-{1000000 + secrets.randbelow(8000000)}-{secrets.randbelow(9) + 1}"
        
        mock_text = f"""
ISLAMIC REPUBLIC OF PAKISTAN
COMPUTERIZED NATIONAL IDENTITY CARD

Name: Mobeen Shoukat
Father's Name: Shoukat Ali
Date of Birth: 16-04-1999
CNIC: {mock_cnic}
Date of Issue: 15-03-2020
Date of Expiry: 15-03-2030
Address: House 123, Street 45, Lahore, Punjab
        """.strip()
        
        confidence = base_confidence + (secrets.randbelow(8) / 100)  # Add small variance
        
        return {
            "success": True,
            "text": mock_text,
            "confidence": min(0.99, confidence),
            "fields": {
                "cnic_number": mock_cnic,
                "name": "Mobeen Shoukat",
                "father_name": "Shoukat Ali",
                "dob": "16-04-1999",
                "issue_date": "15-03-2020",
                "expiry_date": "15-03-2030",
                "address": "House 123, Street 45, Lahore, Punjab"
            },
            "document_type": "cnic",
            "mock": True
        }
    
    async def _extract_license(self, base_confidence: float) -> Dict[str, Any]:
        """Generate mock driving license extraction results."""
        mock_license = f"LHR{100000 + secrets.randbelow(900000)}"
        
        mock_text = f"""
GOVERNMENT OF PUNJAB
DRIVING LICENSE

Name: Mobeen Shoukat
Father's Name: Shoukat Ali
License No: {mock_license}
Category: LTV, HTV, Motorcycle
Date of Issue: 20-06-2021
Valid Till: 20-06-2026
Blood Group: B+
        """.strip()
        
        confidence = base_confidence + (secrets.randbelow(8) / 100)
        
        return {
            "success": True,
            "text": mock_text,
            "confidence": min(0.99, confidence),
            "fields": {
                "license_number": mock_license,
                "name": "Mobeen Shoukat",
                "father_name": "Shoukat Ali",
                "category": "LTV, HTV, Motorcycle",
                "issue_date": "20-06-2021",
                "expiry_date": "20-06-2026",
                "blood_group": "B+"
            },
            "document_type": "driving_license",
            "mock": True
        }
    
    async def _extract_vehicle_registration(self, base_confidence: float) -> Dict[str, Any]:
        """Generate mock vehicle registration extraction results."""
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        mock_plate = f"L{letters[secrets.randbelow(26)]}{letters[secrets.randbelow(26)]}-{1000 + secrets.randbelow(9000)}"
        
        mock_text = f"""
MOTOR VEHICLE REGISTRATION
EXCISE & TAXATION DEPARTMENT

Registration No: {mock_plate}
Engine No: ABC123XYZ456
Chassis No: DEF789GHI012
Make: Toyota
Model: Corolla
Year: 2020
Color: White
Owner: Mobeen Shoukat
        """.strip()
        
        confidence = base_confidence + (secrets.randbelow(8) / 100)
        
        return {
            "success": True,
            "text": mock_text,
            "confidence": min(0.99, confidence),
            "fields": {
                "registration_number": mock_plate,
                "engine_number": "ABC123XYZ456",
                "chassis_number": "DEF789GHI012",
                "make": "Toyota",
                "model": "Corolla",
                "year": "2020",
                "color": "White",
                "owner": "Mobeen Shoukat"
            },
            "document_type": "vehicle_registration",
            "mock": True
        }
    
    async def _extract_generic(self, base_confidence: float) -> Dict[str, Any]:
        """Generate mock generic document extraction results."""
        mock_text = "Document content extracted successfully (mock implementation)"
        
        confidence = base_confidence + (secrets.randbelow(8) / 100)
        
        return {
            "success": True,
            "text": mock_text,
            "confidence": min(0.99, confidence),
            "fields": {},
            "document_type": "generic",
            "mock": True
        }
    
    async def validate_fields(self, extracted: Dict[str, Any], expected_fields: List[str]) -> float:
        """
        Validate extracted fields against expected fields.
        
        Args:
            extracted: Result from extract_text()
            expected_fields: List of required field names
        
        Returns:
            Validation score (0.0 - 1.0)
        """
        if not extracted.get("success"):
            return 0.0
        
        fields = extracted.get("fields", {})
        
        if not expected_fields:
            # No specific validation required
            return extracted.get("confidence", 0.8)
        
        # Count how many expected fields are present
        found_count = sum(1 for field in expected_fields if field in fields and fields[field])
        
        if len(expected_fields) == 0:
            return extracted.get("confidence", 0.8)
        
        # Calculate completeness
        completeness = found_count / len(expected_fields)
        
        # Combine with OCR confidence
        ocr_confidence = extracted.get("confidence", 0.8)
        
        # Weighted average: 60% completeness + 40% OCR confidence
        validation_score = (0.6 * completeness) + (0.4 * ocr_confidence)
        
        logger.info(f"[OCR VALIDATION] {found_count}/{len(expected_fields)} fields found, score: {validation_score:.2f}")
        
        return min(1.0, validation_score)


class GoogleVisionOCRAdapter(OCRAdapter):
    """
    Google Cloud Vision OCR adapter.

    Uses Document Text Detection and applies lightweight field extraction
    for CNIC, driving license, and vehicle registration documents.
    """

    def __init__(self, credentials_path: str = "", project_id: str = ""):
        self.credentials_path = (credentials_path or "").strip()
        self.project_id = (project_id or "").strip()
        self._client = None
        self._vision = None

    def _get_client(self):
        if self._client is not None and self._vision is not None:
            return self._client, self._vision

        try:
            from google.cloud import vision
        except Exception as exc:
            raise RuntimeError(
                "google-cloud-vision is not installed. Install with: pip install google-cloud-vision"
            ) from exc

        credentials = None
        if self.credentials_path:
            cred_path = Path(self.credentials_path)
            if not cred_path.exists():
                raise FileNotFoundError(f"Google credentials file not found: {cred_path}")
            try:
                from google.oauth2 import service_account
                credentials = service_account.Credentials.from_service_account_file(str(cred_path))
            except Exception as exc:
                raise RuntimeError(f"Failed to load Google service account JSON: {exc}") from exc

        if credentials is not None:
            self._client = vision.ImageAnnotatorClient(credentials=credentials)
        else:
            # Falls back to ADC (GOOGLE_APPLICATION_CREDENTIALS or default identity chain)
            self._client = vision.ImageAnnotatorClient()

        self._vision = vision
        return self._client, self._vision

    async def extract_text(self, image_bytes: bytes, document_type: str = "generic") -> Dict[str, Any]:
        if not image_bytes:
            return {
                "success": False,
                "text": "",
                "confidence": 0.0,
                "fields": {},
                "error": "Empty image payload"
            }

        try:
            client, vision = self._get_client()
            image = vision.Image(content=image_bytes)
            response = await asyncio.to_thread(client.document_text_detection, image=image)

            if response.error and response.error.message:
                return {
                    "success": False,
                    "text": "",
                    "confidence": 0.0,
                    "fields": {},
                    "error": response.error.message,
                    "document_type": document_type,
                    "mock": False,
                }

            text = ""
            if response.full_text_annotation and response.full_text_annotation.text:
                text = response.full_text_annotation.text.strip()
            elif response.text_annotations:
                text = response.text_annotations[0].description.strip()

            # Fallback for tiny/cropped images where document_text_detection
            # returns empty but text_detection can still recover visible text.
            if not text:
                text_response = await asyncio.to_thread(client.text_detection, image=image)
                if text_response.error and text_response.error.message:
                    return {
                        "success": False,
                        "text": "",
                        "confidence": 0.0,
                        "fields": {},
                        "error": text_response.error.message,
                        "document_type": document_type,
                        "mock": False,
                    }

                if text_response.full_text_annotation and text_response.full_text_annotation.text:
                    text = text_response.full_text_annotation.text.strip()
                elif text_response.text_annotations:
                    text = text_response.text_annotations[0].description.strip()

            fields = _extract_structured_fields(text, document_type)
            confidence = _estimate_google_confidence(response, fields, document_type)

            return {
                "success": bool(text),
                "text": text,
                "confidence": confidence,
                "fields": fields,
                "document_type": document_type,
                "mock": False,
            }
        except Exception as exc:
            logger.error("[GOOGLE OCR] Extraction failed: %s", exc)
            return {
                "success": False,
                "text": "",
                "confidence": 0.0,
                "fields": {},
                "error": str(exc),
                "document_type": document_type,
                "mock": False,
            }

    async def validate_fields(self, extracted: Dict[str, Any], expected_fields: List[str]) -> float:
        return _calculate_validation_score(extracted, expected_fields)


class AWSTextractOCRAdapter(OCRAdapter):
    """
    AWS Textract OCR adapter.

    Uses DetectDocumentText API for plain OCR extraction and then applies
    domain-specific field extraction for CNIC/license/registration documents.
    """

    def __init__(
        self,
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None,
        region_name: str = "ap-south-1",
    ):
        self.region_name = region_name or "ap-south-1"

        try:
            import boto3
        except Exception as exc:
            raise RuntimeError("boto3 is not installed. Install with: pip install boto3") from exc

        client_kwargs = {
            "service_name": "textract",
            "region_name": self.region_name,
        }

        if aws_access_key_id and aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = aws_access_key_id
            client_kwargs["aws_secret_access_key"] = aws_secret_access_key

        self._client = boto3.client(**client_kwargs)

    async def extract_text(self, image_bytes: bytes, document_type: str = "generic") -> Dict[str, Any]:
        if not image_bytes:
            return {
                "success": False,
                "text": "",
                "confidence": 0.0,
                "fields": {},
                "error": "Empty image payload",
                "document_type": document_type,
                "mock": False,
            }

        try:
            response = await asyncio.to_thread(
                self._client.detect_document_text,
                Document={"Bytes": image_bytes},
            )

            blocks = response.get("Blocks", [])
            lines = [
                (b.get("Text") or "").strip()
                for b in blocks
                if b.get("BlockType") == "LINE" and b.get("Text")
            ]
            text = "\n".join(lines).strip()

            confidences = [
                float(b.get("Confidence", 0.0)) / 100.0
                for b in blocks
                if b.get("BlockType") == "LINE" and b.get("Confidence") is not None
            ]
            base_confidence = sum(confidences) / len(confidences) if confidences else 0.0

            fields = _extract_structured_fields(text, document_type)
            field_bonus = min(1.0, len(fields) / 5.0) if fields else 0.0
            confidence = round(min(0.99, max(0.0, (0.75 * base_confidence) + (0.25 * field_bonus))), 3)

            return {
                "success": bool(text),
                "text": text,
                "confidence": confidence if text else 0.0,
                "fields": fields,
                "document_type": document_type,
                "mock": False,
                "details": {
                    "region": self.region_name,
                    "blocks_count": len(blocks),
                },
            }
        except Exception as exc:
            logger.error("[AWS OCR] Textract extraction failed: %s", exc)
            return {
                "success": False,
                "text": "",
                "confidence": 0.0,
                "fields": {},
                "error": str(exc),
                "document_type": document_type,
                "mock": False,
            }

    async def validate_fields(self, extracted: Dict[str, Any], expected_fields: List[str]) -> float:
        return _calculate_validation_score(extracted, expected_fields)


class AzureComputerVisionOCRAdapter(OCRAdapter):
    """
    Azure Computer Vision Read OCR adapter.

    Uses the asynchronous Read API:
    - POST /vision/v3.2/read/analyze
    - poll Operation-Location until status == succeeded
    """

    def __init__(
        self,
        endpoint: str = "",
        api_key: str = "",
        poll_interval_seconds: float = 1.0,
        max_polls: int = 15,
    ):
        self.endpoint = (endpoint or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.poll_interval_seconds = max(0.5, float(poll_interval_seconds or 1.0))
        self.max_polls = max(1, int(max_polls or 15))

    def _headers(self, content_type: str = None) -> Dict[str, str]:
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _ensure_configured(self) -> None:
        if not self.endpoint or not self.api_key:
            raise RuntimeError(
                "Azure OCR is not configured. Set AZURE_VISION_ENDPOINT and AZURE_VISION_API_KEY."
            )

    async def extract_text(self, image_bytes: bytes, document_type: str = "generic") -> Dict[str, Any]:
        if not image_bytes:
            return {
                "success": False,
                "text": "",
                "confidence": 0.0,
                "fields": {},
                "error": "Empty image payload",
                "document_type": document_type,
                "mock": False,
            }

        try:
            self._ensure_configured()
            analyze_url = f"{self.endpoint}/vision/v3.2/read/analyze"

            async with httpx.AsyncClient(timeout=30.0) as client:
                submit_response = await client.post(
                    analyze_url,
                    headers=self._headers(content_type="application/octet-stream"),
                    content=image_bytes,
                )

                if submit_response.status_code >= 400:
                    raise RuntimeError(
                        f"Azure Read analyze request failed ({submit_response.status_code}): "
                        f"{submit_response.text[:300]}"
                    )

                operation_url = (
                    submit_response.headers.get("Operation-Location")
                    or submit_response.headers.get("operation-location")
                )
                if not operation_url:
                    raise RuntimeError("Azure Read API did not return Operation-Location header")

                result_payload: Dict[str, Any] = {}
                for _ in range(self.max_polls):
                    poll_response = await client.get(operation_url, headers=self._headers())
                    if poll_response.status_code >= 400:
                        raise RuntimeError(
                            f"Azure Read poll failed ({poll_response.status_code}): "
                            f"{poll_response.text[:300]}"
                        )

                    result_payload = poll_response.json()
                    status_value = str(result_payload.get("status", "")).lower()

                    if status_value == "succeeded":
                        break
                    if status_value in {"failed", "error"}:
                        raise RuntimeError(f"Azure Read operation failed: {result_payload}")

                    await asyncio.sleep(self.poll_interval_seconds)
                else:
                    raise RuntimeError("Azure Read operation timed out while polling")

            analyze_result = result_payload.get("analyzeResult", {}) if isinstance(result_payload, dict) else {}
            read_results = analyze_result.get("readResults", []) if isinstance(analyze_result, dict) else []

            lines: List[str] = []
            word_confidences: List[float] = []

            for page in read_results or []:
                for line in page.get("lines", []) or []:
                    line_text = (line.get("text") or "").strip()
                    if line_text:
                        lines.append(line_text)
                    for word in line.get("words", []) or []:
                        confidence = word.get("confidence")
                        if confidence is None:
                            continue
                        try:
                            word_confidences.append(float(confidence))
                        except (TypeError, ValueError):
                            continue

            text = "\n".join(lines).strip()
            if not text and isinstance(analyze_result, dict):
                text = str(analyze_result.get("content") or "").strip()

            base_confidence = (
                sum(word_confidences) / len(word_confidences) if word_confidences else 0.0
            )
            fields = _extract_structured_fields(text, document_type)
            field_bonus = min(1.0, len(fields) / 5.0) if fields else 0.0
            confidence = round(min(0.99, max(0.0, (0.75 * base_confidence) + (0.25 * field_bonus))), 3)

            return {
                "success": bool(text),
                "text": text,
                "confidence": confidence if text else 0.0,
                "fields": fields,
                "document_type": document_type,
                "mock": False,
                "details": {
                    "operation_status": result_payload.get("status") if isinstance(result_payload, dict) else None,
                },
            }
        except Exception as exc:
            logger.error("[AZURE OCR] Read extraction failed: %s", exc)
            return {
                "success": False,
                "text": "",
                "confidence": 0.0,
                "fields": {},
                "error": str(exc),
                "document_type": document_type,
                "mock": False,
            }

    async def validate_fields(self, extracted: Dict[str, Any], expected_fields: List[str]) -> float:
        return _calculate_validation_score(extracted, expected_fields)

# Factory function to get OCR adapter
def get_ocr_adapter(adapter_type: str = "local", **kwargs) -> OCRAdapter:
    """
    Factory function to get OCR adapter instance.
    
    Args:
        adapter_type: Type of adapter ("local", "google", "aws", "azure")
    
    Returns:
        OCRAdapter instance
    
    Usage:
        >>> ocr = get_ocr_adapter("local")
        >>> result = await ocr.extract_text(image_bytes, "cnic")
    """
    normalized_adapter = (adapter_type or "local").strip().lower()

    if normalized_adapter in {"local", "stub", "mock"}:
        return LocalOCRStubAdapter()
    elif normalized_adapter in {"google", "google_vision", "gcp"}:
        return GoogleVisionOCRAdapter(
            credentials_path=kwargs.get("credentials_path", ""),
            project_id=kwargs.get("project_id", ""),
        )
    elif normalized_adapter in {"aws", "textract", "aws_textract"}:
        return AWSTextractOCRAdapter(
            aws_access_key_id=kwargs.get("aws_access_key_id"),
            aws_secret_access_key=kwargs.get("aws_secret_access_key"),
            region_name=kwargs.get("region_name", "ap-south-1"),
        )
    elif normalized_adapter in {"azure", "azure_ai", "azure-ai", "azure_vision"}:
        return AzureComputerVisionOCRAdapter(
            endpoint=kwargs.get("endpoint") or kwargs.get("azure_endpoint", ""),
            api_key=kwargs.get("api_key") or kwargs.get("subscription_key") or kwargs.get("azure_api_key", ""),
            poll_interval_seconds=kwargs.get("poll_interval_seconds", 1.0),
            max_polls=kwargs.get("max_polls", 15),
        )
    else:
        raise ValueError(f"Unknown OCR adapter type: {adapter_type}")

# === VERIFICATION FUNCTIONALITY END ===
