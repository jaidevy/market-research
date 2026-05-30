from datetime import date, datetime
from zoneinfo import ZoneInfo

from market_research.ingestion.calendar import TradeCalendar


IST = ZoneInfo("Asia/Kolkata")


def test_weekend_is_not_trade_day() -> None:
    calendar = TradeCalendar.from_iso_holidays([])
    assert calendar.is_trade_day(date(2026, 5, 24)) is False


def test_market_hours_gate_requires_trade_day() -> None:
    calendar = TradeCalendar.from_iso_holidays([])
    monday = datetime(2026, 5, 25, 10, 0, tzinfo=IST)
    assert calendar.is_trade_day(monday) is True
    assert calendar.is_market_open(monday) is True
