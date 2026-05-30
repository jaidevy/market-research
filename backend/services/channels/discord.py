from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from typing import Any

import httpx

from apps.agents.models import Agent
from apps.messaging.models import ChannelConversation, ChannelMessage
from apps.runs.models import WorkflowTemplate
from services.runtime.langgraph_workflow import LangGraphWorkflowRunner
from services.runtime.workflow_templates import seed_generic_workflow_assets


LOG = logging.getLogger(__name__)


def verify_signature(payload: bytes, signature: str | None) -> bool:
    secret = os.environ.get("DISCORD_WEBHOOK_SECRET", "")
    if not secret:
        return True
    if not signature:
        return False
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def _send_outbound_message(
    provider: str,
    external_user_id: str,
    message: str,
    discord_channel_id: int | None = None,
) -> dict:
    from services.channels.discord_bot import bot_gateway  # noqa: PLC0415

    if bot_gateway.is_running() and discord_channel_id:
        return bot_gateway.send_to_channel_sync(discord_channel_id, message)

    provider_norm = (provider or "").strip().lower()
    if provider_norm == "bot":
        return {"ok": False, "error": "bot_not_running"}
    if provider_norm in {"agent_tool", ""}:
        return {"ok": False, "error": "provider_agent_tool"}
    if provider_norm not in {"webhook", "discord_webhook", "http"}:
        return {"ok": False, "error": f"unsupported_provider:{provider_norm}"}

    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return {"ok": False, "error": "missing_discord_webhook_url"}

    payload: dict = {
        "content": f"[{external_user_id}] {message}" if external_user_id else message,
        "username": os.environ.get("DISCORD_WEBHOOK_USERNAME", "Agent Orchestrator") or "Agent Orchestrator",
    }

    try:
        response = httpx.post(webhook_url, json=payload, timeout=30)
        response.raise_for_status()
        return {"ok": True, "status_code": response.status_code}
    except Exception as exc:
        LOG.exception("Discord webhook send failed")
        return {"ok": False, "error": str(exc)}


def _build_workflow_summary(run_result: dict[str, Any]) -> str:
    run = run_result.get("run") if isinstance(run_result, dict) else {}
    workflow = run_result.get("workflow") if isinstance(run_result, dict) else {}
    result = run_result.get("result") if isinstance(run_result, dict) else {}
    final = result.get("final") if isinstance(result, dict) else {}
    outputs = result.get("outputs") if isinstance(result, dict) else {}

    run_id = run.get("id") if isinstance(run, dict) else None
    workflow_name = str((workflow or {}).get("name") or "Workflow")
    summary = str((final or {}).get("summary") or "Workflow completed.").strip()
    details = str((final or {}).get("details") or "").strip()
    if not details and isinstance(outputs, dict):
        detail_rows = []
        for node_key, output in outputs.items():
            if isinstance(output, dict) and output.get("summary"):
                detail_rows.append(f"- {node_key}: {output.get('summary')}")
        details = "\n".join(detail_rows[:4])

    lines = [f"**{workflow_name} - Run #{run_id or '-'}**", summary]
    if details:
        lines.append(details[:1200])
    lines.append(f"_Run #{run_id or '-'} completed_")
    return "\n".join(line for line in lines if line)


def _ensure_discord_channel_assets(agent: Agent) -> Agent:
    tools = list(agent.tools) if isinstance(agent.tools, list) else []
    channels = list(agent.channels) if isinstance(agent.channels, list) else []
    if "discord_rw" not in tools:
        tools.append("discord_rw")
    if "discord" not in channels:
        channels.append("discord")
    changed = tools != agent.tools or channels != agent.channels or not agent.is_active
    if changed:
        agent.tools = tools
        agent.channels = channels
        agent.is_active = True
        agent.save(update_fields=["tools", "channels", "is_active", "updated_at"])
    return agent


def _seed_generic_assets_if_needed() -> dict[str, Any]:
    if WorkflowTemplate.objects.filter(is_active=True).exists() and Agent.objects.filter(name="ConciergeAgent").exists():
        return {"templates": list(WorkflowTemplate.objects.filter(is_active=True))}
    return seed_generic_workflow_assets()


def _select_discord_workflow_template(body: str, seeded: dict[str, Any]) -> WorkflowTemplate | None:
    active_templates = list(WorkflowTemplate.objects.filter(is_active=True).order_by("name"))
    if not active_templates and seeded.get("templates"):
        active_templates = [item for item in seeded["templates"] if getattr(item, "is_active", False)]
    if not active_templates:
        return None

    body_words = set(re.findall(r"[a-z0-9]+", str(body or "").lower()))
    ranked: list[tuple[int, WorkflowTemplate]] = []
    for template in active_templates:
        name_words = set(re.findall(r"[a-z0-9]+", str(template.name or "").lower())) - {"workflow"}
        if not name_words:
            continue
        score = len(body_words & name_words)
        if score:
            ranked.append((score, template))
    if ranked:
        ranked.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        return ranked[0][1]

    return next(
        (template for template in active_templates if template.name == "Customer Support Triage Workflow"),
        active_templates[0],
    )


def _run_generic_discord_workflow(
    *,
    body: str,
    external_user_id: str,
    agent: Agent,
    conversation: ChannelConversation,
    discord_channel_id: int | None = None,
) -> dict[str, Any] | None:
    seeded = _seed_generic_assets_if_needed()
    template = _select_discord_workflow_template(body, seeded)
    if template is None:
        return None
    return LangGraphWorkflowRunner().run(
        template=template,
        payload={
            "channel": "discord",
            "objective": body,
            "body": body,
            "external_user_id": external_user_id,
            "target_agent": agent.name,
            "conversation_id": conversation.id,
            "discord_channel_id": discord_channel_id,
            "provider": os.environ.get("DISCORD_PROVIDER", "agent_tool").strip().lower(),
            "trigger": "discord",
        },
        trigger="discord",
    )


def ingest_message(
    external_user_id: str,
    body: str,
    target_agent_name: str,
    discord_channel_id: int | None = None,
) -> dict[str, object]:
    try:
        raw_channel_id = discord_channel_id
        if raw_channel_id in {None, ""}:
            discord_channel_id = None
        else:
            discord_channel_id = int(str(raw_channel_id))
    except (TypeError, ValueError):
        discord_channel_id = None
    provider = os.environ.get("DISCORD_PROVIDER", "agent_tool").strip().lower()
    delivery_mode = "local_record_only"
    externally_sent = False

    _seed_generic_assets_if_needed()
    target_agent_name = target_agent_name or "ConciergeAgent"
    agent = Agent.objects.filter(name=target_agent_name).first()
    if agent is None:
        return {"processed": False, "error": "Target agent not found"}
    agent = _ensure_discord_channel_assets(agent)

    conversation, _ = ChannelConversation.objects.get_or_create(
        external_channel="discord",
        external_user_id=external_user_id,
        target_agent=agent,
    )

    ChannelMessage.objects.create(
        conversation=conversation,
        direction="inbound",
        body=body,
        metadata={"provider": provider, "source": "channel_ingest"},
    )

    accepted = ChannelMessage.objects.create(
        conversation=conversation,
        direction="outbound",
        body="Concierge ping: I received your request and started the agent workflow.",
        metadata={"source": "langgraph_workflow", "status": "accepted", "provider": provider},
    )
    if provider != "agent_tool" or discord_channel_id:
        send_result = _send_outbound_message(provider, external_user_id, accepted.body, discord_channel_id)
        externally_sent = externally_sent or bool(send_result.get("ok"))
        if discord_channel_id and send_result.get("ok"):
            delivery_mode = "discord_bot"
        elif provider in {"webhook", "discord_webhook", "http"}:
            delivery_mode = "discord_webhook" if send_result.get("ok") else "discord_webhook_failed"
        elif provider == "bot":
            delivery_mode = "discord_bot" if send_result.get("ok") else "discord_bot_not_running"
        accepted.metadata = {**(accepted.metadata or {}), "sent_via": provider, "send_result": send_result}
        accepted.save(update_fields=["metadata", "updated_at"])

    try:
        run_result = _run_generic_discord_workflow(
            body=body,
            external_user_id=external_user_id,
            agent=agent,
            conversation=conversation,
            discord_channel_id=discord_channel_id,
        )
        workflow_payload = run_result.get("workflow") if isinstance(run_result, dict) else None
        if run_result is None:
            return {"processed": False, "conversation_id": conversation.id, "error": "Customer Support Triage Workflow is not available"}
    except Exception as exc:
        failed = ChannelMessage.objects.create(
            conversation=conversation,
            direction="outbound",
            body=f"Agent workflow failed: {exc}",
            metadata={"source": "langgraph_workflow", "status": "failed", "provider": provider},
        )
        if provider != "agent_tool" or discord_channel_id:
            send_result = _send_outbound_message(provider, external_user_id, failed.body, discord_channel_id)
            failed.metadata = {**(failed.metadata or {}), "sent_via": provider, "send_result": send_result}
            failed.save(update_fields=["metadata", "updated_at"])
        return {"processed": False, "conversation_id": conversation.id, "error": str(exc)}

    run_payload = run_result.get("run") if isinstance(run_result, dict) else {}
    run_id = run_payload.get("id") if isinstance(run_payload, dict) else None
    run_status = run_payload.get("status") if isinstance(run_payload, dict) else "completed"
    result_payload = run_result.get("result") if isinstance(run_result, dict) else {}
    outputs_payload = result_payload.get("outputs") if isinstance(result_payload, dict) else {}
    reply_output = outputs_payload.get("reply") if isinstance(outputs_payload, dict) else {}
    reply_tools = reply_output.get("tools") if isinstance(reply_output, dict) else {}
    discord_rw_result = reply_tools.get("discord_rw") if isinstance(reply_tools, dict) else None
    if isinstance(discord_rw_result, dict):
        externally_sent = externally_sent or bool(discord_rw_result.get("externally_sent"))
        delivery_mode = str(discord_rw_result.get("delivery_mode") or delivery_mode)

    if run_id:
        from apps.runs.models import UnifiedRun

        run = UnifiedRun.objects.filter(id=run_id).first()
        if run is not None:
            conversation.active_run = run
            conversation.save(update_fields=["active_run", "updated_at"])

    completed = ChannelMessage.objects.create(
        conversation=conversation,
        direction="outbound",
        body=_build_workflow_summary(run_result),
        metadata={
            "source": "langgraph_workflow",
            "status": run_status,
            "run_id": run_id,
            "provider": provider,
            "delivery_mode": delivery_mode,
            "externally_sent": externally_sent,
            "delivered_by": "discord_rw" if isinstance(discord_rw_result, dict) else "channel_sender",
        },
    )
    if not isinstance(discord_rw_result, dict) and (provider != "agent_tool" or discord_channel_id):
        from services.runtime.tool_registry import dispatch  # noqa: PLC0415

        send_result = dispatch(
            "discord_rw",
            {
                "operation": "write",
                "message": completed.body,
                "external_user_id": external_user_id,
                "conversation_id": conversation.id,
                "discord_channel_id": discord_channel_id,
                "provider": provider,
            },
            {
                "run_id": str(run_id or ""),
                "agent_name": agent.name,
                "node_key": "discord_completed_reply",
                "input": {
                    "external_user_id": external_user_id,
                    "conversation_id": conversation.id,
                    "discord_channel_id": discord_channel_id,
                    "provider": provider,
                },
            },
        )
        externally_sent = externally_sent or bool(send_result.get("externally_sent"))
        delivery_mode = str(send_result.get("delivery_mode") or delivery_mode)
        completed.metadata = {**(completed.metadata or {}), "sent_via": provider, "send_result": send_result, "delivered_by": "discord_rw"}
        completed.save(update_fields=["metadata", "updated_at"])

    return {
        "processed": True,
        "conversation_id": conversation.id,
        "run_id": run_id,
        "run_status": run_status,
        "completed_steps": 6,
        "reply": completed.body,
        "provider": provider,
        "delivery_mode": delivery_mode,
        "externally_sent": externally_sent,
        "workflow": workflow_payload,
    }
