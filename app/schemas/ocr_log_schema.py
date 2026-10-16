from typing import Any
import uuid
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator


class CreateOcrLogRequest(BaseModel):
    image_blob_url: str = Field(min_length=1, max_length=5000, description="HTTPS blob URL of the receipt slip")


class OcrLogAccepted(BaseModel):
    id: uuid.UUID
    image_url: str
    status: str
    stage: str
    extracted_data: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def bind_extracted_data(cls, v: Any) -> Any:
        if isinstance(v, dict):
            if "extracted_data" not in v and "data" in v:
                v["extracted_data"] = v.pop("data")
        return v

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

    @model_validator(mode="before")
    @classmethod
    def bind_extracted_data(cls, v: Any) -> Any:
        if isinstance(v, dict):
            if "extracted_data" not in v and "data" in v:
                v["extracted_data"] = v.pop("data")
        return v

    model_config = {"from_attributes": True}


class OcrLogResponse(BaseModel):
    statusCode: int = 200
    message: str = "Success"
    data: OcrLogView

