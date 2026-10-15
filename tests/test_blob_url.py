import pytest

from app.services.blob_url import BlobUrlError, access_url, redact_secrets, storage_url


def test_storage_url_drops_the_sas_query():
    stored = storage_url("https://storage.example/receipts/receipt-123.pdf?sig=secret")
    assert stored == "https://storage.example/receipts/receipt-123.pdf"


def test_access_url_appends_sas_when_the_caller_omits_it():
    readable = access_url("https://storage.example/receipts/receipt-123.pdf", "?sig=secret")
    assert readable == "https://storage.example/receipts/receipt-123.pdf?sig=secret"


def test_access_url_keeps_a_caller_supplied_query():
    original = "https://storage.example/receipts/receipt-123.pdf?sig=caller"
    assert access_url(original, "sig=ignored") == original


def test_rejects_non_https_and_missing_sas():
    with pytest.raises(BlobUrlError):
        storage_url("http://storage.example/receipt.pdf")
    with pytest.raises(BlobUrlError):
        access_url("https://storage.example/receipt.pdf", "")


def test_redacts_query_strings_from_errors():
    assert redact_secrets("failed for https://blob/file.pdf?sig=secret token") == (
        "failed for https://blob/file.pdf?redacted token"
    )
