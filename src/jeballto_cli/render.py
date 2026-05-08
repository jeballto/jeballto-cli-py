"""Output rendering and formatting for CLI responses."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import yaml
from rich.console import Console
from rich.pretty import Pretty
from rich.table import Table

from jeballto_cli.settings import OutputFormat


def _add_wrapping_column(table: Table, name: str) -> None:
    table.add_column(name, overflow="fold", no_wrap=False)


def _scalar(value: Any) -> str:
    """Convert a single value to its string representation.

    Args:
        value: Any JSON-compatible value.

    Returns:
        String suitable for table cell display.
    """
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
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
    """Render a dict as a two-column Rich table (Field / Value).

    Args:
        console: Rich console instance.
        data: Dictionary to render.
        title: Optional table title.
    """
    table = Table(title=title)
    _add_wrapping_column(table, "Field")
    _add_wrapping_column(table, "Value")

    for key, value in data.items():
        table.add_row(key, _scalar(value))

    console.print(table)


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
        ordered_columns: list[str] = []
        for row in rows:
            assert isinstance(row, dict)
            for key in row:
                if key not in ordered_columns:
                    ordered_columns.append(key)

        table = Table(title=title, expand=True)
        for column in ordered_columns:
            _add_wrapping_column(table, column)

        for row in rows:
            assert isinstance(row, dict)
            table.add_row(*[_scalar(row.get(column)) for column in ordered_columns])

        console.print(table)
        return

    table = Table(title=title)
    _add_wrapping_column(table, "#")
    _add_wrapping_column(table, "Value")
    for index, row in enumerate(rows, start=1):
        table.add_row(str(index), _scalar(row))

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
        output_format: Desired output format (JSON, YAML, or TABLE).
        title: Optional title for table output.
    """
    if payload is None:
        console.print("OK")
        return

    if output_format == OutputFormat.JSON:
        console.print_json(data=payload)
        return

    if output_format == OutputFormat.YAML:
        yaml_text = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
        console.print(yaml_text)
        return

    if isinstance(payload, dict):
        _render_dict_table(console, payload, title)
        return

    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        _render_list_table(console, list(payload), title)
        return

    console.print(Pretty(payload))
