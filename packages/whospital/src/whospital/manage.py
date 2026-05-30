#!/usr/bin/env python
"""Django management script for whospital."""

import os
import sys

from django.core import management


def main() -> None:
    """Run management tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "whospital.settings")
    management.execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
