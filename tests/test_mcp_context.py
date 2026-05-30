from datetime import datetime
from zoneinfo import ZoneInfo

from market_research.models import UpstoxMcpContextPayload


IST = ZoneInfo("Asia/Kolkata")


def test_upstox_mcp_payload_converts_to_account_context() -> None:
    payload = UpstoxMcpContextPayload(
        retrieved_at=datetime(2026, 5, 25, 10, 15, tzinfo=IST),
        holdings=[
            {"symbol": "RELIANCE", "market_value": 60000.0, "quantity": 10, "pnl_pct": 2.5, "weight": 0.9},
            {"symbol": "HDFCBANK", "market_value": 40000.0, "quantity": 8, "pnl_pct": -1.0, "weight": 0.1},
        ],
        positions=[
            {"symbol": "NIFTY26MAY22500CE", "quantity": 2, "pnl_pct": 4.0, "unrealized_pnl": 1800.0},
        ],
        margins={"available": 25000.0, "utilized": 75000.0, "total": 100000.0},
        daily_pnl_pct=1.2,
        market_bias_hint=0.15,
        account_status="active",
        notes=["Portfolio synced from Upstox MCP."],
    )

    context = payload.to_account_context()

    assert context.source == "upstox-mcp"
    assert context.available_margin == 25000.0
    assert context.used_margin == 75000.0
    assert context.holdings_count == 2
    assert context.open_positions == 1
    assert context.market_bias == 0.15
    assert context.risk_pressure() > 0.6
    assert any("Upstox status=active" in note for note in context.notes)