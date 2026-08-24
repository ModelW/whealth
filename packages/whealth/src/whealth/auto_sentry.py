"""Auto-detection of the Sentry SDK.

When ``sentry_sdk`` is installed this module re-exports the real Sentry
functions directly.  Otherwise it provides no-op stubs so callers can
always ``from whealth.auto_sentry import capture_exception`` without
worrying about ImportErrors.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])


class _NoOpSpan:
    """Stand-in for a Sentry span/transaction when the SDK is missing."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def set_data(self, key: str, value: Any) -> None:
        """No-op stub — Sentry SDK is not installed."""

    def set_tag(self, key: str, value: Any) -> None:
        """No-op stub — Sentry SDK is not installed."""


try:
    import sentry_sdk

    capture_checkin: Any = sentry_sdk.crons.capture_checkin
    capture_exception: Any = sentry_sdk.capture_exception
    isolation_scope: Any = sentry_sdk.isolation_scope
    start_span: Any = sentry_sdk.start_span
    start_transaction: Any = sentry_sdk.start_transaction
    _sentry_trace: Any = sentry_sdk.trace
except ImportError:

    def capture_checkin(
        monitor_slug: str | None = None,
        check_in_id: str | None = None,
        status: str | None = None,
        duration: float | None = None,
        monitor_config: dict[str, Any] | None = None,
    ) -> str | None:
        """No-op stub — Sentry SDK is not installed."""
        return None

    def capture_exception(
        error: BaseException | None = None,
        **extra: Any,
    ) -> str | None:
        """No-op stub — Sentry SDK is not installed."""
        return None

    @contextlib.contextmanager
    def isolation_scope() -> Iterator[None]:
        """No-op stub — Sentry SDK is not installed."""
        yield None

    def start_span(**kwargs: Any) -> _NoOpSpan:
        """No-op stub — Sentry SDK is not installed."""
        return _NoOpSpan()

    def start_transaction(**kwargs: Any) -> _NoOpSpan:
        """No-op stub — Sentry SDK is not installed."""
        return _NoOpSpan()

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
