"""Minimal generic system catalog aligned with runtime tool handlers."""
from __future__ import annotations


SYSTEM_TOOLS: list[dict] = [
    {
        "name": "list_skills",
        "description": "List available skills.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {},
    },
    {
        "name": "load_skill",
        "description": "Load full markdown for a skill by name.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {"name": "string"},
    },
    {
        "name": "web_search",
        "description": "Search the web for current context.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {"query": "string"},
    },
    {
        "name": "read_url",
        "description": "Read content from an HTTP(S) URL.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {"url": "string"},
    },
    {
        "name": "knowledge_base_search",
        "description": "Search internal policy and support knowledge.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {"query": "string"},
    },
    {
        "name": "memory_read",
        "description": "Read run or agent memory.",
        "category": "memory",
        "capabilities": ["read"],
        "config_schema": {"agent_name": "string", "run_id": "string", "key": "string"},
    },
    {
        "name": "memory_write",
        "description": "Write run or agent memory.",
        "category": "memory",
        "capabilities": ["write"],
        "config_schema": {"agent_name": "string", "run_id": "string", "key": "string", "value": "object"},
    },
    {
        "name": "read_file",
        "description": "Read a generated artifact file.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {"path": "string"},
    },
    {
        "name": "write_file",
        "description": "Write a generated artifact file.",
        "category": "monitoring",
        "capabilities": ["write"],
        "config_schema": {"path": "string", "content": "string"},
    },
    {
        "name": "write_artifact",
        "description": "Write run-scoped workflow artifacts.",
        "category": "monitoring",
        "capabilities": ["write"],
        "config_schema": {"path": "string", "content": "string"},
    },
    {
        "name": "ticket_create",
        "description": "Create an escalation ticket for human follow-up.",
        "category": "communication",
        "capabilities": ["write"],
        "config_schema": {"summary": "string", "priority": "string"},
    },
    {
        "name": "send_channel_message",
        "description": "Prepare outbound message payload for a channel.",
        "category": "communication",
        "capabilities": ["write"],
        "config_schema": {"channel": "string", "message": "string"},
    },
    {
        "name": "discord_rw",
        "description": "Read latest Discord message metadata or send an update.",
        "category": "communication",
        "capabilities": ["read", "write"],
        "config_schema": {"operation": "string", "external_user_id": "string", "message": "string"},
    },
    {
        "name": "backtest",
        "description": "Run a dry-run backtest request.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {},
    },
    {
        "name": "start_research_goal",
        "description": "Create or update a research goal.",
        "category": "research",
        "capabilities": ["write"],
        "config_schema": {"operation": "string"},
    },
    {
        "name": "get_research_goal",
        "description": "Get current research goal state.",
        "category": "research",
        "capabilities": ["read"],
        "config_schema": {},
    },
    {
        "name": "add_goal_evidence",
        "description": "Attach evidence to a research goal.",
        "category": "research",
        "capabilities": ["write"],
        "config_schema": {},
    },
    {
        "name": "update_research_goal_status",
        "description": "Update research goal status.",
        "category": "research",
        "capabilities": ["write"],
        "config_schema": {},
    },
]


STALE_SYSTEM_TOOL_NAMES = {
    "run_swarm",
    "list_swarm_presets",
}

STALE_SYSTEM_SKILL_NAMES = {
    "swarm-on-explicit-request",
}


SYSTEM_SKILLS: list[dict] = [
    {
        "name": "skill-routing",
        "description": "Discover and load skills before specialized reasoning.",
        "category": "policy",
        "trigger": "always",
        "priority": 10,
        "requires_tools": ["list_skills", "load_skill"],
        "output_schema": "SkillRoutingDecision",
        "abort_on_fail": False,
        "markdown": (
            "## Skill Routing\n"
            "1. Start with list_skills.\n"
            "2. Use load_skill when a domain skill is required.\n"
            "3. Avoid assumptions when no matching skill exists."
        ),
    },
    {
        "name": "evidence-first-research",
        "description": "Collect external and internal evidence before conclusions.",
        "category": "procedure",
        "trigger": "research",
        "priority": 20,
        "requires_tools": ["web_search", "knowledge_base_search", "read_url"],
        "output_schema": "ResearchBrief",
        "abort_on_fail": False,
        "markdown": (
            "## Evidence-First Research\n"
            "1. Collect source evidence.\n"
            "2. Cross-check findings for consistency.\n"
            "3. Call out uncertainty and missing data explicitly."
        ),
    },
    {
        "name": "communication-handoff",
        "description": "Create clean user-facing updates and escalation handoff when needed.",
        "category": "output",
        "trigger": "always",
        "priority": 40,
        "requires_tools": ["send_channel_message", "ticket_create"],
        "output_schema": "HandoffPayload",
        "abort_on_fail": False,
        "markdown": (
            "## Communication Handoff\n"
            "Use concise summaries, clear next steps, and escalation context when human review is required."
        ),
    },
]


SYSTEM_AGENTS: list[dict] = [
    {
        "name": "ConciergeAgent",
        "role": "Concierge",
        "description": "Routes requests and prepares clear responses.",
        "system_prompt": (
            "You are a general-purpose orchestration concierge. "
            "Classify intent, run the appropriate generic workflow tools, and respond with concise, factual output."
        ),
        "tools": [
            "list_skills",
            "load_skill",
            "web_search",
            "knowledge_base_search",
            "read_url",
            "send_channel_message",
            "ticket_create",
            "memory_read",
            "memory_write",
        ],
        "channels": ["ui", "discord", "internal"],
        "schedule": {},
        "memory_profile": {"scope": "session", "ttl_minutes": 1440},
        "skills": ["skill-routing", "evidence-first-research", "communication-handoff"],
        "interaction_rules": [],
        "guardrails": ["No fabricated facts", "Escalate when uncertain"],
        "limits": {"max_steps": 8},
        "is_active": True,
    }
]
