from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.runs.views import UnifiedRunViewSet, WorkflowTemplateViewSet

router = DefaultRouter()
router.register(r"runs", UnifiedRunViewSet, basename="run")
router.register(r"workflow-templates", WorkflowTemplateViewSet, basename="workflow-template")

urlpatterns = [
    path("", include(router.urls)),
]
