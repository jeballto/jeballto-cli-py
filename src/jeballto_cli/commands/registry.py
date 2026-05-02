"""OCI registry authentication commands."""

from __future__ import annotations

from typing import Annotated

import typer

from jeballto_cli._context import require_context
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command()
def login(
    ctx: typer.Context,
    registry: Annotated[str, typer.Argument(help="Registry hostname.")],
    username: Annotated[
        str | None, typer.Option("--username", "-u", help="Registry username.")
    ] = None,
    password: Annotated[
        str | None, typer.Option("--password", "-p", help="Registry password.")
    ] = None,
) -> None:
    """Authenticate to an OCI registry."""
    context = require_context(ctx)
    resolved_username = username or typer.prompt("Username")
    resolved_password = password or typer.prompt("Password", hide_input=True)
    data = context.client.registry_login(registry, resolved_username, resolved_password)
    render_output(context.console, data, output_format=context.settings.output, title="Login")


@app.command()
def logout(
    ctx: typer.Context,
    registry: Annotated[str, typer.Argument(help="Registry hostname.")],
) -> None:
    """Remove credentials for an OCI registry."""
    context = require_context(ctx)
    data = context.client.registry_logout(registry)
    render_output(context.console, data, output_format=context.settings.output, title="Logout")
