"""Database health control."""

from whealth import BaseControl


class Control(BaseControl):
    """Check that the database connection is healthy."""

    def check(self) -> None:
        """Run the database health check."""
