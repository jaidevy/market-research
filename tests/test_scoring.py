from datetime import datetime
from zoneinfo import ZoneInfo

from market_research.models import AccountContext, MarketSnapshot, ResearchBrief
from market_research.strategy.scoring import TradeScorer


IST = ZoneInfo("Asia/Kolkata")


def test_bullish_scoring_produces_call_plan_with_target_and_stop() -> None:
    snapshot = MarketSnapshot(
        symbol="NIFTY50",
        last_price=22500.0,
        open_price=22380.0,
        high_price=22560.0,
        low_price=22330.0,
        atr=120.0,
        trend_strength=0.6,
        volume_ratio=1.2,
        implied_volatility=16.5,
        sentiment_score=0.4,
        captured_at=datetime(2026, 5, 25, 10, 15, tzinfo=IST),
        session="regular",
    )
    brief = ResearchBrief(
        generated_at=snapshot.captured_at,
        summary="Positive catalysts outweigh macro risks.",
        bullish_catalysts=["Inflows improve"],
        bearish_risks=[],
        sentiment_score=0.55,
        source_count=3,
    )

    plan = TradeScorer(strike_step=50, minimum_confidence=0.65).score(snapshot, brief)

    assert plan.option_side == "CE"
    assert plan.confidence > 0.65
    assert plan.stop_loss < plan.entry_price < plan.target
    assert plan.strike_hint is not None


def test_account_context_makes_scoring_more_conservative() -> None:
    snapshot = MarketSnapshot(
        symbol="NIFTY50",
        last_price=22500.0,
        open_price=22380.0,
        high_price=22560.0,
        low_price=22330.0,
        atr=120.0,
        trend_strength=0.6,
        volume_ratio=1.2,
        implied_volatility=16.5,
        sentiment_score=0.4,
        captured_at=datetime(2026, 5, 25, 10, 15, tzinfo=IST),
        session="regular",
    )
    brief = ResearchBrief(
        generated_at=snapshot.captured_at,
        summary="Positive catalysts outweigh macro risks.",
        bullish_catalysts=["Inflows improve"],
        bearish_risks=[],
        sentiment_score=0.55,
        source_count=3,
    )
    account_context = AccountContext(
        retrieved_at=snapshot.captured_at,
        available_margin=2500.0,
        used_margin=47500.0,
        open_positions=8,
        holdings_count=12,
        concentration_score=0.9,
        market_bias=-0.2,
    )

    scorer = TradeScorer(strike_step=50, minimum_confidence=0.65)
    baseline = scorer.score(snapshot, brief)
    conservative = scorer.score(snapshot, brief, account_context=account_context)

    assert conservative.confidence < baseline.confidence
    assert any("Account pressure" in line for line in conservative.rationale)
