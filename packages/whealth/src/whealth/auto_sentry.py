"""Auto-detection of the Sentry SDK.

When ``sentry_sdk`` is installed this module re-exports the real Sentry
functions directly.  Otherwise it provides no-op stubs so callers can
always ``from whealth.auto_sentry import capture_exception`` without
worrying about ImportErrors.
"""

from __future__ import annotations

from typing import Any

try:
    import sentry_sdk

    capture_exception: Any = sentry_sdk.capture_exception
except ImportError:

    def capture_exception(
        error: BaseException | None = None,
        **extra: Any,
    ) -> str | None:
        """No-op stub — Sentry SDK is not installed."""
        return None
