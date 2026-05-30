from __future__ import annotations

import os

import django


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from services.runtime.unified_run import UnifiedRunRunner


class _StubMarket:
    pass


def test_build_step_usage_overrides_marks_deterministic_steps_zero() -> None:
    runner = UnifiedRunRunner(market=_StubMarket())

    overrides = runner._build_step_usage_overrides(market_output={})

    assert overrides["ingestion"]["input_tokens"] == 0
    assert overrides["ingestion"]["output_tokens"] == 0
    assert overrides["option_chain"]["input_tokens"] == 0
    assert overrides["option_chain"]["output_tokens"] == 0
    assert overrides["scoring"]["input_tokens"] == 0
    assert overrides["risk"]["input_tokens"] == 0
    assert overrides["approval"]["input_tokens"] == 0
    assert "research" not in overrides


def test_build_step_usage_overrides_includes_research_when_usage_present() -> None:
    runner = UnifiedRunRunner(market=_StubMarket())

    overrides = runner._build_step_usage_overrides(
        market_output={
            "agentic": {
                "model": "gpt-4.1-mini",
                "token_usage": {
                    "input_tokens": 321,
                    "output_tokens": 123,
                },
            }
        }
    )

    assert overrides["research"] == {
        "input_tokens": 321,
        "output_tokens": 123,
        "model_name": "gpt-4.1-mini",
    }


def test_build_step_detail_contexts_emits_decision_depth_for_all_stages() -> None:
    runner = UnifiedRunRunner(market=_StubMarket())

    details = runner._build_step_detail_contexts(
        market_output={
            "symbol": "NIFTY50",
            "insight": {
                "trade_day_allowed": True,
                "market_open": False,
                "notes": ["Trade day is valid, but the current timestamp is outside market hours."],
                "research": {
                    "summary": "Momentum is positive with moderate breadth.",
                    "source_count": 3,
                    "sentiment_score": 0.2,
                },
                "market_snapshot": {
                    "option_chain_context": {
                        "source": "upstox-option-chain",
                        "atm_strike": 22500,
                        "pcr": 1.08,
                        "directional_bias": 0.12,
                        "call_oi_itm": 120000,
                        "call_oi_otm": 140000,
                        "put_oi_itm": 130000,
                        "put_oi_otm": 150000,
                    }
                },
                "plan": {
                    "direction": "bullish",
                    "option_side": "CE",
                    "confidence": 0.73,
                    "strike_hint": 22500,
                    "entry_price": 22480,
                    "stop_loss": 22360,
                    "target": 22620,
                    "rationale": ["Trend and breadth support a call-side setup."],
                },
            },
            "agentic": {
                "status": "pending_approval",
                "provider": "deepagents",
                "model": "nvidia/nemotron-3-super-120b-a12b:free",
                "tool_trace": [{"name": "market_data"}],
                "token_usage": {"input_tokens": 250, "output_tokens": 150},
                "approval_ticket": {
                    "ticket_id": "abc-123",
                    "status": "pending",
                    "summary": "Review before execution.",
                },
            },
        }
    )

    assert [item["node_key"] for item in details] == ["ingestion", "option_chain", "research", "scoring", "risk", "approval"]

    option_chain_context = next(item["context"] for item in details if item["node_key"] == "option_chain")
    assert option_chain_context["status"] == "available"
    assert option_chain_context["source"] == "upstox-option-chain"
    assert option_chain_context["atm_strike"] == 22500.0
    assert option_chain_context["pcr"] == 1.08

    scoring_context = next(item["context"] for item in details if item["node_key"] == "scoring")
    assert scoring_context["decision"] == "CE"
    assert scoring_context["direction"] == "bullish"
    assert scoring_context["confidence"] == 0.73

    risk_context = next(item["context"] for item in details if item["node_key"] == "risk")
    assert risk_context["risk_state"] == "outside_market_hours"
    assert risk_context["trade_day_allowed"] is True

    approval_context = next(item["context"] for item in details if item["node_key"] == "approval")
    assert approval_context["decision"] == "awaiting_human"
    assert approval_context["ticket_status"] == "pending"
