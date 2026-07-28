"""Tests for Jeballtofile run commands."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from jeballto_cli.cli import app
from tests.conftest import JEBALLTOFILE_RESPONSE

EXECUTION_ID = JEBALLTOFILE_RESPONSE["id"]
STEPS = '[{"type":"start"},{"type":"execute","command":"echo hello"}]'


def test_run_submit_waits_by_default(invoke: Any) -> None:
    """Submit watches the run and prints its terminal payload by default."""
    result = invoke(["--output", "json", "run", "submit", "my-vm", "--steps", STEPS])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == EXECUTION_ID
    assert payload["status"] == "completed"
    assert result.stderr == ""


def test_run_submit_human_progress_uses_stderr(invoke: Any) -> None:
    """Human progress stays on stderr while the final result uses stdout."""
    result = invoke(["run", "submit", "my-vm", "--steps", STEPS])

    assert result.exit_code == 0
    assert "Run Result" in result.stdout
    assert "completed" in result.stdout
    assert "Jeballtofile: completed" in result.stderr


def test_run_submit_detach_returns_execution_id(invoke: Any) -> None:
    """Detached submission returns the active run without polling."""
    result = invoke(["--output", "json", "run", "submit", "my-vm", "--steps", STEPS, "--detach"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["id"] == EXECUTION_ID
    assert payload["status"] == "running"
    assert result.stderr == ""


def test_run_submit_from_json_file(invoke: Any, tmp_path: Any) -> None:
    """Submit a JSON Jeballtofile."""
    file_path = tmp_path / "Jeballtofile.json"
    file_path.write_text(
        '{"name":"json-file-vm","steps":' + STEPS + "}",
        encoding="utf-8",
    )

    result = invoke(["--output", "json", "run", "submit", "--file", str(file_path)])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "completed"


def test_run_submit_from_yaml_file(invoke: Any, tmp_path: Any) -> None:
    """Submit a YAML Jeballtofile."""
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

    result = invoke(["--output", "json", "run", "submit", "--file", str(file_path)])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "completed"


@pytest.mark.parametrize("suffix", ["json", "yaml"])
def test_run_file_preserves_integer_resources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
    suffix: str,
) -> None:
    """File resource sizes remain integer byte counts in the API request."""
    captured: list[dict[str, Any]] = []
    file_path = tmp_path / f"Jeballtofile.{suffix}"
    if suffix == "json":
        file_path.write_text(
            json.dumps(
                {
                    "name": "file-vm",
                    "resources": {
                        "cpuCount": 4,
                        "memorySize": 8589934592,
                        "diskSize": 68719476736,
                    },
                    "steps": [{"type": "start"}],
                }
            ),
            encoding="utf-8",
        )
    else:
        file_path.write_text(
            (
                "name: file-vm\n"
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
        return httpx.Response(202, json=JEBALLTOFILE_RESPONSE)

    result = _invoke_with_handler(
        monkeypatch,
        ["--output", "json", "run", "submit", "--file", str(file_path), "--detach"],
        handler,
    )

    assert result.exit_code == 0
    assert captured[0]["resources"] == {
        "cpuCount": 4,
        "memorySize": 8589934592,
        "diskSize": 68719476736,
    }


def test_run_submit_rejects_invalid_steps_json(invoke: Any) -> None:
    """Submit fails when --steps JSON is invalid."""
    result = invoke(["run", "submit", "my-vm", "--steps", "{bad json}"])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "Invalid steps JSON" in result.stderr


def test_run_submit_requires_one_blueprint_source(invoke: Any, tmp_path: Any) -> None:
    """Submit requires exactly one of inline steps and a file."""
    file_path = tmp_path / "Jeballtofile.json"
    file_path.write_text('{"name":"vm","steps":[{"type":"start"}]}', encoding="utf-8")

    missing = invoke(["run", "submit", "my-vm"])
    both = invoke(
        ["run", "submit", "my-vm", "--steps", '[{"type":"start"}]', "--file", str(file_path)]
    )

    assert missing.exit_code != 0
    assert both.exit_code != 0
    assert "exactly one" in missing.stderr
    assert "exactly one" in both.stderr


def test_run_submit_rejects_empty_steps(invoke: Any) -> None:
    """A blueprint must contain at least one step object."""
    empty = invoke(["run", "submit", "my-vm", "--steps", "[]"])
    scalar = invoke(["run", "submit", "my-vm", "--steps", '["start"]'])

    assert empty.exit_code != 0
    assert scalar.exit_code != 0
    assert "non-empty steps array" in empty.stderr
    assert "must be an object" in scalar.stderr


def test_run_list_preserves_machine_envelope(invoke: Any) -> None:
    """Run list keeps executions and total in structured output."""
    result = invoke(["--output", "json", "run", "list"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["executions"][0]["id"] == EXECUTION_ID
    assert payload["total"] == 1


def test_run_get_uses_one_based_human_progress(invoke: Any) -> None:
    """Completed runs display all steps without exposing zero-based indexes."""
    result = invoke(["run", "get", EXECUTION_ID])

    assert result.exit_code == 0
    assert "completed (2/2)" in result.stdout
    assert "1. start" in result.stdout
    assert "2. execute" in result.stdout


def test_run_wait(invoke: Any) -> None:
    """Wait observes an already submitted run."""
    result = invoke(["--output", "json", "run", "wait", EXECUTION_ID])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "completed"


@pytest.mark.parametrize("terminal_status", ["failed", "cancelled"])
def test_run_non_success_terminal_state_returns_one(
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: str,
) -> None:
    """Failed and cancelled submitted runs return a nonzero exit status."""
    final = {
        **JEBALLTOFILE_RESPONSE,
        "status": terminal_status,
        "currentStep": 0,
        "error": "step did not complete" if terminal_status == "failed" else None,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json=JEBALLTOFILE_RESPONSE)
        return httpx.Response(200, json=final)

    result = _invoke_with_handler(
        monkeypatch,
        ["--output", "json", "run", "submit", "my-vm", "--steps", STEPS],
        handler,
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == terminal_status


def test_run_cancel_waits_by_default(invoke: Any) -> None:
    """Cancellation waits for the cooperative terminal response by default."""
    result = invoke(["--output", "json", "run", "cancel", EXECUTION_ID])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "completed"


def test_run_cancel_detach_returns_request(invoke: Any) -> None:
    """Detached cancellation returns after the API accepts the request."""
    result = invoke(["--output", "json", "run", "cancel", EXECUTION_ID, "--detach"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["success"] is True


def test_run_delete_confirmed(invoke: Any) -> None:
    """Delete a finished run with --yes."""
    result = invoke(["run", "delete", EXECUTION_ID, "--yes"])

    assert result.exit_code == 0
    assert "Done" in result.stdout or "deleted" in result.stdout.lower()


def test_run_delete_requires_yes_without_tty(invoke: Any) -> None:
    """Deletion fails safely without confirmation in non-interactive mode."""
    result = invoke(["run", "delete", EXECUTION_ID])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "--yes" in result.stderr


def test_run_help_and_leftovers(invoke: Any) -> None:
    """Root help exposes run while the old Jeballtofile hierarchy is gone."""
    root_help = invoke(["--help"])
    run_help = invoke(["run", "--help"])
    leftover = invoke(["jeballtofile", "run"])

    assert root_help.exit_code == 0
    assert "run" in root_help.stdout
    assert run_help.exit_code == 0
    for command in ("submit", "list", "get", "wait", "cancel", "delete"):
        assert command in run_help.stdout
    assert leftover.exit_code != 0


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
