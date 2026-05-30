from rest_framework import serializers

from apps.messaging.models import ApprovalTicket, ChannelConversation, ChannelMessage, InterAgentMessage


class InterAgentMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = InterAgentMessage
        fields = [
            "id",
            "run",
            "message_id",
            "from_agent",
            "to_agent",
            "channel",
            "status",
            "payload",
            "retry_count",
            "created_at",
            "updated_at",
        ]


class ApprovalTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalTicket
        fields = [
            "id",
            "run",
            "ticket_key",
            "requested_by",
            "status",
            "summary",
            "reviewer",
            "comment",
            "decided_at",
            "created_at",
            "updated_at",
        ]


class ChannelMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChannelMessage
        fields = ["id", "direction", "body", "metadata", "created_at", "updated_at"]


class ChannelConversationSerializer(serializers.ModelSerializer):
    messages = ChannelMessageSerializer(many=True, read_only=True)

    class Meta:
        model = ChannelConversation
        fields = [
            "id",
            "external_channel",
            "external_user_id",
            "target_agent",
            "active_run",
            "messages",
            "created_at",
            "updated_at",
        ]
