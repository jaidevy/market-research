from django.apps import AppConfig


def _tool_names(raw_tools) -> set[str]:
    names: set[str] = set()
    if not isinstance(raw_tools, list):
        return names
    for item in raw_tools:
        if isinstance(item, str):
            name = item.strip()
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = ""
        if name:
            names.add(name)
    return names


def _append_tools(raw_tools, tool_names: list[str]) -> list:
    tools = list(raw_tools) if isinstance(raw_tools, list) else []
    existing = _tool_names(tools)
    for tool_name in tool_names:
        if tool_name not in existing:
            tools.append(tool_name)
            existing.add(tool_name)
    return tools


def _append_names(raw_names, names: list[str]) -> list[str]:
    values = [str(item).strip() for item in raw_names] if isinstance(raw_names, list) else []
    existing = {name for name in values if name}
    for name in names:
        if name not in existing:
            values.append(name)
            existing.add(name)
    return values


class AgentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.agents"

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(_seed_system_after_migrate, sender=self)

        # Also seed on every server start (safe: get_or_create is idempotent)
        _seed_system_on_startup()


def _seed_system_on_startup():
    """Seed system catalog on every process start. Completely safe to re-run."""
    try:
        from django.db import connection
        table_names = connection.introspection.table_names()
        if "apps_agents_agent" not in table_names:
            return  # Tables not migrated yet — skip silently
        _run_seed()
    except Exception:
        pass  # Never crash startup


def _seed_system_after_migrate(sender, **kwargs):
    """Also seed after every migrate (covers fresh installs)."""
    try:
        _run_seed()
    except Exception:
        pass


def _run_seed():
    from apps.agents.models import Agent, Skill, Tool
    from apps.agents.system_catalog import (
        STALE_SYSTEM_SKILL_NAMES,
        STALE_SYSTEM_TOOL_NAMES,
        SYSTEM_AGENTS,
        SYSTEM_SKILLS,
        SYSTEM_TOOLS,
    )

    for agent in Agent.objects.all():
        current_tools = agent.tools if isinstance(agent.tools, list) else []
        current_skills = agent.skills if isinstance(agent.skills, list) else []
        next_tools = [tool for tool in current_tools if tool not in STALE_SYSTEM_TOOL_NAMES]
        next_skills = [skill for skill in current_skills if skill not in STALE_SYSTEM_SKILL_NAMES]
        if next_tools != agent.tools or next_skills != agent.skills:
            agent.tools = next_tools
            agent.skills = next_skills
            agent.save(update_fields=["tools", "skills", "updated_at"])
    Tool.objects.filter(name__in=STALE_SYSTEM_TOOL_NAMES).delete()
    Skill.objects.filter(name__in=STALE_SYSTEM_SKILL_NAMES).delete()

    for spec in SYSTEM_TOOLS:
        defaults = {k: v for k, v in spec.items() if k != "name"}
        defaults["is_system"] = True
        Tool.objects.get_or_create(name=spec["name"], defaults=defaults)

    for spec in SYSTEM_SKILLS:
        defaults = {k: v for k, v in spec.items() if k != "name"}
        Skill.objects.get_or_create(name=spec["name"], defaults=defaults)

    for spec in SYSTEM_AGENTS:
        defaults = {k: v for k, v in spec.items() if k != "name"}
        agent, _ = Agent.objects.get_or_create(name=spec["name"], defaults=defaults)
        next_tools = _append_tools(agent.tools, list(spec.get("tools") or []))
        next_skills = _append_names(agent.skills, list(spec.get("skills") or []))
        if next_tools != agent.tools or next_skills != agent.skills:
            agent.tools = next_tools
            agent.skills = next_skills
            agent.save(update_fields=["tools", "skills", "updated_at"])

    _BROKEN_AGENT_NAMES: set[str] = set()
    if _BROKEN_AGENT_NAMES:
        Agent.objects.filter(name__in=_BROKEN_AGENT_NAMES).delete()

