import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Index, Numeric, String, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base

REVIEW_NEW = "NEW"
REVIEW_APPROVED = "APPROVED"
REVIEW_REJECTED = "REJECTED"


class ReceiptEvidence(Base):
    __tablename__ = "receipt_evidence"
    __table_args__ = (
        CheckConstraint(
            f"review_status IN ('{REVIEW_NEW}', '{REVIEW_APPROVED}', '{REVIEW_REJECTED}')",
            name="ck_receipt_evidence_review_status",
        ),
        Index("ix_receipt_evidence_jira_ticket_id", "jira_ticket_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jira_ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    mid: Mapped[str | None] = mapped_column(String(100))
    tid: Mapped[str | None] = mapped_column(String(100))
    txn_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    txn_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_date: Mapped[date | None] = mapped_column(Date)
    txn_reference: Mapped[str | None] = mapped_column(String(150))
    auth_code: Mapped[str | None] = mapped_column(String(50))
    card_last4: Mapped[str | None] = mapped_column(String(4))
    scheme: Mapped[str | None] = mapped_column(String(30))
    outlet_address: Mapped[str | None] = mapped_column(String(250))
    evidence_file_url: Mapped[str] = mapped_column(String(200), nullable=False)
    extraction_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    extracted_data: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default=REVIEW_NEW, server_default=REVIEW_NEW)
    evidence_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    reviewed_by: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
