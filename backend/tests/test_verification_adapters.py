"""
Adapter-level verification tests for OCR and face providers.

These tests use mocked clients/responses so they do not require live cloud APIs.
"""

from types import SimpleNamespace

import pytest

from app.modules.verification import face_match_adapter, ocr_adapter
from app.modules.verification import service as verification_service


class _FakeTextractClient:
    def detect_document_text(self, Document):
        return {
            "Blocks": [
                {"BlockType": "LINE", "Text": "CNIC: 12345-1234567-1", "Confidence": 97.0},
                {"BlockType": "LINE", "Text": "Name: Ali Raza", "Confidence": 95.0},
            ]
        }


class _FakeHTTPResponse:
    def __init__(self, status_code=200, headers=None, payload=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload
        self.text = text
        self.content = b"" if payload is None else b"non-empty"

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_aws_textract_adapter_extracts_cnic_fields(monkeypatch):
    adapter = ocr_adapter.AWSTextractOCRAdapter(region_name="ap-south-1")
    monkeypatch.setattr(adapter, "_client", _FakeTextractClient())

    result = await adapter.extract_text(b"image-bytes", "cnic")

    assert result["success"] is True
    assert result["fields"]["cnic_number"] == "12345-1234567-1"
    assert result["fields"]["name"] == "Ali Raza"
    assert result["confidence"] > 0


@pytest.mark.asyncio
async def test_google_ocr_adapter_extracts_fields_with_mocked_client(monkeypatch):
    class _FakeClient:
        def document_text_detection(self, image):
            return SimpleNamespace(
                error=SimpleNamespace(message=""),
                full_text_annotation=SimpleNamespace(
                    text="CNIC: 12345-1234567-1\nName: Ali Raza",
                    pages=[],
                ),
                text_annotations=[],
            )

    class _FakeVision:
        class Image:
            def __init__(self, content):
                self.content = content

    adapter = ocr_adapter.GoogleVisionOCRAdapter()
    monkeypatch.setattr(adapter, "_get_client", lambda: (_FakeClient(), _FakeVision))

    result = await adapter.extract_text(b"image-bytes", "cnic")

    assert result["success"] is True
    assert result["fields"]["cnic_number"] == "12345-1234567-1"
    assert result["fields"]["name"] == "Ali Raza"


@pytest.mark.asyncio
async def test_azure_ocr_adapter_extracts_fields_with_mocked_http(monkeypatch):
    class _FakeAzureOCRClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, content=None):
            return _FakeHTTPResponse(
                status_code=202,
                headers={"Operation-Location": "https://example.org/ops/123"},
                payload={},
            )

        async def get(self, url, headers=None):
            return _FakeHTTPResponse(
                status_code=200,
                payload={
                    "status": "succeeded",
                    "analyzeResult": {
                        "readResults": [
                            {
                                "lines": [
                                    {
                                        "text": "CNIC: 12345-1234567-1",
                                        "words": [{"confidence": 0.98}],
                                    },
                                    {
                                        "text": "Name: Ali Raza",
                                        "words": [{"confidence": 0.96}],
                                    },
                                ]
                            }
                        ]
                    },
                },
            )

    monkeypatch.setattr(ocr_adapter.httpx, "AsyncClient", lambda *args, **kwargs: _FakeAzureOCRClient())

    adapter = ocr_adapter.AzureComputerVisionOCRAdapter(
        endpoint="https://example.cognitiveservices.azure.com",
        api_key="fake-key",
        poll_interval_seconds=0.5,
        max_polls=2,
    )

    result = await adapter.extract_text(b"image-bytes", "cnic")

    assert result["success"] is True
    assert result["fields"]["cnic_number"] == "12345-1234567-1"
    assert result["fields"]["name"] == "Ali Raza"
    assert result["confidence"] > 0


@pytest.mark.asyncio
async def test_azure_face_adapter_match_and_detect_with_mocked_http(monkeypatch):
    class _FakeAzureFaceClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, params=None, headers=None, content=None, json=None):
            if url.endswith("/face/v1.0/detect"):
                return _FakeHTTPResponse(
                    status_code=200,
                    payload=[
                        {
                            "faceId": "face-1",
                            "faceAttributes": {"qualityForRecognition": "high"},
                        }
                    ],
                )

            if url.endswith("/face/v1.0/verify"):
                return _FakeHTTPResponse(
                    status_code=200,
                    payload={"isIdentical": True, "confidence": 0.92},
                )

            return _FakeHTTPResponse(status_code=404, payload={})

    monkeypatch.setattr(face_match_adapter.httpx, "AsyncClient", lambda *args, **kwargs: _FakeAzureFaceClient())

    adapter = face_match_adapter.AzureFaceAPIAdapter(
        subscription_key="fake-key",
        endpoint="https://example.cognitiveservices.azure.com",
        match_threshold=0.8,
    )

    match_result = await adapter.match(b"selfie", b"document")
    detect_result = await adapter.detect_face(b"selfie")

    assert match_result["success"] is True
    assert match_result["match"] is True
    assert match_result["similarity"] >= 0.9

    assert detect_result["success"] is True
    assert detect_result["face_detected"] is True
    assert detect_result["face_count"] == 1


def test_adapter_factories_support_azure_variants():
    ocr = ocr_adapter.get_ocr_adapter(
        "azure",
        endpoint="https://example.cognitiveservices.azure.com",
        api_key="fake-key",
    )
    face = face_match_adapter.get_face_match_adapter(
        "azure",
        endpoint="https://example.cognitiveservices.azure.com",
        subscription_key="fake-key",
    )

    assert isinstance(ocr, ocr_adapter.AzureComputerVisionOCRAdapter)
    assert isinstance(face, face_match_adapter.AzureFaceAPIAdapter)


def test_verification_provider_policy_prefers_google_ocr_and_azure_face():
    assert verification_service._resolve_ocr_provider("google") == "google"
    assert verification_service._resolve_ocr_provider("gcp") == "google"
    assert verification_service._resolve_ocr_provider("aws") == "google"

    assert verification_service._resolve_face_provider("azure") == "azure"
    assert verification_service._resolve_face_provider("azure_face") == "azure"
    assert verification_service._resolve_face_provider("aws") == "azure"
