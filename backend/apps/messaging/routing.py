from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


_ALLOWED_INTENTS = ["research", "support", "approval", "config", "general"]


@dataclass(slots=True)
class RouteResult:
    intent: str
    sub_intent: str
    mode: str
    selected_agent: str
    selected_team_preset: str
    symbol: str
    confidence: float
    rationale: str
    required_skills: list[str]
    required_tools: list[str]
    requires_clarification: bool
    clarification_question: str
    clarification_options: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _runtime_catalog() -> list[dict[str, Any]]:
    from apps.agents.models import Agent
    from services.runtime.tool_registry import extract_tool_names

    required_tools: set[str] = set()
    required_skills: set[str] = set()
    agents: list[str] = []
    for agent in Agent.objects.filter(is_active=True).order_by("name"):
        agents.append(agent.name)
        required_tools.update(extract_tool_names(agent.tools))
        if isinstance(agent.skills, list):
            required_skills.update(str(skill).strip() for skill in agent.skills if str(skill).strip())

    return [
        {
            "name": "generic_agentic_graph",
            "description": "Generic multi-agent orchestration runtime for research and support workflows.",
            "agents": sorted(set(agents)),
            "required_skills": sorted(required_skills),
            "required_tools": sorted(required_tools),
        }
    ]


def resolve_route_with_model(
    *,
    user_text: str,
    requested_agent_name: str,
    active_agents: list[Any],
    session_context: dict[str, str] | None = None,
) -> RouteResult:
    text = str(user_text or "").lower().strip()
    intent = "research"
    rationale = "General analysis request."

    if any(word in text for word in ["refund", "billing", "charged", "support", "issue", "ticket"]):
        intent = "support"
        rationale = "Support/triage language detected."
    elif any(word in text for word in ["approve", "approval", "reject"]):
        intent = "approval"
        rationale = "Approval workflow language detected."
    elif any(word in text for word in ["config", "settings", "setup"]):
        intent = "config"
        rationale = "Configuration request detected."
    elif any(word in text for word in ["hello", "hi", "hey"]) and len(text.split()) <= 3:
        intent = "general"
        rationale = "Greeting or short generic message."

    required_skills: list[str] = []
    required_tools: list[str] = []
    catalog = _runtime_catalog()
    if catalog:
        required_skills = list(catalog[0].get("required_skills") or [])
        required_tools = list(catalog[0].get("required_tools") or [])

    return RouteResult(
        intent=intent,
        sub_intent=intent,
        mode="agentic_graph",
        selected_agent=str(requested_agent_name or "").strip(),
        selected_team_preset="generic_agentic_graph",
        symbol="",
        confidence=0.9,
        rationale=rationale,
        required_skills=required_skills,
        required_tools=required_tools,
        requires_clarification=False,
        clarification_question="",
        clarification_options=[],
    )
