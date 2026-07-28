"""Tests for human and machine output rendering."""

from __future__ import annotations

import json
from io import StringIO

import yaml
from rich.console import Console

from jeballto_cli.render import render_output
from jeballto_cli.settings import OutputFormat


def _capture_console(*, width: int = 200) -> tuple[Console, StringIO]:
    """Create a deterministic non-terminal console and its output buffer."""
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, width=width)
    return console, buffer


def test_render_none_in_human_mode() -> None:
    """A successful empty human response has a clear acknowledgement."""
    console, buffer = _capture_console()

    render_output(console, None, output_format=OutputFormat.HUMAN)

    assert buffer.getvalue() == "OK\n"


def test_render_human_dict() -> None:
    """A dictionary becomes copy-friendly key and value lines."""
    console, buffer = _capture_console()

    render_output(
        console,
        {"name": "test", "value": 42},
        output_format=OutputFormat.HUMAN,
    )

    assert buffer.getvalue() == "name: test\nvalue: 42\n"


def test_render_human_values_do_not_interpret_rich_markup() -> None:
    """Agent-provided brackets remain literal text in human output."""
    console, buffer = _capture_console()

    render_output(
        console,
        {"message": "[bold]literal[/]"},
        output_format=OutputFormat.HUMAN,
    )

    assert "[bold]literal[/]" in buffer.getvalue()


def test_render_human_list_table() -> None:
    """Short dictionary rows remain easy to scan as a table."""
    console, buffer = _capture_console()

    render_output(
        console,
        [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}],
        output_format=OutputFormat.HUMAN,
    )

    output = buffer.getvalue()
    assert "a" in output
    assert "b" in output


def test_render_human_dict_wraps_long_values_without_ellipsis() -> None:
    """Long dictionary values wrap without losing copyable text."""
    console, buffer = _capture_console(width=36)

    render_output(
        console,
        {"url": "registry.example.com/very/long/path/that/keeps/going:latest"},
        output_format=OutputFormat.HUMAN,
    )

    output = buffer.getvalue()
    assert "…" not in output
    assert "registry" in output
    assert "latest" in output


def test_render_human_wide_rows_without_ellipsis() -> None:
    """Wide records use a layout that does not truncate identifiers."""
    console, buffer = _capture_console(width=52)

    render_output(
        console,
        [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "reference": "registry.example.com/vms/macos:latest",
                "status": "downloaded-and-ready",
            }
        ],
        output_format=OutputFormat.HUMAN,
    )

    output = buffer.getvalue()
    assert "…" not in output
    assert "550e8400" in output
    assert "latest" in output
    assert "downloaded" in output


def test_render_image_rows_as_copy_friendly_records() -> None:
    """Image identifiers and references render as plain copyable fields."""
    console, buffer = _capture_console(width=80)
    reference = "registry.example.com/team/macos-26-xcode:latest"

    render_output(
        console,
        [
            {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "reference": reference,
                "digest": "sha256:abc123",
            }
        ],
        output_format=OutputFormat.HUMAN,
    )

    output = buffer.getvalue()
    assert "reference: " + reference in output
    assert "digest: sha256:abc123" in output
    assert "│" not in output


def test_render_human_unpacks_nested_values() -> None:
    """Nested dictionaries use readable dotted paths."""
    console, buffer = _capture_console()

    render_output(
        console,
        {
            "resources": {"cpuCount": 4, "memorySize": 8 * 1024**3},
            "tags": ["ci", "macos"],
        },
        output_format=OutputFormat.HUMAN,
    )

    output = buffer.getvalue()
    assert "resources.cpuCount: 4" in output
    assert f"resources.memorySize: {8 * 1024**3}" in output
    assert "- ci" in output


def test_render_human_parses_embedded_json_strings() -> None:
    """JSON embedded in string fields is rendered as readable content."""
    console, buffer = _capture_console()

    render_output(
        console,
        {"details": '{"phase":"download","items":[{"name":"chunk","done":true}]}'},
        output_format=OutputFormat.HUMAN,
    )

    output = buffer.getvalue()
    assert '\\"phase\\"' not in output
    assert "phase: download" in output
    assert "name: chunk" in output


def test_render_human_list_flattens_nested_columns() -> None:
    """Compact row dictionaries expose nested values as columns."""
    console, buffer = _capture_console()

    render_output(
        console,
        [{"name": "vm", "resources": {"cpuCount": 4}, "network": {"sshPort": 2222}}],
        output_format=OutputFormat.HUMAN,
    )

    output = buffer.getvalue()
    assert "resources.cpuCount" in output
    assert "network.sshPort" in output


def test_render_empty_human_list() -> None:
    """An empty collection is explicit in human output."""
    console, buffer = _capture_console()

    render_output(console, [], output_format=OutputFormat.HUMAN)

    assert buffer.getvalue() == "(empty)\n"


def test_render_json() -> None:
    """JSON output can be consumed directly by a parser."""
    console, buffer = _capture_console()
    payload = {"key": "val", "nested": {"count": 2}}

    render_output(console, payload, output_format=OutputFormat.JSON)

    assert json.loads(buffer.getvalue()) == payload


def test_render_json_none_as_null() -> None:
    """An empty API response remains valid JSON in machine mode."""
    console, buffer = _capture_console()

    render_output(console, None, output_format=OutputFormat.JSON)

    assert json.loads(buffer.getvalue()) is None


def test_render_jsonl_is_one_compact_line() -> None:
    """JSONL emits one compact JSON object per render call."""
    console, buffer = _capture_console()
    payload = {"event": "state", "data": {"from": "stopped", "to": "running"}}

    render_output(console, payload, output_format=OutputFormat.JSONL)

    output = buffer.getvalue()
    assert output.count("\n") == 1
    assert " " not in output
    assert json.loads(output) == payload


def test_render_yaml() -> None:
    """YAML output can be consumed directly by a parser."""
    console, buffer = _capture_console()
    payload = {"key": "val", "items": [1, 2]}

    render_output(console, payload, output_format=OutputFormat.YAML)

    assert yaml.safe_load(buffer.getvalue()) == payload
