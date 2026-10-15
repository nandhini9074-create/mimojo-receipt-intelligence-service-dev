# mimojo-receipt-intelligence-service

OCR layer for a payment terminal slip. A caller posts a Jira ticket id and a blob URL. The service stores a `receipt_evidence` row in Postgres, reads the file, and fills the transaction fields.

The processing shape follows [Azure-Samples/ARGUS](https://github.com/Azure-Samples/ARGUS): Document Intelligence reads the document, then Azure OpenAI maps that text onto a fixed JSON schema. This service keeps that scan path only. Results go to Postgres. There is no Cosmos DB, dataset catalog, chat, or second OCR provider.

Blob URLs follow `mimojo-outlet-images-service`: the value must be `https`, and a SAS query is not stored. When the caller omits a query string, `BLOB_SAS_TOKEN` is appended for the read.

## Flow

1. `POST /api/v1/receipts` validates the body and inserts a row with `review_status = NEW` and `evidence_ready = false`.
2. The response is `202` with the new id. The SAS URL stays in memory for the background job.
3. Azure Document Intelligence `prebuilt-read` returns the slip text.
4. Azure OpenAI returns the receipt schema: merchant id, terminal id, amount, currency, date, reference, auth code, card last 4, scheme, outlet address, and a confidence score.
5. The same row is updated. A completed extraction sets `evidence_ready` to true and leaves `review_status` as `NEW`.
6. A blob, OCR, or model failure keeps the row, leaves `evidence_ready` false, and writes `{"error", "stage"}` into `extracted_data`.

`GET /api/v1/receipts/{id}` returns the row so the caller can poll. Review approval is not part of this skeleton.

Request validation failures (a non-https URL, a stored URL longer than 200 characters, or a missing SAS token when the URL has no query) return `422` and do not insert a row.

## API

```http
POST /api/v1/receipts
Content-Type: application/json

{
  "jira_ticket_id": "759a4289-cc8d-407d-94e0-98589d702f37",
  "image_blob_url": "https://storage.example/receipts/receipt-123.pdf"
}
```

```json
{
  "id": "2d8c1c2e-1b4a-4f0e-9c2a-6b7e0e5a9c11",
  "jira_ticket_id": "759a4289-cc8d-407d-94e0-98589d702f37",
  "review_status": "NEW",
  "evidence_ready": false,
  "evidence_file_url": "https://storage.example/receipts/receipt-123.pdf"
}
```

`jira_ticket_id` is stored as a UUID. `effective_date` is a date. `evidence_file_url` is the blob URL with the query string removed.

## Local run

```powershell
copy .env.example .env
docker compose up --build
```

The API listens on `http://localhost:3000`. Tables are created on startup. `migrations/001_create_receipt_evidence.sql` is the same Postgres schema for a manual apply.

Without Docker, point `DATABASE_URL` at Postgres and run:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

## Tests

```powershell
pytest
```

## Configuration

| Variable | Use |
| --- | --- |
| `DATABASE_URL` | Postgres URL. Local default is `postgresql+psycopg://receipt:receipt@localhost:5432/receipt_intelligence`. |
| `BLOB_SAS_TOKEN` | Appended when `image_blob_url` has no query string. |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | Document Intelligence endpoint. |
| `AZURE_DOCUMENT_INTELLIGENCE_KEY` | Document Intelligence key. |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint. Same name as outlet-images. |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI key. |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment used for the receipt schema. |
| `AZURE_OPENAI_API_VERSION` | Defaults to `2024-10-21`. |
| `ENVIRONMENT` | Deployment name attached to telemetry. Local value is `dev`. |
| `OTEL_SERVICE_NAME` | Service name in Grafana. Set to `mimojo-receipt-intelligence`. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP HTTP collector (`http://host:4318`). Traces go to Tempo, logs to Loki, and metrics to the same collector. Leave empty to run without export. |

The background job runs in the API process. A restart before OCR finishes leaves the row with `evidence_ready = false`, and the SAS URL is not stored for a retry.
