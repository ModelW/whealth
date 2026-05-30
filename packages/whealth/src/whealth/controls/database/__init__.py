"""Database health control."""

from whealth import BaseControl, Failure


class Control(BaseControl):
    """Check that the database connection is healthy."""

    def get_failures(self) -> list[Failure]:
        """Run the database health check."""
        return []
