from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def api_root(_request):
    return JsonResponse(
        {
            "service": "agentic-platform-backend",
            "status": "ok",
            "ui": "Unified Django backend with React frontend on http://127.0.0.1:5173",
        }
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.agents.urls")),
    path("api/", include("apps.runs.urls")),
    path("api/", include("apps.messaging.urls")),
    path("api/", include("apps.monitoring.urls")),
    path("", api_root, name="api-root"),
]
