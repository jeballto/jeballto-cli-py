"""Tests for system commands."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from jeballto_cli.cli import app


def test_system_reset_soft_yes(invoke: Any) -> None:
    """Soft reset succeeds with --yes."""
    result = invoke(["system", "reset", "soft", "--yes"])
    assert result.exit_code == 0
    assert "soft" in result.stdout.lower()
    assert "config deleted: no" in result.stdout
    assert "logs deleted: no" in result.stdout


def test_system_reset_hard_yes(invoke: Any) -> None:
    """Hard reset succeeds with --yes."""
    result = invoke(["system", "reset", "hard", "--yes"])
    assert result.exit_code == 0
    assert "hard" in result.stdout.lower()
    assert "config deleted: yes" in result.stdout
    assert "logs deleted: yes" in result.stdout
    assert "agent will terminate: yes" in result.stdout


def test_system_reset_requires_yes_without_tty(invoke: Any) -> None:
    """Reset without --yes fails safely in non-interactive mode."""
    result = invoke(["system", "reset", "soft"])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "--yes" in result.stderr


def test_system_reset_invalid_mode(invoke: Any) -> None:
    """Invalid mode fails validation."""
    result = invoke(["system", "reset", "invalid", "--yes"])
    assert result.exit_code != 0


def test_system_hard_reset_partial_http_500_returns_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial hard reset body remains visible and produces exit status one."""
    payload = {
        "mode": "hard",
        "vmsDeleted": 1,
        "vmsFailed": 1,
        "imagesDeleted": 1,
        "imagesFailed": 0,
        "ipswCacheCleared": True,
        "configDeleted": False,
        "logsDeleted": False,
        "willTerminate": False,
        "errors": ["one VM could not be deleted"],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/system/reset"
        return httpx.Response(500, json=payload)

    result = _invoke_with_handler(
        monkeypatch,
        ["--output", "json", "system", "reset", "hard", "--yes"],
        handler,
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == payload
    assert result.stderr == ""


def test_system_capabilities(invoke: Any) -> None:
    """Get system capabilities."""
    result = invoke(["system", "capabilities"])
    assert result.exit_code == 0
    assert "macOSVirtualization" in result.stdout
    assert "ociImagePackaging" in result.stdout


def test_system_capabilities_json_is_clean(invoke: Any) -> None:
    """Capabilities preserve the host and feature payload for automation."""
    result = invoke(["--output", "json", "system", "capabilities"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["host"]["virtualizationSupported"] is True
    assert payload["features"][0]["minimumOS"]
    assert result.stderr == ""


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
