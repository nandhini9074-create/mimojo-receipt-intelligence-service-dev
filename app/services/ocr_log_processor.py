import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from opentelemetry import trace

from app.models.ocr_log_model import (
    STAGE_COMPLETED,
    STAGE_EXTRACTION,
    STAGE_OCR,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_SUCCESS,
    OcrLog,
)
from app.services.blob_url import redact_secrets
from app.services.document_intelligence import DocumentIntelligenceOcr
from app.services.errors import ProcessingError
from app.services.receipt_extractor import OCR_LOG_SYSTEM_PROMPT, ReceiptExtractor
from app.tracer import get_logger, log_extra

log = get_logger(__name__)
tracer = trace.get_tracer(__name__)


class OcrLogProcessor:
    def __init__(self, ocr: DocumentIntelligenceOcr, extractor: ReceiptExtractor, session_factory):
        self._ocr = ocr
        self._extractor = extractor
        self._session_factory = session_factory

    def run(self, log_id: uuid.UUID, access_url: str) -> None:
        started = time.perf_counter()
        log_id_str = str(log_id)
        with tracer.start_as_current_span("ocr_log.process") as span:
            span.set_attribute("ocr_log.id", log_id_str)
            log.info(
                "[OcrLogProcessor] process started",
                extra=log_extra(evidence_id=log_id_str, execution_step="ocr_log.process", status="started"),
            )
            session = self._session_factory()
            try:
                row = session.get(OcrLog, log_id)
                if row is None:
                    log.warning(
                        "[OcrLogProcessor] row disappeared before processing",
                        extra=log_extra(evidence_id=log_id_str, status="missing"),
                    )
                    return

                row.status = STATUS_PROCESSING
                row.stage = STAGE_OCR
                session.commit()

                try:
                    ocr_text = self._ocr.extract_text(access_url)

                    row.stage = STAGE_EXTRACTION
                    session.commit()

                    raw = self._extractor.extract(ocr_text, system_prompt=OCR_LOG_SYSTEM_PROMPT)

                    row.extracted_data = raw
                    row.status = STATUS_SUCCESS
                    row.stage = STAGE_COMPLETED
                    row.error_stage = None
                    row.error_message = None
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    row.duration_ms = Decimal(str(duration_ms))

                    log.info(
                        "[OcrLogProcessor] process success",
                        extra=log_extra(
                            evidence_id=log_id_str,
                            execution_step="ocr_log.process",
                            status="success",
                            duration_ms=duration_ms,
                        ),
                    )
                except ProcessingError as exc:
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    _mark_failed(row, exc.stage, redact_secrets(str(exc)), duration_ms, log_id_str)
                except Exception as exc:
                    duration_ms = round((time.perf_counter() - started) * 1000, 2)
                    _mark_failed(row, row.stage or "processing", redact_secrets(str(exc)), duration_ms, log_id_str)

                row.updated_at = datetime.now(timezone.utc)
                session.commit()
            finally:
                session.close()


def _mark_failed(row: OcrLog, stage: str, message: str, duration_ms: float, log_id_str: str) -> None:
    row.status = STATUS_FAILED
    row.error_stage = stage
    row.error_message = message
    row.duration_ms = Decimal(str(duration_ms))
    row.extracted_data = {"error": message, "stage": stage}
    log.warning(
        "[OcrLogProcessor] process failed during %s: %s",
        stage,
        message,
        extra=log_extra(
            evidence_id=log_id_str,
            execution_step=stage,
            status="failed",
            stage=stage,
            duration_ms=duration_ms,
        ),
    )
