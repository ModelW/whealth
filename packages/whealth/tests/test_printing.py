"""Tests for whealth.printing."""

from __future__ import annotations

from io import StringIO

from whealth.printing import print_json

SAMPLE = {"a": 1, "b": [2, 3]}

PLAIN = '{\n    "a": 1,\n    "b": [\n        2,\n        3\n    ]\n}'


def test_plain_json() -> None:
    """Default output when rich is not installed or not forced."""
    buf = StringIO()
    print_json(SAMPLE, file=buf)
    assert buf.getvalue().rstrip("\n") == PLAIN


def test_plain_json_force_false() -> None:
    """force_rich=False always produces plain JSON."""
    buf = StringIO()
    print_json(SAMPLE, file=buf, force_rich=False)
    assert buf.getvalue().rstrip("\n") == PLAIN


def test_rich_force_true() -> None:
    """force_rich=True produces rich ANSI-coloured output."""
    buf = StringIO()
    print_json(SAMPLE, file=buf, force_rich=True)
    result = buf.getvalue()
    # Rich emits ANSI escape sequences.
    assert "\x1b[" in result
    assert "a" in result


class _TtyStringIO(StringIO):
    """A StringIO that pretends to be a terminal.

    Lets the auto-detection branch of ``print_json`` be tested without a
    real TTY (unavailable under pytest/CI, where stdout is a pipe).
    """

    def isatty(self) -> bool:
        return True


def test_rich_auto_on_tty() -> None:
    """Auto-detect uses rich when the output stream reports being a TTY."""
    buf = _TtyStringIO()
    print_json(SAMPLE, file=buf)
    assert "\x1b[" in buf.getvalue()


def test_rich_auto_on_non_tty() -> None:
    """Auto-detect stays plain when the output stream is not a TTY."""
    buf = StringIO()
    print_json(SAMPLE, file=buf)
    assert "\x1b[" not in buf.getvalue()
    assert buf.getvalue().rstrip("\n") == PLAIN


def test_defaults_to_stdout() -> None:
    """When no file is passed, prints to sys.stdout (no crash)."""
    print_json(SAMPLE)


def test_force_rich_non_tty() -> None:
    """force_rich=True outputs ANSI codes even on a non-TTY stream."""
    buf = StringIO()
    print_json(SAMPLE, file=buf, force_rich=True)
    assert "\x1b[" in buf.getvalue()
