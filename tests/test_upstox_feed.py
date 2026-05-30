from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from market_research.ingestion.market import UpstoxMarketFeed


IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.asyncio
async def test_upstox_feed_prefers_websocket_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    feed = UpstoxMarketFeed(
        analytics_token="token",
        instrument_key="NSE_INDEX|Nifty 50",
        instrument_master_url="",
    )

    async def fake_ws(self: UpstoxMarketFeed, instrument_key: str) -> dict[str, object]:
        assert instrument_key == "NSE_INDEX|Nifty 50"
        return {
            "last_price": 22590.5,
            "instrument_token": "NSE_INDEX|Nifty 50",
            "ltq": 75,
            "volume": 1450000,
            "cp": 22420.0,
        }

    async def fake_ltp(self: UpstoxMarketFeed, instrument_key: str) -> dict[str, object]:
        raise AssertionError("LTP fallback should not be used when websocket succeeds")

    monkeypatch.setattr(UpstoxMarketFeed, "_fetch_websocket_quote", fake_ws)
    monkeypatch.setattr(UpstoxMarketFeed, "_fetch_ltp_quote", fake_ltp)

    snapshot = await feed.snapshot("NIFTY50")

    assert snapshot.symbol == "NIFTY50"
    assert snapshot.last_price == 22590.5
    assert snapshot.atr > 0.0
    assert snapshot.trend_strength > 0.0
    assert snapshot.session == "regular"
    assert snapshot.captured_at.tzinfo == IST


@pytest.mark.asyncio
async def test_upstox_feed_falls_back_to_ltp_when_websocket_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    feed = UpstoxMarketFeed(
        analytics_token="token",
        instrument_key="NSE_INDEX|Nifty 50",
        instrument_master_url="",
    )

    async def fake_ws(self: UpstoxMarketFeed, instrument_key: str) -> dict[str, object]:
        raise RuntimeError("websocket unavailable")

    async def fake_ltp(self: UpstoxMarketFeed, instrument_key: str) -> dict[str, object]:
        assert instrument_key == "NSE_INDEX|Nifty 50"
        return {
            "last_price": 22540.5,
            "instrument_token": "NSE_INDEX|Nifty 50",
            "ltq": 75,
            "volume": 1450000,
            "cp": 22420.0,
        }

    monkeypatch.setattr(UpstoxMarketFeed, "_fetch_websocket_quote", fake_ws)
    monkeypatch.setattr(UpstoxMarketFeed, "_fetch_ltp_quote", fake_ltp)

    snapshot = await feed.snapshot("NIFTY50")

    assert snapshot.symbol == "NIFTY50"
    assert snapshot.last_price == 22540.5
    assert snapshot.trend_strength > 0.0


@pytest.mark.asyncio
async def test_upstox_resolve_instrument_key_rejects_unsupported_symbol() -> None:
    feed = UpstoxMarketFeed(
        analytics_token="token",
        instrument_key="NSE_INDEX|Nifty 50",
        instrument_master_url="",
    )

    with pytest.raises(ValueError, match="Unsupported Upstox symbol mapping"):
        await feed._resolve_instrument_key("CL")


@pytest.mark.asyncio
async def test_upstox_resolve_instrument_key_supports_equity_aliases_and_commodities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed = UpstoxMarketFeed(
        analytics_token="token",
        instrument_key="NSE_INDEX|Nifty 50",
        instrument_master_url="",
    )

    async def fake_llm_suggestions(self: UpstoxMarketFeed, query) -> list[str]:
        return {
            "HDFC": ["NSE_EQ|HDFCBANK"],
            "HDFCBANK": ["NSE_EQ|HDFCBANK"],
            "GOLD": ["MCX_FO|GOLD"],
        }.get(query.compact_symbol, [])

    async def fake_is_valid(self: UpstoxMarketFeed, instrument_key: str) -> bool:
        return instrument_key in {"NSE_EQ|HDFCBANK", "MCX_FO|GOLD"}

    monkeypatch.setattr(UpstoxMarketFeed, "_llm_instrument_key_suggestions", fake_llm_suggestions)
    monkeypatch.setattr(UpstoxMarketFeed, "_is_valid_instrument_key", fake_is_valid)

    assert await feed._resolve_instrument_key("HDFC") == "NSE_EQ|HDFCBANK"
    assert await feed._resolve_instrument_key("HDFCBANK") == "NSE_EQ|HDFCBANK"
    assert await feed._resolve_instrument_key("GOLD") == "MCX_FO|GOLD"


@pytest.mark.asyncio
async def test_upstox_resolve_instrument_key_supports_generic_equities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed = UpstoxMarketFeed(
        analytics_token="token",
        instrument_key="NSE_INDEX|Nifty 50",
        instrument_master_url="",
    )

    async def fake_llm_suggestions(self: UpstoxMarketFeed, query) -> list[str]:
        return ["NSE_EQ|RELIANCE"] if query.compact_symbol == "RELIANCE" else []

    async def fake_is_valid(self: UpstoxMarketFeed, instrument_key: str) -> bool:
        return instrument_key == "NSE_EQ|RELIANCE"

    monkeypatch.setattr(UpstoxMarketFeed, "_llm_instrument_key_suggestions", fake_llm_suggestions)
    monkeypatch.setattr(UpstoxMarketFeed, "_is_valid_instrument_key", fake_is_valid)

    assert await feed._resolve_instrument_key("RELIANCE") == "NSE_EQ|RELIANCE"


@pytest.mark.asyncio
async def test_upstox_resolves_commodity_future_from_instrument_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed = UpstoxMarketFeed(
        analytics_token="token",
        instrument_key="NSE_INDEX|Nifty 50",
        instrument_master_url="memory://instruments",
    )

    async def fake_master(self: UpstoxMarketFeed) -> list[dict[str, object]]:
        return [
            {
                "instrument_key": "MCX_FO|123456",
                "segment": "MCX_FO",
                "trading_symbol": "CRUDEOILM18JUN26FUT",
                "name": "CRUDEOILM",
                "instrument_type": "FUTCOM",
                "expiry": "2026-06-18",
            },
            {
                "instrument_key": "MCX_FO|999999",
                "segment": "MCX_FO",
                "trading_symbol": "CRUDEOILM19JUN26FUT",
                "name": "CRUDEOILM",
                "instrument_type": "FUTCOM",
                "expiry": "2026-06-19",
            },
        ]

    async def fake_is_valid(self: UpstoxMarketFeed, instrument_key: str) -> bool:
        return instrument_key == "MCX_FO|123456"

    monkeypatch.setattr(UpstoxMarketFeed, "_fetch_instrument_master", fake_master)
    monkeypatch.setattr(UpstoxMarketFeed, "_is_valid_instrument_key", fake_is_valid)

    assert await feed._resolve_instrument_key("CRUDEOILM 18JUN26 FUT") == "MCX_FO|123456"


@pytest.mark.asyncio
async def test_upstox_preserves_spaced_commodity_future_details_in_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feed = UpstoxMarketFeed(
        analytics_token="token",
        instrument_key="NSE_INDEX|Nifty 50",
        instrument_master_url="memory://instruments",
    )

    async def fake_master(self: UpstoxMarketFeed) -> list[dict[str, object]]:
        return [
            {
                "instrument_key": "MCX_FO|CRUDE16JUNFUT",
                "segment": "MCX_FO",
                "trading_symbol": "CRUDEOIL16JUN26FUT",
                "name": "CRUDEOIL",
                "instrument_type": "FUTCOM",
                "expiry": "2026-06-16",
            }
        ]

    async def fake_is_valid(self: UpstoxMarketFeed, instrument_key: str) -> bool:
        return instrument_key == "MCX_FO|CRUDE16JUNFUT"

    monkeypatch.setattr(UpstoxMarketFeed, "_fetch_instrument_master", fake_master)
    monkeypatch.setattr(UpstoxMarketFeed, "_is_valid_instrument_key", fake_is_valid)

    assert await feed._resolve_instrument_key("crude oil 16 jun FUT") == "MCX_FO|CRUDE16JUNFUT"