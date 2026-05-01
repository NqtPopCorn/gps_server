

from monitor.views import HeartbeatView, MonitorStatsView
from django.urls import path

urlpatterns = [
    path("heartbeat", HeartbeatView.as_view(), name="heartbeat"),
    path("stats", MonitorStatsView.as_view(), name="monitor_stats"),
]

