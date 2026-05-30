from rest_framework import serializers

from apps.monitoring.models import RuntimeEvent, TokenCostLedger


class RuntimeEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RuntimeEvent
        fields = [
            "id",
            "run",
            "level",
            "event_type",
            "message",
            "context",
            "created_at",
            "updated_at",
        ]


class TokenCostLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = TokenCostLedger
        fields = [
            "id",
            "run",
            "agent",
            "step_key",
            "input_tokens",
            "output_tokens",
            "model_name",
            "estimated_cost_usd",
            "is_estimated",
            "created_at",
            "updated_at",
        ]
