from rest_framework import serializers

from apps.agents.models import Agent, Skill, Tool
from services.runtime.tool_registry import extract_tool_names, has_registered_handler


class ToolSerializer(serializers.ModelSerializer):
    is_system = serializers.BooleanField(read_only=True)

    class Meta:
        model = Tool
        fields = [
            "id",
            "name",
            "description",
            "category",
            "capabilities",
            "config_schema",
            "is_active",
            "is_system",
            "created_at",
            "updated_at",
        ]


class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = [
            "id",
            "name",
            "description",
            "category",
            "trigger",
            "priority",
            "requires_tools",
            "output_schema",
            "abort_on_fail",
            "markdown",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def validate_requires_tools(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("requires_tools must be a list of tool names.")

        names = [str(item).strip() for item in value if str(item).strip()]
        if not names:
            return []

        existing = set(Tool.objects.filter(name__in=names).values_list("name", flat=True))
        missing = sorted(set(names) - existing)
        if missing:
            raise serializers.ValidationError(
                f"Unknown tool references: {', '.join(missing)}. Create these in Tool Library first."
            )
        without_handlers = sorted(name for name in names if not has_registered_handler(name))
        if without_handlers:
            raise serializers.ValidationError(
                f"Tools without runtime handlers: {', '.join(without_handlers)}. Register a handler before requiring them."
            )
        return names


class AgentSerializer(serializers.ModelSerializer):
    def validate_tools(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("tools must be a list of tool names or tool objects.")

        names = extract_tool_names(value)
        if not names:
            return []

        existing = set(Tool.objects.filter(name__in=names).values_list("name", flat=True))
        missing = sorted(set(names) - existing)
        if missing:
            raise serializers.ValidationError(
                f"Unknown tools: {', '.join(missing)}. Create these in Tool Library first."
            )

        without_handlers = sorted(name for name in names if not has_registered_handler(name))
        if without_handlers:
            raise serializers.ValidationError(
                f"Tools without runtime handlers: {', '.join(without_handlers)}. Register a handler before assigning them."
            )

        normalized = []
        tool_rows = {tool.name: tool for tool in Tool.objects.filter(name__in=names)}
        for name in names:
            tool = tool_rows.get(name)
            normalized.append({"name": name, "capabilities": list(tool.capabilities or []) if tool else []})
        return normalized

    def validate_skills(self, value):
        if isinstance(value, str):
            # Legacy mode: raw markdown or JSON-like text allowed.
            return value

        if not isinstance(value, list):
            raise serializers.ValidationError("skills must be a list of skill names/objects or a markdown string.")

        extracted_names: list[str] = []
        for item in value:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    extracted_names.append(name)
                continue
            if isinstance(item, dict):
                raw_name = item.get("name")
                name = str(raw_name).strip() if raw_name else ""
                if name:
                    extracted_names.append(name)
                continue
            raise serializers.ValidationError("Each skill must be a string name or object containing name.")

        if not extracted_names:
            return []

        existing = set(Skill.objects.filter(name__in=extracted_names).values_list("name", flat=True))
        missing = sorted(set(extracted_names) - existing)
        if missing:
            raise serializers.ValidationError(
                f"Unknown skills: {', '.join(missing)}. Create these in Skill Studio first."
            )

        return extracted_names

    def _normalize_rule_list(self, value, field_name):
        if not isinstance(value, list):
            raise serializers.ValidationError({field_name: "must be a list."})

        normalized = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    normalized.append(text)
                continue
            if isinstance(item, dict):
                normalized.append(item)
                continue
            raise serializers.ValidationError({field_name: "Each rule must be a string or object."})
        return normalized

    def validate_interaction_rules(self, value):
        return self._normalize_rule_list(value, "interaction_rules")

    def validate_guardrails(self, value):
        return self._normalize_rule_list(value, "guardrails")

    class Meta:
        model = Agent
        fields = [
            "id",
            "name",
            "role",
            "description",
            "system_prompt",
            "tools",
            "channels",
            "schedule",
            "memory_profile",
            "skills",
            "interaction_rules",
            "guardrails",
            "limits",
            "is_active",
            "created_at",
            "updated_at",
        ]
