"""
Face Match Adapter - Pluggable Interface for Facial Recognition

Purpose: Provides a pluggable interface for face matching services with mock implementation.
         Can be replaced with real face recognition APIs (AWS Rekognition, Azure Face API, etc.).

Author: M. Mobeen Shoukat Ch
Partner: M. Shayan Khan
Project: SmartCarpoolingApp (Backend)
Date: December 7, 2025
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
import secrets
import asyncio
import logging
import httpx

logger = logging.getLogger(__name__)


class FaceMatchAdapter(ABC):
    """
    Abstract base class for face matching adapters.

    Provides interface for comparing faces between document photo and selfie.
    Implementations can use different face recognition services while maintaining
    consistent API.
    """

    @abstractmethod
    async def match(self, selfie_bytes: bytes, document_photo_bytes: bytes) -> Dict[str, Any]:
        """
        Compare two face images and return similarity score.

        Args:
            selfie_bytes: User selfie image data
            document_photo_bytes: Photo from document (CNIC, license)

        Returns:
            Dictionary containing:
            - success: bool
            - similarity: Similarity score (0.0 - 1.0)
            - confidence: Confidence in the match (0.0 - 1.0)
            - match: Boolean indicating if faces match (threshold-based)
            - details: Additional metadata (optional)
            - error: Error message if failed (optional)
        """
        pass

    @abstractmethod
    async def detect_face(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Detect if a face is present in the image.

        Args:
            image_bytes: Image data

        Returns:
            Dictionary containing:
            - success: bool
            - face_detected: bool
            - face_count: Number of faces detected
            - confidence: Detection confidence (0.0 - 1.0)
            - quality_score: Face image quality (0.0 - 1.0)
            - details: Bounding boxes, landmarks, etc. (optional)
        """
        pass


class LocalFaceMatchStubAdapter(FaceMatchAdapter):
    """
    Mock face matching adapter for development and testing.

    Provides deterministic simulated face matching results.
    Replace this with real face recognition service in production.

    Features:
    - Simulated processing delay
    - Quality-based scoring
    - Face detection validation
    - Threshold-based match decision

    Matching Threshold: 0.80 (80% similarity for positive match)
    """

    def __init__(self, match_threshold: float = 0.80):
        """
        Initialize face match adapter.

        Args:
            match_threshold: Minimum similarity score for positive match (0.0 - 1.0)
        """
        self.match_threshold = match_threshold
        self.processing_delay = 1.2  # Simulated processing time in seconds

    async def match(self, selfie_bytes: bytes, document_photo_bytes: bytes) -> Dict[str, Any]:
        """
        Mock face matching with simulated results.

        Simulates realistic face matching behavior:
        - Good quality images -> high similarity (0.85-0.95)
        - Medium quality -> moderate similarity (0.70-0.85)
        - Poor quality -> low similarity (0.40-0.70)

        Args:
            selfie_bytes: User selfie image data
            document_photo_bytes: Document photo image data

        Returns:
            Simulated face match results
        """
        # Simulate processing delay
        await asyncio.sleep(self.processing_delay)

        selfie_size = len(selfie_bytes)
        doc_size = len(document_photo_bytes)

        logger.info(f"[MOCK FACE MATCH] Comparing faces - Selfie: {selfie_size} bytes, Document: {doc_size} bytes")

        # Determine quality based on image sizes (mock heuristic)
        avg_size = (selfie_size + doc_size) / 2

        if avg_size > 500000:  # Large, high-quality images
            base_similarity = 0.90
            base_confidence = 0.95
        elif avg_size > 200000:  # Medium quality
            base_similarity = 0.78
            base_confidence = 0.85
        elif avg_size > 50000:  # Low quality
            base_similarity = 0.55
            base_confidence = 0.70
        else:  # Very poor quality
            base_similarity = 0.40
            base_confidence = 0.60

        # Add small random variance for realism
        variance = (secrets.randbelow(10) - 5) / 100  # -0.05 to +0.05
        similarity = max(0.0, min(1.0, base_similarity + variance))
        confidence = max(0.0, min(1.0, base_confidence + variance))

        # Determine match based on threshold
        is_match = similarity >= self.match_threshold

        logger.info(f"[MOCK FACE MATCH] Similarity: {similarity:.2f}, Match: {is_match}")

        return {
            "success": True,
            "similarity": round(similarity, 3),
            "confidence": round(confidence, 3),
            "match": is_match,
            "threshold": self.match_threshold,
            "details": {
                "selfie_quality": self._assess_quality(selfie_size),
                "document_quality": self._assess_quality(doc_size),
                "processing_time_ms": int(self.processing_delay * 1000)
            },
            "mock": True
        }

    async def detect_face(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Mock face detection in image.

        Simulates face detection with deterministic results.

        Args:
            image_bytes: Image data

        Returns:
            Simulated face detection results
        """
        # Simulate processing delay (shorter than full match)
        await asyncio.sleep(0.5)

        image_size = len(image_bytes)

        logger.info(f"[MOCK FACE DETECT] Analyzing image: {image_size} bytes")

        # Simulate face detection based on image size
        if image_size < 10000:  # Too small
            face_detected = False
            face_count = 0
            confidence = 0.30
            quality_score = 0.20
        elif image_size < 50000:  # Small but acceptable
            face_detected = True
            face_count = 1
            confidence = 0.70
            quality_score = 0.60
        elif image_size < 200000:  # Good size
            face_detected = True
            face_count = 1
            confidence = 0.90
            quality_score = 0.85
        else:  # Large, high quality
            face_detected = True
            face_count = 1
            confidence = 0.95
            quality_score = 0.92

        # Add small variance
        if face_detected:
            variance = secrets.randbelow(5) / 100
            confidence = min(1.0, confidence + variance)
            quality_score = min(1.0, quality_score + variance)

        return {
            "success": True,
            "face_detected": face_detected,
            "face_count": face_count,
            "confidence": round(confidence, 3),
            "quality_score": round(quality_score, 3),
            "details": {
                "image_size": image_size,
                "quality_assessment": self._assess_quality(image_size),
                "recommended": face_detected and quality_score > 0.70
            },
            "mock": True
        }

    def _assess_quality(self, image_size: int) -> str:
        """
        Assess image quality based on file size.

        Args:
            image_size: Image file size in bytes

        Returns:
            Quality assessment string
        """
        if image_size < 50000:
            return "poor"
        elif image_size < 200000:
            return "fair"
        elif image_size < 500000:
            return "good"
        else:
            return "excellent"


class AWSRekognitionAdapter(FaceMatchAdapter):
    """
    AWS Rekognition face matching adapter.

    TODO: Implement integration with AWS Rekognition CompareFaces API.

    Requirements:
    - boto3 library
    - AWS credentials configured
    - IAM permissions for rekognition:CompareFaces

    Example:
        >>> adapter = AWSRekognitionAdapter(
        ...     aws_access_key_id="...",
        ...     aws_secret_access_key="...",
        ...     region_name="us-east-1"
        ... )
        >>> result = await adapter.match(selfie_bytes, doc_bytes)
    """

    def __init__(
        self,
        aws_access_key_id: str = None,
        aws_secret_access_key: str = None,
        region_name: str = "ap-south-1",
        match_threshold: float = 0.80,
    ):
        self.match_threshold = max(0.0, min(1.0, match_threshold))
        self.region_name = region_name or "ap-south-1"

        try:
            import boto3
        except Exception as exc:
            raise RuntimeError("boto3 is not installed. Install with: pip install boto3") from exc

        client_kwargs = {
            "service_name": "rekognition",
            "region_name": self.region_name,
        }

        if aws_access_key_id and aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = aws_access_key_id
            client_kwargs["aws_secret_access_key"] = aws_secret_access_key

        self._client = boto3.client(**client_kwargs)

    async def match(self, selfie_bytes: bytes, document_photo_bytes: bytes) -> Dict[str, Any]:
        if not selfie_bytes or not document_photo_bytes:
            return {
                "success": False,
                "similarity": 0.0,
                "confidence": 0.0,
                "match": False,
                "error": "Both selfie and document photo are required",
            }

        threshold_pct = round(self.match_threshold * 100, 2)

        try:
            response = await asyncio.to_thread(
                self._client.compare_faces,
                SourceImage={"Bytes": document_photo_bytes},
                TargetImage={"Bytes": selfie_bytes},
                SimilarityThreshold=threshold_pct,
            )

            face_matches = response.get("FaceMatches", [])
            if face_matches:
                top_match = max(face_matches, key=lambda m: m.get("Similarity", 0.0))
                similarity = float(top_match.get("Similarity", 0.0)) / 100.0
            else:
                similarity = 0.0

            is_match = similarity >= self.match_threshold

            return {
                "success": True,
                "similarity": round(similarity, 3),
                "confidence": round(similarity, 3),
                "match": is_match,
                "threshold": self.match_threshold,
                "details": {
                    "region": self.region_name,
                    "face_matches_count": len(face_matches),
                    "unmatched_faces_count": len(response.get("UnmatchedFaces", [])),
                },
                "mock": False,
            }
        except Exception as exc:
            logger.error("[AWS FACE MATCH] CompareFaces failed: %s", exc)
            return {
                "success": False,
                "similarity": 0.0,
                "confidence": 0.0,
                "match": False,
                "threshold": self.match_threshold,
                "error": str(exc),
                "mock": False,
            }

    async def detect_face(self, image_bytes: bytes) -> Dict[str, Any]:
        if not image_bytes:
            return {
                "success": False,
                "face_detected": False,
                "face_count": 0,
                "confidence": 0.0,
                "quality_score": 0.0,
                "error": "Empty image payload",
            }

        try:
            response = await asyncio.to_thread(
                self._client.detect_faces,
                Image={"Bytes": image_bytes},
                Attributes=["DEFAULT"],
            )

            faces = response.get("FaceDetails", [])
            face_detected = len(faces) > 0
            face_count = len(faces)

            confidence = 0.0
            quality_score = 0.0

            if face_detected:
                primary = faces[0]
                confidence = float(primary.get("Confidence", 0.0)) / 100.0
                quality = primary.get("Quality", {})
                brightness = float(quality.get("Brightness", 0.0)) / 100.0
                sharpness = float(quality.get("Sharpness", 0.0)) / 100.0
                quality_score = round((brightness + sharpness) / 2.0, 3)

            return {
                "success": True,
                "face_detected": face_detected,
                "face_count": face_count,
                "confidence": round(confidence, 3),
                "quality_score": round(quality_score, 3),
                "details": {
                    "region": self.region_name,
                    "recommended": face_detected and quality_score >= 0.6,
                },
                "mock": False,
            }
        except Exception as exc:
            logger.error("[AWS FACE MATCH] DetectFaces failed: %s", exc)
            return {
                "success": False,
                "face_detected": False,
                "face_count": 0,
                "confidence": 0.0,
                "quality_score": 0.0,
                "error": str(exc),
                "mock": False,
            }


class AzureFaceAPIAdapter(FaceMatchAdapter):
    """
    Azure Face API matching adapter.

    TODO: Implement integration with Azure Cognitive Services Face API.

    Requirements:
    - azure-cognitiveservices-vision-face library
    - Azure subscription key
    - Face API endpoint URL

    Example:
        >>> adapter = AzureFaceAPIAdapter(
        ...     subscription_key="...",
        ...     endpoint="https://....cognitiveservices.azure.com/"
        ... )
        >>> result = await adapter.match(selfie_bytes, doc_bytes)
    """

    def __init__(
        self,
        subscription_key: str = None,
        endpoint: str = None,
        match_threshold: float = 0.80,
        detection_model: str = "detection_03",
        recognition_model: str = "recognition_04",
    ):
        self.subscription_key = (subscription_key or "").strip()
        self.endpoint = (endpoint or "").strip().rstrip("/")
        self.match_threshold = max(0.0, min(1.0, float(match_threshold)))
        self.detection_model = detection_model or "detection_03"
        self.recognition_model = recognition_model or "recognition_04"

    def _ensure_configured(self) -> None:
        if not self.subscription_key or not self.endpoint:
            raise RuntimeError(
                "Azure Face API is not configured. Set AZURE_FACE_ENDPOINT and AZURE_FACE_API_KEY."
            )

    def _headers(self, content_type: str = None) -> Dict[str, str]:
        headers = {
            "Ocp-Apim-Subscription-Key": self.subscription_key,
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _quality_score_from_face(self, face_item: Dict[str, Any]) -> float:
        quality = (
            face_item.get("faceAttributes", {}).get("qualityForRecognition")
            or face_item.get("qualityForRecognition")
            or ""
        )
        quality_map = {
            "low": 0.4,
            "medium": 0.7,
            "high": 0.9,
        }
        return quality_map.get(str(quality).lower(), 0.6)

    async def _detect_faces(self, image_bytes: bytes, return_face_id: bool = True) -> List[Dict[str, Any]]:
        self._ensure_configured()
        if not image_bytes:
            return []

        detect_url = f"{self.endpoint}/face/v1.0/detect"
        params = {
            "returnFaceId": str(bool(return_face_id)).lower(),
            "returnFaceAttributes": "qualityForRecognition",
            "detectionModel": self.detection_model,
            "recognitionModel": self.recognition_model,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                detect_url,
                params=params,
                headers=self._headers(content_type="application/octet-stream"),
                content=image_bytes,
            )

        if response.status_code >= 400:
            raise RuntimeError(
                f"Azure Face detect failed ({response.status_code}): {response.text[:300]}"
            )

        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected Azure Face detect response format")
        return payload

    async def match(self, selfie_bytes: bytes, document_photo_bytes: bytes) -> Dict[str, Any]:
        if not selfie_bytes or not document_photo_bytes:
            return {
                "success": False,
                "similarity": 0.0,
                "confidence": 0.0,
                "match": False,
                "error": "Both selfie and document photo are required",
            }

        try:
            selfie_faces = await self._detect_faces(selfie_bytes, return_face_id=True)
            doc_faces = await self._detect_faces(document_photo_bytes, return_face_id=True)

            if not selfie_faces:
                return {
                    "success": False,
                    "similarity": 0.0,
                    "confidence": 0.0,
                    "match": False,
                    "threshold": self.match_threshold,
                    "error": "No face detected in selfie image",
                    "mock": False,
                }

            if not doc_faces:
                return {
                    "success": False,
                    "similarity": 0.0,
                    "confidence": 0.0,
                    "match": False,
                    "threshold": self.match_threshold,
                    "error": "No face detected in document image",
                    "mock": False,
                }

            selfie_face = max(selfie_faces, key=self._quality_score_from_face)
            doc_face = max(doc_faces, key=self._quality_score_from_face)

            selfie_face_id = selfie_face.get("faceId")
            doc_face_id = doc_face.get("faceId")
            if not selfie_face_id or not doc_face_id:
                raise RuntimeError("Azure Face detect did not return faceId for verification")

            verify_url = f"{self.endpoint}/face/v1.0/verify"
            verify_payload = {
                "faceId1": doc_face_id,
                "faceId2": selfie_face_id,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                verify_response = await client.post(
                    verify_url,
                    headers=self._headers(content_type="application/json"),
                    json=verify_payload,
                )

            if verify_response.status_code >= 400:
                raise RuntimeError(
                    f"Azure Face verify failed ({verify_response.status_code}): {verify_response.text[:300]}"
                )

            verify_data = verify_response.json() if verify_response.content else {}
            confidence = float(verify_data.get("confidence", 0.0))
            is_identical = bool(verify_data.get("isIdentical", False))
            is_match = is_identical and confidence >= self.match_threshold

            return {
                "success": True,
                "similarity": round(confidence, 3),
                "confidence": round(confidence, 3),
                "match": is_match,
                "threshold": self.match_threshold,
                "details": {
                    "is_identical": is_identical,
                    "selfie_faces_count": len(selfie_faces),
                    "document_faces_count": len(doc_faces),
                    "detection_model": self.detection_model,
                    "recognition_model": self.recognition_model,
                    "selfie_quality": round(self._quality_score_from_face(selfie_face), 3),
                    "document_quality": round(self._quality_score_from_face(doc_face), 3),
                },
                "mock": False,
            }
        except Exception as exc:
            logger.error("[AZURE FACE MATCH] Verification failed: %s", exc)
            return {
                "success": False,
                "similarity": 0.0,
                "confidence": 0.0,
                "match": False,
                "threshold": self.match_threshold,
                "error": str(exc),
                "mock": False,
            }

    async def detect_face(self, image_bytes: bytes) -> Dict[str, Any]:
        if not image_bytes:
            return {
                "success": False,
                "face_detected": False,
                "face_count": 0,
                "confidence": 0.0,
                "quality_score": 0.0,
                "error": "Empty image payload",
            }

        try:
            faces = await self._detect_faces(image_bytes, return_face_id=False)
            face_detected = len(faces) > 0
            face_count = len(faces)

            quality_score = (
                sum(self._quality_score_from_face(face) for face in faces) / face_count
                if face_count
                else 0.0
            )

            return {
                "success": True,
                "face_detected": face_detected,
                "face_count": face_count,
                "confidence": round(1.0 if face_detected else 0.0, 3),
                "quality_score": round(quality_score, 3),
                "details": {
                    "detection_model": self.detection_model,
                    "recognition_model": self.recognition_model,
                    "recommended": face_detected and quality_score >= 0.6,
                },
                "mock": False,
            }
        except Exception as exc:
            logger.error("[AZURE FACE MATCH] Detect face failed: %s", exc)
            return {
                "success": False,
                "face_detected": False,
                "face_count": 0,
                "confidence": 0.0,
                "quality_score": 0.0,
                "error": str(exc),
                "mock": False,
            }


# Factory function to get face match adapter
def get_face_match_adapter(adapter_type: str = "local", **kwargs) -> FaceMatchAdapter:
    """
    Factory function to get face match adapter instance.

    Args:
        adapter_type: Type of adapter ("local", "aws", "azure")
        **kwargs: Additional configuration for specific adapters

    Returns:
        FaceMatchAdapter instance

    Usage:
        >>> adapter = get_face_match_adapter("local")
        >>> result = await adapter.match(selfie_bytes, doc_bytes)
    """
    normalized_adapter = (adapter_type or "local").strip().lower()

    if normalized_adapter in {"local", "stub", "mock"}:
        match_threshold = kwargs.get("match_threshold", 0.80)
        return LocalFaceMatchStubAdapter(match_threshold=match_threshold)
    elif normalized_adapter in {"aws", "rekognition", "aws_rekognition"}:
        return AWSRekognitionAdapter(
            aws_access_key_id=kwargs.get("aws_access_key_id"),
            aws_secret_access_key=kwargs.get("aws_secret_access_key"),
            region_name=kwargs.get("region_name", "ap-south-1"),
            match_threshold=kwargs.get("match_threshold", 0.80),
        )
    elif normalized_adapter in {"azure", "azure_face", "azure-face"}:
        return AzureFaceAPIAdapter(
            subscription_key=kwargs.get("subscription_key") or kwargs.get("api_key"),
            endpoint=kwargs.get("endpoint"),
            match_threshold=kwargs.get("match_threshold", 0.80),
            detection_model=kwargs.get("detection_model", "detection_03"),
            recognition_model=kwargs.get("recognition_model", "recognition_04"),
        )
    else:
        raise ValueError(f"Unknown face match adapter type: {adapter_type}")
