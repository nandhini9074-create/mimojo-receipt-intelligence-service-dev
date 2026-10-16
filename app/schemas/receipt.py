import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CreateReceiptRequest(BaseModel):
    jira_ticket_id: uuid.UUID
    image_blob_url: str = Field(min_length=1, max_length=5000)


class ReceiptAccepted(BaseModel):
    id: uuid.UUID
    jira_ticket_id: uuid.UUID
    review_status: str
    evidence_ready: bool
    evidence_file_url: str

    model_config = {"from_attributes": True}


class ReceiptAcceptedResponse(BaseModel):
    statusCode: int = 200
    message: str = "Success"
    data: ReceiptAccepted



class ReceiptEvidenceView(BaseModel):
    id: uuid.UUID
    jira_ticket_id: uuid.UUID
    mid: str | None = None
    tid: str | None = None
    txn_amount: Decimal | None = None
    currency: str | None = None
    txn_date: datetime | None = None
    effective_date: date | None = None
    txn_reference: str | None = None
    auth_code: str | None = None
    card_last4: str | None = None
    scheme: str | None = None
    outlet_address: str | None = None
    evidence_file_url: str
    extraction_confidence: Decimal | None = None
    extracted_data: dict | None = None
    review_status: str
    evidence_ready: bool
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
