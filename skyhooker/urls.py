from django.urls import path

from . import views

app_name = "skyhooker"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("skyhook/<int:structure_id>/", views.skyhook_detail, name="skyhook_detail"),
    path("register-token/", views.register_token, name="register_token"),
    path("alerts/unresolved/", views.unresolved_alerts, name="unresolved_alerts"),
    path("alerts/<int:alert_id>/resolve/", views.resolve_alert, name="resolve_alert"),
    path("report/", views.report, name="report"),
]
