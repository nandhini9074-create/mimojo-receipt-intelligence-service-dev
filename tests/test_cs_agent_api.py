import uuid
from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app
from app.services.errors import ProcessingError
from app.services.ocr_log_processor import OcrLogProcessor
from app.services.receipt_extractor import OCR_LOG_SYSTEM_PROMPT


class RecordingOcr:
    def __init__(self):
        self.urls: list[str] = []

    def extract_text(self, url: str) -> str:
        self.urls.append(url)
        return "MID M1 TID T1 TOTAL 50.00 AED AMEX 1234"


class RecordingExtractor:
    def __init__(self):
        self.captured_prompt: str | None = None

    def extract(self, ocr_text: str, system_prompt: str | None = None) -> dict:
        self.captured_prompt = system_prompt
        return {
            "mid": "M1",
            "tid": "T1",
            "txn_amount": 50,
            "currency": "AED",
            "txn_date": "2026-10-15T12:00:00Z",
            "txn_reference": "RRN999",
            "auth_code": "AUTH1",
            "card_last4": "1234",
            "scheme": "American Express",
            "outlet_address": "Dubai Mall",
            "confidence": 0.95,
        }


def _client(sas_token: str = "sig=env") -> TestClient:
    app = create_app(Settings(database_url="sqlite://", blob_sas_token=sas_token))
    return TestClient(app)


def test_post_cs_agent_receipt_accepts_and_processes_in_background():
    app = create_app(Settings(database_url="sqlite://", blob_sas_token="sig=env"))
    ocr = RecordingOcr()
    extractor = RecordingExtractor()
    with TestClient(app) as client:
        app.state.ocr_log_processor = OcrLogProcessor(ocr, extractor, app.state.session_factory)
        response = client.post(
            "/api/v1/cs-agent/receipts",
            json={
                "image_blob_url": "https://storage.example/receipts/cs-receipt.pdf",
            },
        )
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "PENDING"
        assert body["stage"] == "intake"
        assert body["image_url"] == "https://storage.example/receipts/cs-receipt.pdf"
        assert ocr.urls == ["https://storage.example/receipts/cs-receipt.pdf?sig=env"]

        stored = client.get(f"/api/v1/cs-agent/receipts/{body['id']}")

    assert stored.status_code == 200
    stored_body = stored.json()
    assert stored_body["status"] == "SUCCESS"
    assert stored_body["stage"] == "completed"
    assert stored_body["duration_ms"] is not None
    assert stored_body["extracted_data"]["scheme"] == "American Express"
    assert stored_body["extracted_data"]["card_last4"] == "1234"
    assert extractor.captured_prompt == OCR_LOG_SYSTEM_PROMPT


def test_post_cs_agent_receipt_rejects_non_https():
    with _client() as client:
        response = client.post(
            "/api/v1/cs-agent/receipts",
            json={"image_blob_url": "http://insecure.example/receipt.pdf"},
        )
    assert response.status_code == 422


def test_get_missing_cs_agent_receipt_is_404():
    with _client() as client:
        response = client.get(f"/api/v1/cs-agent/receipts/{uuid.uuid4()}")
    assert response.status_code == 404


def test_cs_agent_receipt_records_ocr_failure():
    app = create_app(Settings(database_url="sqlite://", blob_sas_token="sig=env"))

    class FailingOcr:
        def extract_text(self, url: str) -> str:
            raise ProcessingError("ocr", "storage rejected the signature https://blob/file.pdf?sig=secret")

    with TestClient(app) as client:
        app.state.ocr_log_processor = OcrLogProcessor(FailingOcr(), RecordingExtractor(), app.state.session_factory)
        created = client.post(
            "/api/v1/cs-agent/receipts",
            json={"image_blob_url": "https://storage.example/receipt.pdf?sig=caller"},
        )
        stored = client.get(f"/api/v1/cs-agent/receipts/{created.json()['id']}")

    assert created.status_code == 202
    assert stored.status_code == 200
    stored_body = stored.json()
    assert stored_body["status"] == "FAILED"
    assert stored_body["error_stage"] == "ocr"
    assert "?redacted" in stored_body["error_message"]
    assert "sig=secret" not in stored_body["error_message"]
    assert stored_body["extracted_data"] == {
        "error": "storage rejected the signature https://blob/file.pdf?redacted",
        "stage": "ocr",
    }
