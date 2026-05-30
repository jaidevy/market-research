import os
import json
import queue
import time
from datetime import timedelta
from typing import Callable

from django.db.models import Q
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from apps.agents.models import Agent, AgentMemory, Skill, Tool
from apps.messaging.models import ApprovalTicket, ChannelConversation, InterAgentMessage
from apps.messaging.serializers import (
    ApprovalTicketSerializer,
    ChannelConversationSerializer,
    InterAgentMessageSerializer,
)
from apps.messaging.routing import resolve_route_with_model
from services.channels.discord import ingest_message, verify_signature


def _session_memory_config() -> dict[str, str | int]:
    return {
        "agent_name": "ChatSessionMemoryAgent",
        "key": "chat_session",
        "ttl_minutes": 12 * 60,
    }


def _sanitize_session_context(raw_context: dict | None) -> dict[str, str]:
    context = raw_context if isinstance(raw_context, dict) else {}
    return {
        "last_intent": str(context.get("last_intent") or "").strip().lower(),
        "last_agent_name": str(context.get("last_agent_name") or "").strip(),
        "last_user_turn": str(context.get("last_user_turn") or "").strip()[:280],
        "last_reply": str(context.get("last_reply") or "").strip()[:280],
    }


def _load_session_context(conversation_id) -> dict[str, str]:
    if not conversation_id:
        return {}
    cfg = _session_memory_config()
    record = (
        AgentMemory.objects.filter(
            agent_name=str(cfg["agent_name"]),
            run_id=str(conversation_id),
            key=str(cfg["key"]),
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        .order_by("-updated_at")
        .first()
    )
    if record is None:
        return {}
    return _sanitize_session_context(record.value)


def _store_session_context(*, conversation_id, route: dict[str, str | float], user_text: str, reply: str, extra: dict[str, str] | None = None) -> dict[str, str]:
    if not conversation_id:
        return {}
    cfg = _session_memory_config()
    base = {
        "last_intent": str(route.get("intent") or ""),
        "last_agent_name": str(route.get("selected_team_preset") or route.get("selected_agent") or ""),
        "last_user_turn": user_text,
        "last_reply": reply,
    }
    if extra:
        base.update(extra)
    context = _sanitize_session_context(base)
    ttl_minutes = int(cfg["ttl_minutes"])
    expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
    AgentMemory.objects.update_or_create(
        agent_name=str(cfg["agent_name"]),
        run_id=str(conversation_id),
        key=str(cfg["key"]),
        defaults={
            "value": context,
            "ttl_minutes": ttl_minutes,
            "expires_at": expires_at,
        },
    )
    return context


def _resolve_conversation_agent(*, active_agents: list[Agent], requested_name: str) -> Agent:
    requested = Agent.objects.filter(name=requested_name, is_active=True).first() if requested_name else None
    if requested is not None:
        return requested
    concierge = Agent.objects.filter(name="ConciergeAgent", is_active=True).first()
    if concierge is not None:
        return concierge
    return active_agents[0]


def _chat_help_text() -> str:
    return "\n".join(
        [
            "Chat Commands:",
            "/help",
            "/create-agent NAME | ROLE | SYSTEM_PROMPT",
            "/create-tool NAME | CATEGORY | CAP1,CAP2 | DESCRIPTION",
            "/create-skill NAME | CATEGORY | MARKDOWN",
        ]
    )


def _handle_chat_command(text: str) -> tuple[bool, str]:
    raw = str(text or "").strip()
    if not raw.startswith("/"):
        return False, ""

    def split_parts(payload: str, expected: int) -> list[str]:
        parts = [part.strip() for part in payload.split("|")]
        while len(parts) < expected:
            parts.append("")
        return parts[:expected]

    command, _, tail = raw.partition(" ")
    cmd = command.lower().strip()
    data = tail.strip()

    handlers: dict[str, Callable[[str], str]] = {}

    def _help(_: str) -> str:
        return _chat_help_text()

    def _create_agent(payload: str) -> str:
        name, role, system_prompt = split_parts(payload, 3)
        if not name or not role or not system_prompt:
            return "Invalid command. Use: /create-agent NAME | ROLE | SYSTEM_PROMPT"
        obj, created = Agent.objects.get_or_create(
            name=name,
            defaults={
                "role": role,
                "description": f"Created from chat command for role: {role}",
                "system_prompt": system_prompt,
                "channels": ["ui", "discord"],
                "tools": [],
                "skills": [],
                "interaction_rules": [],
                "guardrails": [],
                "limits": {},
                "schedule": {},
                "memory_profile": {},
                "is_active": True,
            },
        )
        if not created:
            obj.role = role
            obj.system_prompt = system_prompt
            obj.is_active = True
            obj.save(update_fields=["role", "system_prompt", "is_active", "updated_at"])
            return f"Updated agent '{obj.name}' (id={obj.id})."
        return f"Created agent '{obj.name}' (id={obj.id})."

    def _create_tool(payload: str) -> str:
        name, category, capabilities_text, description = split_parts(payload, 4)
        allowed_categories = {"ingestion", "memory", "risk", "research", "communication", "monitoring"}
        cat = category.lower() if category else "research"
        if cat not in allowed_categories:
            cat = "research"
        capabilities = [item.strip() for item in capabilities_text.split(",") if item.strip()] or ["read"]
        if not name:
            return "Invalid command. Use: /create-tool NAME | CATEGORY | CAP1,CAP2 | DESCRIPTION"
        obj, created = Tool.objects.get_or_create(
            name=name,
            defaults={
                "category": cat,
                "capabilities": capabilities,
                "description": description,
                "is_active": True,
                "is_system": False,
            },
        )
        if not created:
            obj.category = cat
            obj.capabilities = capabilities
            obj.description = description
            obj.is_active = True
            obj.save(update_fields=["category", "capabilities", "description", "is_active", "updated_at"])
            return f"Updated tool '{obj.name}' (id={obj.id})."
        return f"Created tool '{obj.name}' (id={obj.id})."

    def _create_skill(payload: str) -> str:
        name, category, markdown = split_parts(payload, 3)
        allowed_categories = {"policy", "procedure", "output", "general"}
        cat = category.lower() if category else "general"
        if cat not in allowed_categories:
            cat = "general"
        if not name or not markdown:
            return "Invalid command. Use: /create-skill NAME | CATEGORY | MARKDOWN"
        obj, created = Skill.objects.get_or_create(
            name=name,
            defaults={
                "description": "Created from chat command",
                "category": cat,
                "trigger": "always",
                "priority": 100,
                "requires_tools": [],
                "output_schema": "",
                "abort_on_fail": False,
                "markdown": markdown,
                "is_active": True,
            },
        )
        if not created:
            obj.category = cat
            obj.markdown = markdown
            obj.is_active = True
            obj.save(update_fields=["category", "markdown", "is_active", "updated_at"])
            return f"Updated skill '{obj.name}' (id={obj.id})."
        return f"Created skill '{obj.name}' (id={obj.id})."

    handlers["/help"] = _help
    handlers["/create-agent"] = _create_agent
    handlers["/create-tool"] = _create_tool
    handlers["/create-skill"] = _create_skill

    handler = handlers.get(cmd)
    if handler is None:
        return True, f"Unknown command '{cmd}'.\n{_chat_help_text()}"
    return True, handler(data)


def _stream_row(event: str, **payload) -> bytes:
    row = {"event": event, **payload}
    return (json.dumps(row, ensure_ascii=True) + "\n").encode("utf-8")


def _chunk_text(text: str, max_chars: int = 140) -> list[str]:
    words = str(text or "").split()
    if not words:
        return []
    chunks: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = word
    if current:
        chunks.append(current)
    return chunks


class InterAgentMessageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = InterAgentMessage.objects.all().order_by("-created_at")
    serializer_class = InterAgentMessageSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        run_id = self.request.query_params.get("run_id")
        if run_id:
            queryset = queryset.filter(run_id=run_id)
        return queryset


class ApprovalTicketViewSet(viewsets.ModelViewSet):
    queryset = ApprovalTicket.objects.all().order_by("-created_at")
    serializer_class = ApprovalTicketSerializer

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        status_value = request.data.get("status")
        if status_value in {"approved", "rejected"}:
            instance.status = status_value
            instance.reviewer = request.data.get("reviewer", "human")
            instance.comment = request.data.get("comment", "")
            instance.decided_at = timezone.now()
            instance.save(update_fields=["status", "reviewer", "comment", "decided_at", "updated_at"])
        return Response(self.get_serializer(instance).data)


class ChannelConversationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ChannelConversation.objects.all().order_by("-created_at")
    serializer_class = ChannelConversationSerializer

    @action(detail=True, methods=["delete"], url_path="delete")
    def delete_conversation(self, request, pk=None):
        conversation = self.get_object()
        conversation.delete()
        return Response({"deleted": True}, status=status.HTTP_200_OK)


@api_view(["POST"])
def discord_webhook(request):
    signature = request.headers.get("X-Webhook-Signature")
    payload_bytes = request.body or b""
    if not verify_signature(payload_bytes, signature):
        return Response({"detail": "Invalid signature"}, status=status.HTTP_403_FORBIDDEN)

    external_user_id = request.data.get("from", "unknown")
    body = request.data.get("body", "")
    target_agent_name = request.data.get("target_agent", "ConciergeAgent")
    discord_channel_id = request.data.get("discord_channel_id") or request.data.get("channel_id")
    result = ingest_message(
        external_user_id=external_user_id,
        body=body,
        target_agent_name=target_agent_name,
        discord_channel_id=discord_channel_id,
    )
    code = status.HTTP_200_OK if result.get("processed") else status.HTTP_400_BAD_REQUEST
    return Response(result, status=code)


@api_view(["GET"])
def discord_bot_status(request):
    """Return the current state of the Discord bot gateway."""
    from services.channels.discord_bot import bot_gateway  # noqa: PLC0415

    return Response(bot_gateway.get_status())


@api_view(["POST"])
def discord_bot_start(request):
    """Start the Discord bot gateway (token read from DISCORD_BOT_TOKEN env var)."""
    from services.channels.discord_bot import bot_gateway  # noqa: PLC0415

    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        return Response(
            {"detail": "DISCORD_BOT_TOKEN is not configured."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    target_agent = request.data.get("target_agent", "ConciergeAgent")
    try:
        bot_gateway.start(token=token, target_agent=target_agent)
    except RuntimeError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response({"started": True, "target_agent": target_agent})


@api_view(["POST"])
def discord_bot_stop(request):
    """Stop the Discord bot gateway."""
    from services.channels.discord_bot import bot_gateway  # noqa: PLC0415

    bot_gateway.stop()
    return Response({"stopped": True})
