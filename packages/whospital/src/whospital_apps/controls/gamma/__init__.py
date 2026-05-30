"""gamma health control."""

from whealth import BaseControl, Failure

from whospital_apps.controls._utils import check_keyvalue


class Control(BaseControl):
    """Check that gamma is healthy."""

    def get_failures(self) -> list[Failure]:
        """Run the gamma health check."""
        return check_keyvalue("gamma")
