"""Tests for the health command and global options."""

from __future__ import annotations

import json
from typing import Any


def test_health_human(invoke: Any) -> None:
    """Health command renders a concise human summary by default."""
    result = invoke(["health"])

    assert result.exit_code == 0
    assert "Jeballto agent: healthy" in result.stdout
    assert "uptime: 1h" in result.stdout
    assert result.stderr == ""


def test_health_json(invoke: Any) -> None:
    """Health JSON is a clean machine-readable stdout stream."""
    result = invoke(["--output", "json", "health"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "healthy"
    assert result.stderr == ""


def test_health_jsonl(invoke: Any) -> None:
    """JSONL emits exactly one compact object for a single response."""
    result = invoke(["--output", "jsonl", "health"])

    assert result.exit_code == 0
    assert len(result.stdout.splitlines()) == 1
    assert json.loads(result.stdout)["status"] == "healthy"
    assert result.stderr == ""


def test_health_yaml(invoke: Any) -> None:
    """Health command renders YAML when requested."""
    result = invoke(["--output", "yaml", "health"])
    assert result.exit_code == 0
    assert "status: healthy" in result.stdout
    assert result.stderr == ""


def test_removed_table_output_name_is_rejected(invoke: Any) -> None:
    """The output mode is named human, not the old table implementation detail."""
    result = invoke(["--output", "table", "health"])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "table" in result.stderr


def test_doctor_reports_ready_agent(invoke: Any) -> None:
    """Doctor checks connection, authentication, and host capabilities."""
    result = invoke(["doctor"])

    assert result.exit_code == 0
    assert "connection" in result.stdout
    assert "authentication" in result.stdout
    assert "virtualization" in result.stdout


def test_version_flag(invoke: Any) -> None:
    """--version prints the version string and exits."""
    result = invoke(["--version"])
    assert result.exit_code == 0
    assert "jeballto-cli" in result.stdout


def test_help_flag(invoke: Any) -> None:
    """--help shows usage information."""
    result = invoke(["--help"])
    assert result.exit_code == 0
    assert "Manage Jeballto VMs, images, config, and automation." in result.stdout
    assert "doctor" in result.stdout
    assert "run" in result.stdout
