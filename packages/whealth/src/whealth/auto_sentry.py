"""Auto-detection of the Sentry SDK.

When ``sentry_sdk`` is installed this module re-exports the real Sentry
functions directly.  Otherwise it provides no-op stubs so callers can
always ``from whealth.auto_sentry import capture_exception`` without
worrying about ImportErrors.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

try:
    import sentry_sdk

    capture_checkin: Any = sentry_sdk.crons.capture_checkin
    capture_exception: Any = sentry_sdk.capture_exception
    _sentry_trace: Any = sentry_sdk.trace
except ImportError:

    def capture_checkin(
        monitor_slug: str,
        status: str,
        duration_s: float | None = None,
        check_in_id: str | None = None,
    ) -> str | None:
        """No-op stub — Sentry SDK is not installed."""
        return None

    def capture_exception(
        error: BaseException | None = None,
        **extra: Any,
    ) -> str | None:
        """No-op stub — Sentry SDK is not installed."""
        return None

    def _sentry_trace(
        func: Any = None,
        **kwargs: Any,
    ) -> Any:
        """No-op decorator — Sentry SDK is not installed."""
        if func is not None:
            return func
        return lambda f: f


def task_trace(name: str) -> Callable[[_F], _F]:
    """Wrap a function with a Sentry trace span, or no-op if unavailable."""
    return _sentry_trace(op="queue.task.procrastinate", name=name)  # type: ignore[no-any-return]
