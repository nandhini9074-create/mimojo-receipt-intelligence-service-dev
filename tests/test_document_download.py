from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from app.services.document_intelligence import download_document
from app.services.errors import ProcessingError


def _forbidden(url: str) -> HTTPError:
    return HTTPError(url=url, code=403, msg="Forbidden", hdrs=None, fp=BytesIO())


def test_download_document_returns_the_file_bytes():
    with patch("app.services.document_intelligence.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = b"receipt-bytes"
        payload = download_document("https://storage.example/receipt.jpg?sig=secret")

    assert payload == b"receipt-bytes"


def test_download_document_retries_without_the_rejected_signature():
    signed = "https://storage.example/receipt.jpg?sig=secret"
    calls = []

    def open_url(request, timeout):
        calls.append(request.full_url)
        if "?" in request.full_url:
            raise _forbidden(request.full_url)
        response = BytesIO(b"receipt-bytes")
        response.__enter__ = lambda: response
        response.__exit__ = lambda *args: None
        return response

    with patch("app.services.document_intelligence.urlopen", side_effect=open_url):
        assert download_document(signed) == b"receipt-bytes"

    assert calls == [signed, "https://storage.example/receipt.jpg"]


def test_download_document_reports_a_rejected_signature():
    with patch("app.services.document_intelligence.urlopen", side_effect=_forbidden("https://storage.example/receipt.jpg?sig=secret")):
        with pytest.raises(ProcessingError, match="rejected the request signature"):
            download_document("https://storage.example/receipt.jpg?sig=secret")


def test_download_document_redacts_a_sas_included_in_the_error():
    with patch(
        "app.services.document_intelligence.urlopen",
        side_effect=URLError("failed for https://storage.example/receipt.jpg?sig=secret"),
    ):
        with pytest.raises(ProcessingError) as caught:
            download_document("https://storage.example/receipt.jpg?sig=secret")

    assert "sig=secret" not in str(caught.value)
    assert "?redacted" in str(caught.value)
