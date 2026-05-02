"""Tests for jeballtofile commands."""

from __future__ import annotations

from typing import Any

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
