from typing import Any

from django.db.models import Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agents.models import Agent
from apps.messaging.models import InterAgentMessage
from apps.monitoring.models import RuntimeEvent, TokenCostLedger
from apps.monitoring.serializers import RuntimeEventSerializer, TokenCostLedgerSerializer
from apps.runs.models import UnifiedRun, UnifiedRunStep


class RuntimeMetricsView(APIView):
    def get(self, request):
        run_id = request.query_params.get("run_id")
        token_qs = TokenCostLedger.objects.all().order_by("-created_at")
        event_qs = RuntimeEvent.objects.all().order_by("-created_at")
        run: UnifiedRun | None = None

        if run_id:
            token_qs = token_qs.filter(run_id=run_id)
            event_qs = event_qs.filter(run_id=run_id)
            run = UnifiedRun.objects.filter(id=run_id).first()

        aggregate = token_qs.aggregate(
            input_tokens=Sum("input_tokens"),
            output_tokens=Sum("output_tokens"),
            estimated_cost_usd=Sum("estimated_cost_usd"),
        )
        achievements = self._build_agent_achievements(run)
        complete_log = self._build_complete_log(run)

        return Response(
            {
                "summary": {
                    "input_tokens": aggregate["input_tokens"] or 0,
                    "output_tokens": aggregate["output_tokens"] or 0,
                    "estimated_cost_usd": str(aggregate["estimated_cost_usd"] or 0),
                },
                "token_entries": TokenCostLedgerSerializer(token_qs[:200], many=True).data,
                "events": RuntimeEventSerializer(event_qs[:200], many=True).data,
                "agent_logs": self._build_agent_logs(token_qs=token_qs[:200], event_qs=event_qs[:200], run_id=run_id)
                + self._build_achievement_log_lines(achievements),
                "run": self._build_run_payload(run),
                "workflow_result": run.output_payload if run is not None else {},
                "agent_achievements": achievements,
                "complete_log": complete_log,
            }
        )

    def _build_achievement_log_lines(self, achievements: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for item in achievements:
            agent = str(item.get("agent") or "Agent")
            node_key = str(item.get("node_key") or "step")
            available_tools = self._join_log_list(item.get("available_tools"))
            picked_tools = self._join_log_list(item.get("picked_tools"))
            available_skills = self._join_log_list(item.get("available_skills"))
            picked_skills = self._join_log_list(item.get("picked_skills"))
            output = str(item.get("summary") or item.get("details") or "No output summary recorded.").strip()
            if len(output) > 280:
                output = f"{output[:277]}..."
            lines.append(
                f"Agent {agent} [{node_key}] | tools available: {available_tools} | tools picked: {picked_tools} | "
                f"skills available: {available_skills} | skills picked: {picked_skills} | output: {output}"
            )
        return lines

    def _join_log_list(self, value: object) -> str:
        if not isinstance(value, list):
            return "none"
        items = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(items) if items else "none"

    def _build_run_payload(self, run: UnifiedRun | None) -> dict[str, Any]:
        if run is None:
            return {}
        return {
            "id": run.id,
            "run_name": run.run_name,
            "status": run.status,
            "trigger": run.trigger,
            "input_payload": run.input_payload,
            "output_payload": run.output_payload,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        }

    def _build_agent_achievements(self, run: UnifiedRun | None) -> list[dict[str, Any]]:
        if run is None:
            return []

        achievements: list[dict[str, Any]] = []
        steps = UnifiedRunStep.objects.filter(run=run).order_by("created_at", "id")
        for step in steps:
            output = step.output_payload if isinstance(step.output_payload, dict) else {}
            input_payload = step.input_payload if isinstance(step.input_payload, dict) else {}
            raw_node = input_payload.get("node")
            node = raw_node if isinstance(raw_node, dict) else {}
            raw_tools = output.get("tools")
            tools = raw_tools if isinstance(raw_tools, dict) else {}
            tool_trace = output.get("tool_trace") if isinstance(output.get("tool_trace"), list) else []
            raw_skills = output.get("skills")
            skills = raw_skills if isinstance(raw_skills, list) else []
            agent_name = str(output.get("agent") or node.get("agent") or "Agent").strip()
            agent = Agent.objects.filter(name=agent_name).first()
            available_tools = list(agent.tools) if agent is not None and isinstance(agent.tools, list) else []
            available_skills = list(agent.skills) if agent is not None and isinstance(agent.skills, list) else []
            requested_tools = [str(tool).strip() for tool in node.get("tools") or [] if str(tool).strip()]
            requested_skills = [str(skill).strip() for skill in node.get("skills") or [] if str(skill).strip()]
            picked_tools = list(tools.keys())
            picked_skills = [str(skill.get("name") or "").strip() for skill in skills if isinstance(skill, dict) and str(skill.get("name") or "").strip()]
            achievements.append(
                {
                    "step_id": step.id,
                    "node_key": step.node_key,
                    "node_label": str(node.get("label") or step.node_key).strip(),
                    "agent": agent_name,
                    "status": step.status,
                    "objective": str(output.get("objective") or node.get("objective") or "").strip(),
                    "summary": str(output.get("summary") or "").strip(),
                    "details": str(output.get("details") or "").strip(),
                    "confidence": output.get("confidence"),
                    "available_tools": available_tools,
                    "available_skills": available_skills,
                    "requested_tools": requested_tools,
                    "requested_skills": requested_skills,
                    "picked_tools": picked_tools,
                    "picked_skills": picked_skills,
                    "tools": tools,
                    "tool_trace": tool_trace,
                    "skills": skills,
                    "artifact_path": output.get("artifact_path"),
                    "message_id": output.get("message_id"),
                    "error": step.error_message or str(output.get("error") or ""),
                    "started_at": step.created_at.isoformat() if step.created_at else None,
                    "completed_at": step.updated_at.isoformat() if step.updated_at else None,
                    "result": output,
                }
            )
        return achievements

    def _build_complete_log(self, run: UnifiedRun | None) -> list[dict[str, Any]]:
        if run is None:
            return []

        rows: list[dict[str, Any]] = []
        for event in RuntimeEvent.objects.filter(run=run).order_by("created_at", "id"):
            context = event.context if isinstance(event.context, dict) else {}
            rows.append(
                {
                    "kind": "event",
                    "time": event.created_at.isoformat() if event.created_at else None,
                    "level": event.level,
                    "title": event.event_type.replace("_", " ").title(),
                    "message": event.message,
                    "node_key": context.get("node_key"),
                    "payload": context,
                }
            )

        for message in InterAgentMessage.objects.filter(run=run).select_related("from_agent", "to_agent").order_by("created_at", "id"):
            payload = message.payload if isinstance(message.payload, dict) else {}
            rows.append(
                {
                    "kind": "message",
                    "time": message.created_at.isoformat() if message.created_at else None,
                    "level": message.status,
                    "title": "Inter-Agent Message",
                    "message": str(payload.get("summary") or payload.get("message") or "Message exchanged."),
                    "node_key": payload.get("node_key"),
                    "from_agent": message.from_agent.name if message.from_agent else None,
                    "to_agent": message.to_agent.name if message.to_agent else None,
                    "payload": payload,
                }
            )

        for token in TokenCostLedger.objects.filter(run=run).select_related("agent").order_by("created_at", "id"):
            rows.append(
                {
                    "kind": "token_cost",
                    "time": token.created_at.isoformat() if token.created_at else None,
                    "level": "estimated" if token.is_estimated else "actual",
                    "title": "Token Usage",
                    "message": f"{token.step_key or 'unknown'} used {token.input_tokens} input and {token.output_tokens} output tokens.",
                    "node_key": token.step_key,
                    "from_agent": token.agent.name if token.agent else None,
                    "payload": {
                        "input_tokens": token.input_tokens,
                        "output_tokens": token.output_tokens,
                        "model_name": token.model_name,
                        "estimated_cost_usd": str(token.estimated_cost_usd),
                        "is_estimated": token.is_estimated,
                    },
                }
            )

        return sorted(rows, key=lambda row: str(row.get("time") or ""))

    def _build_agent_logs(self, token_qs, event_qs, run_id: str | None) -> list[str]:
        lines: list[str] = []
        for event in reversed(list(event_qs)):
            lines.append(self._format_event_line(event=event))

        for token in reversed(list(token_qs)):
            lines.append(self._format_token_line(token=token))

        if not lines:
            suffix = f" for run #{run_id}" if run_id else ""
            return [f"No agent logs available{suffix}."]
        return lines

    def _format_event_line(self, event: RuntimeEvent) -> str:
        ts = timezone.localtime(event.created_at).strftime("%H:%M:%S")
        run_fragment = f"run={getattr(event, 'run_id', '-')}"
        context = event.context if isinstance(event.context, dict) else {}
        node_key = str(context.get("node_key") or "").strip()

        if event.event_type == "run_started":
            return f"[{ts}] [SYSTEM] [{run_fragment}] run started"
        if event.event_type == "run_completed":
            return f"[{ts}] [SYSTEM] [{run_fragment}] run completed"
        if event.event_type == "unified_run_completed":
            return f"[{ts}] [SYSTEM] [{run_fragment}] unified research flow completed"
        if event.event_type == "step_started" and node_key:
            return f"[{ts}] [AGENT:{node_key}] [{run_fragment}] started"
        if event.event_type == "step_completed" and node_key:
            return f"[{ts}] [AGENT:{node_key}] [{run_fragment}] completed"
        if event.event_type == "step_detail" and node_key:
            return self._format_step_detail_line(
                ts=ts,
                run_fragment=run_fragment,
                node_key=node_key,
                context=context,
            )

        return f"[{ts}] [{event.level.upper()}] [{run_fragment}] {event.message}"

    def _format_token_line(self, token: TokenCostLedger) -> str:
        ts = timezone.localtime(token.created_at).strftime("%H:%M:%S")
        run_fragment = f"run={getattr(token, 'run_id', '-')}"
        step = token.step_key or "unknown"
        return (
            f"[{ts}] [TOKENS:{step}] [{run_fragment}] "
            f"in={token.input_tokens} out={token.output_tokens} model={token.model_name}"
        )

    def _format_step_detail_line(
        self,
        *,
        ts: str,
        run_fragment: str,
        node_key: str,
        context: dict[str, object],
    ) -> str:
        ordered_keys = [
            "decision",
            "status",
            "risk_state",
            "direction",
            "confidence",
            "provider",
            "model",
            "input_tokens",
            "output_tokens",
            "ticket_status",
            "ticket_id",
            "tool_calls",
            "output",
            "reasoning",
            "thinking",
            "summary",
        ]
        parts: list[str] = []
        for key in ordered_keys:
            if key not in context:
                continue
            value = self._format_log_value(context.get(key))
            if not value:
                continue
            parts.append(f"{key}={value}")

        if not parts:
            return f"[{ts}] [AGENT:{node_key}] [{run_fragment}] detail captured"
        return f"[{ts}] [AGENT:{node_key}] [{run_fragment}] " + " ".join(parts)

    def _format_log_value(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, float):
            return f"{value:.4f}".rstrip("0").rstrip(".")

        text = str(value).strip()
        if not text:
            return ""
        if len(text) > 240:
            text = f"{text[:237]}..."
        if " " in text:
            return f'"{text}"'
        return text
