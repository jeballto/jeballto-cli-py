"""Tests for jeballtofile commands."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from jeballto_cli.cli import app
from tests.conftest import JEBALLTOFILE_RESPONSE

EXECUTION_ID = JEBALLTOFILE_RESPONSE["id"]


def test_jeballtofile_run(invoke: Any) -> None:
    """Run a Jeballtofile execution."""
    result = invoke(
        [
            "--output",
            "json",
            "jeballtofile",
            "run",
            "my-vm",
            "--steps",
            '[{"type":"start"},{"type":"execute","command":"echo hello"}]',
        ]
    )
    assert result.exit_code == 0
    assert EXECUTION_ID in result.output


def test_jeballtofile_run_from_json_file(invoke: Any, tmp_path: Any) -> None:
    """Run execution from a JSON Jeballtofile."""
    file_path = tmp_path / "Jeballtofile.json"
    file_path.write_text(
        (
            '{"name":"json-file-vm","steps":[{"type":"start"},'
            '{"type":"execute","command":"echo hello"}]}'
        ),
        encoding="utf-8",
    )

    result = invoke(["--output", "json", "jeballtofile", "run", "--file", str(file_path)])
    assert result.exit_code == 0
    assert EXECUTION_ID in result.output


def test_jeballtofile_run_from_yaml_file(invoke: Any, tmp_path: Any) -> None:
    """Run execution from a YAML Jeballtofile."""
    file_path = tmp_path / "Jeballtofile.yaml"
    file_path.write_text(
        (
            "name: yaml-file-vm\n"
            "steps:\n"
            "  - type: start\n"
            "  - type: execute\n"
            '    command: "echo hello"\n'
        ),
        encoding="utf-8",
    )

    result = invoke(["--output", "json", "jeballtofile", "run", "--file", str(file_path)])
    assert result.exit_code == 0
    assert EXECUTION_ID in result.output


def test_jeballtofile_json_file_preserves_integer_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Run from JSON file keeps byte resource values as integers."""
    captured: list[dict[str, Any]] = []
    file_path = tmp_path / "Jeballtofile.json"
    file_path.write_text(
        json.dumps(
            {
                "name": "json-file-vm",
                "resources": {"cpuCount": 4, "memorySize": 8589934592, "diskSize": 68719476736},
                "steps": [{"type": "start"}],
            }
        ),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            status_code=202,
            headers={"content-type": "application/json"},
            content=json.dumps(JEBALLTOFILE_RESPONSE).encode(),
        )

    _patch_httpx_client(monkeypatch, handler)
    result = CliRunner().invoke(
        app,
        ["--output", "json", "jeballtofile", "run", "--file", str(file_path)],
    )

    assert result.exit_code == 0
    assert captured[0]["resources"]["memorySize"] == 8589934592
    assert captured[0]["resources"]["diskSize"] == 68719476736


def test_jeballtofile_yaml_file_preserves_integer_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Run from YAML file keeps byte resource values as integers."""
    captured: list[dict[str, Any]] = []
    file_path = tmp_path / "Jeballtofile.yaml"
    file_path.write_text(
        (
            "name: yaml-file-vm\n"
            "resources:\n"
            "  cpuCount: 4\n"
            "  memorySize: 8589934592\n"
            "  diskSize: 68719476736\n"
            "steps:\n"
            "  - type: start\n"
        ),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            status_code=202,
            headers={"content-type": "application/json"},
            content=json.dumps(JEBALLTOFILE_RESPONSE).encode(),
        )

    _patch_httpx_client(monkeypatch, handler)
    result = CliRunner().invoke(
        app,
        ["--output", "json", "jeballtofile", "run", "--file", str(file_path)],
    )

    assert result.exit_code == 0
    assert captured[0]["resources"]["memorySize"] == 8589934592
    assert captured[0]["resources"]["diskSize"] == 68719476736


def test_jeballtofile_run_invalid_steps_json(invoke: Any) -> None:
    """Run fails when --steps JSON is invalid."""
    result = invoke(["jeballtofile", "run", "my-vm", "--steps", "{bad json}"])
    assert result.exit_code != 0


def test_jeballtofile_list(invoke: Any) -> None:
    """List executions."""
    result = invoke(["--output", "json", "jeballtofile", "list"])
    assert result.exit_code == 0
    assert EXECUTION_ID in result.output


def test_jeballtofile_ls_alias(invoke: Any) -> None:
    """The 'ls' alias works."""
    result = invoke(["jeballtofile", "ls"])
    assert result.exit_code == 0


def test_jeballtofile_get(invoke: Any) -> None:
    """Get execution status."""
    result = invoke(["jeballtofile", "get", EXECUTION_ID])
    assert result.exit_code == 0
    assert "completed" in result.output.lower()


def test_jeballtofile_delete_confirmed(invoke: Any) -> None:
    """Delete execution with --yes."""
    result = invoke(["jeballtofile", "delete", EXECUTION_ID, "--yes"])
    assert result.exit_code == 0
    assert "done" in result.output.lower() or "deleted" in result.output.lower()


def test_jeballtofile_delete_abort(invoke: Any) -> None:
    """Delete without --yes can be aborted."""
    result = invoke(["jeballtofile", "delete", EXECUTION_ID], input="n\n")
    assert result.exit_code != 0


def test_jeballtofile_cancel(invoke: Any) -> None:
    """Cancel execution."""
    result = invoke(["jeballtofile", "cancel", EXECUTION_ID])
    assert result.exit_code == 0
    assert "done" in result.output.lower() or "cancellation" in result.output.lower()


def _patch_httpx_client(
    monkeypatch: pytest.MonkeyPatch,
    handler: Any,
) -> None:
    monkeypatch.setenv("JEBALLTO_BASE_URL", "http://test:8011/v1")
    monkeypatch.setenv("JEBALLTO_TOKEN", "test-token")
    orig_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, **kwargs: Any) -> None:
        kwargs["transport"] = httpx.MockTransport(handler)
        orig_init(self, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)
