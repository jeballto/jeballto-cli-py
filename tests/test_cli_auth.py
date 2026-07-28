"""Tests for token onboarding and Keychain-backed auth commands."""

from __future__ import annotations

import json
from typing import Any

import pytest

VALID_TOKEN = "test-token-abcdefghijklmnopqrstuvwxyz"


def test_auth_login_verifies_and_saves_token(
    invoke: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Login verifies the token before saving it for this agent URL."""
    saved: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "jeballto_cli.commands.auth.save_token",
        lambda base_url, token: saved.append((base_url, token)),
    )

    result = invoke(["auth", "login", "--token", VALID_TOKEN])

    assert result.exit_code == 0
    assert "Authentication configured" in result.stdout
    assert VALID_TOKEN not in result.stdout
    assert saved == [("http://test:8011/v1", VALID_TOKEN)]


def test_auth_login_json_is_machine_readable(
    invoke: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Login can return a stable structured result without revealing the token."""
    monkeypatch.setattr("jeballto_cli.commands.auth.save_token", lambda _url, _token: None)

    result = invoke(["--output", "json", "auth", "login", "--token", VALID_TOKEN])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "status": "authenticated",
        "baseUrl": "http://test:8011/v1",
        "storedIn": "macOS Keychain",
    }
    assert VALID_TOKEN not in result.stdout


def test_auth_login_rejects_invalid_token_without_saving(
    invoke: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid tokens are rejected locally and never reach Keychain storage."""
    called = False

    def save(_base_url: str, _token: str) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("jeballto_cli.commands.auth.save_token", save)

    result = invoke(["auth", "login", "--token", "too-short"])

    assert result.exit_code == 2
    assert "32 to 512" in result.output
    assert called is False


def test_auth_login_prompts_to_replace_saved_keychain_token(
    invoke: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Login does not silently reuse a stale token already saved in Keychain."""
    old_token = "old-token-abcdefghijklmnopqrstuvwxyz0"
    new_token = "new-token-abcdefghijklmnopqrstuvwxyz0"
    saved: list[str] = []
    monkeypatch.delenv("JEBALLTO_TOKEN", raising=False)
    monkeypatch.setattr("jeballto_cli.settings.load_token", lambda _url: old_token)
    monkeypatch.setattr(
        "jeballto_cli.commands.auth.save_token",
        lambda _url, token: saved.append(token),
    )

    result = invoke(["auth", "login"], input=f"{new_token}\n")

    assert result.exit_code == 0
    assert saved == [new_token]
    assert old_token not in result.output


def test_auth_status_reports_environment_source(invoke: Any) -> None:
    """Status shows both verification state and token provenance."""
    result = invoke(["auth", "status"])

    assert result.exit_code == 0
    assert "authenticated" in result.stdout
    assert "token source: environment" in result.stdout


def test_auth_status_without_token_returns_nonzero(
    invoke: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing authentication gives a recovery command and a nonzero exit."""
    monkeypatch.delenv("JEBALLTO_TOKEN", raising=False)
    monkeypatch.setattr("jeballto_cli.settings.load_token", lambda _url: None)

    result = invoke(["auth", "status"])

    assert result.exit_code == 1
    assert "not_authenticated" in result.stdout
    assert "auth login" in result.stderr


def test_auth_logout_deletes_only_current_agent_token(
    invoke: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logout deletes the Keychain item keyed by the resolved agent URL."""
    deleted: list[str] = []

    def delete(base_url: str) -> bool:
        deleted.append(base_url)
        return True

    monkeypatch.setattr("jeballto_cli.commands.auth.delete_token", delete)

    result = invoke(["auth", "logout"])

    assert result.exit_code == 0
    assert "Saved token deleted" in result.stdout
    assert deleted == ["http://test:8011/v1"]
    assert "environment remains active" in result.stderr
