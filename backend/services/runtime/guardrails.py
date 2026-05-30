from __future__ import annotations

from services.runtime.planner import AgenticGraphPlan, PlannerValidationError


def enforce_guardrails(plan: AgenticGraphPlan) -> None:
    node_keys = {node.node_key for node in plan.nodes}
    if plan.intent in {"options", "risk", "trade", "approval"} and "risk_gate" not in node_keys:
        raise PlannerValidationError("Agentic graph requires risk_gate for market intents.")
    if plan.intent in {"options", "risk", "trade", "approval"} and "approval" not in node_keys:
        raise PlannerValidationError("Agentic graph requires approval before final response for this intent.")