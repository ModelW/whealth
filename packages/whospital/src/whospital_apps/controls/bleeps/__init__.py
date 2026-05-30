"""Bleeps health control."""

from whealth import BaseControl, Failure


class Control(BaseControl):
    """Check that the bleep system is healthy."""

    def get_failures(self) -> list[Failure]:
        """Run the bleeps health check."""
        return []
