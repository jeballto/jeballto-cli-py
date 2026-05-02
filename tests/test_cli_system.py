"""Tests for system commands."""

from __future__ import annotations

from typing import Any


def test_system_reset_soft_yes(invoke: Any) -> None:
    """Soft reset succeeds with --yes."""
    result = invoke(["system", "reset", "soft", "--yes"])
    assert result.exit_code == 0
    assert "soft" in result.output.lower()


def test_system_reset_hard_yes(invoke: Any) -> None:
    """Hard reset succeeds with --yes."""
    result = invoke(["system", "reset", "hard", "--yes"])
    assert result.exit_code == 0
    assert "hard" in result.output.lower()


def test_system_reset_abort(invoke: Any) -> None:
    """Reset without --yes can be aborted."""
    result = invoke(["system", "reset", "soft"], input="n\n")
    assert result.exit_code != 0


def test_system_reset_invalid_mode(invoke: Any) -> None:
    """Invalid mode fails validation."""
    result = invoke(["system", "reset", "invalid", "--yes"])
    assert result.exit_code != 0
