"""Tests for the JeballtoClient class."""

from __future__ import annotations

import json

import httpx
import pytest

from jeballto_cli.client import (
    IMAGE_OPERATION_MAX_TIMEOUT,
    APIError,
    JeballtoClient,
)
from jeballto_cli.settings import OutputFormat, Settings, TokenSource


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
        "token_source": TokenSource.ARGUMENT,
        "request_timeout": None,
        "insecure": False,
        "output": OutputFormat.HUMAN,
        "config_file": Path("/dev/null"),
        "details": False,
        "no_input": False,
        "debug": False,
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
    assert exc_info.value.payload == error_body
    client.close()


def test_api_error_preserves_structured_details() -> None:
    """Structured API details remain available to CLI error handling."""
    error_body = {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Invalid request",
            "details": {"field": "name", "reason": "required"},
        }
    }
    client = JeballtoClient(_settings(), transport=_transport(error_body, 400))

    with pytest.raises(APIError) as exc_info:
        client.health()

    assert exc_info.value.details == {"field": "name", "reason": "required"}
    assert exc_info.value.payload == error_body
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


def test_success_response_requires_json_content_type() -> None:
    """A proxy HTML page cannot masquerade as a successful API response."""
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<h1>OK</h1>",
        )
    )
    client = JeballtoClient(_settings(), transport=transport)

    with pytest.raises(APIError, match="content type") as exc_info:
        client.health()

    assert exc_info.value.code == "INVALID_RESPONSE"
    client.close()


def test_success_response_rejects_malformed_json() -> None:
    """Malformed JSON becomes a stable API error instead of a traceback."""
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "application/json"},
            text="not json",
        )
    )
    client = JeballtoClient(_settings(), transport=transport)

    with pytest.raises(APIError, match="malformed JSON") as exc_info:
        client.health()

    assert exc_info.value.code == "INVALID_RESPONSE"
    client.close()


def test_api_error_on_timeout_failure() -> None:
    """Client raises APIError with REQUEST_TIMEOUT on HTTP timeout."""

    def failing_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    transport = httpx.MockTransport(failing_handler)
    client = JeballtoClient(_settings(), transport=transport)
    with pytest.raises(APIError) as exc_info:
        client.health()
    assert exc_info.value.code == "REQUEST_TIMEOUT"
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


def test_execute_timeout_sets_body_and_http_timeout() -> None:
    """execute timeout controls API body and HTTP transport timeout."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps({"exitCode": 0, "stdout": "", "stderr": ""}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.execute("abc", "echo hello", timeout=600)
    body = json.loads(captured[0].content)
    assert body["timeout"] == 600
    assert captured[0].extensions["timeout"]["read"] == 630.0
    client.close()


def test_execute_without_timeout_omits_body_timeout() -> None:
    """execute without timeout leaves the API default in place."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps({"exitCode": 0, "stdout": "", "stderr": ""}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.execute("abc", "echo hello")
    body = json.loads(captured[0].content)
    assert "timeout" not in body
    assert captured[0].extensions["timeout"]["read"] is None
    client.close()


def test_execute_rejects_timeout_above_api_limit() -> None:
    """execute rejects timeout above OpenAPI documented maximum."""
    client = JeballtoClient(_settings(), transport=_transport({}))
    with pytest.raises(ValueError):
        client.execute("abc", "echo hello", timeout=601)
    client.close()


def test_pull_image_timeout_sets_body_and_http_timeout() -> None:
    """pull_image timeout controls API body and HTTP transport timeout."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps({"status": "pulled"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.pull_image("registry.example.com/image:latest", timeout=3600)
    body = json.loads(captured[0].content)
    assert body["timeout"] == 3600
    assert captured[0].extensions["timeout"]["read"] == 3630.0
    client.close()


def test_pull_image_rejects_timeout_above_api_limit() -> None:
    """pull_image rejects timeout above OpenAPI documented maximum."""
    client = JeballtoClient(_settings(), transport=_transport({}))
    with pytest.raises(ValueError):
        client.pull_image(
            "registry.example.com/image:latest",
            timeout=IMAGE_OPERATION_MAX_TIMEOUT + 1,
        )
    client.close()


def test_pull_image_without_timeout_is_unlimited_by_default() -> None:
    """pull_image without timeout leaves body and HTTP timeout unlimited."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps({"status": "pulled"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.pull_image("registry.example.com/image:latest")
    body = json.loads(captured[0].content)
    assert "timeout" not in body
    assert captured[0].extensions["timeout"]["read"] is None
    client.close()


def test_pull_image_async_uses_pull_endpoint_with_async_flag() -> None:
    """pull_image async starts through the pull endpoint with async=true."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=202,
            headers={"content-type": "application/json"},
            content=json.dumps({"status": "started", "operationId": "op"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.pull_image("registry.example.com/image:latest", timeout=3600, async_=True)
    body = json.loads(captured[0].content)
    assert captured[0].method == "POST"
    assert captured[0].url.path == "/v1/images/pull"
    assert body["async"] is True
    assert body["reference"] == "registry.example.com/image:latest"
    assert body["timeout"] == 3600
    client.close()


def test_push_image_timeout_sets_body_and_http_timeout() -> None:
    """push_image timeout controls API body and HTTP transport timeout."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps({"status": "pushed"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.push_image(
        "registry.example.com/image:latest",
        source="vm:550e8400-e29b-41d4-a716-446655440000",
        timeout=7200,
    )
    body = json.loads(captured[0].content)
    assert body["timeout"] == 7200
    assert captured[0].extensions["timeout"]["read"] == 7230.0
    client.close()


def test_push_image_rejects_timeout_above_api_limit() -> None:
    """push_image rejects timeout above OpenAPI documented maximum."""
    client = JeballtoClient(_settings(), transport=_transport({}))
    with pytest.raises(ValueError):
        client.push_image(
            "registry.example.com/image:latest",
            source="vm:550e8400-e29b-41d4-a716-446655440000",
            timeout=IMAGE_OPERATION_MAX_TIMEOUT + 1,
        )
    client.close()


def test_push_image_async_uses_push_endpoint_with_async_flag() -> None:
    """push_image async starts through the push endpoint with async=true."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=202,
            headers={"content-type": "application/json"},
            content=json.dumps({"status": "started", "operationId": "op"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.push_image(
        "registry.example.com/image:latest",
        source="vm:550e8400-e29b-41d4-a716-446655440000",
        timeout=7200,
        async_=True,
    )
    body = json.loads(captured[0].content)
    assert captured[0].method == "POST"
    assert captured[0].url.path == "/v1/images/push"
    assert body["async"] is True
    assert body["reference"] == "registry.example.com/image:latest"
    assert body["source"] == "vm:550e8400-e29b-41d4-a716-446655440000"
    assert body["timeout"] == 7200
    client.close()


def test_image_operation_routes() -> None:
    """Image operation helpers call the documented typed operation routes."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        status_code = 202 if request.method == "POST" else 200
        return httpx.Response(
            status_code=status_code,
            headers={"content-type": "application/json"},
            content=json.dumps({"operationId": "op", "status": "completed"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.pull_image("registry.example.com/image:latest", timeout=3600, async_=True)
    client.push_image(
        "registry.example.com/image:latest",
        source="vm:550e8400-e29b-41d4-a716-446655440000",
        timeout=7200,
        async_=True,
    )
    client.list_image_operations()
    client.list_image_operations(type_="push", active_only=False)
    client.image_operation("op")
    client.image_operation("op", type_="push")
    client.cancel_image_operation("op")
    client.cancel_image_operation("op", type_="push")
    client.cancel_image_operations()
    client.cancel_image_operations(type_="pull")
    assert [(request.method, request.url.path) for request in captured] == [
        ("POST", "/v1/images/pull"),
        ("POST", "/v1/images/push"),
        ("GET", "/v1/images/pull/operations"),
        ("GET", "/v1/images/push/operations"),
        ("GET", "/v1/images/push/operations"),
        ("GET", "/v1/images/pull/operations/op"),
        ("GET", "/v1/images/push/operations/op"),
        ("DELETE", "/v1/images/pull/operations/op"),
        ("DELETE", "/v1/images/push/operations/op"),
        ("DELETE", "/v1/images/pull/operations"),
        ("DELETE", "/v1/images/push/operations"),
        ("DELETE", "/v1/images/pull/operations"),
    ]
    assert dict(captured[2].url.params) == {"activeOnly": "true"}
    assert dict(captured[3].url.params) == {"activeOnly": "true"}
    assert dict(captured[4].url.params) == {"activeOnly": "false"}
    client.close()


def test_image_operation_infers_push_after_pull_not_found() -> None:
    """Untyped image_operation falls back from pull to push on 404."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path == "/v1/images/pull/operations/op":
            return httpx.Response(
                status_code=404,
                headers={"content-type": "application/json"},
                content=json.dumps(
                    {"error": {"code": "IMAGE_OPERATION_NOT_FOUND", "message": "not found"}}
                ).encode(),
            )
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps(
                {"operationId": "op", "type": "push", "status": "completed"}
            ).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    result = client.image_operation("op")
    assert isinstance(result, dict)
    assert result["type"] == "push"
    assert [(request.method, request.url.path) for request in captured] == [
        ("GET", "/v1/images/pull/operations/op"),
        ("GET", "/v1/images/push/operations/op"),
    ]
    client.close()


def test_auth_verify() -> None:
    """auth_verify returns status dict."""
    client = JeballtoClient(_settings(), transport=_transport({"status": "ok"}))
    result = client.auth_verify()
    assert isinstance(result, dict)
    assert result["status"] == "ok"
    client.close()


def test_clone_vm_ephemeral_and_lifetime() -> None:
    """clone_vm sends ephemeral and lifetime settings."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=201,
            headers={"content-type": "application/json"},
            content=json.dumps({"id": "c"}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.clone_vm("src", "clone", ephemeral=True, lifetime_seconds=900)
    body = json.loads(captured[0].content)
    assert body["ephemeral"] is True
    assert body["lifetimeSeconds"] == 900
    client.close()


@pytest.mark.parametrize("status", [201, 202, 204, 302])
def test_health_rejects_undocumented_status(status: int) -> None:
    """A method accepts only its documented response status."""
    client = JeballtoClient(_settings(), transport=_transport({"status": "healthy"}, status))

    with pytest.raises(APIError) as exc_info:
        client.health()

    assert exc_info.value.status_code == status
    assert exc_info.value.code in {"UNEXPECTED_STATUS", f"HTTP_{status}"}
    client.close()


def test_system_reset_parses_partial_response_returned_with_500() -> None:
    """A reset response body remains usable when cleanup is partially unsuccessful."""
    payload = {
        "mode": "hard",
        "vmsDeleted": 1,
        "vmsFailed": 1,
        "imagesDeleted": 0,
        "imagesFailed": 0,
        "ipswCacheCleared": True,
        "configDeleted": True,
        "logsDeleted": False,
        "willTerminate": False,
        "errors": ["Could not delete one VM"],
    }
    client = JeballtoClient(_settings(), transport=_transport(payload, 500))

    result = client.system_reset("hard")

    assert result == payload
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


def test_system_capabilities_route() -> None:
    """system_capabilities calls the documented route."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps({"host": {}, "features": []}).encode(),
        )

    client = JeballtoClient(_settings(), transport=httpx.MockTransport(handler))
    client.system_capabilities()
    assert captured[0].method == "GET"
    assert captured[0].url.path == "/v1/system/capabilities"
    client.close()
