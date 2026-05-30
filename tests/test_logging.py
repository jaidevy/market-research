from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_research.ingestion.market import InMemoryMarketFeed
from market_research.models import MarketSnapshot, TradeOutcome
from market_research.services.log_store import EngineLogStore
from market_research.services.orchestrator import InsightEngine


IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.asyncio
async def test_generate_insight_writes_research_log(tmp_path: Path) -> None:
    engine = InsightEngine()
    engine.market_feed = InMemoryMarketFeed(
        snapshot_data=MarketSnapshot(
            symbol="NIFTY50",
            last_price=22500.0,
            open_price=22380.0,
            high_price=22560.0,
            low_price=22330.0,
            atr=120.0,
            trend_strength=0.4,
            volume_ratio=1.15,
            implied_volatility=16.0,
            sentiment_score=0.2,
            captured_at=datetime(2026, 5, 26, 10, 0, tzinfo=IST),
            session="regular",
        )
    )
    engine.log_store = EngineLogStore(tmp_path)

    snapshot = await engine.market_feed.snapshot("NIFTY50")
    _ = await engine.generate_insight(snapshot)

    research_logs = engine.recent_research_logs(limit=10)
    assert len(research_logs) >= 1
    assert research_logs[-1]["symbol"] == "NIFTY50"
    assert "research" in research_logs[-1]


def test_record_outcome_writes_eval_log(tmp_path: Path) -> None:
    engine = InsightEngine()
    engine.log_store = EngineLogStore(tmp_path)
    outcome = TradeOutcome(
        plan_id="plan-log-1",
        pnl_pct=-0.8,
        is_profitable=False,
        max_adverse_excursion_pct=1.2,
        closed_at=datetime(2026, 5, 26, 15, 15, tzinfo=IST),
    )

    engine.record_outcome(outcome)

    eval_logs = engine.recent_eval_logs(limit=10)
    assert len(eval_logs) >= 1
    assert eval_logs[-1]["plan_id"] == "plan-log-1"
    assert "strategy_state" in eval_logs[-1]