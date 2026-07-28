"""Output rendering and formatting for CLI responses."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import yaml
from rich.console import Console
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text

from jeballto_cli.settings import OutputFormat


def _write_machine_output(console: Console, value: str) -> None:
    """Write exact machine-readable text without Rich styling or wrapping."""
    console.file.write(value)
    console.file.flush()


def _add_wrapping_column(table: Table, name: str) -> None:
    table.add_column(Text(name), overflow="fold", no_wrap=False)


def _indent_multiline(value: str, *, prefix: str = "  ") -> str:
    lines = value.splitlines()
    if len(lines) <= 1:
        return value
    return ("\n" + prefix).join(lines)


def _parse_embedded_json(value: str) -> Any:
    stripped = value.strip()
    if not stripped or stripped[0] not in "{[":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _flatten_dict(data: dict[str, Any], *, prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten_dict(value, prefix=full_key))
        else:
            flattened[full_key] = value
    return flattened


def _scalar(value: Any) -> str:
    """Convert a single value to its string representation.

    Args:
        value: Any JSON-compatible value.

    Returns:
        String suitable for table cell display.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        parsed = _parse_embedded_json(value)
        if parsed is not value:
            return _scalar(parsed)
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (dict, list)):
        return yaml.safe_dump(
            value,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ).strip()
    return json.dumps(value, ensure_ascii=False)


def _render_dict_table(console: Console, data: dict[str, Any], title: str | None) -> None:
    """Render a dict as copy-friendly key-value lines.

    Args:
        console: Rich console instance.
        data: Dictionary to render.
        title: Optional table title.
    """
    if title:
        console.print(f"[bold]{title}[/]")

    for key, value in _flatten_dict(data).items():
        scalar = _indent_multiline(_scalar(value))
        console.print(f"{key}: {scalar}", highlight=False, markup=False)


def _needs_record_layout(rows: list[dict[str, Any]], columns: list[str], width: int) -> bool:
    if len(columns) > 6:
        return True
    copy_sensitive_columns = {"reference", "digest", "localPath", "statusUrl"}
    if copy_sensitive_columns.intersection(columns):
        return True
    long_value_limit = max(32, min(80, width // 2))
    for row in rows:
        for value in row.values():
            if len(_scalar(value)) > long_value_limit:
                return True
    return False


def _render_record_list(
    console: Console,
    rows: list[dict[str, Any]],
    columns: list[str],
    title: str | None,
) -> None:
    if title:
        console.print(f"[bold]{title}[/]")

    for index, row in enumerate(rows, start=1):
        if index > 1:
            console.print("")
        console.print(f"{index}.", highlight=False)
        for column in columns:
            scalar = _indent_multiline(_scalar(row.get(column)))
            console.print(f"{column}: {scalar}", highlight=False, markup=False)


def _render_list_table(console: Console, rows: list[Any], title: str | None) -> None:
    """Render a list as a Rich table.

    If all items are dicts, columns are derived from keys. Otherwise
    a simple indexed table is produced.

    Args:
        console: Rich console instance.
        rows: List of items to render.
        title: Optional table title.
    """
    if not rows:
        console.print("(empty)")
        return

    if all(isinstance(row, dict) for row in rows):
        original_rows = [row for row in rows if isinstance(row, dict)]
        flattened_rows = [_flatten_dict(row) for row in original_rows]
        flattened_columns = {key for row in flattened_rows for key in row}
        table_rows = flattened_rows if len(flattened_columns) <= 8 else original_rows
        ordered_columns: list[str] = []
        for row in table_rows:
            assert isinstance(row, dict)
            for key in row:
                if key not in ordered_columns:
                    ordered_columns.append(key)

        if _needs_record_layout(table_rows, ordered_columns, console.width):
            _render_record_list(console, table_rows, ordered_columns, title)
            return

        table = Table(title=title, expand=True)
        for column in ordered_columns:
            _add_wrapping_column(table, column)

        for row in table_rows:
            table.add_row(*[Text(_scalar(row.get(column))) for column in ordered_columns])

        console.print(table)
        return

    table = Table(title=title)
    _add_wrapping_column(table, "#")
    _add_wrapping_column(table, "Value")
    for index, row in enumerate(rows, start=1):
        table.add_row(str(index), Text(_scalar(row)))

    console.print(table)


def render_output(
    console: Console,
    payload: Any,
    *,
    output_format: OutputFormat,
    title: str | None = None,
) -> None:
    """Format and print a payload to the console.

    Args:
        console: Rich console instance.
        payload: Data to render (dict, list, scalar, or ``None``).
        output_format: Desired output format.
        title: Optional title for table output.
    """
    if payload is None and output_format == OutputFormat.HUMAN:
        console.print("OK")
        return

    if output_format == OutputFormat.JSON:
        _write_machine_output(
            console,
            f"{json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)}\n",
        )
        return

    if output_format == OutputFormat.JSONL:
        _write_machine_output(
            console,
            f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)}\n",
        )
        return

    if output_format == OutputFormat.YAML:
        yaml_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        _write_machine_output(console, yaml_text)
        return

    if isinstance(payload, dict):
        _render_dict_table(console, payload, title)
        return

    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        _render_list_table(console, list(payload), title)
        return

    console.print(Pretty(payload))
