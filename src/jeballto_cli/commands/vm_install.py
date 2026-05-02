"""VM macOS installation commands."""

from __future__ import annotations

import time
from typing import Annotated

import typer
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from jeballto_cli._context import require_context
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command()
def start(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    source: Annotated[
        str | None,
        typer.Option(
            "--source",
            help="IPSW source: HTTPS URL, file:// URL, or absolute path. "
            "Omit to download the latest macOS from Apple.",
        ),
    ] = None,
    wait: Annotated[
        bool, typer.Option("--wait", "-w", help="Wait for installation to complete.")
    ] = False,
) -> None:
    """Start macOS installation on a VM."""
    context = require_context(ctx)
    data = context.client.install(vm_id, source=source)

    if not wait:
        render_output(
            context.console,
            data,
            output_format=context.settings.output,
            title="Install Started",
        )
        return

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=context.console,
    ) as progress:
        task = progress.add_task("Installing macOS...", total=100)
        while True:
            status_data = context.client.install_status(vm_id)
            if not isinstance(status_data, dict):
                break

            install_status = str(status_data.get("status", ""))
            raw_pct = status_data.get("progress") or 0
            pct = raw_pct * 100 if isinstance(raw_pct, (int, float)) else 0
            msg = status_data.get("message") or "Installing..."

            progress.update(task, completed=pct, description=str(msg))

            if install_status == "completed":
                progress.update(task, completed=100, description="Installation complete.")
                break
            if install_status == "failed":
                msg = status_data.get("message", "Unknown error")
                context.console.print(
                    f"[bold red]Installation failed:[/] {msg}",
                )
                raise typer.Exit(code=1)

            time.sleep(3)

    context.console.print("[green]macOS installation completed.[/]")


@app.command()
def status(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    watch: Annotated[bool, typer.Option("--watch", help="Continuously poll status.")] = False,
) -> None:
    """Get macOS installation status."""
    context = require_context(ctx)

    if not watch:
        data = context.client.install_status(vm_id)
        render_output(
            context.console,
            data,
            output_format=context.settings.output,
            title="Install Status",
        )
        return

    try:
        while True:
            data = context.client.install_status(vm_id)
            render_output(
                context.console,
                data,
                output_format=context.settings.output,
                title="Install Status",
            )
            if isinstance(data, dict):
                s = str(data.get("status", ""))
                if s in ("completed", "failed"):
                    break
            time.sleep(3)
    except KeyboardInterrupt:
        pass
