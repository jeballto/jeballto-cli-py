"""Shared CLI context object passed through Typer's context chain."""

from __future__ import annotations

from dataclasses import dataclass, field

import typer
from rich.console import Console

from jeballto_cli.client import JeballtoClient
from jeballto_cli.settings import Settings


@dataclass
class CliContext:
    """Holds resolved settings, a Rich console, and a lazy API client.

    Attributes:
        settings: Resolved application settings.
        console: Rich console used for all output.
    """

    settings: Settings
    console: Console
    _client: JeballtoClient | None = field(default=None, repr=False)

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
