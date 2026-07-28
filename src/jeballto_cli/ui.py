"""Shared human-output formatting and interaction helpers."""

from __future__ import annotations

import math
import sys
from collections.abc import Iterable

import typer

from jeballto_cli._context import CliContext


def format_bytes(value: object) -> str | None:
    """Format a byte count with compact IEC units."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    unit = units[0]
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            break
        amount /= 1024
    if unit == "B":
        return f"{int(amount)} {unit}"
    precision = 0 if amount.is_integer() else 1
    return f"{amount:.{precision}f} {unit}"


def format_duration(value: object) -> str | None:
    """Format seconds as at most two readable units."""
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        return None
    remaining = int(value)
    parts: list[str] = []
    for seconds, suffix in ((86400, "d"), (3600, "h"), (60, "m"), (1, "s")):
        amount, remaining = divmod(remaining, seconds)
        if amount or (suffix == "s" and not parts):
            parts.append(f"{amount}{suffix}")
        if len(parts) == 2:
            break
    return " ".join(parts)


def progress_percent(value: object) -> float | None:
    """Convert an API progress value to a finite percentage."""
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return None
    percent = float(value * 100 if 0 <= value <= 1 else value)
    return percent if 0 <= percent <= 100 else None


def format_progress(value: object) -> str | None:
    """Format an API progress fraction as a percentage."""
    percent = progress_percent(value)
    if percent is None:
        return None
    return f"{percent:.0f}%"


def yes_no(value: object) -> str:
    """Format a tri-state boolean without relying on color."""
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def status_style(status: str) -> str:
    """Return a consistent Rich style for a textual status."""
    normalized = status.casefold()
    if normalized in {
        "available",
        "completed",
        "healthy",
        "ok",
        "open",
        "ready",
        "running",
        "success",
    }:
        return "green"
    if normalized in {
        "cancelled",
        "error",
        "failed",
        "interrupted",
        "unavailable",
    }:
        return "red"
    if normalized in {
        "cancelling",
        "finalizing",
        "installing",
        "pausing",
        "resuming",
        "started",
        "starting",
        "stopping",
    }:
        return "yellow"
    return "white"


def confirm_action(context: CliContext, prompt: str, *, yes: bool) -> None:
    """Confirm a destructive action without polluting stdout."""
    if yes:
        return
    if context.settings.no_input or not sys.stdin.isatty():
        raise typer.BadParameter(
            "Confirmation is required. Rerun with --yes in non-interactive mode.",
            param_hint="--yes",
        )
    typer.confirm(prompt, abort=True, err=True)


def has_failures(
    payload: object,
    *,
    count_fields: Iterable[str] = ("failed",),
) -> bool:
    """Return whether a bulk operation reports any partial failures."""
    if not isinstance(payload, dict):
        return False
    if any(
        isinstance(payload.get(field), int)
        and not isinstance(payload[field], bool)
        and payload[field] > 0
        for field in count_fields
    ):
        return True
    errors = payload.get("errors")
    return isinstance(errors, list) and bool(errors)
