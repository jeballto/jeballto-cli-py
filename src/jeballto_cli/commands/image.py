"""OCI image and background operation commands."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

import typer
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from jeballto_cli._context import CliContext, require_context
from jeballto_cli.client import IMAGE_OPERATION_MAX_TIMEOUT, JSONValue
from jeballto_cli.errors import CLIError
from jeballto_cli.polling import poll_status
from jeballto_cli.presenters.image import (
    render_image,
    render_image_list,
    render_operation,
    render_operation_list,
)
from jeballto_cli.references import resolve_image_id, resolve_vm_id
from jeballto_cli.render import render_output
from jeballto_cli.ui import (
    confirm_action,
    format_bytes,
    format_progress,
    has_failures,
    progress_percent,
)
from jeballto_cli.validation import require_int_range

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")
operation_app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")
app.add_typer(operation_app, name="operation", help="Inspect or cancel background transfers.")

IMAGE_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})


class ImageOperationType(StrEnum):
    """Valid image operation types."""

    pull = "pull"
    push = "push"


@app.command("list")
def list_images(
    ctx: typer.Context,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-l", help="Show at most this many images."),
    ] = None,
    offset: Annotated[
        int | None,
        typer.Option("--offset", help="Skip this many images."),
    ] = None,
) -> None:
    """List local VM images."""
    context = require_context(ctx)
    limit = require_int_range(limit, name="--limit", minimum=1, maximum=1000)
    offset = require_int_range(offset, name="--offset", minimum=0)
    render_image_list(context, context.client.list_images(limit=limit, offset=offset))


@app.command()
def get(
    ctx: typer.Context,
    image: Annotated[str, typer.Argument(help="Image reference or ID.")],
) -> None:
    """Show one local image."""
    context = require_context(ctx)
    image_id = resolve_image_id(context, image)
    render_image(context, context.client.get_image(image_id))


@app.command()
def delete(
    ctx: typer.Context,
    image: Annotated[str, typer.Argument(help="Image reference or ID.")],
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Do not ask for confirmation."),
    ] = False,
) -> None:
    """Delete a local image."""
    context = require_context(ctx)
    image_id = resolve_image_id(context, image)
    confirm_action(context, f"Delete image {image} ({image_id})?", yes=yes)
    context.client.delete_image(image_id)
    result = {"success": True, "imageId": image_id}
    if context.human_output:
        context.console.print("Image deleted.", highlight=False)
    else:
        render_output(context.console, result, output_format=context.settings.output)


@app.command()
def wipe(
    ctx: typer.Context,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Do not ask for confirmation."),
    ] = False,
) -> None:
    """Delete every local image."""
    context = require_context(ctx)
    confirm_action(context, "Delete every local image?", yes=yes)
    result = context.client.wipe_images()
    if context.human_output and isinstance(result, dict):
        context.console.print(f"Images deleted: {result.get('deleted', 0)}", highlight=False)
        if result.get("failed"):
            context.console.print(f"failed: {result['failed']}", highlight=False)
        if result.get("errors"):
            context.console.print(f"errors: {result['errors']}", highlight=False, markup=False)
    else:
        render_output(
            context.console,
            result,
            output_format=context.settings.output,
            title="Image Wipe",
        )
    if has_failures(result):
        raise typer.Exit(code=1)


@app.command()
def pull(
    ctx: typer.Context,
    reference: Annotated[str, typer.Argument(help="Image reference to pull.")],
    timeout: Annotated[
        int | None,
        typer.Option("--timeout", help="Agent-side transfer timeout in seconds."),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option(
            "--wait/--detach",
            help="Watch the transfer, or return its operation ID immediately.",
        ),
    ] = True,
    wait_timeout: Annotated[
        int | None,
        typer.Option(
            "--wait-timeout",
            help="Stop watching after this many seconds. The transfer keeps running.",
        ),
    ] = None,
) -> None:
    """Pull an image from a registry."""
    context = require_context(ctx)
    timeout = _operation_timeout(timeout)
    wait_timeout = _wait_timeout(wait_timeout, operation_timeout=timeout)
    initial = context.client.pull_image(reference, timeout=timeout, async_=True)
    result = (
        _wait_for_image_operation(
            context,
            "pull",
            initial,
            wait_timeout=wait_timeout,
        )
        if wait
        else initial
    )
    render_operation(
        context,
        result,
        title="Image Pull" if wait else "Image Pull Started",
    )
    if wait and _operation_failed(result):
        raise typer.Exit(code=1)


@app.command()
def push(
    ctx: typer.Context,
    reference: Annotated[str, typer.Argument(help="Target image reference.")],
    vm: Annotated[str | None, typer.Option("--vm", help="Source VM name or ID.")] = None,
    image: Annotated[
        str | None,
        typer.Option("--image", help="Source image reference or ID."),
    ] = None,
    timeout: Annotated[
        int | None,
        typer.Option("--timeout", help="Agent-side transfer timeout in seconds."),
    ] = None,
    wait: Annotated[
        bool,
        typer.Option(
            "--wait/--detach",
            help="Watch the transfer, or return its operation ID immediately.",
        ),
    ] = True,
    wait_timeout: Annotated[
        int | None,
        typer.Option(
            "--wait-timeout",
            help="Stop watching after this many seconds. The transfer keeps running.",
        ),
    ] = None,
) -> None:
    """Push a VM or local image to a registry.

    Provide exactly one of --vm or --image as the source.
    """
    if bool(vm) == bool(image):
        raise typer.BadParameter("Provide exactly one of --vm or --image.")

    context = require_context(ctx)
    timeout = _operation_timeout(timeout)
    wait_timeout = _wait_timeout(wait_timeout, operation_timeout=timeout)
    if vm:
        source = f"vm:{resolve_vm_id(context, vm)}"
    else:
        assert image is not None
        source = f"image:{resolve_image_id(context, image)}"

    initial = context.client.push_image(
        reference,
        source=source,
        timeout=timeout,
        async_=True,
    )
    result = (
        _wait_for_image_operation(
            context,
            "push",
            initial,
            wait_timeout=wait_timeout,
        )
        if wait
        else initial
    )
    render_operation(
        context,
        result,
        title="Image Push" if wait else "Image Push Started",
    )
    if wait and _operation_failed(result):
        raise typer.Exit(code=1)


@operation_app.command("list")
def list_operations(
    ctx: typer.Context,
    type_: Annotated[
        ImageOperationType | None,
        typer.Option("--type", help="Show only pull or push operations."),
    ] = None,
    active: Annotated[
        bool,
        typer.Option("--active", help="Show only active operations."),
    ] = False,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Show at most this many operations."),
    ] = 10,
) -> None:
    """List background image operations."""
    context = require_context(ctx)
    limit = require_int_range(limit, name="--limit", minimum=1, maximum=1000) or limit
    operation_type = type_.value if type_ is not None else None
    data = context.client.list_image_operations(type_=operation_type, active_only=active)
    render_operation_list(context, _limit_operations(data, limit))


@operation_app.command("get")
def get_operation(
    ctx: typer.Context,
    operation_id: Annotated[str, typer.Argument(help="Image operation ID.")],
    type_: Annotated[
        ImageOperationType | None,
        typer.Option("--type", help="Skip type discovery with pull or push."),
    ] = None,
) -> None:
    """Show a background image operation."""
    context = require_context(ctx)
    operation_type = type_.value if type_ is not None else None
    render_operation(
        context,
        context.client.image_operation(operation_id, type_=operation_type),
    )


@operation_app.command("wait")
def wait_operation(
    ctx: typer.Context,
    operation_id: Annotated[str, typer.Argument(help="Image operation ID.")],
    type_: Annotated[
        ImageOperationType | None,
        typer.Option("--type", help="Skip type discovery with pull or push."),
    ] = None,
    wait_timeout: Annotated[
        int | None,
        typer.Option("--wait-timeout", help="Stop watching after this many seconds."),
    ] = None,
) -> None:
    """Watch an image operation until it finishes."""
    context = require_context(ctx)
    wait_timeout = _wait_timeout(wait_timeout, operation_timeout=None)
    operation_type = type_.value if type_ is not None else None
    initial = context.client.image_operation(operation_id, type_=operation_type)
    if isinstance(initial, dict):
        operation_type = str(initial.get("type") or operation_type or "pull")
    else:
        operation_type = operation_type or "pull"
    result = _wait_for_image_operation(
        context,
        operation_type,
        initial,
        wait_timeout=wait_timeout,
    )
    render_operation(context, result)
    if _operation_failed(result):
        raise typer.Exit(code=1)


@operation_app.command("cancel")
def cancel_operation(
    ctx: typer.Context,
    operation_id: Annotated[
        str | None,
        typer.Argument(help="Image operation ID."),
    ] = None,
    type_: Annotated[
        ImageOperationType | None,
        typer.Option("--type", help="Use a known pull or push operation type."),
    ] = None,
    all_: Annotated[
        bool,
        typer.Option("--all", help="Cancel all active image operations."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Do not ask for bulk confirmation."),
    ] = False,
) -> None:
    """Cancel one or all background image operations."""
    context = require_context(ctx)
    operation_type = type_.value if type_ is not None else None
    if all_:
        if operation_id is not None:
            raise typer.BadParameter("Use an operation ID or --all, not both.")
        label = f"all active {operation_type} operations" if operation_type else "all operations"
        confirm_action(context, f"Cancel {label}?", yes=yes)
        result = context.client.cancel_image_operations(type_=operation_type)
        if context.human_output and isinstance(result, dict):
            context.console.print(
                f"Cancellation requested for {result.get('cancelled', 0)} operation(s).",
                highlight=False,
            )
            operations = result.get("operations")
            if isinstance(operations, list) and operations:
                render_operation_list(
                    context,
                    {"operations": operations, "total": len(operations), "shown": len(operations)},
                )
        else:
            render_output(
                context.console,
                result,
                output_format=context.settings.output,
                title="Cancellation Result",
            )
        return

    if operation_id is None:
        raise typer.BadParameter("Pass an operation ID, or use --all.")
    result = context.client.cancel_image_operation(operation_id, type_=operation_type)
    render_operation(context, result, title="Cancellation Result")


def _operation_timeout(value: int | None) -> int | None:
    return require_int_range(
        value,
        name="--timeout",
        minimum=1,
        maximum=IMAGE_OPERATION_MAX_TIMEOUT,
    )


def _wait_timeout(value: int | None, *, operation_timeout: int | None) -> int | None:
    validated = require_int_range(
        value,
        name="--wait-timeout",
        minimum=1,
        maximum=IMAGE_OPERATION_MAX_TIMEOUT,
    )
    if validated is not None:
        return validated
    return operation_timeout + 30 if operation_timeout is not None else None


def _wait_for_image_operation(
    context: CliContext,
    operation_type: str,
    initial: JSONValue,
    *,
    wait_timeout: int | None,
) -> dict[str, Any]:
    if not isinstance(initial, dict) or not initial.get("operationId"):
        raise CLIError(
            "The agent did not return an image operation ID.",
            hint="Rerun with --debug and inspect the agent logs.",
        )
    operation_id = str(initial["operationId"])

    with Progress(
        TextColumn("{task.description}", markup=False),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=context.error_console,
        disable=not context.progress_enabled,
    ) as progress:
        task = progress.add_task(f"Image {operation_type}", total=100)

        def on_update(payload: dict[str, Any]) -> None:
            status = str(payload.get("status") or "running")
            stage = payload.get("stage")
            description = f"Image {operation_type}: {stage or status}"
            raw_progress = payload.get("progress")
            completed = progress_percent(raw_progress) or 0.0
            if context.progress_enabled:
                progress.update(task, completed=completed, description=description)
            elif context.is_human:
                progress_text = format_progress(raw_progress)
                bytes_completed = format_bytes(payload.get("bytesCompleted"))
                bytes_total = format_bytes(payload.get("bytesTotal"))
                transfer_text = None
                if bytes_completed or bytes_total:
                    transfer_text = f"{bytes_completed or '0 B'} / {bytes_total or 'unknown'}"
                context.error_console.print(
                    " ".join(part for part in (description, progress_text, transfer_text) if part),
                    highlight=False,
                    markup=False,
                )

        try:
            return poll_status(
                lambda: context.client.image_operation(operation_id, type_=operation_type),
                operation=f"image {operation_type} {operation_id}",
                terminal_statuses=IMAGE_TERMINAL_STATES,
                timeout=wait_timeout,
                interval=3.0,
                on_update=on_update if context.is_human else None,
            )
        except KeyboardInterrupt:
            context.error_console.print(
                f"Transfer is still running. Resume with: jeballto image operation wait "
                f"{operation_id} --type {operation_type}",
                highlight=False,
            )
            raise typer.Exit(code=130) from None


def _operation_failed(payload: object) -> bool:
    return isinstance(payload, dict) and payload.get("status") in {"failed", "cancelled"}


def _limit_operations(payload: object, limit: int) -> object:
    if not isinstance(payload, dict):
        return payload
    operations = payload.get("operations")
    if not isinstance(operations, list):
        return payload
    limited = dict(payload)
    limited["operations"] = operations[:limit]
    limited["shown"] = min(limit, len(operations))
    limited["total"] = payload.get("total", len(operations))
    return limited
