"""Shared polling for asynchronous agent operations."""

from __future__ import annotations

import time
from collections.abc import Callable, Collection
from typing import Any

from jeballto_cli.errors import CLIError

StatusPayload = dict[str, Any]


def poll_status(
    fetch: Callable[[], object],
    *,
    operation: str,
    terminal_statuses: Collection[str],
    timeout: float | None,
    interval: float = 2.0,
    on_update: Callable[[StatusPayload], None] | None = None,
) -> StatusPayload:
    """Poll a status endpoint until it reaches a terminal state."""
    deadline = time.monotonic() + timeout if timeout is not None else None
    previous_snapshot: tuple[object, ...] | None = None

    while True:
        payload = fetch()
        if not isinstance(payload, dict):
            raise CLIError(
                f"The agent returned an invalid {operation} status response.",
                hint="Rerun with --debug and inspect the agent logs.",
            )

        status = payload.get("status")
        if not isinstance(status, str) or not status:
            raise CLIError(
                f"The agent returned {operation} status without a status field.",
                hint="Rerun with --debug and inspect the agent logs.",
            )

        snapshot = (
            status,
            payload.get("progress"),
            payload.get("stage"),
            payload.get("stageProgress"),
            payload.get("phaseProgress"),
            payload.get("bytesCompleted"),
            payload.get("bytesDownloaded"),
            payload.get("chunksCompleted"),
            payload.get("currentStep"),
            payload.get("totalSteps"),
            payload.get("message"),
        )
        if on_update is not None and snapshot != previous_snapshot:
            on_update(payload)
        previous_snapshot = snapshot

        if status in terminal_statuses:
            return payload
        if deadline is not None and time.monotonic() >= deadline:
            raise CLIError(
                f"Timed out while waiting for {operation} after {timeout:g} seconds.",
                hint="Inspect the current status before deciding what to do next.",
            )
        time.sleep(interval)
