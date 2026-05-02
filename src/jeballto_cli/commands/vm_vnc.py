"""VM VNC forwarding commands."""

from __future__ import annotations

from typing import Annotated

import typer

from jeballto_cli._context import require_context
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command()
def info(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Get VNC connection info."""
    context = require_context(ctx)
    data = context.client.vnc_info(vm_id)
    render_output(context.console, data, output_format=context.settings.output, title="VNC Info")


@app.command()
def enable(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Enable VNC forwarding."""
    context = require_context(ctx)
    data = context.client.vnc_enable(vm_id)
    render_output(context.console, data, output_format=context.settings.output, title="VNC Enabled")


@app.command()
def disable(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Disable VNC forwarding."""
    context = require_context(ctx)
    data = context.client.vnc_disable(vm_id)
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="VNC Disabled",
    )
