"""VM macOS installation commands."""

from __future__ import annotations

from typing import Annotated, Any

import typer
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from jeballto_cli._context import CliContext, require_context
from jeballto_cli.polling import poll_status
from jeballto_cli.references import resolve_vm_id
from jeballto_cli.render import render_output
from jeballto_cli.ui import format_bytes, format_progress, progress_percent
from jeballto_cli.validation import require_int_range

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")

INSTALL_TERMINAL_STATES = frozenset(
    {"not_started", "completed", "failed", "cancelled", "interrupted"}
)
DEFAULT_INSTALL_WAIT_TIMEOUT = 9_000


@app.command()
def start(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
    source: Annotated[
        str | None,
        typer.Option(
            "--ipsw",
            "--source",
            help="Install from this IPSW path or HTTPS URL. Omit to download from Apple.",
        ),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option(
            "--wait/--detach",
            help="Wait for installation, or return immediately after it starts.",
        ),
    ] = True,
    wait_timeout: Annotated[
        int,
        typer.Option(
            "--wait-timeout",
            help="Stop watching after this many seconds. Installation keeps running.",
        ),
    ] = DEFAULT_INSTALL_WAIT_TIMEOUT,
) -> None:
    """Install macOS in a VM."""
    context = require_context(ctx)
    wait_timeout = (
        require_int_range(wait_timeout, name="--wait-timeout", minimum=1, maximum=604800)
        or wait_timeout
    )
    vm_id = resolve_vm_id(context, vm)
    initial = context.client.install(vm_id, source=source)

    if not wait:
        _render_install_status(context, initial, title="Install Started")
        return

    result = _wait_for_install(context, vm_id, vm, wait_timeout=wait_timeout)
    _render_install_status(context, result, title="Install Result")
    if result.get("status") != "completed":
        raise typer.Exit(code=1)


@app.command()
def status(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
    watch: Annotated[
        bool,
        typer.Option("--watch", "-w", help="Watch until installation finishes."),
    ] = False,
    wait_timeout: Annotated[
        int,
        typer.Option(
            "--wait-timeout",
            help="With --watch, stop after this many seconds.",
        ),
    ] = DEFAULT_INSTALL_WAIT_TIMEOUT,
) -> None:
    """Show macOS installation progress."""
    context = require_context(ctx)
    wait_timeout = (
        require_int_range(wait_timeout, name="--wait-timeout", minimum=1, maximum=604800)
        or wait_timeout
    )
    vm_id = resolve_vm_id(context, vm)

    if not watch:
        data = context.client.install_status(vm_id)
        _render_install_status(context, data, title="Install Status")
        return

    result = _wait_for_install(context, vm_id, vm, wait_timeout=wait_timeout)
    _render_install_status(context, result, title="Install Result")
    if result.get("status") != "completed":
        raise typer.Exit(code=1)


def _wait_for_install(
    context: CliContext,
    vm_id: str,
    vm_ref: str,
    *,
    wait_timeout: int,
) -> dict[str, Any]:
    """Watch installation with TTY-safe progress and a resumable interrupt."""
    with Progress(
        TextColumn("{task.description}", markup=False),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=context.error_console,
        disable=not context.progress_enabled,
    ) as progress:
        task = progress.add_task("Installing macOS", total=100)

        def on_update(payload: dict[str, Any]) -> None:
            status_value = str(payload.get("status") or "installing")
            message = str(payload.get("message") or status_value)
            percent_value = payload.get("progress")
            percent = progress_percent(percent_value) or 0.0
            if context.progress_enabled:
                progress.update(task, completed=percent, description=message)
            elif context.is_human:
                context.error_console.print(
                    f"Install {format_progress(percent_value) or ''} {message}".strip(),
                    highlight=False,
                    markup=False,
                )

        try:
            return poll_status(
                lambda: context.client.install_status(vm_id),
                operation=f"installation for {vm_ref}",
                terminal_statuses=INSTALL_TERMINAL_STATES,
                timeout=wait_timeout,
                interval=3.0,
                on_update=on_update if context.is_human else None,
            )
        except KeyboardInterrupt:
            context.error_console.print(
                f"Installation is still running. Resume with: jeballto vm install status "
                f"{vm_ref} --watch",
                highlight=False,
            )
            raise typer.Exit(code=130) from None


def _render_install_status(context: CliContext, data: object, *, title: str) -> None:
    """Render installation status with useful phase and transfer details."""
    if context.human_output and isinstance(data, dict):
        status_value = data.get("status") or "unknown"
        progress_text = format_progress(data.get("progress"))
        summary = f"{title}: {status_value}"
        if progress_text:
            summary = f"{summary} ({progress_text})"
        context.console.print(summary, highlight=False, markup=False)

        for label, value in (
            ("phase", data.get("phase")),
            ("phase progress", format_progress(data.get("phaseProgress"))),
            ("message", data.get("message")),
        ):
            if value not in (None, ""):
                context.console.print(f"{label}: {value}", highlight=False, markup=False)

        downloaded = format_bytes(data.get("bytesDownloaded"))
        total = format_bytes(data.get("bytesTotal"))
        if downloaded or total:
            context.console.print(
                f"download: {downloaded or '0 B'} / {total or 'unknown'}",
                highlight=False,
            )
        speed = format_bytes(data.get("downloadSpeed"))
        if speed:
            context.console.print(f"speed: {speed}/s", highlight=False)
        return

    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title=title,
    )
