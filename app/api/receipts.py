import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.models.receipt_evidence import REVIEW_NEW, ReceiptEvidence
from app.schemas.receipt import CreateReceiptRequest, ReceiptAccepted, ReceiptEvidenceView
from app.services.blob_url import BlobUrlError, access_url, storage_url
from app.tracer import get_logger, log_extra

log = get_logger(__name__)
router = APIRouter(prefix="/receipts", tags=["receipts"])


def get_db(request: Request):
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@router.post("", status_code=202, response_model=ReceiptAccepted)
def create_receipt(
    body: CreateReceiptRequest,
    background: BackgroundTasks,
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

    row = ReceiptEvidence(
        jira_ticket_id=body.jira_ticket_id,
        evidence_file_url=stored,
        review_status=REVIEW_NEW,
        evidence_ready=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    background.add_task(request.app.state.processor.run, row.id, readable)
    log.info(
        "[API] receipt accepted",
        extra=log_extra(
            evidence_id=str(row.id),
            jira_ticket_id=body.jira_ticket_id,
            execution_step="intake",
            status="accepted",
        ),
    )
    return row


@router.get("/{evidence_id}", response_model=ReceiptEvidenceView)
def get_receipt(evidence_id: uuid.UUID, db: Session = Depends(get_db)):
    row = db.get(ReceiptEvidence, evidence_id)
    if row is None:
        log.warning(
            "[API] receipt not found",
            extra=log_extra(evidence_id=str(evidence_id), execution_step="read", status="not_found"),
        )
        raise HTTPException(status_code=404, detail="Receipt evidence not found")
    return row
