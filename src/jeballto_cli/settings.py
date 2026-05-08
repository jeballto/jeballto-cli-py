from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://localhost:8011/v1"
DEFAULT_TIMEOUT: float | None = None
DEFAULT_AGENT_CONFIG_PATH = Path.home() / "Library/Application Support/Jeballto/config.json"


class OutputFormat(StrEnum):
    JSON = "json"
    YAML = "yaml"
    TABLE = "table"


@dataclass(slots=True, frozen=True)
class Settings:
    base_url: str
    token: str | None
    timeout: float | None
    insecure: bool
    output: OutputFormat
    config_file: Path


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
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name} value: {raw!r}") from exc
    if value <= 0:
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


def _extract_agent_token(agent_config: dict[str, Any]) -> str | None:
    api = agent_config.get("api")
    if not isinstance(api, dict):
        return None
    token = api.get("token")
    if token is None:
        return None
    token_str = str(token).strip()
    return token_str or None


def _extract_agent_base_url(agent_config: dict[str, Any]) -> str | None:
    api = agent_config.get("api")
    if not isinstance(api, dict):
        return None

    host = api.get("host")
    port = api.get("port")
    enable_https = api.get("enableHTTPS")

    if not isinstance(host, str):
        return None
    if not isinstance(port, int):
        return None
    if not isinstance(enable_https, bool):
        return None

    scheme = "https" if enable_https else "http"
    return f"{scheme}://{host}:{port}/v1"


def load_settings(
    *,
    base_url: str | None,
    token: str | None,
    timeout: float | None,
    insecure: bool | None,
    output: OutputFormat | None,
    config_file: Path | None,
) -> Settings:
    cfg_path = (config_file or default_config_path()).expanduser()
    parsed = _load_toml_file(cfg_path)
    client_cfg_raw = parsed.get("client", {})

    if not isinstance(client_cfg_raw, dict):
        raise ValueError("Config field [client] must be a TOML table")

    client_cfg = client_cfg_raw

    agent_cfg = _load_json_file(default_agent_config_path())
    agent_token = _extract_agent_token(agent_cfg)
    agent_base_url = _extract_agent_base_url(agent_cfg)

    env_base_url = os.environ.get("JEBALLTO_BASE_URL")
    env_token = os.environ.get("JEBALLTO_TOKEN")
    env_timeout = os.environ.get("JEBALLTO_TIMEOUT")
    env_insecure = os.environ.get("JEBALLTO_INSECURE")
    env_output = os.environ.get("JEBALLTO_OUTPUT")

    resolved_base_url = (
        base_url
        or env_base_url
        or (str(client_cfg.get("base_url")) if client_cfg.get("base_url") else None)
        or agent_base_url
        or DEFAULT_BASE_URL
    )

    resolved_token = (
        token
        or env_token
        or (str(client_cfg.get("token")) if client_cfg.get("token") else None)
        or agent_token
    )

    resolved_timeout: float | None
    if timeout is not None:
        resolved_timeout = timeout
    elif env_timeout is not None:
        resolved_timeout = _coerce_float(env_timeout, "timeout")
    elif client_cfg.get("timeout") is not None:
        resolved_timeout = _coerce_float(client_cfg.get("timeout"), "timeout")
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
        resolved_output = OutputFormat.TABLE

    return Settings(
        base_url=resolved_base_url.rstrip("/"),
        token=resolved_token,
        timeout=resolved_timeout,
        insecure=resolved_insecure,
        output=resolved_output,
        config_file=cfg_path,
    )
