from datetime import datetime, timezone
from decimal import Decimal

from app.services.mapping import map_extraction


def test_maps_terminal_slip_fields():
    mapped = map_extraction(
        {
            "mid": "MID-100",
            "tid": "TID-9",
            "txn_amount": "25.5",
            "currency": "aed",
            "txn_date": "08/10/2026 14:30:00",
            "txn_reference": "123456789012",
            "auth_code": "A99",
            "card_last4": "****4242",
            "scheme": "Visa",
            "outlet_address": "Dubai Mall",
            "confidence": 0.91234,
        }
    )

    assert mapped["mid"] == "MID-100"
    assert mapped["tid"] == "TID-9"
    assert mapped["txn_amount"] == Decimal("25.50")
    assert mapped["currency"] == "AED"
    assert mapped["txn_date"] == datetime(2026, 10, 8, 14, 30, tzinfo=timezone.utc)
    assert mapped["txn_reference"] == "123456789012"
    assert mapped["auth_code"] == "A99"
    assert mapped["card_last4"] == "4242"
    assert mapped["scheme"] == "Visa"
    assert mapped["outlet_address"] == "Dubai Mall"
    assert mapped["extraction_confidence"] == Decimal("0.9123")


def test_drops_values_that_do_not_fit_the_columns():
    mapped = map_extraction(
        {
            "txn_amount": "not-a-number",
            "currency": "dirham",
            "txn_date": "yesterday",
            "card_last4": "42",
            "confidence": 1.4,
        }
    )

    assert mapped["txn_amount"] is None
    assert mapped["currency"] is None
    assert mapped["txn_date"] is None
    assert mapped["card_last4"] is None
    assert mapped["extraction_confidence"] is None
