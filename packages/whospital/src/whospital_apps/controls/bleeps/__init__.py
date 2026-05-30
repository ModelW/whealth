"""Bleeps health control."""

from whealth import BaseControl


class Control(BaseControl):
    """Check that the bleep system is healthy."""

    def check(self) -> None:
        """Run the bleeps health check."""
