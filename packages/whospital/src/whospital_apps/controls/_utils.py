"""Shared utilities for whospital_apps controls."""

from whealth import Failure


def check_keyvalue(slug: str) -> list[Failure]:
    """Check a KeyValue entry and return failures based on its value.

    * Missing key or empty value → no failures (healthy).
    * ``"warning"`` → warning failure.
    * ``"error"`` → error failure.
    * ``"internal_error"`` → internal_error failure.
    * Any other value → raises ``ValueError``.
    """
    from whospital_apps.models import KeyValue

    try:
        kv = KeyValue.objects.get(key=slug)
    except KeyValue.DoesNotExist:
        return []

    value = kv.value.strip()

    if not value:
        return []

    if value == "warning":
        return [Failure(key=slug, outcome="warning")]
    if value == "error":
        return [Failure(key=slug, outcome="error")]
    if value == "internal_error":
        return [Failure(key=slug, outcome="internal_error")]

    msg = f"Unexpected KeyValue value for {slug!r}: {value!r}"
    raise ValueError(msg)
