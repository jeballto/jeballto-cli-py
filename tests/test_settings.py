"""Tests for settings resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from jeballto_cli.settings import OutputFormat, load_settings


def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear all Jeballto env vars and redirect agent config to a nonexistent file."""
    for var in (
        "JEBALLTO_BASE_URL",
        "JEBALLTO_TOKEN",
        "JEBALLTO_TIMEOUT",
        "JEBALLTO_INSECURE",
        "JEBALLTO_OUTPUT",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("JEBALLTO_AGENT_CONFIG", str(tmp_path / "no-agent.json"))


def test_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Default settings resolve correctly when no config or env vars exist."""
    _isolate_env(monkeypatch, tmp_path)
    settings = load_settings(
        base_url=None,
        token=None,
        timeout=None,
        insecure=None,
        output=None,
        config_file=tmp_path / "nonexistent" / "config.toml",
    )
    assert settings.base_url == "http://localhost:8011/v1"
    assert settings.token is None
    assert settings.timeout is None
    assert settings.insecure is False
    assert settings.output == OutputFormat.TABLE


def test_cli_args_override_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """CLI arguments take priority over environment variables."""
    _isolate_env(monkeypatch, tmp_path)
    monkeypatch.setenv("JEBALLTO_BASE_URL", "http://env:9090/v1")
    monkeypatch.setenv("JEBALLTO_TOKEN", "env-token")
    settings = load_settings(
        base_url="http://cli:1234/v1",
        token="cli-token",
        timeout=10.0,
        insecure=True,
        output=OutputFormat.JSON,
        config_file=tmp_path / "nonexistent" / "config.toml",
    )
    assert settings.base_url == "http://cli:1234/v1"
    assert settings.token == "cli-token"
    assert settings.timeout == 10.0
    assert settings.insecure is True
    assert settings.output == OutputFormat.JSON


def test_env_vars(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Environment variables are picked up when CLI args are not set."""
    _isolate_env(monkeypatch, tmp_path)
    monkeypatch.setenv("JEBALLTO_BASE_URL", "http://env:9090/v1")
    monkeypatch.setenv("JEBALLTO_TOKEN", "env-token")
    monkeypatch.setenv("JEBALLTO_TIMEOUT", "60")
    monkeypatch.setenv("JEBALLTO_INSECURE", "true")
    monkeypatch.setenv("JEBALLTO_OUTPUT", "yaml")
    settings = load_settings(
        base_url=None,
        token=None,
        timeout=None,
        insecure=None,
        output=None,
        config_file=tmp_path / "nonexistent" / "config.toml",
    )
    assert settings.base_url == "http://env:9090/v1"
    assert settings.token == "env-token"
    assert settings.timeout == 60.0
    assert settings.insecure is True
    assert settings.output == OutputFormat.YAML


def test_toml_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Settings are loaded from a TOML config file."""
    _isolate_env(monkeypatch, tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[client]\nbase_url = "http://toml:7070/v1"\ntoken = "toml-token"\ntimeout = 45\n'
    )
    settings = load_settings(
        base_url=None,
        token=None,
        timeout=None,
        insecure=None,
        output=None,
        config_file=config_path,
    )
    assert settings.base_url == "http://toml:7070/v1"
    assert settings.token == "toml-token"
    assert settings.timeout == 45.0
