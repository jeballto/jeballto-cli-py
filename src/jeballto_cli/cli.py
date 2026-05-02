"""Root Typer application, global options, and entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from jeballto_cli import __version__
from jeballto_cli._context import CliContext
from jeballto_cli.client import APIError
from jeballto_cli.commands.auth import app as auth_app
from jeballto_cli.commands.config import app as config_app
from jeballto_cli.commands.image import app as image_app
from jeballto_cli.commands.jeballtofile import app as jeballtofile_app
from jeballto_cli.commands.registry import app as registry_app
from jeballto_cli.commands.system import app as system_app
from jeballto_cli.commands.vm import app as vm_app
from jeballto_cli.render import render_output
from jeballto_cli.settings import OutputFormat, load_settings

app = typer.Typer(
    name="jeballto",
    help="CLI for the Jeballto VM Agent API.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

app.add_typer(vm_app, name="vm", help="Manage virtual machines.")
app.add_typer(image_app, name="image", help="Manage OCI images.")
app.add_typer(registry_app, name="registry", help="OCI registry authentication.")
app.add_typer(config_app, name="config", help="Agent runtime configuration.")
app.add_typer(jeballtofile_app, name="jeballtofile", help="Jeballtofile blueprint execution.")
app.add_typer(system_app, name="system", help="System-level operations.")
app.add_typer(auth_app, name="auth", help="Authentication utilities.")


def _version_callback(value: bool) -> None:
    """Print version and exit when ``--version`` is passed.

    Args:
        value: Whether the flag was set.
    """
    if value:
        print(f"jeballto-cli {__version__}")
        raise typer.Exit()


@app.callback()
def _callback(
    ctx: typer.Context,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            "-u",
            help="Jeballto agent base URL.",
            envvar="JEBALLTO_BASE_URL",
        ),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option("--token", "-t", help="Bearer token.", envvar="JEBALLTO_TOKEN"),
    ] = None,
    timeout: Annotated[
        float | None,
        typer.Option("--timeout", help="Request timeout in seconds.", envvar="JEBALLTO_TIMEOUT"),
    ] = None,
    insecure: Annotated[
        bool,
        typer.Option("--insecure", "-k", help="Disable TLS verification."),
    ] = False,
    output: Annotated[
        OutputFormat | None,
        typer.Option("--output", "-o", help="Output format: json, yaml, table."),
    ] = None,
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to config file."),
    ] = None,
    _version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Jeballto CLI - manage macOS virtual machines on Apple Silicon."""
    settings = load_settings(
        base_url=base_url,
        token=token,
        timeout=timeout,
        insecure=insecure or None,
        output=output,
        config_file=config_file,
    )
    console = Console(stderr=True)
    ctx.obj = CliContext(settings=settings, console=console)


@app.command()
def health(ctx: typer.Context) -> None:
    """Check agent health status."""
    from jeballto_cli._context import require_context

    context = require_context(ctx)
    data = context.client.health()
    render_output(context.console, data, output_format=context.settings.output, title="Health")


def main() -> None:
    """CLI entry point with top-level error handling."""
    try:
        app()
    except APIError as exc:
        console = Console(stderr=True)
        if exc.code == "NETWORK_ERROR":
            console.print(
                f"[bold red]Connection error:[/] {exc.message}\n"
                "Is the Jeballto agent running? Check --base-url.",
            )
        elif exc.status_code == 401:
            console.print(
                "[bold red]Authentication failed.[/] Check your token or config.",
            )
        else:
            console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
