from datetime import date

from app.ipos import ipo_status


def test_status_from_printed_bid_dates() -> None:
    opens, closes = date(2026, 10, 29), date(2026, 11, 2)
    assert ipo_status(date(2026, 10, 28), opens, closes) == "upcoming"
    assert ipo_status(date(2026, 10, 29), opens, closes) == "open"
    assert ipo_status(date(2026, 11, 2), opens, closes) == "open"
    assert ipo_status(date(2026, 11, 3), opens, closes) == "closed"
    assert ipo_status(date(2026, 11, 3), None, closes) == "unknown"
