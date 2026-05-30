#!/usr/bin/env python
"""Django management script for whospital."""

from django.core import management


def main() -> None:
    """Run management tasks."""
    management.execute_from_command_line()


if __name__ == "__main__":
    main()
