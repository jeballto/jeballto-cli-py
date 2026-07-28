"""Tests for config and registry commands."""

from __future__ import annotations

import json
from typing import Any

import pytest


def test_config_get(invoke: Any) -> None:
    """Get current agent config without removed HTTPS settings."""
    result = invoke(["config", "get"])

    assert result.exit_code == 0
    assert "8011" in result.stdout
    assert "concurrent requests" in result.stdout
    assert "HTTPS" not in result.stdout


def test_config_get_json_is_clean_machine_output(invoke: Any) -> None:
    """Config JSON is parseable on stdout and does not use stderr."""
    result = invoke(["--output", "json", "config", "get"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["api"]["maxConcurrentRequests"] > 0
    assert "enableHTTPS" not in payload["api"]
    assert result.stderr == ""


def test_config_set_json(invoke: Any) -> None:
    """Set agent config with --json."""
    result = invoke(["config", "set", "--json", '{"logging": {"level": "debug"}}'])
    assert result.exit_code == 0


def test_config_set_json_requires_object(invoke: Any) -> None:
    """Raw config rejects valid JSON that is not an object."""
    result = invoke(["config", "set", "--json", "[]"])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "JSON object" in result.stderr


def test_config_set_timezone(invoke: Any) -> None:
    """Set config timezone."""
    result = invoke(["config", "set", "--timezone", "UTC"])
    assert result.exit_code == 0


def test_config_set_explicit_clear_flags(
    invoke: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clearable settings have discoverable flags instead of empty-string sentinels."""
    captured: list[dict[str, object]] = []

    def update_config(_self: object, updates: dict[str, object]) -> dict[str, object]:
        captured.append(updates)
        return updates

    monkeypatch.setattr("jeballto_cli.client.JeballtoClient.update_config", update_config)
    result = invoke(
        [
            "config",
            "set",
            "--system-timezone",
            "--clear-default-registry",
            "--clear-insecure-registries",
        ]
    )

    assert result.exit_code == 0
    assert captured == [
        {
            "logging": {"timezone": None},
            "images": {
                "defaultRegistry": None,
                "insecureRegistries": [],
            },
        }
    ]


def test_config_set_rejects_conflicting_clear_flag(invoke: Any) -> None:
    """A value and its clear flag cannot be supplied together."""
    result = invoke(
        ["config", "set", "--registry", "registry.example.com", "--clear-default-registry"]
    )

    assert result.exit_code == 2
    assert "not both" in result.stderr


def test_config_set_vnc_ports(invoke: Any) -> None:
    """Set config VNC port range."""
    result = invoke(
        [
            "config",
            "set",
            "--vnc-start",
            "5901",
            "--vnc-end",
            "5999",
        ]
    )
    assert result.exit_code == 0
    assert "Config updated" in result.stdout
    assert "agent restarts" in result.stderr


def test_config_set_ssh_and_logging_flags(invoke: Any) -> None:
    """Set SSH and logging config flags."""
    result = invoke(
        [
            "config",
            "set",
            "--ssh-start",
            "2222",
            "--ssh-end",
            "2223",
            "--no-ssh-forwarding",
            "--retention-days",
            "14",
            "--max-total-size",
            "4GB",
        ]
    )
    assert result.exit_code == 0


def test_config_set_image_flags(invoke: Any) -> None:
    """Set image config flags."""
    result = invoke(
        [
            "config",
            "set",
            "--registry",
            "registry.example.com",
            "--insecure-registry",
            "registry.local",
            "--blob-transfers",
            "8",
            "--compressions",
            "4",
            "--decompressions",
            "2",
            "--disk-writes",
            "1",
        ]
    )
    assert result.exit_code == 0


def test_config_set_short_flags(invoke: Any) -> None:
    """Set config with shorter UX-friendly flags."""
    result = invoke(
        [
            "config",
            "set",
            "--ssh-start",
            "2222",
            "--ssh-end",
            "2223",
            "--vnc-start",
            "5901",
            "--vnc-end",
            "5902",
            "--registry",
            "registry.example.com",
            "--blob-transfers",
            "8",
            "--compressions",
            "4",
            "--decompressions",
            "2",
            "--disk-writes",
            "1",
        ]
    )
    assert result.exit_code == 0


def test_config_set_no_input(invoke: Any) -> None:
    """Set config with no flags fails."""
    result = invoke(["config", "set"])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "at least one config flag" in result.stderr


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
    assert "authenticated" in result.stdout.lower() or "Login" in result.stdout
    assert "pass" not in result.stdout


def test_registry_logout(invoke: Any) -> None:
    """Logout from a registry."""
    result = invoke(["registry", "logout", "registry.example.com"])
    assert result.exit_code == 0
