"""VM VNC forwarding commands."""

from __future__ import annotations

from typing import Annotated

import typer

from jeballto_cli._context import CliContext, require_context
from jeballto_cli.references import resolve_vm_id
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command()
def info(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Show VNC host and port."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.vnc_info(vm_id)
    if context.human_output and isinstance(data, dict):
        _print_vnc_info(context, data, title="VNC")
        return
    render_output(context.console, data, output_format=context.settings.output, title="VNC Info")


@app.command()
def enable(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Turn on VNC access."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.vnc_enable(vm_id)
    if context.human_output and isinstance(data, dict):
        _print_vnc_info(context, data, title="VNC enabled")
        return
    render_output(context.console, data, output_format=context.settings.output, title="VNC Enabled")


@app.command()
def disable(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Turn off VNC access."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.vnc_disable(vm_id)
    if context.human_output and isinstance(data, dict):
        status = data.get("status") or "disabled"
        context.console.print(f"VNC: {status}", highlight=False)
        return
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="VNC Disabled",
    )


def _print_vnc_info(context: CliContext, data: dict[str, object], *, title: str) -> None:
    status = data.get("status") or "unknown"
    host = data.get("host")
    port = data.get("port")
    context.console.print(f"{title}: {status}", highlight=False)
    if host and port:
        context.console.print(
            f"connect: vnc://{host}:{port}",
            highlight=False,
            markup=False,
        )
