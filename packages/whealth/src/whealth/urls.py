"""URL configuration for whealth views."""

from django.urls import path

from whealth.views import (
    control_deep,
    control_detail,
    control_list,
    recap,
    should_restart,
)

urlpatterns = [
    path("recap.html", recap, name="whealth_recap"),
    path(
        "control/<slug:app>/<slug:slug>.json",
        control_detail,
        name="whealth_control_detail",
    ),
    path(
        "control/<slug:app>/<slug:slug>/deep.json",
        control_deep,
        name="whealth_control_deep",
    ),
    path("control.json", control_list, name="whealth_control_list"),
    path(
        "should-restart/<slug:service>.json",
        should_restart,
        name="whealth_should_restart",
    ),
]
