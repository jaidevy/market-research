from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.agents.models import Agent, Skill
from services.runtime.artifacts import write_node_artifact
from services.runtime.planner import PlannedNode
from services.runtime.tool_registry import dispatch, extract_tool_names


@dataclass(slots=True)
class NodeExecutionResult:
    status: str
    output: dict[str, Any]
    artifact_path: str
    tool_trace: list[dict[str, Any]]


class NodeExecutionError(RuntimeError):
    pass


class AgenticNodeRunner:
    def run_node(
        self,
        *,
        run_id: int,
        node: PlannedNode,
        symbol: str,
        objective: str,
        upstream_context: dict[str, Any],
    ) -> NodeExecutionResult:
        agent = Agent.objects.filter(name=node.agent, is_active=True).first()
        if agent is None:
            raise NodeExecutionError(f"Agent '{node.agent}' is not active.")

        allowed_tools = set(extract_tool_names(agent.tools))
        selected_tools = [tool_name for tool_name in node.tools if tool_name in allowed_tools]
        if len(selected_tools) != len(node.tools):
            blocked = sorted(set(node.tools) - allowed_tools)
            raise NodeExecutionError(f"Agent '{agent.name}' is not allowed to use tools: {blocked}")

        skill_payloads = self._load_allowed_skills(agent=agent, node=node)
        context = {
            "run_id": str(run_id),
            "agent_name": agent.name,
            "symbol": symbol,
            "objective": objective,
            "node_key": node.node_key,
            "node_objective": node.objective,
            "upstream": upstream_context,
            "skills": skill_payloads,
        }
        tool_outputs: dict[str, Any] = {}
        tool_trace: list[dict[str, Any]] = []
        status = "completed"
        for tool_name in selected_tools:
            config = self._tool_config(
                tool_name=tool_name,
                symbol=symbol,
                objective=node.objective or objective,
                context=context,
            )
            tool_trace.append(
                {
                    "event": "tool_request",
                    "agent": agent.name,
                    "node_key": node.node_key,
                    "tool": tool_name,
                    "request": config,
                }
            )
            result = dispatch(tool_name, config, {**context, **tool_outputs})
            tool_outputs[tool_name] = result
            tool_trace.append(
                {
                    "event": "tool_response",
                    "agent": agent.name,
                    "node_key": node.node_key,
                    "tool": tool_name,
                    "response": result,
                }
            )
            if isinstance(result, dict) and str(result.get("status") or "").lower() == "error":
                status = "failed"
                break

        output = {
            "node_key": node.node_key,
            "label": node.label,
            "agent": agent.name,
            "objective": node.objective,
            "status": status,
            "tools": tool_outputs,
            "skills": skill_payloads,
            "summary": self._summarize(
                node=node, agent=agent, tool_outputs=tool_outputs, status=status
            ),
        }
        artifact_path = write_node_artifact(
            run_id=run_id,
            node_key=node.node_key,
            payload=output,
        )
        output["artifact_path"] = artifact_path
        return NodeExecutionResult(
            status=status,
            output=output,
            artifact_path=artifact_path,
            tool_trace=tool_trace,
        )

    def _load_allowed_skills(
        self,
        *,
        agent: Agent,
        node: PlannedNode,
    ) -> list[dict[str, str]]:
        allowed_skill_names = (
            {str(skill_name).strip() for skill_name in agent.skills if str(skill_name).strip()}
            if isinstance(agent.skills, list)
            else set()
        )
        selected_names = [
            skill_name for skill_name in node.skills if skill_name in allowed_skill_names
        ]
        if not selected_names:
            return []
        rows: list[dict[str, str]] = []
        skills = Skill.objects.filter(name__in=selected_names, is_active=True).order_by(
            "priority",
            "name",
        )
        for skill in skills:
            rows.append(
                {
                    "name": skill.name,
                    "description": skill.description,
                    "category": skill.category,
                    "markdown": skill.markdown,
                }
            )
        return rows

    def _tool_config(
        self,
        *,
        tool_name: str,
        symbol: str,
        objective: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if tool_name == "web_search":
            return {"query": objective}
        if tool_name == "read_url":
            return {"url": str(context.get("reference_url") or "")}
        if tool_name == "knowledge_base_search":
            return {"query": objective}
        if tool_name == "send_channel_message":
            return {"message": objective, "channel": "ui"}
        if tool_name == "write_artifact":
            return {"path": f"{context.get('node_key') or 'artifact'}.md", "content": objective}
        if tool_name == "memory_write":
            return {
                "agent_name": context.get("agent_name"),
                "run_id": context.get("run_id"),
                "key": context.get("node_key"),
                "value": context,
            }
        return {"objective": objective}

    def _summarize(
        self,
        *,
        node: PlannedNode,
        agent: Agent,
        tool_outputs: dict[str, Any],
        status: str,
    ) -> str:
        if not tool_outputs:
            return f"{agent.name} completed {node.label} without tool calls."
        successful_tools = [
            name
            for name, value in tool_outputs.items()
            if isinstance(value, dict) and str(value.get("status") or "").lower() == "ok"
        ]
        failed_tools = [
            name
            for name, value in tool_outputs.items()
            if isinstance(value, dict) and str(value.get("status") or "").lower() == "error"
        ]
        if status == "failed":
            failed = ", ".join(failed_tools) or "unknown"
            return f"{agent.name} failed {node.label}; failed tools: {failed}."
        successful = ", ".join(successful_tools) or "none"
        return f"{agent.name} completed {node.label}; successful tools: {successful}."
