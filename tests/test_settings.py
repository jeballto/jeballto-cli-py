"""Tests for settings resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jeballto_cli.settings import OutputFormat, TokenSource, load_settings


def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear Jeballto variables and isolate local discovery and Keychain access."""
    for var in (
        "JEBALLTO_BASE_URL",
        "JEBALLTO_TOKEN",
        "JEBALLTO_REQUEST_TIMEOUT",
        "JEBALLTO_INSECURE",
        "JEBALLTO_OUTPUT",
        "JEBALLTO_DETAILS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("JEBALLTO_AGENT_CONFIG", str(tmp_path / "no-agent.json"))
    monkeypatch.setattr("jeballto_cli.settings.load_token", lambda _base_url: None)


def _load(tmp_path: Path, **overrides: Any) -> Any:
    values: dict[str, Any] = {
        "base_url": None,
        "token": None,
        "request_timeout": None,
        "insecure": None,
        "output": None,
        "config_file": tmp_path / "nonexistent" / "config.toml",
    }
    values.update(overrides)
    return load_settings(**values)


def test_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Defaults are automation-safe and use human output."""
    _isolate_env(monkeypatch, tmp_path)

    settings = _load(tmp_path)

    assert settings.base_url == "http://localhost:8011/v1"
    assert settings.token is None
    assert settings.token_source == TokenSource.NONE
    assert settings.request_timeout is None
    assert settings.insecure is False
    assert settings.output == OutputFormat.HUMAN
    assert settings.details is False
    assert settings.no_input is False
    assert settings.debug is False


def test_cli_args_override_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Explicit command arguments take priority over environment variables."""
    _isolate_env(monkeypatch, tmp_path)
    monkeypatch.setenv("JEBALLTO_BASE_URL", "http://env:9090/v1")
    monkeypatch.setenv("JEBALLTO_TOKEN", "env-token")

    settings = _load(
        tmp_path,
        base_url="https://cli:1234/v1/",
        token="cli-token",
        request_timeout=10.0,
        insecure=True,
        output=OutputFormat.JSON,
        details=True,
        no_input=True,
        debug=True,
    )

    assert settings.base_url == "https://cli:1234/v1"
    assert settings.token == "cli-token"
    assert settings.token_source == TokenSource.ARGUMENT
    assert settings.request_timeout == 10.0
    assert settings.insecure is True
    assert settings.output == OutputFormat.JSON
    assert settings.details is True
    assert settings.no_input is True
    assert settings.debug is True


def test_environment_variables(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Current environment variable names are resolved correctly."""
    _isolate_env(monkeypatch, tmp_path)
    monkeypatch.setenv("JEBALLTO_BASE_URL", "env:9090")
    monkeypatch.setenv("JEBALLTO_TOKEN", "env-token")
    monkeypatch.setenv("JEBALLTO_REQUEST_TIMEOUT", "60")
    monkeypatch.setenv("JEBALLTO_INSECURE", "true")
    monkeypatch.setenv("JEBALLTO_OUTPUT", "jsonl")
    monkeypatch.setenv("JEBALLTO_DETAILS", "true")

    settings = _load(tmp_path)

    assert settings.base_url == "http://env:9090/v1"
    assert settings.token == "env-token"
    assert settings.token_source == TokenSource.ENVIRONMENT
    assert settings.request_timeout == 60.0
    assert settings.insecure is True
    assert settings.output == OutputFormat.JSONL
    assert settings.details is True


def test_toml_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Non-secret client preferences are loaded from TOML."""
    _isolate_env(monkeypatch, tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[client]\nbase_url = "toml:7070"\nrequest_timeout = 45\n'
        'output = "yaml"\ninsecure = true\ndetails = true\n',
        encoding="utf-8",
    )

    settings = _load(tmp_path, config_file=config_path)

    assert settings.base_url == "http://toml:7070/v1"
    assert settings.token is None
    assert settings.token_source == TokenSource.NONE
    assert settings.request_timeout == 45.0
    assert settings.output == OutputFormat.YAML
    assert settings.insecure is True
    assert settings.details is True


def test_toml_token_has_keychain_migration_hint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A plaintext legacy token is rejected with a safe migration command."""
    _isolate_env(monkeypatch, tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text('[client]\ntoken = "plaintext-token"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="auth login"):
        _load(tmp_path, config_file=config_path)


def test_unknown_toml_client_field_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Misspelled and retired settings cannot be silently ignored."""
    _isolate_env(monkeypatch, tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text("[client]\ntimeout = 30\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"client\.timeout"):
        _load(tmp_path, config_file=config_path)


def test_agent_config_wildcard_host_maps_to_localhost_and_uses_keychain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Local agent bind data discovers a usable URL without reading its secrets."""
    _isolate_env(monkeypatch, tmp_path)
    agent_config_path = tmp_path / "agent.json"
    agent_config_path.write_text(
        '{"api":{"host":"0.0.0.0","port":8011},"token":"ignored"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("JEBALLTO_AGENT_CONFIG", str(agent_config_path))
    observed: list[str] = []

    def load_keychain_token(base_url: str) -> str:
        observed.append(base_url)
        return "keychain-token"

    monkeypatch.setattr("jeballto_cli.settings.load_token", load_keychain_token)

    settings = _load(tmp_path)

    assert settings.base_url == "http://localhost:8011/v1"
    assert settings.token == "keychain-token"
    assert settings.token_source == TokenSource.KEYCHAIN
    assert observed == ["http://localhost:8011/v1"]


def test_agent_config_ipv6_host_is_bracketed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An IPv6 bind host becomes a valid client URL."""
    _isolate_env(monkeypatch, tmp_path)
    agent_config_path = tmp_path / "agent.json"
    agent_config_path.write_text(
        '{"api":{"host":"fe80::1","port":8011}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("JEBALLTO_AGENT_CONFIG", str(agent_config_path))

    settings = _load(tmp_path)

    assert settings.base_url == "http://[fe80::1]:8011/v1"


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("agent.example.com:8011", "http://agent.example.com:8011/v1"),
        ("https://agent.example.com", "https://agent.example.com/v1"),
        ("https://agent.example.com/custom/", "https://agent.example.com/custom"),
    ],
)
def test_base_url_normalization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    base_url: str,
    expected: str,
) -> None:
    """URLs gain a scheme and API path only when they are missing."""
    _isolate_env(monkeypatch, tmp_path)

    settings = _load(tmp_path, base_url=base_url)

    assert settings.base_url == expected


@pytest.mark.parametrize(
    "base_url",
    ["ftp://agent.example.com", "http://user:secret@agent.example.com", "http://host/?q=1"],
)
def test_invalid_base_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    base_url: str,
) -> None:
    """Unsafe or unsupported agent URLs are rejected locally."""
    _isolate_env(monkeypatch, tmp_path)

    with pytest.raises(ValueError):
        _load(tmp_path, base_url=base_url)


@pytest.mark.parametrize("request_timeout", [0, -1, True, float("inf"), float("nan")])
def test_invalid_request_timeout_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    request_timeout: float,
) -> None:
    """Request timeouts must be finite positive values."""
    _isolate_env(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="request timeout"):
        _load(tmp_path, request_timeout=request_timeout)
