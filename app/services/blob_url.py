import re

MAX_REQUEST_URL_LENGTH = 5000
MAX_STORED_URL_LENGTH = 200


class BlobUrlError(ValueError):
    pass


def storage_url(image_blob_url: str) -> str:
    """URL persisted on receipt_evidence. Query strings, including SAS tokens, are removed."""
    if not image_blob_url.startswith("https://"):
        raise BlobUrlError('Invalid blobUrl: Must start with "https://"')
    if len(image_blob_url) > MAX_REQUEST_URL_LENGTH:
        raise BlobUrlError("Invalid blobUrl: Must be 5000 characters or fewer")

    sanitized = image_blob_url.split("?", 1)[0]
    if len(sanitized) > MAX_STORED_URL_LENGTH:
        raise BlobUrlError("Sanitized blob URL exceeds the evidence_file_url limit of 200 characters")
    return sanitized


def access_url(image_blob_url: str, sas_token: str) -> str:
    """URL passed to Document Intelligence. An existing query is kept; otherwise BLOB_SAS_TOKEN is appended."""
    stored = storage_url(image_blob_url)
    if "?" in image_blob_url:
        return image_blob_url

    token = sas_token.strip()
    if token.startswith("?"):
        token = token[1:]
    if not token:
        raise BlobUrlError("BLOB_SAS_TOKEN is required when image_blob_url has no query string")
    return f"{stored}?{token}"


def redact_secrets(message: str) -> str:
    return re.sub(r"\?[^\s\"']+", "?redacted", message)
