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


def _capture_console_width(width: int) -> tuple[Console, StringIO]:
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=width)
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


def test_render_dict_table_wraps_long_values_without_ellipsis() -> None:
    """Long dict values wrap instead of truncating with ellipsis."""
    console, buf = _capture_console_width(36)
    render_output(
        console,
        {"url": "registry.example.com/very/long/path/that/keeps/going:latest"},
        output_format=OutputFormat.TABLE,
    )
    output = buf.getvalue()
    assert "…" not in output
    assert "registry" in output
    assert "latest" in output


def test_render_list_table_wraps_wide_rows_without_ellipsis() -> None:
    """Wide list rows wrap instead of truncating with ellipsis."""
    console, buf = _capture_console_width(52)
    render_output(
        console,
        [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "reference": "registry.example.com/vms/macos:latest",
                "status": "downloaded-and-ready",
            }
        ],
        output_format=OutputFormat.TABLE,
    )
    output = buf.getvalue()
    assert "…" not in output
    assert "550e8400" in output
    assert "latest" in output
    assert "downloaded" in output


def test_render_table_unpacks_nested_values() -> None:
    """Nested dict and list values render as readable blocks."""
    console, buf = _capture_console()
    render_output(
        console,
        {
            "resources": {"cpuCount": 4, "memorySize": "8GB"},
            "tags": ["ci", "macos"],
        },
        output_format=OutputFormat.TABLE,
    )
    output = buf.getvalue()
    assert "{'cpuCount'" not in output
    assert '{"cpuCount"' not in output
    assert "cpuCount:" in output
    assert "memorySize:" in output
    assert "- ci" in output


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
