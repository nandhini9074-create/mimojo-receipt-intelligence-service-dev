import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_CARD_DIGITS = re.compile(r"\d")
_CURRENCY = re.compile(r"^[A-Za-z]{3}$")
_DATE_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def _text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def _amount(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None
    if amount.copy_abs() >= Decimal("1e16"):
        return None
    return amount


def _currency(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not _CURRENCY.fullmatch(text):
        return None
    return text.upper()


def _txn_date(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _card_last4(value: object) -> str | None:
    if value is None:
        return None
    digits = "".join(_CARD_DIGITS.findall(str(value)))
    if len(digits) < 4:
        return None
    return digits[-4:]


def _confidence(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        score = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if score < 0 or score > 1:
        return None
    return score.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def map_extraction(payload: dict) -> dict:
    """Normalize model JSON onto receipt_evidence columns. Unusable values stay null; the raw JSON is stored separately."""
    return {
        "mid": _text(payload.get("mid"), 100),
        "tid": _text(payload.get("tid"), 100),
        "txn_amount": _amount(payload.get("txn_amount")),
        "currency": _currency(payload.get("currency")),
        "txn_date": _txn_date(payload.get("txn_date")),
        "txn_reference": _text(payload.get("txn_reference"), 150),
        "auth_code": _text(payload.get("auth_code"), 50),
        "card_last4": _card_last4(payload.get("card_last4")),
        "scheme": _text(payload.get("scheme"), 30),
        "outlet_address": _text(payload.get("outlet_address"), 250),
        "extraction_confidence": _confidence(payload.get("confidence")),
    }
