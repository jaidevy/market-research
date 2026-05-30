from rest_framework import serializers

from apps.runs.models import UnifiedRun, UnifiedRunStep, WorkflowTemplate


class WorkflowTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkflowTemplate
        fields = [
            "id",
            "name",
            "description",
            "version",
            "nodes",
            "edges",
            "input_schema",
            "output_schema",
            "default_agents",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def validate_nodes(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError("nodes must be a non-empty list.")
        keys: set[str] = set()
        for index, node in enumerate(value, start=1):
            if not isinstance(node, dict):
                raise serializers.ValidationError(f"node {index} must be an object.")
            key = str(node.get("key") or node.get("node_key") or "").strip()
            if not key:
                raise serializers.ValidationError(f"node {index} is missing key.")
            if key in keys:
                raise serializers.ValidationError(f"duplicate node key: {key}")
            keys.add(key)
        return value

    def validate_edges(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("edges must be a list.")
        for index, edge in enumerate(value, start=1):
            if not isinstance(edge, dict):
                raise serializers.ValidationError(f"edge {index} must be an object.")
            if not str(edge.get("from") or "").strip() or not str(edge.get("to") or "").strip():
                raise serializers.ValidationError(f"edge {index} must include from and to.")
        return value


class UnifiedRunStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnifiedRunStep
        fields = [
            "id",
            "node_key",
            "status",
            "input_payload",
            "output_payload",
            "error_message",
            "created_at",
            "updated_at",
        ]


class UnifiedRunSerializer(serializers.ModelSerializer):
    steps = UnifiedRunStepSerializer(many=True, read_only=True)
    run_name = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedRun
        fields = [
            "id",
            "run_name",
            "status",
            "trigger",
            "input_payload",
            "output_payload",
            "started_at",
            "finished_at",
            "steps",
            "created_at",
            "updated_at",
        ]

    def get_run_name(self, obj: UnifiedRun) -> str:
        return obj.run_name
