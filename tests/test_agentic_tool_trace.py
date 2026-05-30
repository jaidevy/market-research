from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from market_research.agentic.service import AgenticResearchService
from market_research.config.settings import Settings
from market_research.models import AgenticResearchRequest, InsightBundle, MarketSnapshot, OptionTradePlan, ResearchBrief
from market_research.services.log_store import EngineLogStore


class DummyEngine:
    def __init__(self, root: Path) -> None:
        self.log_store = EngineLogStore(root=root)

    async def generate_live_insight(self, symbol: str) -> InsightBundle:
        now = datetime.now(UTC)
        return InsightBundle(
            trade_day_allowed=True,
            market_open=True,
            market_snapshot=MarketSnapshot(
                symbol=symbol,
                last_price=22500.0,
                open_price=22380.0,
                high_price=22560.0,
                low_price=22330.0,
                atr=120.0,
                trend_strength=0.6,
                volume_ratio=1.2,
                implied_volatility=16.5,
                sentiment_score=0.2,
                captured_at=now,
                session="regular",
            ),
            research=ResearchBrief(
                generated_at=now,
                summary=f"Synthetic summary for {symbol}",
                bullish_catalysts=["Momentum firm"],
                bearish_risks=["Event risk"],
                sentiment_score=0.2,
                source_count=1,
            ),
            plan=OptionTradePlan(
                symbol=symbol,
                direction="bullish",
                option_side="CE",
                confidence=0.71,
                entry_price=22500.0,
                strike_hint=22500.0,
                stop_loss=22380.0,
                target=22720.0,
                expected_move=120.0,
                rationale=["Trend and breadth aligned."],
                generated_at=now,
            ),
            notes=["test bundle"],
        )


@pytest.mark.asyncio
async def test_deepagents_returns_error_when_model_execution_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        agentic_skills_dir=str(tmp_path / "skills"),
        openrouter_api_key="test-key",
        agentic_model="nvidia/nemotron-3-super-120b-a12b:free",
    )
    service = AgenticResearchService(settings=settings, engine=DummyEngine(root=tmp_path))

    async def fake_run_deepagents_for_model(
        self: AgenticResearchService,
        model_name: str,
        tools: list[object],
        system_prompt: str,
        prompt: str,
        require_approval: bool,
    ) -> tuple[str | None, list[dict[str, object]], dict[str, int] | None]:
        raise RuntimeError(f"upstream failed for {model_name}")

    monkeypatch.setattr(AgenticResearchService, "_run_deepagents_for_model", fake_run_deepagents_for_model)

    with pytest.raises(RuntimeError, match="Agent execution error"):
        await service.run(
            AgenticResearchRequest(
                objective="Generate intraday thesis",
                symbol="NIFTY50",
                require_approval=False,
                channel="none",
            )
        )

    assert service.last_deepagents_error is not None
    assert "upstream failed" in service.last_deepagents_error


def test_extract_token_usage_from_message_usage_metadata(tmp_path: Path) -> None:
    settings = Settings(agentic_skills_dir=str(tmp_path / "skills"))
    service = AgenticResearchService(settings=settings, engine=DummyEngine(root=tmp_path))

    usage = service._extract_token_usage(
        {
            "messages": [
                {
                    "role": "assistant",
                    "usage_metadata": {
                        "input_tokens": 123,
                        "output_tokens": 45,
                        "total_tokens": 168,
                    },
                }
            ]
        }
    )

    assert usage == {
        "input_tokens": 123,
        "output_tokens": 45,
        "total_tokens": 168,
    }


def test_extract_token_usage_falls_back_to_response_metadata_token_usage(tmp_path: Path) -> None:
    settings = Settings(agentic_skills_dir=str(tmp_path / "skills"))
    service = AgenticResearchService(settings=settings, engine=DummyEngine(root=tmp_path))

    usage = service._extract_token_usage(
        {
            "messages": [
                {
                    "role": "assistant",
                    "response_metadata": {
                        "token_usage": {
                            "prompt_tokens": 200,
                            "completion_tokens": 80,
                            "total_tokens": 280,
                        }
                    },
                }
            ]
        }
    )

    assert usage == {
        "input_tokens": 200,
        "output_tokens": 80,
        "total_tokens": 280,
    }
