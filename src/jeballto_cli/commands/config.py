"""Agent runtime configuration commands."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from jeballto_cli._context import require_context
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command()
def get(ctx: typer.Context) -> None:
    """Get the agent runtime configuration."""
    context = require_context(ctx)
    data = context.client.get_config()
    render_output(context.console, data, output_format=context.settings.output, title="Config")


@app.command("set")
def set_config(
    ctx: typer.Context,
    data: Annotated[
        str | None,
        typer.Option("--json", "-j", help="JSON string with config updates."),
    ] = None,
    log_level: Annotated[str | None, typer.Option("--log-level", help="Logging level.")] = None,
    timezone: Annotated[
        str | None,
        typer.Option(
            "--timezone",
            help="IANA timezone for log timestamps (e.g. 'UTC'). Empty string clears.",
        ),
    ] = None,
    vnc_port_start: Annotated[
        int | None,
        typer.Option("--vnc-port-range-start", help="VNC port range start (1024-65535)."),
    ] = None,
    vnc_port_end: Annotated[
        int | None,
        typer.Option("--vnc-port-range-end", help="VNC port range end (1024-65535)."),
    ] = None,
) -> None:
    """Update the agent runtime configuration.

    Pass a raw JSON object via --json, or use individual flags.
    """
    context = require_context(ctx)

    updates: dict[str, object]
    if data:
        try:
            updates = json.loads(data)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"Invalid JSON: {exc}") from exc
    else:
        updates = {}

    if log_level is not None:
        updates.setdefault("logging", {})
        if isinstance(updates["logging"], dict):
            updates["logging"]["level"] = log_level

    if timezone is not None:
        updates.setdefault("logging", {})
        if isinstance(updates["logging"], dict):
            updates["logging"]["timezone"] = timezone if timezone != "" else None

    if vnc_port_start is not None or vnc_port_end is not None:
        updates.setdefault("networking", {})
        net = updates["networking"]
        if isinstance(net, dict):
            if vnc_port_start is not None:
                net["vncPortRangeStart"] = vnc_port_start
            if vnc_port_end is not None:
                net["vncPortRangeEnd"] = vnc_port_end

    if not updates:
        raise typer.BadParameter("Provide --json or at least one config flag.")

    result = context.client.update_config(updates)
    render_output(
        context.console,
        result,
        output_format=context.settings.output,
        title="Config Updated",
    )
