"""VM SSH forwarding commands."""

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
    user: Annotated[
        str,
        typer.Option("--user", help="Username to include in the connection command."),
    ] = "admin",
) -> None:
    """Show SSH host, port, and user."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.ssh_info(vm_id)
    if context.human_output and isinstance(data, dict):
        _print_ssh_info(context, data, title="SSH", user=user)
        return
    render_output(context.console, data, output_format=context.settings.output, title="SSH Info")


@app.command()
def enable(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
    user: Annotated[
        str,
        typer.Option("--user", help="Username to include in the connection command."),
    ] = "admin",
) -> None:
    """Turn on SSH access."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.ssh_enable(vm_id)
    if context.human_output and isinstance(data, dict):
        _print_ssh_info(context, data, title="SSH enabled", user=user)
        return
    render_output(context.console, data, output_format=context.settings.output, title="SSH Enabled")


@app.command()
def disable(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Turn off SSH access."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.ssh_disable(vm_id)
    if context.human_output and isinstance(data, dict):
        status = data.get("status") or "disabled"
        context.console.print(f"SSH: {status}", highlight=False)
        return
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="SSH Disabled",
    )


def _print_ssh_info(
    context: CliContext,
    data: dict[str, object],
    *,
    title: str,
    user: str,
) -> None:
    status = data.get("status") or "unknown"
    host = data.get("host")
    port = data.get("port")
    context.console.print(f"{title}: {status}", highlight=False)
    if host and port:
        context.console.print(
            f"connect: ssh -p {port} {user}@{host}",
            highlight=False,
            markup=False,
        )
