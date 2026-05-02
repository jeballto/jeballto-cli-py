"""Tests for the auth commands."""

from __future__ import annotations

from typing import Any


def test_auth_verify_ok(invoke: Any) -> None:
    """Auth verify prints status ok."""
    result = invoke(["auth", "verify"])
    assert result.exit_code == 0
    assert "ok" in result.output.lower()
