"""Authentication utilities."""

from __future__ import annotations

import typer

from jeballto_cli._context import require_context
from jeballto_cli.client import APIError
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command()
def verify(ctx: typer.Context) -> None:
    """Verify the configured bearer token against the agent."""
    context = require_context(ctx)
    try:
        data = context.client.auth_verify()
    except APIError as exc:
        if exc.status_code == 401:
            context.console.print("[bold red]Token invalid or missing.[/]")
            raise typer.Exit(code=1) from exc
        raise
    render_output(context.console, data, output_format=context.settings.output, title="Auth")
