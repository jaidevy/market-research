from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.agents.views import AgentViewSet, SkillViewSet, ToolViewSet

router = DefaultRouter()
router.register(r"agents", AgentViewSet, basename="agent")
router.register(r"tools", ToolViewSet, basename="tool")
router.register(r"skills", SkillViewSet, basename="skill")

urlpatterns = [
    path("", include(router.urls)),
]
