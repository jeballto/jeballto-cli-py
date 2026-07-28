"""OCI registry authentication commands."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from jeballto_cli._context import require_context
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command()
def login(
    ctx: typer.Context,
    registry: Annotated[str, typer.Argument(help="Registry host, such as ghcr.io.")],
    username: Annotated[
        str | None, typer.Option("--username", "-u", help="Username for the registry.")
    ] = None,
    password: Annotated[
        str | None,
        typer.Option(
            "--password",
            "-p",
            help="Password or token. Prefer prompt, stdin, or environment.",
            envvar="JEBALLTO_REGISTRY_PASSWORD",
        ),
    ] = None,
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read the password or token from stdin."),
    ] = False,
) -> None:
    """Sign in to an image registry."""
    context = require_context(ctx)
    if password is not None and password_stdin:
        raise typer.BadParameter("Use --password or --password-stdin, not both.")
    if username is None and context.settings.no_input:
        raise typer.BadParameter("Pass --username when --no-input is enabled.")
    resolved_username = username or typer.prompt("Username", err=True)
    if password_stdin:
        resolved_password = sys.stdin.read().rstrip("\r\n")
        if not resolved_password:
            raise typer.BadParameter("stdin did not contain a password.")
    elif password is not None:
        resolved_password = password
    elif context.settings.no_input:
        raise typer.BadParameter(
            "Pass --password-stdin or set JEBALLTO_REGISTRY_PASSWORD with --no-input."
        )
    else:
        resolved_password = typer.prompt("Password", hide_input=True, err=True)
    data = context.client.registry_login(registry, resolved_username, resolved_password)
    if context.human_output and isinstance(data, dict):
        status = data.get("status") or "saved"
        context.console.print(f"Registry login: {status}", highlight=False)
        context.console.print(f"registry: {data.get('registry') or registry}", highlight=False)
        message = data.get("message")
        if message:
            context.console.print(f"message: {message}", highlight=False, markup=False)
        return
    render_output(context.console, data, output_format=context.settings.output, title="Login")


@app.command()
def logout(
    ctx: typer.Context,
    registry: Annotated[str, typer.Argument(help="Registry host, such as ghcr.io.")],
) -> None:
    """Forget saved registry credentials."""
    context = require_context(ctx)
    data = context.client.registry_logout(registry)
    if context.human_output and isinstance(data, dict):
        context.console.print(f"Registry logout: {registry}", highlight=False)
        message = data.get("message")
        if message:
            context.console.print(f"message: {message}", highlight=False, markup=False)
        return
    render_output(context.console, data, output_format=context.settings.output, title="Logout")
