"""Pretty-printing utilities for CLI output."""

from __future__ import annotations

import json
import sys
from typing import TextIO


def print_json(
    obj: object,
    *,
    file: TextIO | None = None,
    force_rich: bool | None = None,
) -> None:
    """Print *obj* as pretty-printed JSON.

    If the *rich* package is installed and the output is a terminal (or
    *force_rich* is explicitly ``True``), the output is syntax-highlighted.
    Otherwise plain JSON with 4-space indentation is printed.

    Parameters
    ----------
    obj:
        Any JSON-serialisable object.
    file:
        Output stream (defaults to ``sys.stdout``).  Pass ``io.StringIO``
        during tests to capture the output.
    force_rich:
        | ``None`` (default) — auto-detect: use *rich* only if it can be
          imported and *file* (or ``sys.stdout``) is a TTY.
        | ``True`` — always use *rich* (for testing).
        | ``False`` — always use plain JSON (for testing).
    """
    if file is None:
        file = sys.stdout

    try:
        import rich  # noqa: F401
    except ImportError:
        rich_available = False
    else:
        rich_available = True

    use_rich: bool
    if force_rich is True:
        use_rich = rich_available
    elif force_rich is False:
        use_rich = False
    else:
        use_rich = rich_available and file.isatty()

    if use_rich:
        from rich.console import Console

        console = Console(file=file, force_terminal=True)
        console.print_json(data=obj, indent=4)
    else:
        print(json.dumps(obj, indent=4), file=file)
