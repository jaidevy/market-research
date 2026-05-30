from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from apps.agents.models import Agent
from services.runtime.tool_registry import extract_tool_names


@dataclass(slots=True)
class PlannedNode:
    node_key: str
    label: str
    agent: str
    tools: list[str]
    skills: list[str]
    depends_on: list[str]
    objective: str
    expected_artifact: str = ""
    mandatory: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AgenticGraphPlan:
    objective: str
    symbol: str
    intent: str
    final_node_key: str
    nodes: list[PlannedNode]

    def as_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "symbol": self.symbol,
            "intent": self.intent,
            "final_node_key": self.final_node_key,
            "nodes": [node.as_dict() for node in self.nodes],
        }


class PlannerValidationError(ValueError):
    pass


def plan_with_model(
    *,
    user_text: str,
    route: dict[str, Any],
    session_context: dict[str, str] | None = None,
) -> AgenticGraphPlan:
    objective = str(user_text or route.get("rationale") or "Execute workflow objective.").strip()
    intent = str(route.get("intent") or "general").strip().lower() or "general"

    active_agents = list(Agent.objects.filter(is_active=True).order_by("name"))
    if not active_agents:
        raise PlannerValidationError("No active agents are configured.")

    by_name = {agent.name: agent for agent in active_agents}

    def first_existing(names: list[str]) -> str:
        for name in names:
            if name in by_name:
                return name
        return active_agents[0].name

    if intent == "support":
        triage = first_existing(["SupportTriageAgent", "ConciergeAgent"])
        kb = first_existing(["KnowledgeBaseAgent", triage])
        draft = first_existing(["ResponseDraftAgent", triage])
        escalation = first_existing(["EscalationAgent", triage])
        final_agent = first_existing(["ResponseDraftAgent", "ConciergeAgent", triage])

        nodes = [
            PlannedNode(
                node_key="triage",
                label="Triage",
                agent=triage,
                tools=_allowed_tools(triage, ["memory_read", "knowledge_base_search"]),
                skills=_agent_skills(triage),
                depends_on=[],
                objective="Classify the request and determine urgency.",
            ),
            PlannedNode(
                node_key="knowledge",
                label="Knowledge Lookup",
                agent=kb,
                tools=_allowed_tools(kb, ["knowledge_base_search", "read_url"]),
                skills=_agent_skills(kb),
                depends_on=["triage"],
                objective="Collect relevant policy or product context.",
            ),
            PlannedNode(
                node_key="draft",
                label="Draft Response",
                agent=draft,
                tools=_allowed_tools(draft, ["send_channel_message", "write_artifact"]),
                skills=_agent_skills(draft),
                depends_on=["knowledge"],
                objective="Draft a clear response for the user.",
            ),
            PlannedNode(
                node_key="escalation",
                label="Escalation Check",
                agent=escalation,
                tools=_allowed_tools(escalation, ["ticket_create"]),
                skills=_agent_skills(escalation),
                depends_on=["draft"],
                objective="Decide whether human handoff is needed.",
            ),
            PlannedNode(
                node_key="final_response",
                label="Final Response",
                agent=final_agent,
                tools=_allowed_tools(final_agent, ["send_channel_message"]),
                skills=_agent_skills(final_agent),
                depends_on=["escalation"],
                objective="Send final response back to the requesting channel.",
            ),
        ]
    else:
        planner = first_existing(["ResearchPlannerAgent", "ConciergeAgent"])
        researcher = first_existing(["WebResearchAgent", planner])
        summarizer = first_existing(["SummarizerAgent", planner])
        reviewer = first_existing(["QualityReviewAgent", summarizer])

        nodes = [
            PlannedNode(
                node_key="plan",
                label="Plan",
                agent=planner,
                tools=_allowed_tools(planner, ["memory_read", "memory_write"]),
                skills=_agent_skills(planner),
                depends_on=[],
                objective="Clarify objective and structure the workflow.",
            ),
            PlannedNode(
                node_key="research",
                label="Research",
                agent=researcher,
                tools=_allowed_tools(researcher, ["web_search", "read_url", "memory_write"]),
                skills=_agent_skills(researcher),
                depends_on=["plan"],
                objective="Gather evidence and source snippets.",
            ),
            PlannedNode(
                node_key="review",
                label="Review",
                agent=reviewer,
                tools=_allowed_tools(reviewer, ["memory_read"]),
                skills=_agent_skills(reviewer),
                depends_on=["research"],
                objective="Check coverage and quality before final response.",
            ),
            PlannedNode(
                node_key="final_response",
                label="Final Response",
                agent=summarizer,
                tools=_allowed_tools(summarizer, ["write_artifact", "send_channel_message"]),
                skills=_agent_skills(summarizer),
                depends_on=["review"],
                objective="Return a concise final answer with artifact output.",
            ),
        ]

    return AgenticGraphPlan(
        objective=objective,
        symbol="",
        intent=intent,
        final_node_key="final_response",
        nodes=nodes,
    )


def validate_plan_payload(payload: dict[str, Any], *, route: dict[str, Any]) -> AgenticGraphPlan:
    if not isinstance(payload, dict):
        raise PlannerValidationError("Planner output must be an object.")
    plan = plan_with_model(user_text=str(payload.get("objective") or ""), route=route)
    return plan


def _agent_skills(agent_name: str) -> list[str]:
    agent = Agent.objects.filter(name=agent_name, is_active=True).first()
    if agent is None or not isinstance(agent.skills, list):
        return []
    return [str(item).strip() for item in agent.skills if str(item).strip()]


def _allowed_tools(agent_name: str, preferred: list[str]) -> list[str]:
    agent = Agent.objects.filter(name=agent_name, is_active=True).first()
    if agent is None:
        return []
    available = set(extract_tool_names(agent.tools if isinstance(agent.tools, list) else []))
    chosen = [tool for tool in preferred if tool in available]
    if chosen:
        return chosen
    return list(sorted(available))[:2]
