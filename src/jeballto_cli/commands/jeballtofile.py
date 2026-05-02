"""Jeballtofile blueprint execution commands."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from jeballto_cli._context import require_context
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command()
def run(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(
            help="VM display name (1-100 characters). Optional when provided by --file.",
        ),
    ] = None,
    steps: Annotated[
        str | None,
        typer.Option(
            "--steps",
            "-s",
            help="JSON array of step objects to execute. Mutually exclusive with --file.",
        ),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            "-f",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Path to a Jeballtofile JSON/YAML file.",
        ),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option(
            "--source",
            help="IPSW source for macOS installation steps: HTTPS URL, file:// URL, or "
            "absolute path. Required when steps include an 'install' step.",
        ),
    ] = None,
    cpu: Annotated[int | None, typer.Option("--cpu", help="Number of CPU cores.")] = None,
    memory: Annotated[
        str | None, typer.Option("--memory", help="Memory size (e.g. '8GB').")
    ] = None,
    disk: Annotated[str | None, typer.Option("--disk", help="Disk size (e.g. '64GB').")] = None,
    wait: Annotated[
        bool,
        typer.Option("--wait", "-w", help="Poll until execution completes or fails."),
    ] = False,
) -> None:
    """Execute a Jeballtofile blueprint.

    Creates a VM and runs all steps asynchronously. Returns immediately with an
    execution ID for status polling, unless --wait is passed.

    Example steps JSON:

    \b
    '[{"type":"start"},{"type":"execute","command":"echo hello"}]'
    """
    if steps is None and file is None:
        raise typer.BadParameter("Provide exactly one of --steps or --file.")
    if steps is not None and file is not None:
        raise typer.BadParameter("Provide only one of --steps or --file.")

    resolved_name = name
    parsed_steps: list[Any]
    file_source = source
    file_cpu = cpu
    file_memory = memory
    file_disk = disk

    if file is not None:
        raw_content = file.read_text(encoding="utf-8")
        try:
            payload = (
                json.loads(raw_content)
                if file.suffix.lower() == ".json"
                else yaml.safe_load(raw_content)
            )
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise typer.BadParameter(f"Invalid file format for --file: {exc}") from exc

        if isinstance(payload, list):
            parsed_steps = payload
        elif isinstance(payload, dict):
            raw_steps = payload.get("steps")
            if not isinstance(raw_steps, list):
                raise typer.BadParameter("Jeballtofile must contain a 'steps' array.")
            parsed_steps = raw_steps

            if resolved_name is None and isinstance(payload.get("name"), str):
                resolved_name = payload["name"]

            if source is None and isinstance(payload.get("source"), str):
                file_source = payload["source"]

            resources = payload.get("resources")
            if isinstance(resources, dict):
                if cpu is None and isinstance(resources.get("cpuCount"), int):
                    file_cpu = resources["cpuCount"]
                if memory is None and isinstance(resources.get("memorySize"), str):
                    file_memory = resources["memorySize"]
                if disk is None and isinstance(resources.get("diskSize"), str):
                    file_disk = resources["diskSize"]
        else:
            raise typer.BadParameter("Jeballtofile file must be a JSON/YAML object or array.")
    else:
        assert steps is not None
        try:
            parsed_steps = json.loads(steps)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"Invalid JSON for --steps: {exc}") from exc

    if not isinstance(parsed_steps, list):
        raise typer.BadParameter("--steps must resolve to a JSON array.")
    if resolved_name is None:
        raise typer.BadParameter("Name is required (argument or file field 'name').")

    context = require_context(ctx)
    data = context.client.create_jeballtofile(
        resolved_name,
        parsed_steps,
        source=file_source,
        cpu=file_cpu,
        memory=file_memory,
        disk=file_disk,
    )

    if not wait:
        render_output(
            context.console,
            data,
            output_format=context.settings.output,
            title="Jeballtofile Started",
        )
        return

    execution_id = data.get("id") if isinstance(data, dict) else None
    if not execution_id:
        render_output(
            context.console,
            data,
            output_format=context.settings.output,
            title="Jeballtofile Started",
        )
        return

    context.console.print(f"Waiting for execution [bold]{execution_id}[/] to finish...")
    try:
        while True:
            status_data = context.client.get_jeballtofile(str(execution_id))
            if isinstance(status_data, dict):
                status = str(status_data.get("status", ""))
                current = status_data.get("currentStep", 0)
                total = status_data.get("totalSteps", 0)
                context.console.print(
                    f"  step {current}/{total} - {status}",
                    highlight=False,
                )
                if status in ("completed", "failed", "cancelled"):
                    render_output(
                        context.console,
                        status_data,
                        output_format=context.settings.output,
                        title="Jeballtofile Result",
                    )
                    if status != "completed":
                        raise typer.Exit(code=1)
                    return
            time.sleep(3)
    except KeyboardInterrupt:
        pass


@app.command("list")
def list_jeballtofiles(ctx: typer.Context) -> None:
    """List all active and recent Jeballtofile executions."""
    context = require_context(ctx)
    data = context.client.list_jeballtofiles()
    if isinstance(data, dict):
        render_output(
            context.console,
            data.get("executions", []),
            output_format=context.settings.output,
            title="Jeballtofile Executions",
        )
    else:
        render_output(
            context.console,
            data,
            output_format=context.settings.output,
            title="Jeballtofile Executions",
        )


@app.command("ls", hidden=True)
def list_jeballtofiles_alias(ctx: typer.Context) -> None:
    """List Jeballtofile executions (alias for 'list')."""
    list_jeballtofiles(ctx)


@app.command()
def get(
    ctx: typer.Context,
    execution_id: Annotated[str, typer.Argument(help="Execution identifier (UUID).")],
) -> None:
    """Get status and per-step results of a Jeballtofile execution."""
    context = require_context(ctx)
    data = context.client.get_jeballtofile(execution_id)
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="Jeballtofile Status",
    )


@app.command()
def delete(
    ctx: typer.Context,
    execution_id: Annotated[str, typer.Argument(help="Execution identifier (UUID).")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")] = False,
) -> None:
    """Delete a completed, failed, or cancelled Jeballtofile execution.

    Running executions cannot be deleted - cancel them first.
    """
    context = require_context(ctx)
    if not yes:
        typer.confirm(f"Delete Jeballtofile execution {execution_id}?", abort=True)
    data = context.client.delete_jeballtofile(execution_id)
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="Execution Deleted",
    )


@app.command()
def cancel(
    ctx: typer.Context,
    execution_id: Annotated[str, typer.Argument(help="Execution identifier (UUID).")],
) -> None:
    """Cancel a running Jeballtofile execution.

    The current step will finish before execution halts.
    """
    context = require_context(ctx)
    data = context.client.cancel_jeballtofile(execution_id)
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="Cancellation Requested",
    )
