import uuid

from app.config import Settings
from app.db import Base, make_engine, make_session_factory
from app.models.receipt_evidence import REVIEW_NEW, ReceiptEvidence
from app.services.errors import ProcessingError
from app.services.receipt_processor import ReceiptProcessor


class StubOcr:
    def __init__(self, text: str = "slip", error: Exception | None = None):
        self.text = text
        self.error = error
        self.urls: list[str] = []

    def extract_text(self, url: str) -> str:
        self.urls.append(url)
        if self.error:
            raise self.error
        return self.text


class StubExtractor:
    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self.payload = payload or {}
        self.error = error

    def extract(self, ocr_text: str) -> dict:
        if self.error:
            raise self.error
        return self.payload


def _session_factory():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return make_session_factory(engine)


def _seed(session_factory) -> uuid.UUID:
    session = session_factory()
    row = ReceiptEvidence(
        jira_ticket_id=uuid.UUID("759a4289-cc8d-407d-94e0-98589d702f37"),
        evidence_file_url="https://storage.example/receipt.pdf",
        review_status=REVIEW_NEW,
        evidence_ready=False,
    )
    session.add(row)
    session.commit()
    evidence_id = row.id
    session.close()
    return evidence_id


def test_successful_scan_fills_the_row_and_marks_it_ready():
    session_factory = _session_factory()
    evidence_id = _seed(session_factory)
    processor = ReceiptProcessor(
        ocr=StubOcr(),
        extractor=StubExtractor(
            {
                "mid": "M1",
                "tid": "T1",
                "txn_amount": 18.25,
                "currency": "AED",
                "txn_date": "2026-10-08T09:15:00+04:00",
                "txn_reference": "RRN9",
                "auth_code": "OK1",
                "card_last4": "1111",
                "scheme": "Mastercard",
                "outlet_address": "Marina",
                "confidence": 0.8,
            }
        ),
        session_factory=session_factory,
    )

    processor.run(evidence_id, "https://storage.example/receipt.pdf?sig=secret")

    session = session_factory()
    row = session.get(ReceiptEvidence, evidence_id)
    assert row.evidence_ready is True
    assert row.review_status == REVIEW_NEW
    assert row.mid == "M1"
    assert row.currency == "AED"
    assert row.extracted_data["txn_reference"] == "RRN9"
    assert "sig=secret" not in str(row.extracted_data)
    session.close()


def test_ocr_failure_keeps_the_row_and_records_the_error():
    session_factory = _session_factory()
    evidence_id = _seed(session_factory)
    processor = ReceiptProcessor(
        ocr=StubOcr(error=ProcessingError("ocr", "blob missing https://blob/file.pdf?sig=secret")),
        extractor=StubExtractor(),
        session_factory=session_factory,
    )

    processor.run(evidence_id, "https://storage.example/receipt.pdf?sig=secret")

    session = session_factory()
    row = session.get(ReceiptEvidence, evidence_id)
    assert row.evidence_ready is False
    assert row.mid is None
    assert row.extracted_data == {
        "error": "blob missing https://blob/file.pdf?redacted",
        "stage": "ocr",
    }
    session.close()


def test_settings_are_constructable_for_sqlite():
    settings = Settings(database_url="sqlite://", blob_sas_token="sig=test")
    assert settings.database_url == "sqlite://"
    assert settings.blob_sas_token == "sig=test"
