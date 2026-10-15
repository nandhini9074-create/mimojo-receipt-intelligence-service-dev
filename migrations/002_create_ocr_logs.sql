-- Matches app/models/ocr_log.py
-- Local startup also creates this table from the SQLAlchemy model.

CREATE TABLE IF NOT EXISTS ocr_logs (
    id UUID PRIMARY KEY,
    image_url VARCHAR(500) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    stage VARCHAR(30) NOT NULL DEFAULT 'intake',
    duration_ms NUMERIC(10, 2),
    extracted_data JSONB,
    error_stage VARCHAR(30),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_ocr_logs_status
        CHECK (status IN ('PENDING', 'PROCESSING', 'SUCCESS', 'FAILED')),
    CONSTRAINT ck_ocr_logs_stage
        CHECK (stage IN ('intake', 'download', 'ocr', 'extraction', 'completed'))
);

CREATE INDEX IF NOT EXISTS ix_ocr_logs_status ON ocr_logs (status);
CREATE INDEX IF NOT EXISTS ix_ocr_logs_created_at ON ocr_logs (created_at DESC);
