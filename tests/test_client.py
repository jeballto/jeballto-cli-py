"""Tests for the JeballtoClient class."""

from __future__ import annotations

import json

import httpx
import pytest

from jeballto_cli.client import APIError, JeballtoClient
from jeballto_cli.settings import OutputFormat, Settings


def _settings(**overrides: object) -> Settings:
    """Create a Settings instance with defaults.

    Args:
        **overrides: Fields to override.

    Returns:
        A Settings dataclass instance.
    """
    from pathlib import Path

    defaults = {
        "base_url": "http://test:8011/v1",
        "token": "test-token",
        "timeout": 30.0,
        "insecure": False,
        "output": OutputFormat.TABLE,
        "config_file": Path("/dev/null"),
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _transport(data: object, status: int = 200) -> httpx.MockTransport:
    """Create a MockTransport returning a fixed JSON response.

    Args:
        data: JSON-serializable response payload.
        status: HTTP status code.

    Returns:
        An httpx.MockTransport.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if data is None:
            return httpx.Response(status_code=status)
        return httpx.Response(
            status_code=status,
            headers={"content-type": "application/json"},
            content=json.dumps(data).encode(),
        )

    return httpx.MockTransport(handler)


def test_health() -> None:
    """Health returns parsed JSON."""
    client = JeballtoClient(_settings(), transport=_transport({"status": "healthy"}))
    result = client.health()
    assert isinstance(result, dict)
    assert result["status"] == "healthy"
    client.close()


def test_context_manager() -> None:
    """Client can be used as a context manager."""
    with JeballtoClient(_settings(), transport=_transport({"ok": True})) as client:
        result = client.health()
        assert isinstance(result, dict)


def test_api_error_on_401() -> None:
    """Client raises APIError on 401."""
    error_body = {"error": {"code": "UNAUTHORIZED", "message": "Bad token"}}
    client = JeballtoClient(_settings(), transport=_transport(error_body, 401))
    with pytest.raises(APIError) as exc_info:
        client.health()
    assert exc_info.value.status_code == 401
    assert exc_info.value.code == "UNAUTHORIZED"
    client.close()


def test_api_error_on_network_failure() -> None:
    """Client raises APIError with NETWORK_ERROR on connection failure."""

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(failing_handler)
    client = JeballtoClient(_settings(), transport=transport)
    with pytest.raises(APIError) as exc_info:
        client.health()
    assert exc_info.value.code == "NETWORK_ERROR"
    client.close()


def test_create_vm() -> None:
    """create_vm sends correct payload."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=201,
            headers={"content-type": "application/json"},
            content=json.dumps({"id": "abc", "name": "test"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    result = client.create_vm("test", cpu=4, memory="8GB", disk="64GB")
    assert isinstance(result, dict)
    assert result["name"] == "test"

    body = json.loads(captured[0].content)
    assert body["name"] == "test"
    assert body["resources"]["cpuCount"] == 4
    assert body["resources"]["memorySize"] == "8GB"
    client.close()


def test_delete_vm_204() -> None:
    """delete_vm succeeds on 204."""
    client = JeballtoClient(_settings(), transport=_transport(None, 204))
    client.delete_vm("some-id")
    client.close()


def test_create_vm_ephemeral_body() -> None:
    """create_vm sends ephemeral and lifetimeSeconds."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=201,
            headers={"content-type": "application/json"},
            content=json.dumps({"id": "abc"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.create_vm("v", cpu=2, memory="4GB", ephemeral=True, lifetime_seconds=600)
    body = json.loads(captured[0].content)
    assert body["ephemeral"] is True
    assert body["lifetimeSeconds"] == 600
    client.close()


def test_create_vm_image_resource_conflict() -> None:
    """create_vm rejects image + resources combination."""
    client = JeballtoClient(_settings(), transport=_transport({}))
    with pytest.raises(ValueError):
        client.create_vm("v", cpu=2, image="reg/image:tag")
    client.close()


def test_update_vm_sends_patch() -> None:
    """update_vm issues PATCH with body."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps({"id": "abc", "name": "new"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.update_vm("abc", name="new", memory="16GB")
    assert captured[0].method == "PATCH"
    body = json.loads(captured[0].content)
    assert body["name"] == "new"
    assert body["resources"]["memorySize"] == "16GB"
    client.close()


def test_update_vm_requires_field() -> None:
    """update_vm with no field raises ValueError."""
    client = JeballtoClient(_settings(), transport=_transport({}))
    with pytest.raises(ValueError):
        client.update_vm("abc")
    client.close()


def test_auth_verify() -> None:
    """auth_verify returns status dict."""
    client = JeballtoClient(_settings(), transport=_transport({"status": "ok"}))
    result = client.auth_verify()
    assert isinstance(result, dict)
    assert result["status"] == "ok"
    client.close()


def test_clone_vm_ephemeral() -> None:
    """clone_vm sends ephemeral flag."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=201,
            headers={"content-type": "application/json"},
            content=json.dumps({"id": "c"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.clone_vm("src", "clone", ephemeral=True)
    body = json.loads(captured[0].content)
    assert body["ephemeral"] is True
    client.close()


def test_screenshot_returns_bytes() -> None:
    """screenshot returns raw bytes."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            headers={"content-type": "image/png"},
            content=b"\x89PNG\r\n",
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    data = client.screenshot("vm-id")
    assert isinstance(data, bytes)
    assert data.startswith(b"\x89PNG")
    client.close()
