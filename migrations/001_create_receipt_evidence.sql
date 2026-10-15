-- Matches app/models/receipt_evidence.py
-- Local startup also creates this table from the SQLAlchemy model.

CREATE TABLE IF NOT EXISTS receipt_evidence (
    id UUID PRIMARY KEY,
    jira_ticket_id UUID NOT NULL,
    mid VARCHAR(100),
    tid VARCHAR(100),
    txn_amount NUMERIC(18, 2),
    currency VARCHAR(3),
    txn_date TIMESTAMPTZ,
    effective_date DATE,
    txn_reference VARCHAR(150),
    auth_code VARCHAR(50),
    card_last4 VARCHAR(4),
    scheme VARCHAR(30),
    outlet_address VARCHAR(250),
    evidence_file_url VARCHAR(200) NOT NULL,
    extraction_confidence NUMERIC(5, 4),
    extracted_data JSONB,
    review_status VARCHAR(30) NOT NULL DEFAULT 'NEW',
    evidence_ready BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_receipt_evidence_review_status
        CHECK (review_status IN ('NEW', 'APPROVED', 'REJECTED'))
);

CREATE INDEX IF NOT EXISTS ix_receipt_evidence_jira_ticket_id
    ON receipt_evidence (jira_ticket_id);
