import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Index, Numeric, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base

STATUS_PENDING = "PENDING"
STATUS_PROCESSING = "PROCESSING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"

STAGE_INTAKE = "intake"
STAGE_DOWNLOAD = "download"
STAGE_OCR = "ocr"
STAGE_EXTRACTION = "extraction"
STAGE_COMPLETED = "completed"


class OcrLog(Base):
    __tablename__ = "ocr_logs"
    __table_args__ = (
        CheckConstraint(
            f"status IN ('{STATUS_PENDING}', '{STATUS_PROCESSING}', '{STATUS_SUCCESS}', '{STATUS_FAILED}')",
            name="ck_ocr_logs_status",
        ),
        CheckConstraint(
            f"stage IN ('{STAGE_INTAKE}', '{STAGE_DOWNLOAD}', '{STAGE_OCR}', '{STAGE_EXTRACTION}', '{STAGE_COMPLETED}')",
            name="ck_ocr_logs_stage",
        ),
        Index("ix_ocr_logs_status", "status"),
        Index("ix_ocr_logs_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=STATUS_PENDING, server_default=STATUS_PENDING)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default=STAGE_INTAKE, server_default=STAGE_INTAKE)
    duration_ms: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    extracted_data: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    error_stage: Mapped[str | None] = mapped_column(String(30))
    error_message: Mapped[str | None] = mapped_column(Text)

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
