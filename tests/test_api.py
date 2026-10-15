from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app
from app.services.errors import ProcessingError
from app.services.receipt_processor import ReceiptProcessor


class RecordingOcr:
    def __init__(self):
        self.urls: list[str] = []

    def extract_text(self, url: str) -> str:
        self.urls.append(url)
        return "MID M1 TID T1 TOTAL 10.00 AED"


class RecordingExtractor:
    def extract(self, ocr_text: str) -> dict:
        return {
            "mid": "M1",
            "tid": "T1",
            "txn_amount": 10,
            "currency": "AED",
            "txn_date": "2026-10-08T10:00:00Z",
            "txn_reference": "RRN1",
            "auth_code": "AUTH",
            "card_last4": "4242",
            "scheme": "Visa",
            "outlet_address": "Dubai",
            "confidence": 0.75,
        }


def _client(sas_token: str = "sig=env") -> TestClient:
    app = create_app(Settings(database_url="sqlite://", blob_sas_token=sas_token))
    return TestClient(app)


def test_post_accepts_the_slip_and_finishes_ocr_in_the_background():
    app = create_app(Settings(database_url="sqlite://", blob_sas_token="sig=env"))
    ocr = RecordingOcr()
    with TestClient(app) as client:
        app.state.processor = ReceiptProcessor(ocr, RecordingExtractor(), app.state.session_factory)
        response = client.post(
            "/api/v1/receipts",
            json={
                "jira_ticket_id": "759a4289-cc8d-407d-94e0-98589d702f37",
                "image_blob_url": "https://storage.example/receipts/receipt-123.pdf",
            },
        )
        assert response.status_code == 202
        body = response.json()
        assert body["review_status"] == "NEW"
        assert body["evidence_ready"] is False
        assert body["evidence_file_url"] == "https://storage.example/receipts/receipt-123.pdf"
        assert "sig=" not in body["evidence_file_url"]
        assert ocr.urls == ["https://storage.example/receipts/receipt-123.pdf?sig=env"]

        stored = client.get(f"/api/v1/receipts/{body['id']}")

    assert stored.status_code == 200
    assert stored.json()["evidence_ready"] is True
    assert stored.json()["mid"] == "M1"
    assert stored.json()["card_last4"] == "4242"


def test_post_rejects_a_jira_ticket_id_that_is_not_a_uuid():
    with _client() as client:
        response = client.post(
            "/api/v1/receipts",
            json={
                "jira_ticket_id": "ticket-1",
                "image_blob_url": "https://storage.example/receipt.pdf",
            },
        )
    assert response.status_code == 422


def test_post_rejects_a_blob_url_without_https():
    with _client() as client:
        response = client.post(
            "/api/v1/receipts",
            json={
                "jira_ticket_id": "759a4289-cc8d-407d-94e0-98589d702f37",
                "image_blob_url": "http://storage.example/receipt.pdf",
            },
        )
    assert response.status_code == 422


def test_get_missing_receipt_is_404():
    with _client() as client:
        response = client.get("/api/v1/receipts/759a4289-cc8d-407d-94e0-98589d702f37")
    assert response.status_code == 404


def test_health():
    with _client() as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_background_failure_is_visible_on_the_saved_row():
    app = create_app(Settings(database_url="sqlite://", blob_sas_token="sig=env"))

    class FailingOcr:
        def extract_text(self, url: str) -> str:
            raise ProcessingError("ocr", "container not found")

    with TestClient(app) as client:
        app.state.processor = ReceiptProcessor(FailingOcr(), RecordingExtractor(), app.state.session_factory)
        created = client.post(
            "/api/v1/receipts",
            json={
                "jira_ticket_id": "8f0a1c2e-4b6d-4e8a-9c1f-2a7b6d5e4c30",
                "image_blob_url": "https://storage.example/receipt.pdf?sig=caller",
            },
        )
        stored = client.get(f"/api/v1/receipts/{created.json()['id']}")

    assert created.status_code == 202
    assert created.json()["evidence_file_url"] == "https://storage.example/receipt.pdf"
    assert stored.json()["evidence_ready"] is False
    assert stored.json()["extracted_data"]["stage"] == "ocr"
