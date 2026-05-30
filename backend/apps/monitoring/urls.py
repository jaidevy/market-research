from django.urls import path

from apps.monitoring.views import (
    RuntimeMetricsView,
)

urlpatterns = [
    path("metrics/runs", RuntimeMetricsView.as_view(), name="run-metrics"),
]
