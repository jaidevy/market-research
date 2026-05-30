from datetime import datetime
from zoneinfo import ZoneInfo

from market_research.evaluation.learning_loop import LearningLoop
from market_research.models import AccountContext, TradeOutcome


IST = ZoneInfo("Asia/Kolkata")


def test_learning_loop_raises_floor_after_loss() -> None:
    loop = LearningLoop()
    before = loop.snapshot()

    outcome = TradeOutcome(
        plan_id="plan-1",
        pnl_pct=-1.4,
        is_profitable=False,
        max_adverse_excursion_pct=1.8,
        closed_at=datetime(2026, 5, 25, 15, 20, tzinfo=IST),
    )

    after = loop.update(outcome)

    assert after.confidence_floor > before.confidence_floor
    assert after.volatility_penalty > before.volatility_penalty
    assert after.samples == 1


def test_account_context_pushes_learning_loop_conservative() -> None:
    loop = LearningLoop()
    before = loop.snapshot()

    context = AccountContext(
        retrieved_at=datetime(2026, 5, 25, 10, 15, tzinfo=IST),
        available_margin=1500.0,
        used_margin=48500.0,
        open_positions=9,
        holdings_count=15,
        concentration_score=0.95,
        market_bias=-0.1,
    )

    after = loop.apply_account_context(context)

    assert after.confidence_floor >= before.confidence_floor
    assert after.volatility_penalty >= before.volatility_penalty
