"""Tests for config and registry commands."""

from __future__ import annotations

from typing import Any


def test_config_get(invoke: Any) -> None:
    """Get agent config."""
    result = invoke(["config", "get"])
    assert result.exit_code == 0
    assert "8011" in result.output


def test_config_set_json(invoke: Any) -> None:
    """Set agent config with --json."""
    result = invoke(["config", "set", "--json", '{"logging": {"level": "debug"}}'])
    assert result.exit_code == 0


def test_config_set_timezone(invoke: Any) -> None:
    """Set config timezone."""
    result = invoke(["config", "set", "--timezone", "UTC"])
    assert result.exit_code == 0


def test_config_set_vnc_ports(invoke: Any) -> None:
    """Set config VNC port range."""
    result = invoke(
        [
            "config",
            "set",
            "--vnc-port-range-start",
            "5900",
            "--vnc-port-range-end",
            "5999",
        ]
    )
    assert result.exit_code == 0


def test_config_set_no_input(invoke: Any) -> None:
    """Set config with no flags fails."""
    result = invoke(["config", "set"])
    assert result.exit_code != 0


def test_registry_login(invoke: Any) -> None:
    """Login to a registry with inline credentials."""
    result = invoke(
        [
            "registry",
            "login",
            "registry.example.com",
            "--username",
            "user",
            "--password",
            "pass",
        ]
    )
    assert result.exit_code == 0
    assert "authenticated" in result.output.lower() or "Login" in result.output


def test_registry_logout(invoke: Any) -> None:
    """Logout from a registry."""
    result = invoke(["registry", "logout", "registry.example.com"])
    assert result.exit_code == 0
