"""URL configuration for whealth views."""

from django.urls import path

from whealth.views import control_detail, control_list, recap

urlpatterns = [
    path("recap.html", recap, name="whealth_recap"),
    path(
        "control/<slug:app>/<slug:slug>.json",
        control_detail,
        name="whealth_control_detail",
    ),
    path("control.json", control_list, name="whealth_control_list"),
]
