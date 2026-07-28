"""Shared CLI context object passed through Typer's context chain."""

from __future__ import annotations

from dataclasses import dataclass, field

import typer
from rich.console import Console

from jeballto_cli.client import JeballtoClient
from jeballto_cli.settings import OutputFormat, Settings


@dataclass
class CliContext:
    """Holds resolved settings, a Rich console, and a lazy API client.

    Attributes:
        settings: Resolved application settings.
        console: Rich console used for command results on stdout.
        error_console: Rich console used for progress and diagnostics on stderr.
    """

    settings: Settings
    console: Console
    error_console: Console
    _client: JeballtoClient | None = field(default=None, repr=False)

    @property
    def is_human(self) -> bool:
        """Return whether output is intended for a person."""
        return self.settings.output == OutputFormat.HUMAN

    @property
    def human_output(self) -> bool:
        """Return whether concise human-readable output is active."""
        return self.is_human and not self.settings.details

    @property
    def progress_enabled(self) -> bool:
        """Return whether animated progress is safe and useful."""
        return self.is_human and self.error_console.is_terminal

    @property
    def client(self) -> JeballtoClient:
        """Return the API client, creating it on first access."""
        if self._client is None:
            self._client = JeballtoClient(self.settings)
        return self._client

    def close(self) -> None:
        """Close the underlying HTTP client if it was created."""
        if self._client is not None:
            self._client.close()
            self._client = None


def require_context(ctx: typer.Context) -> CliContext:
    """Extract the ``CliContext`` from a Typer context.

    Args:
        ctx: The current Typer invocation context.

    Returns:
        The ``CliContext`` attached by the root callback.

    Raises:
        typer.Exit: If the context object is missing.
    """
    obj = ctx.find_object(CliContext)
    if obj is None:
        raise typer.Exit(code=1)
    return obj
