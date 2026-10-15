import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from opentelemetry import metrics, trace

from app.models.ocr_log_model import (
    STAGE_COMPLETED,
    STAGE_EXTRACTION,
    STAGE_OCR,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_SUCCESS,
    OcrLog,
)
from app.models.receipt_evidence import ReceiptEvidence
from app.services.blob_url import redact_secrets
from app.services.document_intelligence import DocumentIntelligenceOcr
from app.services.errors import ProcessingError
from app.services.mapping import map_extraction
from app.services.receipt_extractor import ReceiptExtractor
from app.tracer import get_logger, log_extra

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)
outcomes = meter.create_counter(
    "receipt_processing_outcomes",
    unit="1",
    description="Receipt processing results by outcome",
)


class ReceiptProcessor:
    def __init__(self, ocr: DocumentIntelligenceOcr, extractor: ReceiptExtractor, session_factory):
        self._ocr = ocr
        self._extractor = extractor
        self._session_factory = session_factory

    def run(self, evidence_id: uuid.UUID, access_url: str, ocr_log_id: uuid.UUID | None = None) -> None:
        started = time.perf_counter()
        evidence = str(evidence_id)
        with tracer.start_as_current_span("receipt.process") as span:
            span.set_attribute("receipt.evidence_id", evidence)
            log.info(
                "[Processor] receipt started",
                extra=log_extra(evidence_id=evidence, execution_step="receipt.process", status="started"),
            )
            session = self._session_factory()
            try:
                row = session.get(ReceiptEvidence, evidence_id)
                ocr_log = session.get(OcrLog, ocr_log_id) if ocr_log_id else None
                if row is None:
                    span.set_attribute("receipt.outcome", "missing")
                    outcomes.add(1, {"outcome": "missing"})
                    log.warning(
                        "[Processor] receipt disappeared before OCR",
                        extra=log_extra(evidence_id=evidence, execution_step="receipt.process", status="missing"),
                    )
                    return

                if ocr_log:
                    ocr_log.status = STATUS_PROCESSING
                    ocr_log.stage = STAGE_OCR
                    session.commit()

                try:
                    ocr_text = self._ocr.extract_text(access_url)

                    if ocr_log:
                        ocr_log.stage = STAGE_EXTRACTION
                        session.commit()

                    raw = self._extractor.extract(ocr_text)
                    for column, value in map_extraction(raw).items():
                        setattr(row, column, value)
                    row.extracted_data = raw
                    row.evidence_ready = True
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    if ocr_log:
                        ocr_log.status = STATUS_SUCCESS
                        ocr_log.stage = STAGE_COMPLETED
                        ocr_log.extracted_data = raw
                        ocr_log.duration_ms = Decimal(str(duration_ms))
                        ocr_log.error_stage = None
                        ocr_log.error_message = None
                        ocr_log.updated_at = datetime.now(timezone.utc)
                    span.set_attribute("receipt.outcome", "ready")
                    outcomes.add(1, {"outcome": "ready"})
                    log.info(
                        "[Processor] receipt ready",
                        extra=log_extra(
                            evidence_id=evidence,
                            execution_step="receipt.process",
                            status="ready",
                            duration_ms=duration_ms,
                        ),
                    )
                except ProcessingError as exc:
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    span.set_attribute("receipt.outcome", "failed")
                    span.set_attribute("receipt.stage", exc.stage)
                    outcomes.add(1, {"outcome": "failed", "stage": exc.stage})
                    _mark_failed(row, exc.stage, redact_secrets(str(exc)), evidence, started)
                    if ocr_log:
                        _mark_ocr_log_failed(ocr_log, exc.stage, redact_secrets(str(exc)), duration_ms)
                except Exception as exc:
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    stage = ocr_log.stage if ocr_log and ocr_log.stage else "processing"
                    span.set_attribute("receipt.outcome", "failed")
                    span.set_attribute("receipt.stage", stage)
                    outcomes.add(1, {"outcome": "failed", "stage": stage})
                    _mark_failed(row, stage, redact_secrets(str(exc)), evidence, started)
                    if ocr_log:
                        _mark_ocr_log_failed(ocr_log, stage, redact_secrets(str(exc)), duration_ms)
                row.updated_at = datetime.now(timezone.utc)
                session.commit()
            finally:
                session.close()


def _mark_failed(row: ReceiptEvidence, stage: str, message: str, evidence_id: str, started: float) -> None:
    row.evidence_ready = False
    row.extracted_data = {"error": message, "stage": stage}
    log.warning(
        "[Processor] receipt failed during %s: %s",
        stage,
        message,
        extra=log_extra(
            evidence_id=evidence_id,
            execution_step=stage,
            status="failed",
            stage=stage,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        ),
    )


def _mark_ocr_log_failed(ocr_log: OcrLog, stage: str, message: str, duration_ms: float) -> None:
    ocr_log.status = STATUS_FAILED
    ocr_log.error_stage = stage
    ocr_log.error_message = message
    ocr_log.duration_ms = Decimal(str(duration_ms))
    ocr_log.extracted_data = {"error": message, "stage": stage}
    ocr_log.updated_at = datetime.now(timezone.utc)
