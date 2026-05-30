from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Coroutine

from asgiref.sync import sync_to_async

Handler = Callable[[dict, dict], Coroutine[Any, Any, dict]]


async def _handle_list_skills(config: dict, context: dict) -> dict:
    from apps.agents.models import Skill

    rows: list[dict[str, Any]] = []
    async for skill in Skill.objects.filter(is_active=True).order_by("priority", "name"):
        rows.append(
            {
                "name": skill.name,
                "description": skill.description,
                "category": skill.category,
                "trigger": skill.trigger,
                "requires_tools": skill.requires_tools,
            }
        )
    return {"status": "ok", "skills": rows, "count": len(rows)}


async def _handle_load_skill(config: dict, context: dict) -> dict:
    from apps.agents.models import Skill

    name = str(config.get("name") or context.get("skill_name") or "").strip()
    if not name:
        return {"status": "error", "error": "Skill name is required."}
    skill = await Skill.objects.filter(name=name, is_active=True).afirst()
    if skill is None:
        return {"status": "error", "error": f"Active skill '{name}' was not found.", "name": name}
    return {
        "status": "ok",
        "name": skill.name,
        "description": skill.description,
        "category": skill.category,
        "requires_tools": skill.requires_tools,
        "markdown": skill.markdown,
    }


async def _handle_web_search(config: dict, context: dict) -> dict:
    query = str(config.get("query") or context.get("objective") or "").strip()
    if not query:
        return {"status": "error", "error": "query is required"}
    try:
        import httpx
        import xml.etree.ElementTree as ET

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://news.google.com/rss/search",
                params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
            )
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        items = root.findall("./channel/item")[:5]
        related = [str(item.findtext("title") or "").strip() for item in items if str(item.findtext("title") or "").strip()]
        return {
            "status": "ok",
            "query": query,
            "provider": "google-news-rss",
            "results": related,
            "summary": related[0] if related else "No results",
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc), "query": query}


async def _handle_read_url(config: dict, context: dict) -> dict:
    url = str(config.get("url") or "").strip()
    if not url:
        return {"status": "error", "error": "url is required"}
    if not url.lower().startswith(("http://", "https://")):
        return {"status": "error", "error": "Only http(s) URLs are supported.", "url": url}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        text = response.text
        return {
            "status": "ok",
            "url": url,
            "content_type": response.headers.get("content-type", ""),
            "text_excerpt": text[:3000],
            "summary": f"Read {len(text)} characters from {url}.",
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "error": str(exc), "url": url}


async def _handle_write_artifact(config: dict, context: dict) -> dict:
    raw_path = str(config.get("path") or "workflow_artifact.md").strip() or "workflow_artifact.md"
    content = str(config.get("content") or context.get("objective") or "")
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        return {"status": "error", "error": "Only workspace-relative artifact paths are allowed."}
    run_id = str(context.get("run_id") or "manual")
    root = (Path("logs") / "artifacts" / "langgraph_workflows" / f"run_{run_id}").resolve()
    full_path = (root / path).resolve()
    if root not in full_path.parents and full_path != root:
        return {"status": "error", "error": "Path escapes artifact directory."}
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return {
        "status": "ok",
        "path": str(full_path),
        "summary": f"Artifact written to {full_path}.",
    }


async def _handle_knowledge_base_search(config: dict, context: dict) -> dict:
    query = str(config.get("query") or context.get("objective") or "").strip()
    lowered = query.lower()
    articles = [
        {
            "id": "billing-refund-policy",
            "title": "Billing and refund review policy",
            "text": "Duplicate charges and refund requests require billing verification and human review before a refund promise is made.",
            "keywords": ["refund", "charged", "billing", "invoice", "duplicate"],
        },
        {
            "id": "account-access-policy",
            "title": "Account access troubleshooting",
            "text": "Password resets and login issues can be handled with identity confirmation and reset instructions.",
            "keywords": ["login", "password", "account", "access"],
        },
    ]
    matches = []
    for article in articles:
        score = sum(1 for keyword in article["keywords"] if keyword in lowered)
        if score:
            matches.append({"score": score, **article})
    if not matches:
        matches = [{"score": 0, **articles[0]}]
    matches.sort(key=lambda item: item["score"], reverse=True)
    return {
        "status": "ok",
        "query": query,
        "matches": matches[:3],
        "summary": matches[0]["text"],
    }


async def _handle_ticket_create(config: dict, context: dict) -> dict:
    from apps.agents.models import Alert

    summary = str(config.get("summary") or context.get("objective") or "Support follow-up required.").strip()
    priority = str(config.get("priority") or "normal").strip().lower() or "normal"
    run_id = str(context.get("run_id") or "")
    alert = await Alert.objects.acreate(
        run_id=run_id,
        level="warning" if priority in {"high", "urgent"} else "info",
        title="Support escalation ticket",
        message=summary,
        channel=str((context.get("input") or {}).get("channel") or "internal"),
        payload={"priority": priority, "source": "ticket_create"},
    )
    return {
        "status": "ok",
        "ticket_id": str(alert.pk),
        "priority": priority,
        "summary": summary,
    }


async def _handle_send_channel_message(config: dict, context: dict) -> dict:
    message = str(config.get("message") or config.get("content") or context.get("objective") or "").strip()
    channel = str(config.get("channel") or (context.get("input") or {}).get("channel") or "ui").strip()
    return {
        "status": "ok",
        "channel": channel,
        "message": message,
        "summary": f"Prepared outbound message for {channel}.",
    }


async def _handle_memory_read(config: dict, context: dict) -> dict:
    from apps.agents.models import AgentMemory
    from django.db.models import Q
    from django.utils import timezone

    agent_name: str = config.get("agent_name") or context.get("agent_name") or "system"
    run_id: str = config.get("run_id") or context.get("run_id") or ""
    key: str | None = config.get("key")

    qs = AgentMemory.objects.filter(agent_name=agent_name, run_id=run_id)
    if key:
        qs = qs.filter(key=key)
    qs = qs.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))

    data: dict[str, Any] = {}
    async for rec in qs:
        data[rec.key] = rec.value
    return {"status": "ok", "agent_name": agent_name, "run_id": run_id, "data": data}


async def _handle_memory_write(config: dict, context: dict) -> dict:
    from datetime import timedelta
    from django.utils import timezone
    from apps.agents.models import AgentMemory

    agent_name: str = config.get("agent_name") or context.get("agent_name") or "system"
    run_id: str = config.get("run_id") or context.get("run_id") or ""
    key: str = config.get("key") or "state"
    value = config.get("value") or context.get("step_output") or {}
    ttl_minutes: int = int(config.get("ttl_minutes") or 1440)

    expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
    await AgentMemory.objects.aupdate_or_create(
        agent_name=agent_name,
        run_id=run_id,
        key=key,
        defaults={"value": value, "ttl_minutes": ttl_minutes, "expires_at": expires_at},
    )
    return {"status": "ok", "agent_name": agent_name, "key": key, "ttl_minutes": ttl_minutes}


async def _handle_read_file(config: dict, context: dict) -> dict:
    raw_path = str(config.get("path") or context.get("path") or "").strip()
    if not raw_path:
        return {"status": "error", "error": "path is required"}
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        return {"status": "error", "error": "Only workspace-relative artifact paths are allowed."}
    full_path = (Path("logs") / "artifacts" / path).resolve()
    root = (Path("logs") / "artifacts").resolve()
    if root not in full_path.parents and full_path != root:
        return {"status": "error", "error": "Path escapes artifact directory."}
    if not full_path.exists() or not full_path.is_file():
        return {"status": "error", "error": f"Artifact '{raw_path}' was not found."}
    return {"status": "ok", "path": raw_path, "content": full_path.read_text(encoding="utf-8")}


async def _handle_write_file(config: dict, context: dict) -> dict:
    raw_path = str(config.get("path") or context.get("artifact_path") or "report.md").strip()
    content = str(config.get("content") or context.get("artifact_content") or context.get("objective") or "")
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        return {"status": "error", "error": "Only workspace-relative artifact paths are allowed."}
    full_path = (Path("logs") / "artifacts" / path).resolve()
    root = (Path("logs") / "artifacts").resolve()
    if root not in full_path.parents and full_path != root:
        return {"status": "error", "error": "Path escapes artifact directory."}
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return {"status": "ok", "path": str(full_path.relative_to(Path.cwd()))}


async def _handle_backtest(config: dict, context: dict) -> dict:
    return {
        "status": "ok",
        "mode": "dry_run",
        "note": "Backtest request captured. Connect a historical provider to enable execution.",
    }


async def _handle_research_goal(config: dict, context: dict) -> dict:
    operation = str(config.get("operation") or context.get("operation") or "start").strip()
    return {"status": "ok", "operation": operation, "payload": config or context}


async def _handle_discord_rw(config: dict, context: dict) -> dict:
    from services.channels.discord import _send_outbound_message

    operation = str(config.get("operation") or "write").strip().lower()
    external_user_id = str(config.get("external_user_id") or config.get("user_id") or "").strip()

    if operation in {"read", "read_latest", "latest"}:
        return {"status": "ok", "operation": operation, "found": False, "message": ""}

    message = str(config.get("message") or config.get("content") or context.get("objective") or "Run update.").strip()
    provider = str(config.get("provider") or "agent_tool").strip().lower()
    send_result = await sync_to_async(_send_outbound_message, thread_sensitive=False)(provider, external_user_id, message, None)
    return {
        "status": "ok",
        "operation": operation,
        "message": message,
        "user_id": external_user_id,
        "provider": provider,
        "send_result": send_result,
        "summary": "Discord send attempted.",
    }


TOOL_REGISTRY: dict[str, Handler] = {
    "list_skills": _handle_list_skills,
    "load_skill": _handle_load_skill,
    "web_search": _handle_web_search,
    "read_url": _handle_read_url,
    "write_artifact": _handle_write_artifact,
    "knowledge_base_search": _handle_knowledge_base_search,
    "ticket_create": _handle_ticket_create,
    "send_channel_message": _handle_send_channel_message,
    "memory_read": _handle_memory_read,
    "memory_write": _handle_memory_write,
    "read_file": _handle_read_file,
    "write_file": _handle_write_file,
    "backtest": _handle_backtest,
    "start_research_goal": _handle_research_goal,
    "get_research_goal": _handle_research_goal,
    "add_goal_evidence": _handle_research_goal,
    "update_research_goal_status": _handle_research_goal,
    "discord_rw": _handle_discord_rw,
}


def registered_tool_names() -> set[str]:
    return set(TOOL_REGISTRY)


def has_registered_handler(tool_name: str) -> bool:
    return str(tool_name or "").strip() in TOOL_REGISTRY


def extract_tool_names(raw_tools: Any) -> list[str]:
    if not isinstance(raw_tools, list):
        return []
    names: list[str] = []
    for item in raw_tools:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = ""
        if name:
            names.append(name)
    return sorted(set(names))


def dispatch(tool_name: str, config: dict, context: dict) -> dict:
    handler = TOOL_REGISTRY.get(tool_name)
    if handler is None:
        return {
            "status": "error",
            "tool": tool_name,
            "error": f"No handler registered for tool '{tool_name}'.",
        }
    try:
        return asyncio.run(handler(config, context))
    except RuntimeError:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, handler(config, context))
            return future.result(timeout=30)
