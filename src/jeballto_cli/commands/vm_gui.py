"""VM GUI window management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from jeballto_cli._context import CliContext, require_context
from jeballto_cli.references import resolve_vm_id
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command("open")
def open_gui(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Open the VM window."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.gui_open(vm_id)
    _render_gui_status(context, data, title="GUI Opened")


@app.command("close")
def close_gui(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Close the VM window."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.gui_close(vm_id)
    _render_gui_status(context, data, title="GUI Closed")


@app.command()
def status(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Show whether the VM window is open."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.gui_status(vm_id)
    _render_gui_status(context, data, title="GUI Status")


def _render_gui_status(context: CliContext, data: object, *, title: str) -> None:
    """Render GUI state with a concise human default."""
    if context.human_output and isinstance(data, dict):
        gui_open = data.get("guiOpen")
        state = "open" if gui_open is True else "closed" if gui_open is False else "unknown"
        context.console.print(f"{title}: {state}", highlight=False)
        return
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title=title,
    )
