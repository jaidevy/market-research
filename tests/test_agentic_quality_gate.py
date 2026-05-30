from __future__ import annotations

from market_research.agentic.service import AgenticResearchService
from market_research.config.settings import Settings


class _DummyEngine:
    pass


def _service(tmp_path) -> AgenticResearchService:
    settings = Settings(agentic_skills_dir=str(tmp_path / "skills"))
    return AgenticResearchService(settings=settings, engine=_DummyEngine())


def test_quality_gate_marks_incomplete_for_plan_only_and_no_data(tmp_path) -> None:
    service = _service(tmp_path)
    status, reasons, evidence = service._classify_research_deliverable(
        report="### Phase 1\nPlan: gather data and report later.",
        tool_trace=[],
    )

    assert status == "incomplete"
    assert any("plan-only" in reason for reason in reasons)
    assert any("no market data evidence" in reason for reason in reasons)
    assert evidence["data_tool_calls"] == 0


def test_quality_gate_accepts_evidence_backed_structured_report(tmp_path) -> None:
    service = _service(tmp_path)
    report = """
MarketSituation: Trend is constructive.
OptionChain: PCR is elevated with supportive OI structure.
Thesis: Bullish continuation with controlled pullback risk.
Decision: Prefer call-side setup if momentum holds.
Risks: Event volatility and failed breakout.
Invalidation: Break below support with weak breadth.
""".strip()
    status, reasons, evidence = service._classify_research_deliverable(
        report=report,
        tool_trace=[
            {"event": "tool_response", "tool": "get_market_data"},
            {"event": "tool_response", "tool": "analyze_options"},
        ],
    )

    assert status == "completed"
    assert reasons == []
    assert evidence["data_tool_calls"] == 2
