"""Human and structured presenters for OCI images and operations."""

from __future__ import annotations

from typing import Any

from jeballto_cli._context import CliContext
from jeballto_cli.render import render_output
from jeballto_cli.ui import format_bytes, format_progress, status_style


def render_image_list(context: CliContext, payload: object) -> None:
    """Render a paginated image response."""
    if not context.human_output or not isinstance(payload, dict):
        render_output(
            context.console,
            payload,
            output_format=context.settings.output,
            title="Images",
        )
        return

    images = payload.get("images")
    if not isinstance(images, list) or not images:
        context.console.print("No local images found.", highlight=False)
        return

    context.console.print("[bold]Images[/]")
    for index, image in enumerate(images, start=1):
        if not isinstance(image, dict):
            continue
        reference = image.get("reference") or "(unknown reference)"
        image_id = image.get("id") or ""
        size = format_bytes(image.get("size"))
        format_version = image.get("formatVersion")
        context.console.print(f"{index}. {reference}", highlight=False)
        details = [str(image_id)] if image_id else []
        if size:
            details.append(size)
        if format_version:
            details.append(f"format v{format_version}")
        if details:
            context.console.print(f"   {', '.join(details)}", highlight=False)
        timestamp = image.get("pulledAt") or image.get("pushedAt")
        if timestamp:
            context.console.print(f"   stored: {timestamp}", highlight=False)

    _print_page_summary(context, payload, len(images))


def render_image(context: CliContext, payload: object, *, title: str = "Image") -> None:
    """Render one local image."""
    if not context.human_output or not isinstance(payload, dict):
        render_output(
            context.console,
            payload,
            output_format=context.settings.output,
            title=title,
        )
        return

    context.console.print(f"[bold]{title}[/]")
    for label, value in (
        ("reference", payload.get("reference")),
        ("id", payload.get("id")),
        ("digest", payload.get("digest")),
        ("size", format_bytes(payload.get("size"))),
        ("format", _format_version(payload.get("formatVersion"))),
        ("resources", _format_resources(payload.get("resources"))),
        ("pulled", payload.get("pulledAt")),
        ("pushed", payload.get("pushedAt")),
    ):
        if value not in (None, ""):
            context.console.print(f"{label}: {value}", highlight=False, markup=False)


def render_operation(
    context: CliContext,
    payload: object,
    *,
    title: str = "Image Operation",
) -> None:
    """Render one image operation."""
    if not context.human_output or not isinstance(payload, dict):
        render_output(
            context.console,
            payload,
            output_format=context.settings.output,
            title=title,
        )
        return

    status = str(payload.get("status") or "unknown")
    operation_type = payload.get("type") or "image"
    progress = format_progress(payload.get("progress"))
    line = f"{title}: {operation_type} [{status_style(status)}]{status}[/]"
    if progress:
        line = f"{line} ({progress})"
    result = _operation_result(payload)
    if result and result != status:
        line = f"{line}, {result}"
    context.console.print(line, highlight=False)

    for label, value in (
        ("reference", payload.get("reference")),
        ("operation", payload.get("operationId")),
        ("source", payload.get("source")),
        ("stage", payload.get("stage")),
        ("stage progress", format_progress(payload.get("stageProgress"))),
        ("speed", _format_speed(payload.get("averageSpeedMBps"))),
        ("bytes", _format_counter(payload, "bytesCompleted", "bytesTotal", bytes_=True)),
        ("chunks", _format_counter(payload, "chunksCompleted", "chunksTotal")),
        ("digest", payload.get("digest")),
        ("error code", payload.get("errorCode")),
        ("error", payload.get("error")),
        ("started", payload.get("startedAt")),
        ("updated", payload.get("updatedAt")),
        ("completed", payload.get("completedAt")),
    ):
        if value not in (None, ""):
            context.console.print(f"{label}: {value}", highlight=False, markup=False)

    image = payload.get("image")
    if isinstance(image, dict) and image.get("id"):
        size = format_bytes(image.get("size"))
        suffix = f" ({size})" if size else ""
        context.console.print(f"image: {image['id']}{suffix}", highlight=False)


def render_operation_list(context: CliContext, payload: object) -> None:
    """Render a list of image operations."""
    if not context.human_output or not isinstance(payload, dict):
        render_output(
            context.console,
            payload,
            output_format=context.settings.output,
            title="Image Operations",
        )
        return

    operations = payload.get("operations")
    if not isinstance(operations, list) or not operations:
        active_only = payload.get("activeOnly") is True
        message = "No active image operations." if active_only else "No image operations found."
        context.console.print(message, highlight=False)
        return

    context.console.print("[bold]Image Operations[/]")
    for index, operation in enumerate(operations, start=1):
        if not isinstance(operation, dict):
            continue
        status = str(operation.get("status") or "unknown")
        operation_type = operation.get("type") or "image"
        progress = format_progress(operation.get("progress"))
        suffix = f" {progress}" if progress else ""
        context.console.print(
            f"{index}. [{status_style(status)}]{status}[/] {operation_type}{suffix}",
            highlight=False,
        )
        context.console.print(
            f"   reference: {operation.get('reference') or ''}",
            highlight=False,
        )
        context.console.print(
            f"   operation: {operation.get('operationId') or ''}",
            highlight=False,
        )
        timestamp = operation.get("completedAt") or operation.get("updatedAt")
        if timestamp:
            context.console.print(f"   updated: {timestamp}", highlight=False)

    shown = payload.get("shown")
    total = payload.get("total")
    if isinstance(shown, int) and isinstance(total, int) and shown < total:
        context.console.print(f"Showing {shown} of {total}. Use --limit {total}.", highlight=False)


def _print_page_summary(context: CliContext, payload: dict[str, Any], shown: int) -> None:
    total = payload.get("total")
    offset = payload.get("offset")
    if isinstance(total, int) and isinstance(offset, int) and offset + shown < total:
        context.console.print(
            f"Showing {offset + 1}-{offset + shown} of {total}. Use --offset {offset + shown}.",
            highlight=False,
        )


def _format_version(value: object) -> str | None:
    if isinstance(value, int):
        return f"v{value}"
    return None


def _format_resources(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    parts = []
    cpu = value.get("cpuCount")
    if cpu:
        parts.append(f"{cpu} CPU")
    memory = format_bytes(value.get("memorySize"))
    if memory:
        parts.append(f"{memory} memory")
    disk = format_bytes(value.get("diskSize"))
    if disk:
        parts.append(f"{disk} disk")
    return ", ".join(parts) or None


def _format_speed(value: object) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:g} MB/s"
    return None


def _format_counter(
    payload: dict[str, Any],
    completed_key: str,
    total_key: str,
    *,
    bytes_: bool = False,
) -> str | None:
    completed = payload.get(completed_key)
    total = payload.get(total_key)
    if completed is None and total is None:
        return None
    if bytes_:
        completed_text = format_bytes(completed) or "0 B"
        total_text = format_bytes(total) or "unknown"
    else:
        completed_text = str(completed or 0)
        total_text = str(total) if total is not None else "unknown"
    return f"{completed_text} / {total_text}"


def _operation_result(payload: dict[str, Any]) -> str | None:
    if payload.get("status") != "completed":
        return None
    image = payload.get("image")
    if (
        payload.get("type") == "pull"
        and isinstance(image, dict)
        and payload.get("bytesCompleted") == 0
        and payload.get("chunksCompleted") == 0
    ):
        return "already local"
    return "completed"
