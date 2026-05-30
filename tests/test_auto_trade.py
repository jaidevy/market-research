from datetime import datetime
from zoneinfo import ZoneInfo

from market_research.models import AutoTradeRequest, MarketSnapshot
from market_research.services.orchestrator import InsightEngine
from market_research.ingestion.market import InMemoryMarketFeed
from market_research.ingestion.news import NewsAggregator


IST = ZoneInfo("Asia/Kolkata")


def test_auto_trade_generates_action_and_updates_memory() -> None:
    engine = InsightEngine()
    engine.news_aggregator = NewsAggregator(sources=[])
    engine.market_feed = InMemoryMarketFeed(
        snapshot_data=MarketSnapshot(
            symbol="NIFTY50",
            last_price=22500.0,
            open_price=22380.0,
            high_price=22560.0,
            low_price=22330.0,
            atr=120.0,
            trend_strength=0.62,
            volume_ratio=1.2,
            implied_volatility=16.0,
            sentiment_score=0.45,
            captured_at=datetime(2026, 5, 25, 10, 15, tzinfo=IST),
            session="regular",
        )
    )

    decision = engine.run_auto_trade_sync(AutoTradeRequest(go=True, daily_budget=20000.0))

    assert decision.go is True
    assert decision.action in {"BUY_CALL", "SELL_PUT", "BUY_PUT", "SELL_CALL"}
    assert decision.hedge_amount > 0.0
    assert decision.stop_loss_amount > 0.0
    assert decision.target_amount > 0.0
    assert decision.strong_levels.support < decision.strong_levels.pivot < decision.strong_levels.resistance
    assert engine.memory_state().current_day is not None
    assert engine.memory_state().total_sessions >= 1