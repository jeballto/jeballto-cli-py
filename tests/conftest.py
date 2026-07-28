"""Shared test fixtures for the Jeballto CLI test suite."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from jeballto_cli.cli import app

# -- sample API responses ---------------------------------------------------

HEALTH_RESPONSE = {
    "status": "healthy",
    "version": "1.0.0",
    "vmsTotal": 2,
    "vmsRunning": 1,
    "uptime": 3600,
}

VM_RESPONSE = {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "test-vm",
    "state": "stopped",
    "resources": {
        "cpuCount": 4,
        "memorySize": 8 * 1024**3,
        "diskSize": 64 * 1024**3,
    },
    "network": {
        "macAddress": "aa:bb:cc:dd:ee:ff",
        "sshPort": None,
        "vncPort": None,
        "natIP": None,
    },
    "guiOpen": False,
    "ephemeral": False,
    "uptime": None,
    "lifetimeSeconds": None,
    "expiresAt": None,
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:00:00Z",
}

AUTH_VERIFY_RESPONSE = {"status": "ok"}

VM_LIST_RESPONSE = {"vms": [VM_RESPONSE], "total": 1, "limit": 100, "offset": 0}

VM_STATE_RESPONSE = {"state": "running", "uptime": 120}

EVENTS_RESPONSE = {
    "events": [
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "VM_CREATED",
            "vmId": VM_RESPONSE["id"],
            "data": {"name": VM_RESPONSE["name"]},
        },
    ],
    "total": 1,
}

EXECUTE_RESPONSE = {
    "vmId": VM_RESPONSE["id"],
    "exitCode": 0,
    "stdout": "hello\n",
    "stderr": "",
    "stdoutTruncated": False,
    "stderrTruncated": False,
}

KEYSTROKES_RESPONSE = {
    "vmId": VM_RESPONSE["id"],
    "keystrokesCount": 5,
    "message": "Keystrokes injected.",
}

IMAGE_RESPONSE = {
    "id": "660e8400-e29b-41d4-a716-446655440000",
    "reference": "registry.example.com/image:latest",
    "digest": "sha256:abc123",
    "localPath": "/path/to/image",
    "size": 1024000,
    "resources": {
        "cpuCount": 4,
        "memorySize": 8 * 1024**3,
        "diskSize": 64 * 1024**3,
    },
    "formatVersion": 1,
    "pulledAt": "2026-01-01T00:00:00Z",
    "pushedAt": None,
    "metadata": {"source": "test"},
}

IMAGE_LIST_RESPONSE = {"images": [IMAGE_RESPONSE], "total": 1, "limit": 100, "offset": 0}

IMAGE_OPERATION_ID = "880e8400-e29b-41d4-a716-446655440000"

IMAGE_OPERATION_RESPONSE = {
    "operationId": IMAGE_OPERATION_ID,
    "statusUrl": f"/v1/images/pull/operations/{IMAGE_OPERATION_ID}",
    "type": "pull",
    "reference": "registry.example.com/image:latest",
    "source": None,
    "status": "completed",
    "stage": None,
    "progress": 1.0,
    "stageProgress": None,
    "averageSpeedMBps": 12.5,
    "chunksCompleted": 4,
    "chunksTotal": 4,
    "bytesCompleted": 1024000,
    "bytesTotal": 1024000,
    "startedAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-01-01T00:01:00Z",
    "completedAt": "2026-01-01T00:01:00Z",
    "digest": "sha256:abc123",
    "image": IMAGE_RESPONSE,
    "error": None,
}

WIPE_RESPONSE = {"deleted": 2, "failed": 0, "errors": None}

SSH_INFO_RESPONSE = {"host": "127.0.0.1", "port": 2222, "status": "ready"}
VNC_INFO_RESPONSE = {"host": "127.0.0.1", "port": 5901, "status": "ready"}
VNC_DISABLED_RESPONSE = {"host": "127.0.0.1", "port": None, "status": "disabled"}
GUI_STATUS_RESPONSE = {"vmId": VM_RESPONSE["id"], "guiOpen": True}
GUI_CLOSED_RESPONSE = {"vmId": VM_RESPONSE["id"], "guiOpen": False}

INSTALL_STATUS_RESPONSE = {
    "vmId": VM_RESPONSE["id"],
    "status": "completed",
    "progress": 1.0,
    "phaseProgress": 1.0,
    "message": "Installation complete.",
    "phase": "completed",
    "bytesDownloaded": 1024,
    "bytesTotal": 1024,
    "downloadSpeed": 1024,
}

CONFIG_RESPONSE = {
    "api": {"port": 8011, "host": "0.0.0.0", "maxConcurrentRequests": 100},
    "logging": {
        "level": "info",
        "enableFileLogging": True,
        "retentionDays": 7,
        "maxTotalSize": "2GB",
        "timezone": None,
    },
    "networking": {
        "sshPortRangeStart": 2200,
        "sshPortRangeEnd": 2300,
        "autoEnableSSHForwarding": True,
        "vncPortRangeStart": 5901,
        "vncPortRangeEnd": 5902,
    },
    "images": {
        "defaultRegistry": None,
        "insecureRegistries": [],
        "maxParallelImageBlobTransfers": 16,
        "maxParallelImageCompressions": 4,
        "maxParallelImageDecompressions": 2,
        "maxParallelImageDiskWrites": 1,
    },
}

REGISTRY_LOGIN_RESPONSE = {
    "registry": "registry.example.com",
    "status": "authenticated",
}

SUCCESS_RESPONSE = {"success": True, "message": "Done."}

JEBALLTOFILE_RESPONSE = {
    "id": "770e8400-e29b-41d4-a716-446655440000",
    "vmId": VM_RESPONSE["id"],
    "status": "running",
    "currentStep": 0,
    "totalSteps": 2,
    "message": "Execution started.",
}

JEBALLTOFILE_STATUS_RESPONSE = {
    "id": "770e8400-e29b-41d4-a716-446655440000",
    "vmId": VM_RESPONSE["id"],
    "status": "completed",
    "currentStep": 1,
    "totalSteps": 2,
    "stepResults": [
        {"step": 0, "type": "start", "status": "completed", "message": None},
        {"step": 1, "type": "execute", "status": "completed", "message": None},
    ],
    "error": None,
}

JEBALLTOFILE_LIST_RESPONSE = {
    "executions": [JEBALLTOFILE_STATUS_RESPONSE],
    "total": 1,
}

SYSTEM_RESET_RESPONSE = {
    "mode": "soft",
    "vmsDeleted": 2,
    "vmsFailed": 0,
    "imagesDeleted": 1,
    "imagesFailed": 0,
    "ipswCacheCleared": True,
    "configDeleted": False,
    "logsDeleted": False,
    "willTerminate": False,
    "errors": None,
}

SYSTEM_CAPABILITIES_RESPONSE = {
    "host": {
        "architecture": "arm64",
        "macOSVersion": "26.5",
        "virtualizationSupported": True,
        "maxConcurrentVMs": 2,
    },
    "features": [
        {
            "id": "macOSVirtualization",
            "status": "available",
            "enabled": True,
            "lifecycle": "stable",
            "minimumOS": "26.0",
            "deprecation": None,
            "reason": None,
        },
        {
            "id": "ociImagePackaging",
            "status": "available",
            "enabled": True,
            "lifecycle": "development",
            "minimumOS": "26.0",
            "deprecation": None,
            "reason": None,
        },
    ],
}

# -- route table type -------------------------------------------------------

RouteHandler = Callable[[httpx.Request], httpx.Response]


def _json_response(data: Any, status: int = 200) -> httpx.Response:
    """Build an httpx.Response with a JSON body.

    Args:
        data: JSON-serializable payload.
        status: HTTP status code.

    Returns:
        An httpx.Response.
    """
    return httpx.Response(
        status_code=status,
        headers={"content-type": "application/json"},
        content=json.dumps(data).encode(),
    )


# Default route map keyed by (METHOD, path)
DEFAULT_ROUTES: dict[tuple[str, str], tuple[Any, int]] = {
    ("GET", "/health"): (HEALTH_RESPONSE, 200),
    ("GET", "/config"): (CONFIG_RESPONSE, 200),
    ("PATCH", "/config"): (CONFIG_RESPONSE, 200),
    ("GET", "/system/capabilities"): (SYSTEM_CAPABILITIES_RESPONSE, 200),
    ("POST", "/vms"): (VM_RESPONSE, 201),
    ("GET", "/vms"): (VM_LIST_RESPONSE, 200),
    ("DELETE", "/vms"): (WIPE_RESPONSE, 200),
    ("GET", "/images"): (IMAGE_LIST_RESPONSE, 200),
    ("DELETE", "/images"): (WIPE_RESPONSE, 200),
    ("POST", "/registries/login"): (REGISTRY_LOGIN_RESPONSE, 200),
    ("POST", "/registries/logout"): (SUCCESS_RESPONSE, 200),
    ("POST", "/jeballtofiles"): (JEBALLTOFILE_RESPONSE, 202),
    ("GET", "/jeballtofiles"): (JEBALLTOFILE_LIST_RESPONSE, 200),
    ("GET", "/auth/verify"): (AUTH_VERIFY_RESPONSE, 200),
}

# Routes with path patterns containing a UUID segment
DEFAULT_VM_ROUTES: dict[tuple[str, str], tuple[Any, int]] = {
    ("GET", "get"): (VM_RESPONSE, 200),
    ("DELETE", "delete"): (None, 204),
    ("POST", "start"): (VM_RESPONSE, 200),
    ("POST", "stop"): (VM_RESPONSE, 200),
    ("POST", "pause"): (VM_RESPONSE, 200),
    ("POST", "resume"): (VM_RESPONSE, 200),
    ("POST", "clone"): (VM_RESPONSE, 201),
    ("POST", "execute"): (EXECUTE_RESPONSE, 200),
    ("POST", "keystrokes"): (KEYSTROKES_RESPONSE, 200),
    ("GET", "state"): (VM_STATE_RESPONSE, 200),
    ("GET", "events"): (EVENTS_RESPONSE, 200),
    ("POST", "install"): (INSTALL_STATUS_RESPONSE, 202),
    ("GET", "install/status"): (INSTALL_STATUS_RESPONSE, 200),
    ("GET", "ssh"): (SSH_INFO_RESPONSE, 200),
    ("POST", "ssh"): (SSH_INFO_RESPONSE, 200),
    ("DELETE", "ssh"): ({"host": "127.0.0.1", "port": None, "status": "disabled"}, 200),
    ("GET", "vnc"): (VNC_INFO_RESPONSE, 200),
    ("POST", "vnc"): (VNC_INFO_RESPONSE, 200),
    ("DELETE", "vnc"): (VNC_DISABLED_RESPONSE, 200),
    ("POST", "gui"): (GUI_STATUS_RESPONSE, 200),
    ("DELETE", "gui"): (GUI_CLOSED_RESPONSE, 200),
    ("GET", "gui"): (GUI_STATUS_RESPONSE, 200),
    ("GET", "screenshot"): (b"\x89PNG\r\n", 200),
    ("PATCH", "update"): (VM_RESPONSE, 200),
}

DEFAULT_IMAGE_ROUTES: dict[tuple[str, str], tuple[Any, int]] = {
    ("GET", "get"): (IMAGE_RESPONSE, 200),
    ("DELETE", "delete"): (None, 204),
}

DEFAULT_JEBALLTOFILE_ROUTES: dict[tuple[str, str], tuple[Any, int]] = {
    ("GET", "get"): (JEBALLTOFILE_STATUS_RESPONSE, 200),
    ("DELETE", "delete"): (SUCCESS_RESPONSE, 200),
    ("POST", "cancel"): (SUCCESS_RESPONSE, 200),
}


def _build_transport() -> httpx.MockTransport:
    """Create an httpx.MockTransport that routes to canned responses.

    Returns:
        A MockTransport for use in JeballtoClient.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        """Route requests to canned responses."""
        method = request.method
        # Strip the /v1 prefix that httpx prepends from base_url
        raw_path = request.url.path
        path = raw_path.removeprefix("/v1") if raw_path.startswith("/v1") else raw_path

        # System reset response varies by requested mode.
        if method == "POST" and path == "/system/reset":
            mode = "soft"
            if request.content:
                payload = json.loads(request.content)
                if isinstance(payload, dict) and payload.get("mode") in ("soft", "hard"):
                    mode = str(payload["mode"])
            data = dict(SYSTEM_RESET_RESPONSE)
            data["mode"] = mode
            data["willTerminate"] = mode == "hard"
            data["configDeleted"] = mode == "hard"
            data["logsDeleted"] = mode == "hard"
            return _json_response(data, 200)

        if method == "POST" and path in {"/images/pull", "/images/push"}:
            payload: dict[str, Any] = {}
            if request.content:
                loaded = json.loads(request.content)
                if isinstance(loaded, dict):
                    payload = loaded
            is_pull = path == "/images/pull"
            operation_data = dict(IMAGE_OPERATION_RESPONSE)
            operation_data["type"] = "pull" if is_pull else "push"
            operation_data["statusUrl"] = (
                f"/v1/images/{'pull' if is_pull else 'push'}/operations/{IMAGE_OPERATION_ID}"
            )
            if not is_pull:
                operation_data["source"] = f"vm:{VM_RESPONSE['id']}"
                operation_data["stage"] = "uploading"
            if payload.get("async") is True:
                operation_data["status"] = "started"
                operation_data["progress"] = 0.0
                operation_data["stageProgress"] = 0.0 if not is_pull else None
                operation_data["completedAt"] = None
                operation_data["digest"] = None
                operation_data["image"] = None
                return _json_response(operation_data, 202)
            return _json_response(operation_data, 200)

        # Exact match
        key = (method, path)
        if key in DEFAULT_ROUTES:
            data, status = DEFAULT_ROUTES[key]
            if data is None:
                return httpx.Response(status_code=status)
            return _json_response(data, status)

        # VM routes: /vms/{uuid}/...
        parts = path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] == "vms":
            suffix_parts = parts[2:] if len(parts) > 2 else ["get"]
            if not suffix_parts:
                suffix_parts = ["get"]
            suffix = "/".join(suffix_parts) if suffix_parts != ["get"] else "get"
            # Handle bare /vms/{id} as GET, PATCH, or DELETE
            if len(parts) == 2:
                if method == "GET":
                    suffix = "get"
                elif method == "PATCH":
                    suffix = "update"
                else:
                    suffix = "delete"
            vm_key = (method, suffix)
            if vm_key in DEFAULT_VM_ROUTES:
                data, status = DEFAULT_VM_ROUTES[vm_key]
                if isinstance(data, bytes):
                    return httpx.Response(
                        status_code=status,
                        headers={"content-type": "image/png"},
                        content=data,
                    )
                if data is None:
                    return httpx.Response(status_code=status)
                return _json_response(data, status)

        # Image operation routes: /images/{pull|push}/operations[/...]
        if (
            len(parts) >= 3
            and parts[0] == "images"
            and parts[1] in {"pull", "push"}
            and parts[2] == "operations"
        ):
            operation_data = dict(IMAGE_OPERATION_RESPONSE)
            operation_data["type"] = parts[1]
            operation_data["statusUrl"] = f"/v1/images/{parts[1]}/operations/{IMAGE_OPERATION_ID}"
            if parts[1] == "push":
                operation_data["type"] = "push"
                operation_data["source"] = f"vm:{VM_RESPONSE['id']}"
                operation_data["stage"] = "uploading"
            if len(parts) == 3 and method == "GET":
                data = {
                    "operations": [operation_data],
                    "total": 1,
                    "activeOnly": request.url.params.get("activeOnly", "true") != "false",
                    "type": parts[1],
                }
                return _json_response(data, 200)
            if len(parts) == 3 and method == "DELETE":
                operation_data["status"] = "cancelled"
                operation_data["error"] = "Cancelled by user."
                data = {
                    "cancelled": 1,
                    "tasksCancelled": 1,
                    "operations": [operation_data],
                }
                return _json_response(data, 200)
            if len(parts) == 4 and method == "GET":
                return _json_response(operation_data, 200)
            if len(parts) == 4 and method == "DELETE":
                operation_data["status"] = "cancelled"
                operation_data["error"] = "Cancelled by user."
                return _json_response(operation_data, 200)

        # Image routes: /images/{uuid}
        if len(parts) == 2 and parts[0] == "images":
            suffix = "get" if method == "GET" else "delete"
            img_key = (method, suffix)
            if img_key in DEFAULT_IMAGE_ROUTES:
                data, status = DEFAULT_IMAGE_ROUTES[img_key]
                if data is None:
                    return httpx.Response(status_code=status)
                return _json_response(data, status)

        # Jeballtofile routes: /jeballtofiles/{uuid}[/cancel]
        if len(parts) >= 2 and parts[0] == "jeballtofiles":
            suffix_parts = parts[2:] if len(parts) > 2 else ["get"]
            if not suffix_parts:
                suffix_parts = ["get"]
            suffix = "/".join(suffix_parts) if suffix_parts != ["get"] else "get"
            if len(parts) == 2:
                suffix = "get" if method == "GET" else "delete"
            jeballtofile_key = (method, suffix)
            if jeballtofile_key in DEFAULT_JEBALLTOFILE_ROUTES:
                data, status = DEFAULT_JEBALLTOFILE_ROUTES[jeballtofile_key]
                if data is None:
                    return httpx.Response(status_code=status)
                return _json_response(data, status)

        return httpx.Response(status_code=404, content=b"Not Found")

    return httpx.MockTransport(handler)


@pytest.fixture
def runner() -> CliRunner:
    """Provide a Typer CLI test runner.

    Returns:
        A CliRunner instance with separate stdout and stderr capture.
    """
    return CliRunner()


@pytest.fixture
def mock_transport() -> httpx.MockTransport:
    """Provide a mock HTTP transport with canned API responses.

    Returns:
        An httpx.MockTransport.
    """
    return _build_transport()


@pytest.fixture
def invoke(
    runner: CliRunner,
    mock_transport: httpx.MockTransport,
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., Any]:
    """Provide a helper that invokes the CLI with a mocked API backend.

    Args:
        runner: The CliRunner fixture.
        mock_transport: The mock HTTP transport fixture.
        monkeypatch: Pytest monkeypatch for setting env vars.

    Returns:
        A callable that accepts CLI args and returns the CliRunner result.
    """
    monkeypatch.setenv("JEBALLTO_BASE_URL", "http://test:8011/v1")
    monkeypatch.setenv("JEBALLTO_TOKEN", "test-token")

    # Patch httpx.Client to always inject our mock transport
    _orig_httpx_init = httpx.Client.__init__

    def _patched_httpx_init(self: Any, **kwargs: Any) -> None:
        kwargs["transport"] = mock_transport
        _orig_httpx_init(self, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", _patched_httpx_init)

    def _invoke(args: list[str], **kwargs: Any) -> Any:
        return runner.invoke(app, args, **kwargs)

    return _invoke
