import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

from app.config import Settings
from app.services.blob_url import redact_secrets
from app.services.errors import ProcessingError
from app.tracer import get_logger, log_extra

log = get_logger(__name__)
_DOWNLOAD_TIMEOUT_SECONDS = 60


def download_document(url: str) -> bytes:
    """Download the receipt here. A rejected signature falls back to the same link without the query string."""
    payload = _read(url)
    if payload is None and "?" in url:
        payload = _read(url.split("?", 1)[0])
    if payload is None:
        raise ProcessingError(
            "ocr",
            "Could not download the receipt: storage rejected the request signature",
        )
    return payload


def _read(url: str) -> bytes | None:
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
            payload = response.read()
    except HTTPError as exc:
        if exc.code == 403:
            return None
        raise ProcessingError("ocr", redact_secrets(f"Could not download the receipt: {exc}")) from exc
    except (URLError, TimeoutError) as exc:
        raise ProcessingError("ocr", redact_secrets(f"Could not download the receipt: {exc}")) from exc
    if not payload:
        raise ProcessingError("ocr", "Receipt file is empty")
    return payload


class DocumentIntelligenceOcr:
    """OCR step of the ARGUS hybrid pipeline. prebuilt-read returns slip text; field mapping is done by the model."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def extract_text(self, url: str) -> str:
        if not self._settings.document_intelligence_endpoint or not self._settings.document_intelligence_key:
            raise ProcessingError("ocr", "Document Intelligence is not configured")

        log.info("[OCR] document intelligence started", extra=log_extra(execution_step="ocr", status="started"))
        started = time.perf_counter()
        try:
            document = download_document(url)
            client = DocumentIntelligenceClient(
                endpoint=self._settings.document_intelligence_endpoint,
                credential=AzureKeyCredential(self._settings.document_intelligence_key),
            )
            poller = client.begin_analyze_document("prebuilt-read", AnalyzeDocumentRequest(bytes_source=document))
            result = poller.result()
        except ProcessingError:
            raise
        except Exception as exc:
            raise ProcessingError("ocr", redact_secrets(str(exc))) from exc

        content = (result.content or "").strip()
        if not content:
            raise ProcessingError("ocr", "Document Intelligence returned no text")
        log.info(
            "[OCR] document intelligence finished chars=%s",
            len(content),
            extra=log_extra(
                execution_step="ocr",
                status="success",
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            ),
        )
        return content
