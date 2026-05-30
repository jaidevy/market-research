from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from threading import Thread
from typing import Any, Hashable, TypedDict, cast
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.db import close_old_connections
from django.utils import timezone

from apps.agents.models import Agent, Skill
from apps.messaging.models import InterAgentMessage
from apps.monitoring.models import RuntimeEvent, TokenCostLedger
from apps.runs.models import UnifiedRun, UnifiedRunStep, WorkflowTemplate
from services.runtime.artifacts import write_node_artifact
from services.runtime.tool_registry import dispatch, extract_tool_names


class LLMConfigurationError(RuntimeError):
    """Raised when the runtime LLM client is unavailable or misconfigured."""


async def complete_json(*, system_prompt: str, user_payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    raise LLMConfigurationError("LLM backend is not available in this runtime.")


class WorkflowState(TypedDict, total=False):
    objective: str
    input: dict[str, Any]
    outputs: dict[str, Any]
    messages: list[dict[str, Any]]
    visits: dict[str, int]
    final: dict[str, Any]


@dataclass(slots=True)
class LangGraphWorkflowRunner:
    max_node_visits: int = 2

    def _create_run(self, *, template: WorkflowTemplate, payload: dict[str, Any], trigger: str) -> UnifiedRun:
        run = UnifiedRun.objects.create(
            status="running",
            trigger=trigger,
            input_payload={
                "workflow_template_id": template.id,
                "workflow_template": template.name,
                "payload": payload,
            },
            started_at=timezone.now(),
        )
        self._event(run=run, event_type="workflow_run_started", message=f"Workflow '{template.name}' started.")
        return run

    def run_async(
        self,
        *,
        template: WorkflowTemplate,
        payload: dict[str, Any],
        trigger: str = "manual",
    ) -> dict[str, Any]:
        run = self._create_run(template=template, payload=payload, trigger=trigger)

        worker = Thread(
            target=self._run_in_background,
            kwargs={"run_id": run.id, "template_id": template.id},
            daemon=True,
            name=f"workflow-run-{run.id}",
        )
        worker.start()

        return {
            "run": {
                "id": run.id,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": None,
            },
            "workflow": {
                "id": template.id,
                "name": template.name,
                "version": template.version,
            },
            "result": {"status": "running"},
        }

    def run(
        self,
        *,
        template: WorkflowTemplate,
        payload: dict[str, Any],
        trigger: str = "manual",
    ) -> dict[str, Any]:
        run = self._create_run(template=template, payload=payload, trigger=trigger)
        self._execute_graph(run=run, template=template, payload=payload)

        finished_at = run.finished_at
        return {
            "run": {
                "id": run.id,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": finished_at.isoformat() if finished_at else None,
            },
            "workflow": {
                "id": template.id,
                "name": template.name,
                "version": template.version,
            },
            "result": run.output_payload,
        }

    def _run_in_background(self, *, run_id: int, template_id: int) -> None:
        close_old_connections()
        try:
            run = UnifiedRun.objects.get(id=run_id)
            template = WorkflowTemplate.objects.get(id=template_id)
            payload = run.input_payload.get("payload") if isinstance(run.input_payload, dict) else {}
            payload_dict = payload if isinstance(payload, dict) else {}
            self._execute_graph(run=run, template=template, payload=payload_dict)
        finally:
            close_old_connections()

    def _execute_graph(self, *, run: UnifiedRun, template: WorkflowTemplate, payload: dict[str, Any]) -> None:
        try:
            graph = self._compile(template=template, run=run)
            initial_state: WorkflowState = {
                "objective": str(payload.get("objective") or payload.get("body") or payload.get("message") or "").strip(),
                "input": payload,
                "outputs": {},
                "messages": [],
                "visits": {},
            }
            final_state = graph.invoke(initial_state)
            run.status = "completed"
            run.finished_at = timezone.now()
            run.output_payload = {
                "status": "completed",
                "workflow_template": template.name,
                "final": final_state.get("final") or {},
                "outputs": final_state.get("outputs") or {},
                "messages": final_state.get("messages") or [],
            }
            run.save(update_fields=["status", "finished_at", "output_payload", "updated_at"])
            self._event(run=run, event_type="workflow_run_completed", message=f"Workflow '{template.name}' completed.")
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.finished_at = timezone.now()
            run.output_payload = {"status": "failed", "error": str(exc), "workflow_template": template.name}
            run.save(update_fields=["status", "finished_at", "output_payload", "updated_at"])
            self._event(run=run, level="error", event_type="workflow_run_failed", message=str(exc))

    def _compile(self, *, template: WorkflowTemplate, run: UnifiedRun):
        try:
            from langgraph.graph import END, StateGraph
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"LangGraph is not available: {exc}") from exc

        nodes = self._nodes_by_key(template.nodes)
        if not nodes:
            raise ValueError("Workflow template has no nodes.")
        edges_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        incoming: set[str] = set()
        for edge in template.edges if isinstance(template.edges, list) else []:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("from") or "").strip()
            target = str(edge.get("to") or "").strip()
            if not source or not target:
                continue
            edges_by_source[source].append(edge)
            incoming.add(target)

        entry_key = next((key for key in nodes if key not in incoming), next(iter(nodes)))
        graph = StateGraph(WorkflowState)
        for node_key, node in nodes.items():
            graph.add_node(node_key, self._node_callable(run=run, node=node))
        graph.set_entry_point(entry_key)

        for node_key in nodes:
            outgoing = edges_by_source.get(node_key, [])
            if not outgoing:
                graph.add_edge(node_key, END)
                continue
            conditional = [edge for edge in outgoing if isinstance(edge.get("condition"), dict)]
            if conditional:
                labels = cast(dict[Hashable, str], {self._edge_label(edge): str(edge.get("to") or "").strip() for edge in outgoing})
                graph.add_conditional_edges(
                    node_key,
                    self._route_callable(node_key=node_key, edges=outgoing),
                    labels,
                )
                continue
            graph.add_edge(node_key, str(outgoing[0].get("to") or "").strip())
        return graph.compile()

    def _node_callable(self, *, run: UnifiedRun, node: dict[str, Any]):
        def execute(state: WorkflowState) -> WorkflowState:
            node_key = self._node_key(node)
            agent_name = str(node.get("agent") or "").strip()
            agent = Agent.objects.filter(name=agent_name, is_active=True).first()
            visits = dict(state.get("visits") or {})
            visits[node_key] = visits.get(node_key, 0) + 1
            if visits[node_key] > self.max_node_visits:
                outputs = dict(state.get("outputs") or {})
                outputs[node_key] = {
                    "status": "blocked",
                    "summary": f"{node_key} stopped after reaching max visit limit.",
                    "enough_evidence": True,
                }
                return {**state, "visits": visits, "outputs": outputs}

            step = UnifiedRunStep.objects.create(
                run=run,
                node_key=node_key,
                status="running",
                input_payload={"node": node, "state": self._compact_state(state)},
            )
            self._emit_message(
                run=run,
                from_agent=agent,
                status="queued",
                payload={
                    "event": "node_started",
                    "node_key": node_key,
                    "agent": agent_name,
                    "summary": f"{node_key} started.",
                },
            )
            self._event(run=run, event_type="workflow_step_started", message=f"{node_key} started.", context={"node_key": node_key})
            try:
                output = self._execute_agent_node(run=run, node=node, state=state)
                status = str(output.get("status") or "completed")
            except Exception as exc:  # noqa: BLE001
                output = {"status": "failed", "error": str(exc), "summary": f"{node_key} failed: {exc}"}
                status = "failed"
            artifact_path = write_node_artifact(run_id=run.id, node_key=node_key, payload=output)
            output["artifact_path"] = artifact_path
            step.status = status
            step.output_payload = output
            if status == "failed":
                step.error_message = str(output.get("error") or "Node failed.")
            step.save(update_fields=["status", "output_payload", "error_message", "updated_at"])
            self._event(
                run=run,
                event_type="workflow_step_completed" if status != "failed" else "workflow_step_failed",
                message=f"{node_key} {status}.",
                context={"node_key": node_key, "artifact_path": artifact_path},
            )
            self._emit_message(
                run=run,
                from_agent=agent,
                status="acked" if status != "failed" else "error",
                payload={
                    "event": "node_completed" if status != "failed" else "node_failed",
                    "node_key": node_key,
                    "agent": agent_name,
                    "summary": f"{node_key} {status}.",
                    "status": status,
                },
            )
            outputs = dict(state.get("outputs") or {})
            outputs[node_key] = output
            messages = list(state.get("messages") or [])
            messages.append({"node_key": node_key, "summary": str(output.get("summary") or "")})
            final = state.get("final") or {}
            if str(node.get("type") or "").lower() == "final":
                final = output
            return {**state, "outputs": outputs, "messages": messages, "visits": visits, "final": final}

        return execute

    def _execute_agent_node(self, *, run: UnifiedRun, node: dict[str, Any], state: WorkflowState) -> dict[str, Any]:
        node_key = self._node_key(node)
        agent_name = str(node.get("agent") or "").strip()
        agent = Agent.objects.filter(name=agent_name, is_active=True).first()
        if agent is None:
            raise ValueError(f"Agent '{agent_name}' is not active.")

        allowed_tools = set(extract_tool_names(agent.tools))
        requested_tools = [str(tool).strip() for tool in node.get("tools") or [] if str(tool).strip()]
        blocked_tools = sorted(set(requested_tools) - allowed_tools)
        if blocked_tools:
            raise ValueError(f"Agent '{agent.name}' is not allowed to use tools: {blocked_tools}")

        skill_payloads = self._load_allowed_skills(agent=agent, node=node)
        tool_outputs: dict[str, Any] = {}
        tool_trace: list[dict[str, Any]] = []
        deferred_content_tools = {"write_artifact", "send_channel_message", "discord_rw"}
        precompose_tools = [tool_name for tool_name in requested_tools if tool_name not in deferred_content_tools]
        postcompose_tools = [tool_name for tool_name in requested_tools if tool_name in deferred_content_tools]

        def run_tool(tool_name: str, *, agent_output: dict[str, Any] | None = None) -> None:
            config = self._tool_config(tool_name=tool_name, node=node, state=state)
            self._emit_message(
                run=run,
                from_agent=agent,
                status="queued",
                payload={
                    "event": "tool_request",
                    "node_key": node_key,
                    "agent": agent.name,
                    "tool": tool_name,
                    "request": config,
                    "summary": f"{node_key}: calling tool {tool_name}.",
                },
            )
            tool_trace.append({"event": "tool_request", "tool": tool_name, "request": config})
            result = dispatch(tool_name, config, self._tool_context(run=run, agent=agent, node=node, state=state, tool_outputs=tool_outputs))
            tool_outputs[tool_name] = result
            self._emit_message(
                run=run,
                from_agent=agent,
                status="acked",
                payload={
                    "event": "tool_response",
                    "node_key": node_key,
                    "agent": agent.name,
                    "tool": tool_name,
                    "response": result,
                    "summary": f"{node_key}: tool {tool_name} responded.",
                },
            )
            tool_trace.append({"event": "tool_response", "tool": tool_name, "response": result})
            if isinstance(result, dict) and str(result.get("status") or "").lower() == "error":
                raise RuntimeError(f"Tool '{tool_name}' failed: {result.get('error') or result.get('summary') or 'unknown error'}")

        for tool_name in precompose_tools:
            run_tool(tool_name)

        agent_output = self._compose_agent_output(
            agent=agent,
            node=node,
            state=state,
            tool_outputs=tool_outputs,
            skill_payloads=skill_payloads,
        )

        for tool_name in postcompose_tools:
            config = self._tool_config(tool_name=tool_name, node=node, state=state, agent_output=agent_output)
            self._emit_message(
                run=run,
                from_agent=agent,
                status="queued",
                payload={
                    "event": "tool_request",
                    "node_key": node_key,
                    "agent": agent.name,
                    "tool": tool_name,
                    "request": config,
                    "summary": f"{node_key}: calling tool {tool_name}.",
                },
            )
            tool_trace.append({"event": "tool_request", "tool": tool_name, "request": config})
            result = dispatch(tool_name, config, self._tool_context(run=run, agent=agent, node=node, state=state, tool_outputs=tool_outputs))
            tool_outputs[tool_name] = result
            self._emit_message(
                run=run,
                from_agent=agent,
                status="acked",
                payload={
                    "event": "tool_response",
                    "node_key": node_key,
                    "agent": agent.name,
                    "tool": tool_name,
                    "response": result,
                    "summary": f"{node_key}: tool {tool_name} responded.",
                },
            )
            tool_trace.append({"event": "tool_response", "tool": tool_name, "response": result})
            if isinstance(result, dict) and str(result.get("status") or "").lower() == "error":
                raise RuntimeError(f"Tool '{tool_name}' failed: {result.get('error') or result.get('summary') or 'unknown error'}")

        message = InterAgentMessage.objects.create(
            run=run,
            message_id=str(uuid4()),
            from_agent=agent,
            channel="internal",
            status="acked",
            payload={"node_key": node_key, "summary": agent_output.get("summary"), "output": agent_output},
        )
        self._record_estimated_cost(run=run, agent=agent, node_key=node_key, output=agent_output)
        return {
            "status": "completed",
            "node_key": node_key,
            "agent": agent.name,
            "objective": str(node.get("objective") or ""),
            "tools": tool_outputs,
            "tool_trace": tool_trace,
            "skills": skill_payloads,
            "message_id": message.message_id,
            **agent_output,
        }

    def _emit_message(
        self,
        *,
        run: UnifiedRun,
        payload: dict[str, Any],
        from_agent: Agent | None = None,
        status: str = "queued",
    ) -> InterAgentMessage:
        return InterAgentMessage.objects.create(
            run=run,
            message_id=str(uuid4()),
            from_agent=from_agent,
            channel="internal",
            status=status,
            payload=payload,
        )

    def _compose_agent_output(
        self,
        *,
        agent: Agent,
        node: dict[str, Any],
        state: WorkflowState,
        tool_outputs: dict[str, Any],
        skill_payloads: list[dict[str, str]],
    ) -> dict[str, Any]:
        node_key = self._node_key(node)
        if node_key == "quality_review":
            source_output = (state.get("outputs") or {}).get("summarize") or {}
            has_artifact = bool(source_output.get("artifact_path") or (source_output.get("tools") or {}).get("write_artifact"))
            return {
                "summary": "Quality review passed." if has_artifact else "Quality review requested another evidence pass.",
                "enough_evidence": bool(has_artifact),
                "reasons": [] if has_artifact else ["No written artifact was found."],
            }
        if node_key == "escalation":
            objective = str(state.get("objective") or "").lower()
            needs_escalation = any(term in objective for term in ["refund", "charged", "billing", "cancel", "legal"])
            return {
                "summary": "Escalation created." if needs_escalation else "No escalation required.",
                "needs_escalation": needs_escalation,
                "ticket": tool_outputs.get("ticket_create") if needs_escalation else {},
            }

        system_prompt = (
            f"{agent.system_prompt}\n\n"
            "You are executing one node in a LangGraph workflow. Return strict JSON with "
            "summary, details, and confidence. Use only supplied tool outputs and state."
        )
        payload = {
            "agent": agent.name,
            "role": agent.role,
            "node": node,
            "objective": state.get("objective"),
            "input": state.get("input"),
            "prior_outputs": state.get("outputs"),
            "tool_outputs": tool_outputs,
            "skills": skill_payloads,
        }
        schema = {
            "name": "workflow_node_output",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "details": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["summary", "details", "confidence"],
                "additionalProperties": False,
            },
        }
        try:
            parsed = async_to_sync(complete_json)(
                system_prompt=system_prompt,
                user_payload=payload,
                max_tokens=900,
                temperature=0.2,
                reasoning_enabled=False,
                timeout_seconds=15.0,
                context=f"Workflow node {node_key}",
                response_schema=schema,
            )
        except (LLMConfigurationError, RuntimeError, ValueError) as exc:
            raise RuntimeError(f"Failed to compose output for node '{node_key}': {exc}") from exc

        summary = str(parsed.get("summary") or "").strip()
        details = str(parsed.get("details") or "").strip()
        if not summary:
            raise ValueError(f"Workflow node '{node_key}' returned an empty summary.")
        return {
            "summary": summary,
            "details": details,
            "confidence": self._coerce_float(parsed.get("confidence"), default=0.5),
        }

    def _load_allowed_skills(self, *, agent: Agent, node: dict[str, Any]) -> list[dict[str, str]]:
        allowed = {str(skill).strip() for skill in agent.skills if str(skill).strip()} if isinstance(agent.skills, list) else set()
        requested = [str(skill).strip() for skill in node.get("skills") or [] if str(skill).strip()]
        selected = [skill for skill in requested if skill in allowed]
        rows: list[dict[str, str]] = []
        for skill in Skill.objects.filter(name__in=selected, is_active=True).order_by("priority", "name"):
            rows.append({"name": skill.name, "description": skill.description, "category": skill.category, "markdown": skill.markdown})
        return rows

    def _tool_config(
        self,
        *,
        tool_name: str,
        node: dict[str, Any],
        state: WorkflowState,
        agent_output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        objective = str(state.get("objective") or "").strip()
        if tool_name == "web_search":
            return {"query": objective or str(node.get("objective") or "")}
        if tool_name == "read_url":
            return {"url": str((state.get("input") or {}).get("url") or "").strip()}
        if tool_name in {"write_artifact", "send_channel_message"}:
            content = self._tool_content(agent_output=agent_output, node=node, tool_name=tool_name)
            return {"path": f"{self._node_key(node)}.md", "content": content, "message": content, "channel": str((state.get("input") or {}).get("channel") or "ui")}
        if tool_name == "discord_rw":
            input_payload = state.get("input") or {}
            content = self._tool_content(agent_output=agent_output, node=node, tool_name=tool_name)
            return {
                "operation": str(node.get("operation") or "write"),
                "message": content,
                "external_user_id": str(input_payload.get("external_user_id") or ""),
                "conversation_id": input_payload.get("conversation_id"),
                "discord_channel_id": input_payload.get("discord_channel_id"),
                "provider": input_payload.get("provider"),
            }
        if tool_name == "knowledge_base_search":
            return {"query": objective}
        if tool_name == "ticket_create":
            return {"summary": objective or str(node.get("objective") or ""), "priority": "normal"}
        if tool_name in {"memory_read", "memory_write"}:
            return {"agent_name": str(node.get("agent") or "workflow"), "key": self._node_key(node), "value": state.get("outputs") or {}}
        return {"objective": objective}

    def _tool_context(
        self,
        *,
        run: UnifiedRun,
        agent: Agent,
        node: dict[str, Any],
        state: WorkflowState,
        tool_outputs: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "run_id": str(run.id),
            "agent_name": agent.name,
            "node_key": self._node_key(node),
            "objective": state.get("objective"),
            "input": state.get("input") or {},
            "outputs": state.get("outputs") or {},
            **tool_outputs,
        }

    def _route_callable(self, *, node_key: str, edges: list[dict[str, Any]]):
        def route(state: WorkflowState) -> str:
            outputs = state.get("outputs") or {}
            visits = state.get("visits") or {}
            if int(visits.get(node_key, 0)) >= self.max_node_visits:
                fallback = next((edge for edge in edges if str(edge.get("to") or "").strip() not in {node_key}), edges[-1])
                return self._edge_label(fallback)
            unconditional: dict[str, Any] | None = None
            for edge in edges:
                condition = edge.get("condition")
                if not isinstance(condition, dict):
                    unconditional = edge
                    continue
                if self._condition_matches(condition=condition, outputs=outputs):
                    return self._edge_label(edge)
            if unconditional is not None:
                return self._edge_label(unconditional)
            return self._edge_label(edges[-1])

        return route

    def _condition_matches(self, *, condition: dict[str, Any], outputs: dict[str, Any]) -> bool:
        field = str(condition.get("field") or "").strip()
        actual = self._get_path({"outputs": outputs}, field)
        expected = condition.get("value")
        op = str(condition.get("op") or "eq").strip().lower()
        normalized_actual = self._normalize_condition_value(actual)
        normalized_expected = self._normalize_condition_value(expected)
        if op in {"eq", "=="}:
            return normalized_actual == normalized_expected
        if op in {"ne", "!="}:
            return normalized_actual != normalized_expected
        return bool(normalized_actual)

    def _normalize_condition_value(self, value: Any) -> Any:
        if isinstance(value, str):
            trimmed = value.strip()
            lowered = trimmed.lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
            if lowered in {"null", "none"}:
                return None
            try:
                if "." in trimmed:
                    return float(trimmed)
                return int(trimmed)
            except (TypeError, ValueError):
                return trimmed
        return value

    def _get_path(self, payload: dict[str, Any], dotted_path: str) -> Any:
        current: Any = payload
        for part in dotted_path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    def _nodes_by_key(self, raw_nodes: Any) -> dict[str, dict[str, Any]]:
        nodes: dict[str, dict[str, Any]] = {}
        if not isinstance(raw_nodes, list):
            return nodes
        for raw in raw_nodes:
            if not isinstance(raw, dict):
                continue
            key = self._node_key(raw)
            if key:
                nodes[key] = raw
        return nodes

    def _node_key(self, node: dict[str, Any]) -> str:
        return str(node.get("key") or node.get("node_key") or "").strip()

    def _edge_label(self, edge: dict[str, Any]) -> str:
        target = str(edge.get("to") or "").strip()
        condition = edge.get("condition")
        if isinstance(condition, dict):
            return f"{target}:{condition.get('field')}:{condition.get('value')}"
        return target

    def _compact_state(self, state: WorkflowState) -> dict[str, Any]:
        return {
            "objective": state.get("objective"),
            "input": state.get("input"),
            "outputs": list((state.get("outputs") or {}).keys()),
            "visits": state.get("visits") or {},
        }

    def _tool_content(self, *, agent_output: dict[str, Any] | None, node: dict[str, Any], tool_name: str) -> str:
        if not isinstance(agent_output, dict):
            raise ValueError(f"Tool '{tool_name}' on node '{self._node_key(node)}' requires generated agent output.")
        details = str(agent_output.get("details") or "").strip()
        if details:
            return details
        summary = str(agent_output.get("summary") or "").strip()
        if summary:
            return summary
        raise ValueError(f"Tool '{tool_name}' on node '{self._node_key(node)}' requires non-empty output content.")

    def _fallback_summary(self, *, node: dict[str, Any], tool_outputs: dict[str, Any]) -> str:
        successful = [name for name, value in tool_outputs.items() if isinstance(value, dict) and str(value.get("status") or "").lower() == "ok"]
        label = str(node.get("label") or self._node_key(node) or "Node")
        if successful:
            return f"{label} completed with tools: {', '.join(successful)}."
        return f"{label} completed."

    def _fallback_details(self, *, state: WorkflowState, tool_outputs: dict[str, Any]) -> str:
        parts: list[str] = []
        objective = str(state.get("objective") or "").strip()
        if objective:
            parts.append(f"Objective: {objective}")
        for node_key, output in (state.get("outputs") or {}).items():
            if isinstance(output, dict):
                summary = str(output.get("summary") or "").strip()
                if summary:
                    parts.append(f"{node_key}: {summary}")
        for tool_name, output in tool_outputs.items():
            if isinstance(output, dict):
                parts.append(f"{tool_name}: {str(output.get('summary') or output.get('abstract') or output.get('status') or '')[:240]}")
        return "\n".join(part for part in parts if part) or "Workflow node completed."

    def _record_estimated_cost(self, *, run: UnifiedRun, agent: Agent, node_key: str, output: dict[str, Any]) -> None:
        text = f"{output.get('summary', '')} {output.get('details', '')}"
        input_tokens = 120
        output_tokens = max(20, len(text.split()))
        TokenCostLedger.objects.create(
            run=run,
            agent=agent,
            step_key=node_key,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_name="workflow-node-estimate",
            estimated_cost_usd=Decimal("0.000001") * Decimal(input_tokens + output_tokens),
            is_estimated=True,
        )

    def _event(self, *, run: UnifiedRun, event_type: str, message: str, level: str = "info", context: dict[str, Any] | None = None) -> None:
        RuntimeEvent.objects.create(run=run, level=level, event_type=event_type, message=message, context=context or {})

    def _coerce_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
