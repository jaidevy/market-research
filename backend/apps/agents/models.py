from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


class Agent(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    role = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    system_prompt = models.TextField()
    tools = models.JSONField(default=list)
    channels = models.JSONField(default=list)
    schedule = models.JSONField(default=dict)
    memory_profile = models.JSONField(default=dict)
    skills = models.JSONField(default=list)
    interaction_rules = models.JSONField(default=list)
    guardrails = models.JSONField(default=list)
    limits = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Tool(TimeStampedModel):
    CATEGORIES = [
        ("ingestion", "Ingestion"),
        ("memory", "Memory"),
        ("risk", "Risk"),
        ("research", "Research"),
        ("communication", "Communication"),
        ("monitoring", "Monitoring"),
    ]

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, choices=CATEGORIES, default="ingestion")
    capabilities = models.JSONField(default=list)   # e.g. ["read"] or ["read", "write"]
    config_schema = models.JSONField(default=dict)  # optional per-instance config schema
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return self.name


class Skill(TimeStampedModel):
    CATEGORIES = [
        ("policy", "Policy"),
        ("procedure", "Procedure"),
        ("output", "Output"),
        ("general", "General"),
    ]

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=80, choices=CATEGORIES, default="general")
    trigger = models.CharField(max_length=120, default="always")
    priority = models.IntegerField(default=100)
    requires_tools = models.JSONField(default=list)
    output_schema = models.CharField(max_length=120, blank=True)
    abort_on_fail = models.BooleanField(default=False)
    markdown = models.TextField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["priority", "name"]

    def __str__(self) -> str:
        return self.name


# ──────────────────────────────────────────────────────────────────────────────
# Operational models – used by tool handlers
# ──────────────────────────────────────────────────────────────────────────────

class AgentMemory(TimeStampedModel):
    """Key-value store for agent and run context that persists across steps."""

    agent_name = models.CharField(max_length=120, db_index=True)
    run_id = models.CharField(max_length=36, blank=True, db_index=True)
    key = models.CharField(max_length=120)
    value = models.JSONField(default=dict)
    ttl_minutes = models.IntegerField(default=1440)  # 24 hours
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = [("agent_name", "run_id", "key")]

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    def __str__(self) -> str:
        return f"{self.agent_name}:{self.key}"


class Alert(TimeStampedModel):
    """Structured alert emitted by any agent step, visible in the UI."""

    LEVELS = [("info", "Info"), ("warning", "Warning"), ("critical", "Critical")]

    run_id = models.CharField(max_length=36, blank=True, db_index=True)
    level = models.CharField(max_length=20, choices=LEVELS, default="info")
    title = models.CharField(max_length=200)
    message = models.TextField()
    channel = models.CharField(max_length=40, default="internal")
    is_read = models.BooleanField(default=False)
    payload = models.JSONField(default=dict)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.title}"
