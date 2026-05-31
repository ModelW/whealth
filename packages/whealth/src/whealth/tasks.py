"""Procrastinate tasks for whealth controls.

This module declares itself only when ``procrastinate`` is importable.
Projects that opt in via the ``[procrastinate]`` extra get a periodic cron
that runs all active controls every minute.
"""

from __future__ import annotations

try:
    from procrastinate.contrib.django import app
except ImportError:
    app = None  # type: ignore[assignment]


if app is not None:

    from whealth.procrastinate import ProcrastinateCron, procrastinate_task
    from whealth.runner import ControlRunner
    from whealth.registry import get_control_registry

    @procrastinate_task(
        app=app,
        cron=ProcrastinateCron(expression="* * * * *"),
        queue="health",
    )
    def run_controls(timestamp: int) -> None:
        """Run all registered controls and sync incidents."""
        registry = get_control_registry()
        runner = ControlRunner(registry=registry)
        runner.run_and_sync()
