"""Small validation helpers for friendly CLI errors."""

from __future__ import annotations

import typer


def require_int_range(
    value: int | None,
    *,
    name: str,
    minimum: int,
    maximum: int | None = None,
) -> int | None:
    """Validate an optional integer range without cluttering help output."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise typer.BadParameter(f"{name} must be an integer.", param_hint=name)
    if value < minimum:
        raise typer.BadParameter(f"{name} must be {minimum} or greater.", param_hint=name)
    if maximum is not None and value > maximum:
        raise typer.BadParameter(
            f"{name} must be {maximum} or less.",
            param_hint=name,
        )
    return value
