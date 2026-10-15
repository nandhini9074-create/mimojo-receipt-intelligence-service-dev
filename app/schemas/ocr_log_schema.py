import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class CreateOcrLogRequest(BaseModel):
    image_blob_url: str = Field(min_length=1, max_length=5000, description="HTTPS blob URL of the receipt slip")


class OcrLogAccepted(BaseModel):
    id: uuid.UUID
    image_url: str
    status: str
    stage: str

    model_config = {"from_attributes": True}


class OcrLogView(BaseModel):
    id: uuid.UUID
    image_url: str
    status: str
    stage: str
    duration_ms: Decimal | None = None
    extracted_data: dict | None = None
    error_stage: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
