from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models

from apps.common.models import TimeStampedModel

if TYPE_CHECKING:
    from django.db.models.manager import BaseManager


class UnifiedRun(TimeStampedModel):
    if TYPE_CHECKING:
        events: BaseManager[Any]
        steps: BaseManager[Any]
    status = models.CharField(max_length=24, default="queued")
    trigger = models.CharField(max_length=40, default="manual")
    input_payload = models.JSONField(default=dict)
    output_payload = models.JSONField(default=dict)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    @property
    def run_name(self) -> str:
        if isinstance(self.input_payload, dict):
            workflow_name = str(self.input_payload.get("workflow_template") or "").strip()
            if workflow_name:
                return workflow_name
        return "Unified Workflow Run"


class UnifiedRunStep(TimeStampedModel):
    run = models.ForeignKey(UnifiedRun, on_delete=models.CASCADE, related_name="steps")
    node_key = models.CharField(max_length=80)
    status = models.CharField(max_length=24, default="queued")
    input_payload = models.JSONField(default=dict)
    output_payload = models.JSONField(default=dict)
    error_message = models.TextField(blank=True)


class WorkflowTemplate(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True, default="")
    version = models.CharField(max_length=24, default="1.0")
    nodes = models.JSONField(default=list)
    edges = models.JSONField(default=list)
    input_schema = models.JSONField(default=dict)
    output_schema = models.JSONField(default=dict)
    default_agents = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "version"]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"
