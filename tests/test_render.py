"""Tests for the render module."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from jeballto_cli.render import render_output
from jeballto_cli.settings import OutputFormat


def _capture_console() -> tuple[Console, StringIO]:
    """Create a Console that writes to a StringIO buffer.

    Returns:
        Tuple of (console, buffer).
    """
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=200)
    return console, buf


def test_render_none() -> None:
    """None payload renders 'OK'."""
    console, buf = _capture_console()
    render_output(console, None, output_format=OutputFormat.TABLE)
    assert "OK" in buf.getvalue()


def test_render_dict_table() -> None:
    """Dict payload renders a table."""
    console, buf = _capture_console()
    render_output(console, {"name": "test", "value": 42}, output_format=OutputFormat.TABLE)
    output = buf.getvalue()
    assert "name" in output
    assert "test" in output
    assert "42" in output


def test_render_list_table() -> None:
    """List of dicts renders a multi-row table."""
    console, buf = _capture_console()
    render_output(
        console,
        [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}],
        output_format=OutputFormat.TABLE,
    )
    output = buf.getvalue()
    assert "a" in output
    assert "b" in output


def test_render_empty_list() -> None:
    """Empty list renders '(empty)'."""
    console, buf = _capture_console()
    render_output(console, [], output_format=OutputFormat.TABLE)
    assert "(empty)" in buf.getvalue()


def test_render_json() -> None:
    """JSON output is valid JSON."""
    console, buf = _capture_console()
    render_output(console, {"key": "val"}, output_format=OutputFormat.JSON)
    output = buf.getvalue()
    assert '"key"' in output
    assert '"val"' in output


def test_render_yaml() -> None:
    """YAML output contains key-value pairs."""
    console, buf = _capture_console()
    render_output(console, {"key": "val"}, output_format=OutputFormat.YAML)
    output = buf.getvalue()
    assert "key: val" in output
