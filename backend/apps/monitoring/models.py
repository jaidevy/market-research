from django.db import models

from apps.agents.models import Agent
from apps.common.models import TimeStampedModel
from apps.runs.models import UnifiedRun


class TokenCostLedger(TimeStampedModel):
    run = models.ForeignKey(UnifiedRun, on_delete=models.CASCADE, related_name="token_costs")
    agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.SET_NULL)
    step_key = models.CharField(max_length=80, blank=True)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    model_name = models.CharField(max_length=80, default="nvidia/nemotron-3-super-120b-a12b:free")
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    is_estimated = models.BooleanField(default=True)


class RuntimeEvent(TimeStampedModel):
    run = models.ForeignKey(UnifiedRun, on_delete=models.CASCADE, related_name="events")
    level = models.CharField(max_length=16, default="info")
    event_type = models.CharField(max_length=48)
    message = models.TextField()
    context = models.JSONField(default=dict)
