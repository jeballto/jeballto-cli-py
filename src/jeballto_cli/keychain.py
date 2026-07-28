"""macOS Keychain storage for CLI API tokens."""

from __future__ import annotations

import subprocess

KEYCHAIN_SERVICE = "com.jeballto.cli.api"
SECURITY = "/usr/bin/security"


class KeychainError(Exception):
    """macOS Keychain command failure."""


def load_token(base_url: str) -> str | None:
    """Load a token for one agent URL, returning none when it is unavailable."""
    try:
        result = subprocess.run(
            [
                SECURITY,
                "find-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                base_url,
                "-w",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    token = result.stdout.rstrip("\r\n")
    return token or None


def save_token(base_url: str, token: str) -> None:
    """Store or replace a token without putting it in process arguments."""
    try:
        result = subprocess.run(
            [
                SECURITY,
                "add-generic-password",
                "-U",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                base_url,
                "-l",
                f"Jeballto CLI token for {base_url}",
                "-w",
            ],
            input=f"{token}\n",
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise KeychainError("Could not access the macOS Keychain") from exc
    if result.returncode != 0:
        message = result.stderr.strip() or "The security command failed."
        raise KeychainError(f"Could not save the API token: {message}")


def delete_token(base_url: str) -> bool:
    """Delete a saved token for one agent URL."""
    try:
        result = subprocess.run(
            [
                SECURITY,
                "delete-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                base_url,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise KeychainError("Could not access the macOS Keychain") from exc
    if result.returncode == 0:
        return True
    if result.returncode == 44 or "could not be found" in result.stderr.casefold():
        return False
    raise KeychainError(f"Could not delete the API token: {result.stderr.strip()}")


def validate_token(token: str) -> str:
    """Apply the same basic token constraints as the Jeballto agent."""
    if not 32 <= len(token.encode("utf-8")) <= 512:
        raise ValueError("API tokens must contain 32 to 512 printable ASCII characters")
    if any(not 0x21 <= ord(character) <= 0x7E for character in token):
        raise ValueError("API tokens must contain only printable ASCII without spaces")
    return token
