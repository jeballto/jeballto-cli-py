"""VM GUI window management commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from jeballto_cli._context import require_context
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command("open")
def open_gui(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Open a GUI window for a VM."""
    context = require_context(ctx)
    data = context.client.gui_open(vm_id)
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="GUI Opened",
    )


@app.command("close")
def close_gui(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Close the GUI window for a VM."""
    context = require_context(ctx)
    data = context.client.gui_close(vm_id)
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="GUI Closed",
    )


@app.command()
def status(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Get GUI window status."""
    context = require_context(ctx)
    data = context.client.gui_status(vm_id)
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="GUI Status",
    )


@app.command()
def screenshot(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    output_file: Annotated[
        Path | None,
        typer.Option("--output-file", "-o", help="Output file path (default: <vm_id>.png)."),
    ] = None,
) -> None:
    """Capture a screenshot of a VM and save it as PNG."""
    context = require_context(ctx)
    image_bytes = context.client.screenshot(vm_id)
    dest = output_file or Path(f"{vm_id}.png")
    dest.write_bytes(image_bytes)
    context.console.print(f"[green]Screenshot saved to {dest}[/]")
