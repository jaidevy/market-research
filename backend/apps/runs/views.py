from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.runs.models import UnifiedRun, WorkflowTemplate
from apps.runs.serializers import UnifiedRunSerializer, WorkflowTemplateSerializer
from services.runtime.langgraph_workflow import LangGraphWorkflowRunner
from services.runtime.tool_registry import has_registered_handler
from services.runtime.workflow_templates import seed_generic_workflow_assets
from apps.agents.models import Agent, Skill, Tool


class UnifiedRunViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = UnifiedRun.objects.all().order_by("-created_at")
    serializer_class = UnifiedRunSerializer

    @action(detail=False, methods=["post"], url_path="unified/run")
    def run_unified(self, request):
        return Response(
            {"detail": "Unified legacy run endpoint has been removed from this demo build."},
            status=status.HTTP_410_GONE,
        )

    @action(detail=True, methods=["post"], url_path="stop")
    def stop_run(self, request, pk=None):
        run = self.get_object()
        if run.status not in {"queued", "running"}:
            return Response(
                {"detail": f"Run is already in terminal state '{run.status}'."},
                status=status.HTTP_409_CONFLICT,
            )
        run.status = "cancelled"
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at"])
        return Response(UnifiedRunSerializer(run).data)


class WorkflowTemplateViewSet(viewsets.ModelViewSet):
    queryset = WorkflowTemplate.objects.all().order_by("name", "version")
    serializer_class = WorkflowTemplateSerializer

    @action(detail=False, methods=["post"], url_path="seed-defaults")
    def seed_defaults(self, request):
        seeded = seed_generic_workflow_assets()

        return Response(
            {
                "status": "ok",
                "tools": seeded["tools"],
                "skills": seeded["skills"],
                "agents": seeded["agents"],
                "templates": WorkflowTemplateSerializer(seeded["templates"], many=True).data,
            }
        )

    @action(detail=False, methods=["get"], url_path="compatibility")
    def compatibility(self, request):
        issues: list[dict[str, str]] = []
        tool_names = set(Tool.objects.values_list("name", flat=True))
        agent_names = set(Agent.objects.filter(is_active=True).values_list("name", flat=True))
        skill_names = set(Skill.objects.filter(is_active=True).values_list("name", flat=True))
        for template in WorkflowTemplate.objects.filter(is_active=True):
            nodes = template.nodes if isinstance(template.nodes, list) else []
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_key = str(node.get("key") or node.get("node_key") or "")
                agent_name = str(node.get("agent") or "")
                if agent_name and agent_name not in agent_names:
                    issues.append({"template": template.name, "node": node_key, "issue": "missing_or_inactive_agent", "agent": agent_name})
                for tool_name in [str(item).strip() for item in node.get("tools") or [] if str(item).strip()]:
                    if tool_name not in tool_names:
                        issues.append({"template": template.name, "node": node_key, "issue": "unknown_tool", "tool": tool_name})
                    elif not has_registered_handler(tool_name):
                        issues.append({"template": template.name, "node": node_key, "issue": "missing_handler", "tool": tool_name})
                for skill_name in [str(item).strip() for item in node.get("skills") or [] if str(item).strip()]:
                    if skill_name not in skill_names:
                        issues.append({"template": template.name, "node": node_key, "issue": "missing_or_inactive_skill", "skill": skill_name})
        return Response({"status": "ok" if not issues else "issues", "issue_count": len(issues), "issues": issues})

    @action(detail=True, methods=["post"], url_path="run")
    def run_template(self, request, pk=None):
        template = self.get_object()
        if not template.is_active:
            return Response({"detail": "Workflow template is inactive."}, status=status.HTTP_409_CONFLICT)
        try:
            result = LangGraphWorkflowRunner().run(
                template=template,
                payload=request.data or {},
                trigger=str((request.data or {}).get("trigger") or "manual"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(result, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="run-async")
    def run_template_async(self, request, pk=None):
        template = self.get_object()
        if not template.is_active:
            return Response({"detail": "Workflow template is inactive."}, status=status.HTTP_409_CONFLICT)
        try:
            result = LangGraphWorkflowRunner().run_async(
                template=template,
                payload=request.data or {},
                trigger=str((request.data or {}).get("trigger") or "manual"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(result, status=status.HTTP_202_ACCEPTED)
