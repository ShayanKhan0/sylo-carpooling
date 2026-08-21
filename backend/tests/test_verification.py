"""
Verification tests aligned with the current service contracts.

Focus:
- OCR/profile identity cross-check outcomes
- Legacy wrapper behavior for process_verification()
- Back-document metadata propagation in upload flow
"""

import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.modules.verification import service
from app.modules.verification.models import DocumentTypeEnum


class FakeUploadFile:
    """Small UploadFile-compatible test double for service-layer tests."""

    def __init__(self, filename: str, content_type: str = "image/jpeg", data: bytes = b"file-bytes"):
        self.filename = filename
        self.content_type = content_type
        self._data = data
        self._consumed = False

    async def read(self) -> bytes:
        if self._consumed:
            return b""
        self._consumed = True
        return self._data


class _DummyAttempt:
    def __init__(self, face_match_score=None, ocr_data=None):
        self.face_match_score = face_match_score
        self.ocr_data = ocr_data


def test_identity_cross_check_hard_fail_for_cnic_number_mismatch():
    expected = {
        "full_name": "Ali Raza",
        "cnic_number": "12345-1234567-1",
        "license_number": "",
        "registration_number": "",
    }
    ocr_fields = {
        "cnic_number": "99999-9999999-9",
        "name": "Ali Raza",
    }

    result = service._build_identity_cross_check("cnic", expected, ocr_fields)

    assert result["status"] == "hard_fail"
    assert "cnic_number" in result["mismatch_fields"]


def test_identity_cross_check_soft_fail_for_name_mismatch_only():
    expected = {
        "full_name": "Ali Raza",
        "cnic_number": "12345-1234567-1",
        "license_number": "",
        "registration_number": "",
    }
    ocr_fields = {
        "cnic_number": "12345-1234567-1",
        "name": "Another Person",
    }

    result = service._build_identity_cross_check("cnic", expected, ocr_fields)

    assert result["status"] == "soft_fail"
    assert result["mismatch_fields"] == ["name"]


def test_identity_cross_check_pass_when_profile_matches_ocr():
    expected = {
        "full_name": "Ali Raza",
        "cnic_number": "12345-1234567-1",
        "license_number": "",
        "registration_number": "",
    }
    ocr_fields = {
        "cnic_number": "12345-1234567-1",
        "name": "Ali Raza",
    }

    result = service._build_identity_cross_check("cnic", expected, ocr_fields)

    assert result["status"] == "pass"
    assert result["mismatch_fields"] == []


@pytest.mark.asyncio
async def test_process_verification_wrapper_returns_unified_payload(monkeypatch):
    verification_id = str(uuid4())

    async def fake_upload_document_service(**kwargs):
        return {
            "status": "ok",
            "data": {
                "verification_id": verification_id,
                "status": "verified",
                "ai_confidence": 0.93,
                "decision": "approved",
                "message": "Verified",
            },
            "error": None,
        }

    async def fake_get_verification_attempts(db, verification_uuid):
        assert isinstance(verification_uuid, UUID)
        return [_DummyAttempt(face_match_score=0.91, ocr_data=json.dumps({"cnic_number": "12345-1234567-1"}))]

    monkeypatch.setattr(service, "upload_document_service", fake_upload_document_service)
    monkeypatch.setattr(service.crud, "get_verification_attempts", fake_get_verification_attempts)

    result = await service.process_verification(
        db=SimpleNamespace(),
        user_id=uuid4(),
        document_file=FakeUploadFile("cnic.jpg", data=b"x" * 1024),
        document_back_file=None,
        selfie_file=None,
        document_type="cnic",
    )

    assert result["status"] == "verified"
    assert result["decision"] == "approved"
    assert result["confidence_score"] == 0.93
    assert result["face_match_score"] == 0.91
    assert result["ocr_fields"]["cnic_number"] == "12345-1234567-1"
    assert result["verification_id"] == verification_id


@pytest.mark.asyncio
async def test_process_verification_rejects_unknown_document_type():
    with pytest.raises(HTTPException) as exc:
        await service.process_verification(
            db=SimpleNamespace(),
            user_id=uuid4(),
            document_file=FakeUploadFile("doc.jpg", data=b"x" * 1024),
            document_back_file=None,
            selfie_file=None,
            document_type="invalid_doc_type",
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_document_service_adds_back_document_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path)

    verification_stub = SimpleNamespace(
        id=uuid4(),
        status=SimpleNamespace(value="verified"),
        ai_confidence=0.94,
    )
    captured = {}

    async def fake_ai_verification_service(**kwargs):
        return {
            "confidence": 0.94,
            "decision": "approved",
            "status": "verified",
            "doc_number": "12345-1234567-1",
            "ocr_confidence": 0.95,
            "face_match_score": 0.90,
            "ocr_data": {"cnic_number": "12345-1234567-1"},
            "remarks": "Verified",
            "metadata": {"identity_cross_check": {"status": "pass"}},
        }

    async def fake_create_verification(**kwargs):
        captured["verification_metadata"] = json.loads(kwargs["metadata"])
        return verification_stub

    async def fake_create_verification_attempt(**kwargs):
        captured["attempt_metadata"] = json.loads(kwargs["metadata"])
        return SimpleNamespace(id=uuid4())

    monkeypatch.setattr(service, "perform_ai_verification_service", fake_ai_verification_service)
    monkeypatch.setattr(service.crud, "create_verification", fake_create_verification)
    monkeypatch.setattr(service.crud, "create_verification_attempt", fake_create_verification_attempt)

    result = await service.upload_document_service(
        db=SimpleNamespace(),
        user_id=uuid4(),
        doc_type=DocumentTypeEnum.CNIC,
        file=FakeUploadFile("cnic_front.jpg", data=b"front-bytes" * 200),
        document_back_file=FakeUploadFile("cnic_back.jpg", data=b"back-bytes" * 200),
        selfie_file=FakeUploadFile("selfie.jpg", data=b"selfie-bytes" * 200),
    )

    assert result["status"] == "ok"
    assert "back_document_path" in captured["verification_metadata"]
    assert captured["attempt_metadata"]["back_document_path"] == captured["verification_metadata"]["back_document_path"]
