from __future__ import annotations

import json
import math
import os
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from jeballto_cli.keychain import load_token

DEFAULT_BASE_URL = "http://localhost:8011/v1"
DEFAULT_TIMEOUT: float | None = None
DEFAULT_AGENT_CONFIG_PATH = Path.home() / "Library/Application Support/Jeballto/config.json"


class OutputFormat(StrEnum):
    HUMAN = "human"
    JSON = "json"
    JSONL = "jsonl"
    YAML = "yaml"


class TokenSource(StrEnum):
    ARGUMENT = "argument"
    ENVIRONMENT = "environment"
    KEYCHAIN = "keychain"
    NONE = "none"


@dataclass(slots=True, frozen=True)
class Settings:
    base_url: str
    token: str | None
    token_source: TokenSource
    request_timeout: float | None
    insecure: bool
    output: OutputFormat
    config_file: Path
    details: bool
    no_input: bool
    debug: bool


def default_config_path() -> Path:
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_home).expanduser() if xdg_home else Path.home() / ".config"
    return base / "jeballto-cli" / "config.toml"


def default_agent_config_path() -> Path:
    custom = os.environ.get("JEBALLTO_AGENT_CONFIG")
    if custom:
        return Path(custom).expanduser()
    return DEFAULT_AGENT_CONFIG_PATH


def _parse_bool(raw: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Cannot parse boolean value from: {raw}")


def _coerce_float(raw: Any, field_name: str) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"Invalid {field_name} value: {raw!r}")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name} value: {raw!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be > 0")
    return value


def _parse_output(raw: str | None) -> OutputFormat | None:
    if raw is None:
        return None
    try:
        return OutputFormat(raw.lower())
    except ValueError as exc:
        supported = ", ".join(item.value for item in OutputFormat)
        raise ValueError(f"Invalid output format {raw!r}. Supported: {supported}") from exc


def _load_toml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    data = path.read_text(encoding="utf-8")
    try:
        parsed = tomllib.loads(data)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML in config file {path}: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(f"Config file {path} must contain a TOML table at top-level")

    return parsed


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in Jeballto agent config {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Agent config {path} must contain a JSON object at top-level")

    return payload


def _extract_agent_base_url(agent_config: dict[str, Any]) -> str | None:
    api = agent_config.get("api")
    if not isinstance(api, dict):
        return None

    host = api.get("host")
    port = api.get("port")
    if not isinstance(host, str):
        return None
    if not isinstance(port, int) or isinstance(port, bool):
        return None
    if not 1 <= port <= 65535:
        return None

    connect_host = "localhost" if host in {"0.0.0.0", "::"} else host
    if ":" in connect_host and not connect_host.startswith("["):
        connect_host = f"[{connect_host}]"
    return f"http://{connect_host}:{port}/v1"


def _normalize_base_url(raw: str) -> str:
    """Validate an agent URL and add the default API path when omitted."""
    value = raw.strip()
    if not value:
        raise ValueError("Agent base URL cannot be empty")
    if "://" not in value:
        value = f"http://{value}"

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Agent base URL must use http or https")
    if not parsed.hostname:
        raise ValueError(f"Invalid agent base URL: {raw!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Agent base URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("Agent base URL must not contain a query or fragment")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid agent base URL: {exc}") from exc

    path = parsed.path.rstrip("/")
    if not path:
        path = "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def load_settings(
    *,
    base_url: str | None,
    token: str | None,
    request_timeout: float | None,
    insecure: bool | None,
    output: OutputFormat | None,
    config_file: Path | None,
    details: bool | None = None,
    no_input: bool = False,
    debug: bool = False,
) -> Settings:
    cfg_path = (config_file or default_config_path()).expanduser()
    parsed = _load_toml_file(cfg_path)
    client_cfg_raw = parsed.get("client", {})

    if not isinstance(client_cfg_raw, dict):
        raise ValueError("Config field [client] must be a TOML table")

    client_cfg = client_cfg_raw
    if "token" in client_cfg:
        raise ValueError(
            "Config field client.token is no longer supported. Remove it and run "
            "'jeballto auth login' to use the macOS Keychain."
        )
    supported_client_fields = {
        "base_url",
        "details",
        "insecure",
        "output",
        "request_timeout",
    }
    unknown_fields = sorted(set(client_cfg) - supported_client_fields)
    if unknown_fields:
        fields = ", ".join(f"client.{field}" for field in unknown_fields)
        raise ValueError(f"Unknown CLI config field(s): {fields}")

    configured_base_url = (
        base_url or os.environ.get("JEBALLTO_BASE_URL") or client_cfg.get("base_url")
    )
    agent_cfg = {} if configured_base_url else _load_json_file(default_agent_config_path())
    agent_base_url = _extract_agent_base_url(agent_cfg)

    env_base_url = os.environ.get("JEBALLTO_BASE_URL")
    env_token = os.environ.get("JEBALLTO_TOKEN")
    env_timeout = os.environ.get("JEBALLTO_REQUEST_TIMEOUT")
    env_insecure = os.environ.get("JEBALLTO_INSECURE")
    env_output = os.environ.get("JEBALLTO_OUTPUT")
    env_details = os.environ.get("JEBALLTO_DETAILS")

    raw_base_url = (
        base_url
        or env_base_url
        or (str(client_cfg.get("base_url")) if client_cfg.get("base_url") else None)
        or agent_base_url
        or DEFAULT_BASE_URL
    )
    resolved_base_url = _normalize_base_url(raw_base_url)

    resolved_token: str | None
    if token:
        resolved_token = token
        token_source = TokenSource.ARGUMENT
    elif env_token:
        resolved_token = env_token
        token_source = TokenSource.ENVIRONMENT
    else:
        resolved_token = load_token(resolved_base_url)
        token_source = TokenSource.KEYCHAIN if resolved_token else TokenSource.NONE

    resolved_timeout: float | None
    if request_timeout is not None:
        resolved_timeout = _coerce_float(request_timeout, "request timeout")
    elif env_timeout is not None:
        resolved_timeout = _coerce_float(env_timeout, "request timeout")
    elif client_cfg.get("request_timeout") is not None:
        resolved_timeout = _coerce_float(
            client_cfg.get("request_timeout"),
            "request timeout",
        )
    else:
        resolved_timeout = DEFAULT_TIMEOUT

    if insecure is not None:
        resolved_insecure = insecure
    elif env_insecure is not None:
        resolved_insecure = _parse_bool(env_insecure)
    elif client_cfg.get("insecure") is not None:
        raw_insecure = client_cfg.get("insecure")
        if isinstance(raw_insecure, bool):
            resolved_insecure = raw_insecure
        else:
            raise ValueError("Config field client.insecure must be true or false")
    else:
        resolved_insecure = False

    if output is not None:
        resolved_output = output
    elif env_output is not None:
        parsed_output = _parse_output(env_output)
        if parsed_output is None:
            raise ValueError("JEBALLTO_OUTPUT cannot be empty")
        resolved_output = parsed_output
    elif client_cfg.get("output") is not None:
        parsed_output = _parse_output(str(client_cfg.get("output")))
        if parsed_output is None:
            raise ValueError("Config field client.output cannot be empty")
        resolved_output = parsed_output
    else:
        resolved_output = OutputFormat.HUMAN

    if details is not None:
        resolved_details = details
    elif env_details is not None:
        resolved_details = _parse_bool(env_details)
    elif client_cfg.get("details") is not None:
        raw_details = client_cfg.get("details")
        if isinstance(raw_details, bool):
            resolved_details = raw_details
        else:
            raise ValueError("Config field client.details must be true or false")
    else:
        resolved_details = False

    return Settings(
        base_url=resolved_base_url,
        token=resolved_token,
        token_source=token_source,
        request_timeout=resolved_timeout,
        insecure=resolved_insecure,
        output=resolved_output,
        config_file=cfg_path,
        details=resolved_details,
        no_input=no_input,
        debug=debug,
    )
