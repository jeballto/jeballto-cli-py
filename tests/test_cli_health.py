"""Tests for the health command and global options."""

from __future__ import annotations

from typing import Any


def test_health_table(invoke: Any) -> None:
    """Health command renders a table by default."""
    result = invoke(["health"])
    assert result.exit_code == 0
    assert "healthy" in result.output


def test_health_json(invoke: Any) -> None:
    """Health command renders JSON when requested."""
    result = invoke(["--output", "json", "health"])
    assert result.exit_code == 0
    assert '"status"' in result.output
    assert '"healthy"' in result.output


def test_health_yaml(invoke: Any) -> None:
    """Health command renders YAML when requested."""
    result = invoke(["--output", "yaml", "health"])
    assert result.exit_code == 0
    assert "status: healthy" in result.output


def test_version_flag(invoke: Any) -> None:
    """--version prints the version string and exits."""
    result = invoke(["--version"])
    assert result.exit_code == 0
    assert "jeballto-cli" in result.output


def test_help_flag(invoke: Any) -> None:
    """--help shows usage information."""
    result = invoke(["--help"])
    assert result.exit_code == 0
    assert "CLI for the Jeballto VM Agent API" in result.output
