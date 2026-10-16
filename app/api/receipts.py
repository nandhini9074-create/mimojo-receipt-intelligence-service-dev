import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.ocr_log_model import STAGE_INTAKE, STATUS_PENDING, OcrLog
from app.models.receipt_evidence import REVIEW_NEW, ReceiptEvidence
from app.schemas.ocr_log_schema import (
    CreateOcrLogRequest,
    OcrLogAccepted,
    OcrLogResponse,
    OcrLogView,
)
from app.schemas.receipt import (
    CreateReceiptRequest,
    ReceiptAccepted,
    ReceiptAcceptedResponse,
    ReceiptEvidenceView,
)
from app.services.blob_url import BlobUrlError, access_url, storage_url
from app.tracer import get_logger, log_extra

log = get_logger(__name__)
router = APIRouter(tags=["receipts"])


def get_db(request: Request):
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Core Receipt Intelligence Endpoints (/receipts)
# ---------------------------------------------------------------------------


@router.post("/receipts", status_code=200, response_model=ReceiptAcceptedResponse)
def create_receipt(
    body: CreateReceiptRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        stored = storage_url(body.image_blob_url)
        readable = access_url(body.image_blob_url, request.app.state.settings.blob_sas_token)
    except BlobUrlError as exc:
        log.warning(
            "[API] receipt rejected: %s",
            exc,
            extra=log_extra(
                jira_ticket_id=body.jira_ticket_id,
                execution_step="intake",
                status="rejected",
            ),
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    evidence_row = ReceiptEvidence(
        jira_ticket_id=body.jira_ticket_id,
        evidence_file_url=stored,
        review_status=REVIEW_NEW,
        evidence_ready=False,
    )
    ocr_log_row = OcrLog(
        image_url=stored,
        status=STATUS_PENDING,
        stage=STAGE_INTAKE,
    )
    db.add(evidence_row)
    db.add(ocr_log_row)
    db.commit()
    db.refresh(evidence_row)
    db.refresh(ocr_log_row)

    request.app.state.processor.run(
        evidence_row.id,
        readable,
        ocr_log_id=ocr_log_row.id,
    )
    db.refresh(evidence_row)
    log.info(
        "[API] receipt processed synchronously",
        extra=log_extra(
            evidence_id=str(evidence_row.id),
            jira_ticket_id=body.jira_ticket_id,
            execution_step="receipt.process",
            status="ready" if evidence_row.evidence_ready else "failed",
        ),
    )
    return ReceiptAcceptedResponse(statusCode=200, message="Success", data=evidence_row)


@router.get("/receipts/{evidence_id}", response_model=ReceiptEvidenceView)
def get_receipt(evidence_id: uuid.UUID, db: Session = Depends(get_db)):
    row = db.get(ReceiptEvidence, evidence_id)
    if row is None:
        log.warning(
            "[API] receipt not found",
            extra=log_extra(evidence_id=str(evidence_id), execution_step="read", status="not_found"),
        )
        raise HTTPException(status_code=404, detail="Receipt evidence not found")
    return row


# ---------------------------------------------------------------------------
# CS-Agent Receipt Intelligence Endpoints (/cs-agent/receipts)
# ---------------------------------------------------------------------------


@router.post("/cs-agent/receipts", status_code=200, response_model=OcrLogResponse)
def create_cs_agent_receipt(
    body: CreateOcrLogRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        stored = storage_url(body.image_blob_url)
        readable = access_url(body.image_blob_url, request.app.state.settings.blob_sas_token)
    except BlobUrlError as exc:
        log.warning(
            "[CsAgentAPI] receipt rejected: %s",
            exc,
            extra=log_extra(execution_step="intake", status="rejected"),
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = OcrLog(
        image_url=stored,
        status=STATUS_PENDING,
        stage=STAGE_INTAKE,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    request.app.state.ocr_log_processor.run(row.id, readable)
    db.refresh(row)
    log.info(
        "[CsAgentAPI] receipt processed synchronously",
        extra=log_extra(
            evidence_id=str(row.id),
            execution_step="ocr_log.process",
            status=row.status,
        ),
    )
    return OcrLogResponse(statusCode=200, message="Success", data=row)


@router.get("/cs-agent/receipts/{id}", response_model=OcrLogResponse)
def get_cs_agent_receipt(id: uuid.UUID, db: Session = Depends(get_db)):
    row = db.get(OcrLog, id)
    if row is None:
        log.warning(
            "[CsAgentAPI] receipt log not found",
            extra=log_extra(evidence_id=str(id), execution_step="read", status="not_found"),
        )
        raise HTTPException(status_code=404, detail="OCR log not found")
    return OcrLogResponse(statusCode=200, message="Success", data=row)

