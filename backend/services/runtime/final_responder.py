from __future__ import annotations

from asgiref.sync import async_to_sync
from typing import Any

from apps.agents.models import Skill
from apps.runs.models import UnifiedRun
from services.runtime.artifacts import write_final_artifact


class LLMConfigurationError(RuntimeError):
    """Raised when the runtime LLM client is unavailable or misconfigured."""


async def complete_json(*, system_prompt: str, user_payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    raise LLMConfigurationError("LLM backend is not available in this runtime.")


def summarize_run_state(run: UnifiedRun) -> dict[str, Any]:
    steps = list(run.steps.order_by("created_at"))
    summaries: list[str] = []
    decision_fragments: list[str] = []
    decision_seen: set[str] = set()
    symbol = str((run.input_payload or {}).get("symbol") or "").strip().upper()
    research_sections: list[str] = []
    research_seen: set[str] = set()
    for step in steps:
        output = step.output_payload if isinstance(step.output_payload, dict) else {}
        summary = str(output.get("summary") or "").strip()
        if summary:
            summaries.append(f"{step.node_key}: {summary}")
        tools = output.get("tools") if isinstance(output.get("tools"), dict) else {}
        for tool_name in (
            "web_search",
            "read_url",
            "knowledge_base_search",
            "ticket_create",
            "send_channel_message",
            "memory_read",
            "memory_write",
            "read_file",
            "write_file",
            "discord_rw",
        ):
            tool_output = tools.get(tool_name) if isinstance(tools, dict) else None
            if isinstance(tool_output, dict):
                fragment = _format_tool_decision(tool_name=tool_name, payload=tool_output)
                if fragment:
                    fragment_key = _normalize_fragment(fragment)
                    if tool_name in {"web_search", "news_feed"}:
                        if fragment_key not in research_seen:
                            research_sections.append(fragment)
                            research_seen.add(fragment_key)
                    else:
                        if fragment_key not in decision_seen:
                            decision_fragments.append(fragment)
                            decision_seen.add(fragment_key)

    decision_text = "\n\n".join(fragment for fragment in decision_fragments if fragment).strip()
    research_text = "\n\n".join(section for section in research_sections if section).strip()

    header = f"Agentic run {run.id} for {symbol or 'the request'} completed."
    parts: list[str] = [header]
    if decision_text:
        parts.append(decision_text)
    if research_text:
        parts.append(research_text)
    if not decision_text and not research_text:
        parts.append(" ".join(summaries[:3]))

    fallback_reply = "\n\n".join(part for part in parts if part)
    reply = _compose_skill_reply(
        run=run,
        symbol=symbol,
        decision_fragments=decision_fragments,
        research_sections=research_sections,
        summaries=summaries,
        fallback_reply=fallback_reply,
    )
    artifact_path = write_final_artifact(run_id=run.id, text=reply)
    return {"reply": reply.strip(), "artifact_path": artifact_path, "summaries": summaries}


def _compose_skill_reply(
    *,
    run: UnifiedRun,
    symbol: str,
    decision_fragments: list[str],
    research_sections: list[str],
    summaries: list[str],
    fallback_reply: str,
) -> str:
    skill = _select_final_response_skill()
    if skill is None:
        return fallback_reply

    system_prompt = (
        f"{skill.markdown}\n\n"
        "You are composing the final user-facing response for an agentic workflow run. "
        "Return strict JSON only with a single string field named reply."
    )
    payload = {
        "run_id": run.id,
        "symbol": symbol,
        "decision_sections": decision_fragments,
        "research_sections": research_sections,
        "step_summaries": summaries,
        "fallback_reply": fallback_reply,
        "rules": [
            "Use only supplied evidence; do not fabricate facts.",
            "Turn information into actionable next steps.",
            "If evidence is insufficient, say what to fetch or monitor next.",
        ],
    }
    schema = {
        "name": "final_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"reply": {"type": "string"}},
            "required": ["reply"],
            "additionalProperties": False,
        },
    }
    try:
        parsed = async_to_sync(complete_json)(
            system_prompt=system_prompt,
            user_payload=payload,
            max_tokens=1600,
            temperature=0.2,
            reasoning_enabled=False,
            timeout_seconds=20.0,
            context="Final response skill",
            response_schema=schema,
        )
    except (LLMConfigurationError, RuntimeError, ValueError):
        return fallback_reply
    reply = str(parsed.get("reply") or "").strip()
    return reply or fallback_reply


def _select_final_response_skill() -> Skill | None:
    for skill in Skill.objects.filter(is_active=True, category="output").order_by("priority", "name"):
        trigger = str(skill.trigger or "").strip().lower()
        if trigger in {"final_response", "always", "*", "any"}:
            return skill
    return None


def _normalize_fragment(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _format_tool_decision(*, tool_name: str, payload: dict[str, Any]) -> str:
    if tool_name in {"knowledge_base_search", "memory_read", "memory_write", "ticket_create", "send_channel_message", "read_file", "write_file", "read_url", "discord_rw", "backtest", "start_research_goal", "get_research_goal", "add_goal_evidence", "update_research_goal_status"}:
        summary = str(payload.get("summary") or "").strip()
        status = str(payload.get("status") or "").strip()
        if summary:
            return f"**{tool_name}:** {summary}"
        if status:
            return f"**{tool_name}:** status={status}"
        return f"**{tool_name}:** completed."
    if tool_name == "web_search":
        headlines: list[str] = [str(h).strip() for h in (payload.get("headlines") or []) if str(h).strip()]
        abstract = str(payload.get("abstract") or "").strip()
        related: list[str] = [str(h).strip() for h in (payload.get("related") or []) if str(h).strip()]
        all_headlines = headlines or ([abstract] + related if abstract else related)
        all_headlines = _unique_strings([h for h in all_headlines if h])[:6]
        if not all_headlines:
            return ""
        bullet_lines = "\n".join(f"- {h}" for h in all_headlines)
        return f"**Web search results:**\n{bullet_lines}"
    return ""


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize_fragment(value)
        if not normalized or normalized in seen:
            continue
        unique.append(value)
        seen.add(normalized)
    return unique
