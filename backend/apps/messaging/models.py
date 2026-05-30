from django.db import models

from apps.agents.models import Agent
from apps.common.models import TimeStampedModel
from apps.runs.models import UnifiedRun


class InterAgentMessage(TimeStampedModel):
    run = models.ForeignKey(UnifiedRun, on_delete=models.CASCADE, related_name="messages")
    message_id = models.CharField(max_length=120, unique=True)
    from_agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_messages")
    to_agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.SET_NULL, related_name="received_messages")
    channel = models.CharField(max_length=40, default="internal")
    status = models.CharField(max_length=24, default="queued")
    payload = models.JSONField(default=dict)
    retry_count = models.IntegerField(default=0)


class ChannelConversation(TimeStampedModel):
    external_channel = models.CharField(max_length=24, default="discord")
    external_user_id = models.CharField(max_length=120)
    target_agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="conversations")
    active_run = models.ForeignKey(UnifiedRun, null=True, blank=True, on_delete=models.SET_NULL)


class ChannelMessage(TimeStampedModel):
    conversation = models.ForeignKey(ChannelConversation, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=12)
    body = models.TextField()
    metadata = models.JSONField(default=dict)


class ApprovalTicket(TimeStampedModel):
    run = models.ForeignKey(UnifiedRun, on_delete=models.CASCADE, related_name="approvals")
    ticket_key = models.CharField(max_length=120, unique=True)
    requested_by = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=24, default="pending")
    summary = models.TextField()
    reviewer = models.CharField(max_length=120, blank=True)
    comment = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
