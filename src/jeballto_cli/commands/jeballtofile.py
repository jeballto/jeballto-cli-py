"""Jeballtofile blueprint execution commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from jeballto_cli._context import CliContext, require_context
from jeballto_cli.client import ResourceSize
from jeballto_cli.errors import CLIError
from jeballto_cli.polling import poll_status
from jeballto_cli.render import render_output
from jeballto_cli.ui import confirm_action, status_style
from jeballto_cli.validation import require_int_range

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")

EXECUTION_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})
DEFAULT_EXECUTION_WAIT_TIMEOUT = 9_000


@app.command("submit")
def submit(
    ctx: typer.Context,
    name: Annotated[
        str | None,
        typer.Argument(help="VM name. Optional when the file contains name."),
    ] = None,
    steps: Annotated[
        str | None,
        typer.Option("--steps", "-s", help="Inline steps as a JSON array."),
    ] = None,
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            "-f",
            exists=True,
            dir_okay=False,
            readable=True,
            help="Jeballtofile in JSON or YAML format.",
        ),
    ] = None,
    source: Annotated[
        str | None,
        typer.Option("--source", help="IPSW path or HTTPS URL for an install step."),
    ] = None,
    cpu: Annotated[int | None, typer.Option("--cpu", help="CPU cores for the VM.")] = None,
    memory: Annotated[
        str | None,
        typer.Option("--memory", help="Memory for the VM, such as 8GB."),
    ] = None,
    disk: Annotated[
        str | None,
        typer.Option("--disk", help="Disk size, such as 64GB."),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option(
            "--wait/--detach",
            help="Watch the run, or return its execution ID immediately.",
        ),
    ] = True,
    wait_timeout: Annotated[
        int,
        typer.Option(
            "--wait-timeout",
            help="Stop watching after this many seconds. The run keeps going.",
        ),
    ] = DEFAULT_EXECUTION_WAIT_TIMEOUT,
) -> None:
    """Submit a Jeballtofile blueprint."""
    context = require_context(ctx)
    wait_timeout = _validated_wait_timeout(wait_timeout)
    resolved_name, parsed_steps, resolved_source, resources = _load_blueprint(
        name=name,
        steps=steps,
        file=file,
        source=source,
        cpu=cpu,
        memory=memory,
        disk=disk,
    )
    initial = context.client.create_jeballtofile(
        resolved_name,
        parsed_steps,
        source=resolved_source,
        cpu=resources.get("cpu"),
        memory=resources.get("memory"),
        disk=resources.get("disk"),
    )
    if not wait:
        _render_execution(context, initial, title="Run Submitted")
        return

    execution_id = _execution_id(initial)
    result = _wait_for_execution(
        context,
        execution_id,
        wait_timeout=wait_timeout,
    )
    _render_execution(context, result, title="Run Result")
    if result.get("status") != "completed":
        raise typer.Exit(code=1)


@app.command("list")
def list_runs(ctx: typer.Context) -> None:
    """List recent Jeballtofile runs."""
    context = require_context(ctx)
    data = context.client.list_jeballtofiles()
    if context.human_output and isinstance(data, dict):
        executions = data.get("executions")
        _print_execution_list(context, executions if isinstance(executions, list) else [])
        return
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="Jeballtofile Runs",
    )


@app.command()
def get(
    ctx: typer.Context,
    execution_id: Annotated[str, typer.Argument(help="Run ID from submit.")],
) -> None:
    """Show one Jeballtofile run."""
    context = require_context(ctx)
    _render_execution(
        context,
        context.client.get_jeballtofile(execution_id),
        title="Jeballtofile Run",
    )


@app.command()
def wait(
    ctx: typer.Context,
    execution_id: Annotated[str, typer.Argument(help="Run ID from submit.")],
    wait_timeout: Annotated[
        int,
        typer.Option("--wait-timeout", help="Stop watching after this many seconds."),
    ] = DEFAULT_EXECUTION_WAIT_TIMEOUT,
) -> None:
    """Watch a Jeballtofile run until it finishes."""
    context = require_context(ctx)
    result = _wait_for_execution(
        context,
        execution_id,
        wait_timeout=_validated_wait_timeout(wait_timeout),
    )
    _render_execution(context, result, title="Run Result")
    if result.get("status") != "completed":
        raise typer.Exit(code=1)


@app.command()
def cancel(
    ctx: typer.Context,
    execution_id: Annotated[str, typer.Argument(help="Run ID from submit.")],
    wait: Annotated[
        bool,
        typer.Option(
            "--wait/--detach",
            help="Wait for cancellation, or return after requesting it.",
        ),
    ] = True,
    wait_timeout: Annotated[
        int,
        typer.Option("--wait-timeout", help="Stop watching after this many seconds."),
    ] = 300,
) -> None:
    """Request cooperative cancellation of a run and its active step."""
    context = require_context(ctx)
    response = context.client.cancel_jeballtofile(execution_id)
    if not wait:
        render_output(
            context.console,
            response,
            output_format=context.settings.output,
            title="Cancellation Requested",
        )
        return

    result = _wait_for_execution(
        context,
        execution_id,
        wait_timeout=_validated_wait_timeout(wait_timeout),
    )
    _render_execution(context, result, title="Cancellation Result")
    if result.get("status") == "failed":
        raise typer.Exit(code=1)


@app.command()
def delete(
    ctx: typer.Context,
    execution_id: Annotated[str, typer.Argument(help="Finished run ID.")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Do not ask for confirmation."),
    ] = False,
) -> None:
    """Delete a completed, failed, or cancelled run record."""
    context = require_context(ctx)
    confirm_action(context, f"Delete Jeballtofile run {execution_id}?", yes=yes)
    result = context.client.delete_jeballtofile(execution_id)
    if context.human_output and isinstance(result, dict):
        context.console.print(
            result.get("message") or "Run deleted.",
            highlight=False,
            markup=False,
        )
    else:
        render_output(
            context.console,
            result,
            output_format=context.settings.output,
            title="Run Deleted",
        )


def _load_blueprint(
    *,
    name: str | None,
    steps: str | None,
    file: Path | None,
    source: str | None,
    cpu: int | None,
    memory: ResourceSize | None,
    disk: ResourceSize | None,
) -> tuple[str, list[dict[str, Any]], str | None, dict[str, Any]]:
    if (steps is None) == (file is None):
        raise typer.BadParameter("Provide exactly one of --steps or --file.")

    payload: object
    if file is not None:
        raw = file.read_text(encoding="utf-8")
        try:
            payload = json.loads(raw) if file.suffix.casefold() == ".json" else yaml.safe_load(raw)
        except (json.JSONDecodeError, yaml.YAMLError) as exc:
            raise typer.BadParameter(f"Invalid Jeballtofile: {exc}", param_hint="--file") from exc
    else:
        assert steps is not None
        try:
            payload = json.loads(steps)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"Invalid steps JSON: {exc}", param_hint="--steps") from exc

    resolved_name = name
    resolved_source = source
    resources: dict[str, Any] = {"cpu": cpu, "memory": memory, "disk": disk}
    raw_steps: object
    if isinstance(payload, list):
        raw_steps = payload
    elif isinstance(payload, dict):
        raw_steps = payload.get("steps")
        if resolved_name is None and isinstance(payload.get("name"), str):
            resolved_name = payload["name"]
        if resolved_source is None and isinstance(payload.get("source"), str):
            resolved_source = payload["source"]
        file_resources = payload.get("resources")
        if isinstance(file_resources, dict):
            for cli_key, api_key in (
                ("cpu", "cpuCount"),
                ("memory", "memorySize"),
                ("disk", "diskSize"),
            ):
                if resources[cli_key] is None and isinstance(
                    file_resources.get(api_key),
                    (int, str),
                ):
                    resources[cli_key] = file_resources[api_key]
    else:
        raise typer.BadParameter("A Jeballtofile must be a JSON or YAML object.")

    if not isinstance(raw_steps, list) or not raw_steps:
        raise typer.BadParameter("A Jeballtofile must contain a non-empty steps array.")
    if len(raw_steps) > 1000:
        raise typer.BadParameter("A Jeballtofile can contain at most 1000 steps.")
    if not all(isinstance(step, dict) for step in raw_steps):
        raise typer.BadParameter("Every Jeballtofile step must be an object.")
    if not resolved_name:
        raise typer.BadParameter("Provide a VM name as an argument or in the file.")

    resources["cpu"] = require_int_range(
        resources.get("cpu"),
        name="--cpu",
        minimum=1,
        maximum=32,
    )
    return resolved_name, raw_steps, resolved_source, resources


def _execution_id(payload: object) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("id"), str):
        return payload["id"]
    raise CLIError(
        "The agent did not return a Jeballtofile run ID.",
        hint="Rerun with --debug and inspect the agent logs.",
    )


def _validated_wait_timeout(value: int) -> int:
    return require_int_range(value, name="--wait-timeout", minimum=1, maximum=604800) or value


def _wait_for_execution(
    context: CliContext,
    execution_id: str,
    *,
    wait_timeout: int,
) -> dict[str, Any]:
    with Progress(
        TextColumn("{task.description}", markup=False),
        BarColumn(),
        TextColumn("{task.completed:.0f}/{task.total:.0f}"),
        TimeElapsedColumn(),
        console=context.error_console,
        disable=not context.progress_enabled,
    ) as progress:
        task = progress.add_task("Jeballtofile", total=1)

        def on_update(payload: dict[str, Any]) -> None:
            status = str(payload.get("status") or "running")
            total = _integer(payload.get("totalSteps"), default=1)
            current = _display_step(payload.get("currentStep"), total, status)
            description = f"Jeballtofile: {status}"
            if context.progress_enabled:
                progress.update(task, total=total, completed=current, description=description)
            elif context.is_human:
                context.error_console.print(
                    f"{description} ({current}/{total})",
                    highlight=False,
                )

        try:
            return poll_status(
                lambda: context.client.get_jeballtofile(execution_id),
                operation=f"Jeballtofile run {execution_id}",
                terminal_statuses=EXECUTION_TERMINAL_STATES,
                timeout=wait_timeout,
                interval=3.0,
                on_update=on_update if context.is_human else None,
            )
        except KeyboardInterrupt:
            context.error_console.print(
                f"Run is still active. Resume with: jeballto run wait {execution_id}",
                highlight=False,
            )
            raise typer.Exit(code=130) from None


def _render_execution(context: CliContext, payload: object, *, title: str) -> None:
    if not context.human_output or not isinstance(payload, dict):
        render_output(
            context.console,
            payload,
            output_format=context.settings.output,
            title=title,
        )
        return

    status = str(payload.get("status") or "unknown")
    total = _integer(payload.get("totalSteps"), default=0)
    current = _display_step(payload.get("currentStep"), total, status)
    step_text = f" ({current}/{total})" if total else ""
    context.console.print(
        f"{title}: [{status_style(status)}]{status}[/]{step_text}",
        highlight=False,
    )
    for key, label in (("id", "run"), ("vmId", "vm"), ("message", "message"), ("error", "error")):
        value = payload.get(key)
        if value:
            context.console.print(f"{label}: {value}", highlight=False, markup=False)

    results = payload.get("stepResults")
    if isinstance(results, list) and results:
        context.console.print("steps:", highlight=False)
        for result in results:
            if not isinstance(result, dict):
                continue
            index = _integer(result.get("step"), default=0) + 1
            step_type = result.get("type") or "step"
            step_status = result.get("status") or "unknown"
            message = result.get("message")
            suffix = f": {message}" if message else ""
            context.console.print(
                f"  {index}. {step_type}: {step_status}{suffix}",
                highlight=False,
                markup=False,
            )


def _print_execution_list(context: CliContext, executions: list[object]) -> None:
    if not executions:
        context.console.print("No Jeballtofile runs found.", highlight=False)
        return
    context.console.print("[bold]Jeballtofile Runs[/]")
    for index, execution in enumerate(executions, start=1):
        if not isinstance(execution, dict):
            continue
        status = str(execution.get("status") or "unknown")
        total = _integer(execution.get("totalSteps"), default=0)
        current = _display_step(execution.get("currentStep"), total, status)
        context.console.print(
            f"{index}. [{status_style(status)}]{status}[/] ({current}/{total})",
            highlight=False,
        )
        context.console.print(f"   run: {execution.get('id') or ''}", highlight=False)
        if execution.get("vmId"):
            context.console.print(f"   vm: {execution['vmId']}", highlight=False)


def _display_step(current: object, total: int, status: str) -> int:
    if status == "completed":
        return total
    value = _integer(current, default=0)
    return min(value + 1, total) if total else value + 1


def _integer(value: object, *, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default
