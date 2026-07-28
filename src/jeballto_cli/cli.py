"""Root Typer application, global options, and entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.markup import escape

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
from jeballto_cli.errors import ErrorHandlingGroup
from jeballto_cli.render import render_output
from jeballto_cli.settings import OutputFormat, load_settings
from jeballto_cli.ui import format_duration

app = typer.Typer(
    name="jeballto",
    help="Manage Jeballto VMs, images, config, and automation.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
    pretty_exceptions_enable=False,
    cls=ErrorHandlingGroup,
    epilog=(
        "Examples: jeballto doctor | jeballto vm list | "
        "jeballto image pull registry.example.com/macos:latest"
    ),
)

app.add_typer(auth_app, name="auth", help="Manage the API token in macOS Keychain.")
app.add_typer(vm_app, name="vm", help="Create and control VMs.")
app.add_typer(image_app, name="image", help="Pull, push, inspect, and delete VM images.")
app.add_typer(registry_app, name="registry", help="Sign in to image registries.")
app.add_typer(config_app, name="config", help="View or change agent settings.")
app.add_typer(jeballtofile_app, name="run", help="Submit and inspect Jeballtofiles.")
app.add_typer(system_app, name="system", help="Inspect host features or reset local state.")


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
            help="Agent URL, for example http://127.0.0.1:8011/v1.",
        ),
    ] = None,
    token: Annotated[
        str | None,
        typer.Option(
            "--token",
            "-t",
            help="API token for this command. Prefer 'jeballto auth login'.",
        ),
    ] = None,
    request_timeout: Annotated[
        float | None,
        typer.Option(
            "--request-timeout",
            help="Limit an individual API request in seconds.",
        ),
    ] = None,
    insecure: Annotated[
        bool | None,
        typer.Option(
            "--insecure/--verify-tls",
            "-k",
            help="Disable or require TLS certificate verification.",
        ),
    ] = None,
    output: Annotated[
        OutputFormat | None,
        typer.Option(
            "--output",
            "-o",
            help="Print as human, json, jsonl, or yaml.",
        ),
    ] = None,
    config_file: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="CLI config file to use."),
    ] = None,
    details: Annotated[
        bool | None,
        typer.Option(
            "--details/--no-details",
            help="Show or hide every API field in human output.",
        ),
    ] = None,
    no_input: Annotated[
        bool,
        typer.Option("--no-input", help="Never prompt for input."),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option("--no-color", help="Disable colored output."),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Show diagnostic tracebacks for CLI bugs."),
    ] = False,
    _version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Print version."),
    ] = False,
) -> None:
    """Manage macOS virtual machines with Jeballto."""
    if ctx.resilient_parsing:
        return
    try:
        settings = load_settings(
            base_url=base_url,
            token=token,
            request_timeout=request_timeout,
            insecure=insecure,
            output=output,
            config_file=config_file,
            details=details,
            no_input=no_input,
            debug=debug,
        )
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc), param_hint="configuration") from exc

    context = CliContext(
        settings=settings,
        console=Console(stderr=False, no_color=no_color),
        error_console=Console(stderr=True, no_color=no_color),
    )
    ctx.obj = context
    ctx.call_on_close(context.close)


@app.command()
def health(ctx: typer.Context) -> None:
    """Check whether the agent is reachable."""
    from jeballto_cli._context import require_context

    context = require_context(ctx)
    data = context.client.health()
    if context.human_output and isinstance(data, dict):
        status = data.get("status") or "unknown"
        context.console.print(f"Jeballto agent: {status}", highlight=False)
        for key, label in (
            ("version", "version"),
            ("uptime", "uptime"),
            ("vmsRunning", "running VMs"),
            ("vmsTotal", "total VMs"),
        ):
            value = data.get(key)
            if key == "uptime":
                value = format_duration(value) or value
            if value is not None:
                context.console.print(f"{label}: {value}", highlight=False)
        return
    render_output(context.console, data, output_format=context.settings.output, title="Health")


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Diagnose connection, authentication, and host readiness."""
    from jeballto_cli._context import require_context

    context = require_context(ctx)
    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "name": "configuration",
            "status": "pass",
            "message": f"Agent URL: {context.settings.base_url}",
        }
    )

    health_data: object = None
    try:
        health_data = context.client.health()
        version = health_data.get("version") if isinstance(health_data, dict) else None
        checks.append(
            {
                "name": "connection",
                "status": "pass",
                "message": f"Agent is reachable{f' (v{version})' if version else ''}.",
            }
        )
    except APIError as exc:
        checks.append(
            {
                "name": "connection",
                "status": "fail",
                "message": exc.message,
                "hint": "Start Jeballto or verify --base-url.",
            }
        )

    authenticated = False
    if context.settings.token is None:
        checks.append(
            {
                "name": "authentication",
                "status": "fail",
                "message": "No API token is configured.",
                "hint": "Copy the token from Jeballto, then run 'jeballto auth login'.",
            }
        )
    elif health_data is not None:
        try:
            context.client.auth_verify()
            authenticated = True
            checks.append(
                {
                    "name": "authentication",
                    "status": "pass",
                    "message": f"Token from {context.settings.token_source.value} is valid.",
                }
            )
        except APIError as exc:
            checks.append(
                {
                    "name": "authentication",
                    "status": "fail",
                    "message": exc.message,
                    "hint": "Copy the current token and run 'jeballto auth login'.",
                }
            )
    else:
        checks.append(
            {
                "name": "authentication",
                "status": "skip",
                "message": "Not checked because the agent is unreachable.",
            }
        )

    if authenticated:
        try:
            capabilities = context.client.system_capabilities()
            host = capabilities.get("host") if isinstance(capabilities, dict) else None
            virtualization = host.get("virtualizationSupported") if isinstance(host, dict) else None
            if virtualization is True:
                checks.append(
                    {
                        "name": "virtualization",
                        "status": "pass",
                        "message": "Apple Virtualization is available.",
                    }
                )
            else:
                checks.append(
                    {
                        "name": "virtualization",
                        "status": "fail",
                        "message": "Apple Virtualization is unavailable.",
                        "hint": "Run 'jeballto system capabilities' for the reason.",
                    }
                )
        except APIError as exc:
            checks.append(
                {
                    "name": "capabilities",
                    "status": "fail",
                    "message": exc.message,
                    "hint": "Run 'jeballto system capabilities' after resolving the error.",
                }
            )
    else:
        reason = (
            "Not checked because authentication is unavailable."
            if health_data is not None
            else "Not checked because the agent is unreachable."
        )
        checks.append(
            {
                "name": "virtualization",
                "status": "skip",
                "message": reason,
            }
        )

    result = {
        "status": "ready" if all(check["status"] == "pass" for check in checks) else "issues",
        "checks": checks,
    }
    if context.human_output:
        context.console.print("[bold]Jeballto Doctor[/]")
        for check in checks:
            status = str(check["status"]).upper()
            style = "green" if status == "PASS" else "yellow" if status == "SKIP" else "red"
            context.console.print(
                f"[{style}]{status}[/] {escape(str(check['name']))}: "
                f"{escape(str(check['message']))}",
                highlight=False,
            )
            if check.get("hint"):
                context.console.print(
                    f"     hint: {escape(str(check['hint']))}",
                    highlight=False,
                )
    else:
        render_output(context.console, result, output_format=context.settings.output)
    if result["status"] != "ready":
        raise typer.Exit(code=1)


def main() -> None:
    """CLI entry point with top-level error handling."""
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
