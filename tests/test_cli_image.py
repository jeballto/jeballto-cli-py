"""Tests for image commands."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from jeballto_cli.cli import app
from tests.conftest import IMAGE_OPERATION_ID, IMAGE_RESPONSE

IMAGE_ID = IMAGE_RESPONSE["id"]
REFERENCE = IMAGE_RESPONSE["reference"]


def test_image_list_preserves_machine_envelope(invoke: Any) -> None:
    """JSON output keeps pagination metadata and the image collection."""
    result = invoke(["--output", "json", "image", "list"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["images"][0]["id"] == IMAGE_ID
    assert payload["total"] == 1
    assert result.stderr == ""


def test_image_list_human_output_is_readable(invoke: Any) -> None:
    """Human output prioritizes references and useful image details."""
    result = invoke(["image", "list"])

    assert result.exit_code == 0
    assert REFERENCE in result.stdout
    assert IMAGE_ID in result.stdout


def test_image_list_rejects_invalid_pagination(invoke: Any) -> None:
    """List rejects pagination values outside OpenAPI bounds."""
    assert invoke(["image", "list", "--limit", "0"]).exit_code != 0
    assert invoke(["image", "list", "--offset", "-1"]).exit_code != 0


def test_image_get(invoke: Any) -> None:
    """Get image details by ID."""
    result = invoke(["image", "get", IMAGE_ID])

    assert result.exit_code == 0
    assert REFERENCE in result.stdout
    assert "format" in result.stdout
    assert "resources" in result.stdout


def test_image_get_by_reference(invoke: Any) -> None:
    """Get image details by unique reference."""
    result = invoke(["image", "get", REFERENCE])

    assert result.exit_code == 0
    assert IMAGE_ID in result.stdout


def test_image_reference_not_found_gives_recovery_hint(invoke: Any) -> None:
    """Missing image references explain how to recover on stderr."""
    result = invoke(["image", "get", "registry.example.com/missing:latest"])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "No image with reference" in result.stderr
    assert "pass an ID" in result.stderr


def test_image_delete_confirmed(invoke: Any) -> None:
    """Delete image with --yes."""
    result = invoke(["image", "delete", IMAGE_ID, "--yes"])

    assert result.exit_code == 0
    assert "deleted" in result.stdout.lower()


def test_image_delete_by_reference(invoke: Any) -> None:
    """Delete image with a unique reference."""
    result = invoke(["image", "delete", REFERENCE, "--yes"])

    assert result.exit_code == 0
    assert "deleted" in result.stdout.lower()


def test_image_delete_requires_yes_without_tty(invoke: Any) -> None:
    """Destructive image actions fail safely in non-interactive mode."""
    result = invoke(["image", "delete", IMAGE_ID])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "--yes" in result.stderr


def test_image_wipe_confirmed(invoke: Any) -> None:
    """Wipe all images with --yes."""
    result = invoke(["image", "wipe", "--yes"])

    assert result.exit_code == 0
    assert "Images deleted: 2" in result.stdout


def test_image_wipe_partial_failure_returns_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A partial image wipe prints the result and exits with status one."""
    payload = {"deleted": 1, "failed": 1, "errors": ["image is in use"]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/v1/images"
        return httpx.Response(200, json=payload)

    result = _invoke_with_handler(
        monkeypatch,
        ["--output", "json", "image", "wipe", "--yes"],
        handler,
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == payload


def test_image_pull_waits_by_default(invoke: Any) -> None:
    """Pull watches its background operation and prints the final result."""
    result = invoke(["image", "pull", REFERENCE])

    assert result.exit_code == 0
    assert "completed" in result.stdout.lower()
    assert IMAGE_OPERATION_ID in result.stdout
    assert "Image pull: completed" in result.stderr


def test_image_pull_machine_output_is_clean(invoke: Any) -> None:
    """JSON pull output contains only the final payload on stdout."""
    result = invoke(["--output", "json", "image", "pull", REFERENCE])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operationId"] == IMAGE_OPERATION_ID
    assert payload["status"] == "completed"
    assert result.stderr == ""


def test_image_pull_detach_returns_operation(invoke: Any) -> None:
    """Detached pull returns immediately with a resumable operation ID."""
    result = invoke(["--output", "json", "image", "pull", REFERENCE, "--detach"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["operationId"] == IMAGE_OPERATION_ID
    assert payload["status"] == "started"
    assert result.stderr == ""


def test_image_pull_with_timeouts(invoke: Any) -> None:
    """Pull accepts separate agent and observation timeouts."""
    result = invoke(
        [
            "image",
            "pull",
            REFERENCE,
            "--timeout",
            "3600",
            "--wait-timeout",
            "3630",
        ]
    )

    assert result.exit_code == 0


def test_image_pull_rejects_timeout_above_api_max(invoke: Any) -> None:
    """Pull rejects timeout above the OpenAPI maximum."""
    result = invoke(["image", "pull", REFERENCE, "--timeout", "604801"])

    assert result.exit_code != 0
    assert "604800" in result.stderr


def test_image_pull_old_async_flag_is_removed(invoke: Any) -> None:
    """The old --async flag is replaced by the clearer --detach flag."""
    result = invoke(["image", "pull", REFERENCE, "--async"])

    assert result.exit_code != 0
    assert "--async" in result.stderr


def test_image_push_with_vm_waits_by_default(invoke: Any) -> None:
    """Push from a VM waits for the final operation by default."""
    result = invoke(["image", "push", REFERENCE, "--vm", "test-vm"])

    assert result.exit_code == 0
    assert "completed" in result.stdout.lower()
    assert "push" in result.stdout.lower()


def test_image_push_with_image_reference(invoke: Any) -> None:
    """Push accepts a local image reference as its source."""
    result = invoke(
        [
            "image",
            "push",
            "registry.example.com/image:backup",
            "--image",
            REFERENCE,
        ]
    )

    assert result.exit_code == 0


def test_image_push_detach_returns_operation(invoke: Any) -> None:
    """Detached push returns a started operation."""
    result = invoke(
        [
            "--output",
            "json",
            "image",
            "push",
            REFERENCE,
            "--vm",
            "test-vm",
            "--detach",
        ]
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "push"
    assert payload["status"] == "started"
    assert payload["operationId"] == IMAGE_OPERATION_ID


def test_image_push_rejects_timeout_above_api_max(invoke: Any) -> None:
    """Push rejects timeout above the OpenAPI maximum."""
    result = invoke(
        [
            "image",
            "push",
            REFERENCE,
            "--vm",
            "test-vm",
            "--timeout",
            "604801",
        ]
    )

    assert result.exit_code != 0


def test_image_push_requires_exactly_one_source(invoke: Any) -> None:
    """Push requires one VM or image source, but never both."""
    missing = invoke(["image", "push", REFERENCE])
    both = invoke(
        [
            "image",
            "push",
            REFERENCE,
            "--vm",
            "test-vm",
            "--image",
            REFERENCE,
        ]
    )

    assert missing.exit_code != 0
    assert both.exit_code != 0
    assert "exactly one" in missing.stderr
    assert "exactly one" in both.stderr


def test_image_operation_list(invoke: Any) -> None:
    """List pull and push operations through the operation group."""
    result = invoke(["image", "operation", "list"])

    assert result.exit_code == 0
    assert IMAGE_OPERATION_ID in result.stdout
    assert "pull" in result.stdout
    assert "push" in result.stdout


def test_image_operation_list_filters_type_and_active(invoke: Any) -> None:
    """Operation list supports type and active-only filters."""
    result = invoke(
        ["--output", "json", "image", "operation", "list", "--type", "push", "--active"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["type"] == "push"
    assert payload["activeOnly"] is True
    assert payload["operations"][0]["type"] == "push"


def test_image_operation_list_honors_limit(invoke: Any) -> None:
    """Operation list applies its limit to machine output too."""
    result = invoke(["--output", "json", "image", "operation", "list", "--limit", "1"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload["operations"]) == 1
    assert payload["shown"] == 1


def test_image_operation_list_rejects_invalid_type(invoke: Any) -> None:
    """Operation list rejects unknown operation types."""
    result = invoke(["image", "operation", "list", "--type", "copy"])

    assert result.exit_code != 0


def test_image_operation_get(invoke: Any) -> None:
    """Get a unified image operation."""
    result = invoke(["image", "operation", "get", IMAGE_OPERATION_ID])

    assert result.exit_code == 0
    assert "completed" in result.stdout.lower()
    assert IMAGE_OPERATION_ID in result.stdout


def test_image_operation_get_by_type(invoke: Any) -> None:
    """Get an operation without discovery when its type is known."""
    result = invoke(["image", "operation", "get", IMAGE_OPERATION_ID, "--type", "push"])

    assert result.exit_code == 0
    assert "push" in result.stdout.lower()


def test_image_operation_wait(invoke: Any) -> None:
    """Wait for an existing image operation."""
    result = invoke(["image", "operation", "wait", IMAGE_OPERATION_ID])

    assert result.exit_code == 0
    assert "completed" in result.stdout.lower()


def test_image_operation_cancel(invoke: Any) -> None:
    """Cancel one unified image operation."""
    result = invoke(["image", "operation", "cancel", IMAGE_OPERATION_ID])

    assert result.exit_code == 0
    assert "cancelled" in result.stdout.lower()


def test_image_operation_cancel_all_confirmed(invoke: Any) -> None:
    """Cancel all active image operations."""
    result = invoke(["image", "operation", "cancel", "--all", "--yes"])

    assert result.exit_code == 0
    assert "Cancellation requested" in result.stdout


def test_image_operation_cancel_all_by_type(invoke: Any) -> None:
    """Cancel active image operations by type."""
    result = invoke(["image", "operation", "cancel", "--all", "--type", "pull", "--yes"])

    assert result.exit_code == 0
    assert "Cancellation requested" in result.stdout


def test_image_operation_cancel_validates_target(invoke: Any) -> None:
    """Cancel requires one operation ID or the bulk flag."""
    missing = invoke(["image", "operation", "cancel"])
    conflicting = invoke(["image", "operation", "cancel", IMAGE_OPERATION_ID, "--all", "--yes"])

    assert missing.exit_code != 0
    assert conflicting.exit_code != 0
    assert "operation ID" in missing.stderr
    assert "not both" in conflicting.stderr


def test_image_help_exposes_operation_hierarchy(invoke: Any) -> None:
    """Help presents background transfers as one discoverable command group."""
    image_help = invoke(["image", "--help"])
    operation_help = invoke(["image", "operation", "--help"])

    assert image_help.exit_code == 0
    assert "operation" in image_help.stdout
    assert operation_help.exit_code == 0
    for command in ("list", "get", "wait", "cancel"):
        assert command in operation_help.stdout
    assert "pull-status" not in image_help.stdout
    assert "push-status" not in image_help.stdout


def test_image_leftover_commands_are_removed(invoke: Any) -> None:
    """Old image aliases and flat operation commands are absent."""
    for command in (
        "ls",
        "show",
        "rm",
        "operations",
        "status",
        "cancel",
        "cancel-all",
        "pull-status",
        "push-status",
        "cancel-pull",
        "cancel-push",
    ):
        result = invoke(["image", command])
        assert result.exit_code != 0


def _invoke_with_handler(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    handler: Any,
) -> Any:
    """Invoke the CLI against one local mock handler."""
    monkeypatch.setenv("JEBALLTO_BASE_URL", "http://test:8011/v1")
    monkeypatch.setenv("JEBALLTO_TOKEN", "test-token")
    original_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, **kwargs: Any) -> None:
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)
    return CliRunner().invoke(app, args)
