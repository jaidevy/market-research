from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.agents.models import Agent, Skill, Tool
from apps.agents.serializers import AgentSerializer, SkillSerializer, ToolSerializer
from apps.agents.system_catalog import (
    STALE_SYSTEM_SKILL_NAMES,
    STALE_SYSTEM_TOOL_NAMES,
    SYSTEM_AGENTS,
    SYSTEM_SKILLS,
    SYSTEM_TOOLS,
)
from services.runtime.tool_registry import extract_tool_names, has_registered_handler


def _tool_names(raw_tools) -> set[str]:
    return set(extract_tool_names(raw_tools if isinstance(raw_tools, list) else []))


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


class ToolViewSet(viewsets.ModelViewSet):
    queryset = Tool.objects.all().order_by("category", "name")
    serializer_class = ToolSerializer

    @action(detail=False, methods=["get"], url_path="compatibility")
    def compatibility(self, request):
        active_tools = list(Tool.objects.filter(is_active=True).order_by("name"))
        active_skills = list(Skill.objects.filter(is_active=True).order_by("name"))
        active_agents = list(Agent.objects.filter(is_active=True).order_by("name"))

        tool_issues = [
            {"kind": "tool", "name": tool.name, "issue": "missing_handler"}
            for tool in active_tools
            if not has_registered_handler(tool.name)
        ]
        skill_issues = []
        tool_names = {tool.name for tool in Tool.objects.all()}
        for skill in active_skills:
            for tool_name in skill.requires_tools if isinstance(skill.requires_tools, list) else []:
                if tool_name not in tool_names:
                    skill_issues.append({"kind": "skill", "name": skill.name, "issue": "unknown_tool", "tool": tool_name})
                elif not has_registered_handler(tool_name):
                    skill_issues.append({"kind": "skill", "name": skill.name, "issue": "missing_handler", "tool": tool_name})

        agent_issues = []
        skill_names = {skill.name for skill in Skill.objects.all()}
        active_skills_by_name = {skill.name: skill for skill in active_skills}
        for agent in active_agents:
            agent_tool_names = set(extract_tool_names(agent.tools))
            for tool_name in extract_tool_names(agent.tools):
                if tool_name not in tool_names:
                    agent_issues.append({"kind": "agent", "name": agent.name, "issue": "unknown_tool", "tool": tool_name})
                elif not has_registered_handler(tool_name):
                    agent_issues.append({"kind": "agent", "name": agent.name, "issue": "missing_handler", "tool": tool_name})
            if isinstance(agent.skills, list):
                for skill_name in agent.skills:
                    skill_key = str(skill_name)
                    if skill_key not in skill_names:
                        agent_issues.append({"kind": "agent", "name": agent.name, "issue": "unknown_skill", "skill": skill_key})
                        continue
                    skill = active_skills_by_name.get(skill_key)
                    if skill is None:
                        continue
                    for tool_name in skill.requires_tools if isinstance(skill.requires_tools, list) else []:
                        if str(tool_name) not in agent_tool_names:
                            agent_issues.append(
                                {
                                    "kind": "agent_skill",
                                    "name": agent.name,
                                    "skill": skill.name,
                                    "issue": "skill_tool_not_whitelisted",
                                    "tool": str(tool_name),
                                }
                            )

        issues = [*tool_issues, *skill_issues, *agent_issues]
        return Response({"status": "ok" if not issues else "issues", "issues": issues, "issue_count": len(issues)})


class AgentViewSet(viewsets.ModelViewSet):
    queryset = Agent.objects.all().order_by("name")
    serializer_class = AgentSerializer

    @action(detail=False, methods=["post"], url_path="seed-system")
    def seed_system(self, request):
        """
        Idempotently create/update all system tools, skills, and agents.
        Returns the full list of system agents after seeding.
        """
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
            d = {k: v for k, v in spec.items() if k != "name"}
            d["is_system"] = True
            Tool.objects.get_or_create(name=spec["name"], defaults=d)

        # 2 — skills (depend on tools existing)
        for spec in SYSTEM_SKILLS:
            Skill.objects.get_or_create(
                name=spec["name"],
                defaults={k: v for k, v in spec.items() if k != "name"},
            )

        # 3 — agents (depend on skills existing)
        _BROKEN: set[str] = set()
        if _BROKEN:
            Agent.objects.filter(name__in=_BROKEN).delete()
        created_ids = []
        for spec in SYSTEM_AGENTS:
            agent, _ = Agent.objects.get_or_create(
                name=spec["name"],
                defaults={k: v for k, v in spec.items() if k != "name"},
            )
            next_tools = _append_tools(agent.tools, list(spec.get("tools") or []))
            next_skills = _append_names(agent.skills, list(spec.get("skills") or []))
            if next_tools != agent.tools or next_skills != agent.skills:
                agent.tools = next_tools
                agent.skills = next_skills
                agent.save(update_fields=["tools", "skills", "updated_at"])
            created_ids.append(agent.id)

        agents = Agent.objects.filter(id__in=created_ids).order_by("name")
        return Response(AgentSerializer(agents, many=True).data)


class SkillViewSet(viewsets.ModelViewSet):
    queryset = Skill.objects.all().order_by("priority", "name")
    serializer_class = SkillSerializer
