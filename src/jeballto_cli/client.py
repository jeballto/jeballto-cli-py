"""HTTP client wrapper for the Jeballto VM Agent REST API."""

from __future__ import annotations

from typing import Any

import httpx

from jeballto_cli import __version__
from jeballto_cli.settings import Settings

JSONValue = dict[str, Any] | list[Any] | str | int | float | bool | bytes | None
ResourceSize = str | int
REQUEST_TIMEOUT_CUSHION = 30.0
VM_EXECUTE_MAX_TIMEOUT = 600
IMAGE_OPERATION_MAX_TIMEOUT = 604_800


def _operation_request_timeout(
    timeout: int | None,
    *,
    max_timeout: int | None = None,
) -> float | None:
    if timeout is None:
        return None
    if timeout < 1:
        raise ValueError("timeout must be at least 1 second")
    if max_timeout is not None and timeout > max_timeout:
        raise ValueError(f"timeout must be between 1 and {max_timeout} seconds")
    return timeout + REQUEST_TIMEOUT_CUSHION


def _combine_image_operation_cancellations(*responses: JSONValue) -> JSONValue:
    """Combine typed image operation cancellation responses."""
    cancelled = 0
    tasks_cancelled = 0
    operations: list[Any] = []
    for response in responses:
        if not isinstance(response, dict):
            continue
        raw_cancelled = response.get("cancelled")
        raw_tasks_cancelled = response.get("tasksCancelled")
        raw_operations = response.get("operations")
        if isinstance(raw_cancelled, int):
            cancelled += raw_cancelled
        if isinstance(raw_tasks_cancelled, int):
            tasks_cancelled += raw_tasks_cancelled
        if isinstance(raw_operations, list):
            operations.extend(raw_operations)
    return {
        "cancelled": cancelled,
        "tasksCancelled": tasks_cancelled,
        "operations": operations,
    }


class APIError(Exception):
    """Structured error returned by the Jeballto API.

    Attributes:
        status_code: HTTP status code (0 for network errors).
        code: Machine-readable error code.
        message: Human-readable error description.
        details: Optional extra context from the API.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        payload: JSONValue = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.payload = payload
        super().__init__(message)

    def __str__(self) -> str:
        """Return a compact string representation."""
        return f"{self.code} ({self.status_code}): {self.message}"


class JeballtoClient:
    """Typed HTTP client for the Jeballto VM Agent API.

    Args:
        settings: Resolved application settings.
        transport: Optional custom transport (useful for testing).
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {
            "User-Agent": f"jeballto-cli/{__version__}",
            "Accept": "application/json",
        }
        if settings.token:
            headers["Authorization"] = f"Bearer {settings.token}"

        self._client = httpx.Client(
            base_url=settings.base_url,
            timeout=httpx.Timeout(settings.request_timeout, connect=10.0),
            verify=not settings.insecure,
            headers=headers,
            transport=transport,
        )

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> JeballtoClient:
        """Enter the runtime context."""
        return self

    def __exit__(self, *_args: object) -> None:
        """Exit the runtime context and close the HTTP client."""
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    # -- generic request ----------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        expected_status: int | set[int] = 200,
        expect_binary: bool = False,
        headers: dict[str, str] | None = None,
        request_timeout: float | None = None,
    ) -> JSONValue | bytes | None:
        """Send an HTTP request to the agent API.

        Args:
            method: HTTP method (GET, POST, DELETE, PATCH, ...).
            path: URL path relative to the base URL.
            params: Optional query parameters.
            json_body: Optional JSON request body.
            expected_status: Acceptable status code(s).
            expect_binary: If ``True``, return raw bytes instead of JSON.
            headers: Extra request headers.
            request_timeout: Optional HTTP transport timeout in seconds.

        Returns:
            Parsed JSON, raw bytes, or ``None`` for 204 responses.

        Raises:
            APIError: On network errors or non-2xx responses.
        """
        request_headers = headers or {}

        try:
            kwargs: dict[str, Any] = {
                "method": method,
                "url": path,
                "params": params,
                "json": json_body,
                "headers": request_headers,
            }
            if request_timeout is not None:
                kwargs["timeout"] = httpx.Timeout(request_timeout, connect=10.0)
            response = self._client.request(**kwargs)
        except httpx.TimeoutException as exc:
            details = None
            if request_timeout is not None:
                details = {"timeout": str(request_timeout)}
            raise APIError(
                status_code=0,
                code="REQUEST_TIMEOUT",
                message="Request timed out",
                details=details,
            ) from exc
        except httpx.HTTPError as exc:
            raise APIError(
                status_code=0,
                code="NETWORK_ERROR",
                message=str(exc),
                details=None,
            ) from exc

        allowed = {expected_status} if isinstance(expected_status, int) else expected_status
        if response.status_code not in allowed and not 200 <= response.status_code < 300:
            raise self._api_error(response)
        if response.status_code not in allowed:
            raise APIError(
                status_code=response.status_code,
                code="UNEXPECTED_STATUS",
                message=(f"Expected status {sorted(allowed)}, got {response.status_code}"),
                details=None,
            )

        if expect_binary:
            return response.content

        if response.status_code == 204 or not response.content:
            return None

        content_type = response.headers.get("content-type", "")
        media_type = content_type.partition(";")[0].strip().casefold()
        if media_type != "application/json" and not media_type.endswith("+json"):
            raise APIError(
                status_code=response.status_code,
                code="INVALID_RESPONSE",
                message=f"Agent returned an unexpected content type: {content_type or 'missing'}",
            )
        try:
            return response.json()
        except ValueError as exc:
            raise APIError(
                status_code=response.status_code,
                code="INVALID_RESPONSE",
                message="Agent returned malformed JSON",
            ) from exc

    def _api_error(self, response: httpx.Response) -> APIError:
        """Parse an error response into an ``APIError``.

        Args:
            response: The HTTP response with a 4xx/5xx status.

        Returns:
            A structured ``APIError``.
        """
        code = f"HTTP_{response.status_code}"
        message = response.reason_phrase or "Request failed"
        details: dict[str, Any] | None = None

        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            error_obj = payload.get("error")
            if isinstance(error_obj, dict):
                raw_code = error_obj.get("code")
                raw_message = error_obj.get("message")

                if raw_code is not None:
                    code = str(raw_code)
                if raw_message is not None:
                    message = str(raw_message)

                raw_details = error_obj.get("details")
                if isinstance(raw_details, dict):
                    details = {str(k): v for k, v in raw_details.items()}

        return APIError(
            status_code=response.status_code,
            code=code,
            message=message,
            details=details,
            payload=payload,
        )

    # -- health & config ----------------------------------------------------

    def health(self) -> JSONValue:
        """Check agent health.

        Returns:
            Health status dict with version, VM counts, and uptime.
        """
        return self.request("GET", "/health")

    def get_config(self) -> JSONValue:
        """Get the agent runtime configuration.

        Returns:
            Configuration dict (sensitive values excluded).
        """
        return self.request("GET", "/config")

    def update_config(self, updates: dict[str, Any]) -> JSONValue:
        """Update the agent runtime configuration.

        Args:
            updates: Partial config update (logging, networking, images).

        Returns:
            Updated configuration dict.
        """
        return self.request("PATCH", "/config", json_body=updates)

    # -- auth ---------------------------------------------------------------

    def auth_verify(self) -> JSONValue:
        """Verify the bearer token.

        Returns:
            ``{"status": "ok"}`` when token is valid.
        """
        return self.request("GET", "/auth/verify")

    # -- VM CRUD ------------------------------------------------------------

    def create_vm(
        self,
        name: str,
        *,
        cpu: int | None = None,
        memory: ResourceSize | None = None,
        disk: ResourceSize | None = None,
        image: str | None = None,
        ephemeral: bool | None = None,
        lifetime_seconds: int | None = None,
    ) -> JSONValue:
        """Create a new virtual machine.

        Args:
            name: VM display name.
            cpu: Number of CPU cores.
            memory: Memory size (e.g. "8GB").
            disk: Disk size (e.g. "64GB").
            image: Optional OCI image reference to restore from. Mutually
                exclusive with ``cpu``/``memory``/``disk``.
            ephemeral: When true, VM auto-deletes on terminal state.
            lifetime_seconds: Max lifetime in seconds from first RUNNING.

        Returns:
            Created VM details.
        """
        body: dict[str, Any] = {"name": name}
        if image is not None and (cpu is not None or memory is not None or disk is not None):
            raise ValueError("resources cannot be combined with image; use update_vm after create")
        resources: dict[str, Any] = {}
        if cpu is not None:
            resources["cpuCount"] = cpu
        if memory is not None:
            resources["memorySize"] = memory
        if disk is not None:
            resources["diskSize"] = disk
        if resources:
            body["resources"] = resources
        if image is not None:
            body["image"] = image
        if ephemeral is not None:
            body["ephemeral"] = ephemeral
        if lifetime_seconds is not None:
            body["lifetimeSeconds"] = lifetime_seconds
        return self.request("POST", "/vms", json_body=body, expected_status=201)

    def update_vm(
        self,
        vm_id: str,
        *,
        name: str | None = None,
        cpu: int | None = None,
        memory: ResourceSize | None = None,
        disk: ResourceSize | None = None,
    ) -> JSONValue:
        """Update VM name and/or resources (PATCH).

        Name changeable any non-deleted state. Resource changes need
        stopped/created. Disk grow-only. Resource changes apply on next start.

        Args:
            vm_id: VM identifier (UUID).
            name: New VM name.
            cpu: New CPU count.
            memory: New memory size (e.g. "16GB").
            disk: New disk size (e.g. "128GB"). Grow only.

        Returns:
            Updated VM details.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        resources: dict[str, Any] = {}
        if cpu is not None:
            resources["cpuCount"] = cpu
        if memory is not None:
            resources["memorySize"] = memory
        if disk is not None:
            resources["diskSize"] = disk
        if resources:
            body["resources"] = resources
        if not body:
            raise ValueError("update_vm requires at least one field")
        return self.request("PATCH", f"/vms/{vm_id}", json_body=body)

    def list_vms(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> JSONValue:
        """List virtual machines with optional pagination.

        Args:
            limit: Maximum number of results to return (1-1000).
            offset: Number of results to skip.

        Returns:
            Dict with ``vms`` list, ``total`` count, and optional ``limit``/``offset``.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        return self.request("GET", "/vms", params=params or None)

    def get_vm(self, vm_id: str) -> JSONValue:
        """Get details for a single VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            VM details dict.
        """
        return self.request("GET", f"/vms/{vm_id}")

    def delete_vm(self, vm_id: str, *, force: bool = False) -> None:
        """Delete a virtual machine.

        Args:
            vm_id: VM identifier (UUID).
            force: Force deletion even if the VM is running.
        """
        params: dict[str, Any] = {}
        if force:
            params["force"] = "true"
        self.request("DELETE", f"/vms/{vm_id}", params=params, expected_status=204)

    def wipe_vms(self) -> JSONValue:
        """Delete all virtual machines.

        Returns:
            Dict with ``deleted`` and ``failed`` counts.
        """
        return self.request("DELETE", "/vms", params={"confirm": "true"})

    # -- VM lifecycle -------------------------------------------------------

    def start_vm(self, vm_id: str) -> JSONValue:
        """Start a virtual machine.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            Updated VM details.
        """
        return self.request("POST", f"/vms/{vm_id}/start")

    def stop_vm(self, vm_id: str) -> JSONValue:
        """Stop a virtual machine.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            Updated VM details.
        """
        return self.request("POST", f"/vms/{vm_id}/stop")

    def pause_vm(self, vm_id: str) -> JSONValue:
        """Pause a virtual machine.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            Updated VM details.
        """
        return self.request("POST", f"/vms/{vm_id}/pause")

    def resume_vm(self, vm_id: str) -> JSONValue:
        """Resume a paused virtual machine.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            Updated VM details.
        """
        return self.request("POST", f"/vms/{vm_id}/resume")

    def clone_vm(
        self,
        vm_id: str,
        name: str,
        *,
        cpu: int | None = None,
        memory: ResourceSize | None = None,
        disk: ResourceSize | None = None,
        force: bool = False,
        ephemeral: bool | None = None,
        lifetime_seconds: int | None = None,
    ) -> JSONValue:
        """Clone a virtual machine.

        Args:
            vm_id: Source VM identifier (UUID).
            name: Name for the cloned VM.
            cpu: Override CPU count.
            memory: Override memory size (e.g. "8GB").
            disk: Override disk size (e.g. "64GB").
            force: Auto-stop the source VM if it is running.
            ephemeral: Whether the clone should be disposable.
            lifetime_seconds: Maximum clone lifetime after its first start.

        Returns:
            Cloned VM details.
        """
        body: dict[str, Any] = {"name": name}
        resources: dict[str, Any] = {}
        if cpu is not None:
            resources["cpuCount"] = cpu
        if memory is not None:
            resources["memorySize"] = memory
        if disk is not None:
            resources["diskSize"] = disk
        if resources:
            body["resources"] = resources
        if ephemeral is not None:
            body["ephemeral"] = ephemeral
        if lifetime_seconds is not None:
            body["lifetimeSeconds"] = lifetime_seconds
        params: dict[str, Any] = {}
        if force:
            params["force"] = "true"
        return self.request(
            "POST",
            f"/vms/{vm_id}/clone",
            json_body=body,
            params=params,
            expected_status=201,
        )

    def execute(
        self,
        vm_id: str,
        command: str,
        *,
        user: str = "admin",
        password: str | None = None,
        timeout: int | None = None,
    ) -> JSONValue:
        """Execute a command inside a VM via SSH.

        Args:
            vm_id: VM identifier (UUID).
            command: Shell command to run.
            user: SSH user (default ``admin``).
            password: SSH password.
            timeout: Command timeout in seconds. If omitted, the agent uses its default.

        Returns:
            Dict with ``exitCode``, ``stdout``, and ``stderr``.
        """
        body: dict[str, Any] = {"command": command, "user": user}
        if password is not None:
            body["password"] = password
        if timeout is not None:
            body["timeout"] = timeout
        request_timeout = _operation_request_timeout(timeout, max_timeout=VM_EXECUTE_MAX_TIMEOUT)
        return self.request(
            "POST",
            f"/vms/{vm_id}/execute",
            json_body=body,
            request_timeout=request_timeout,
        )

    def keystrokes(self, vm_id: str, keys: list[str]) -> JSONValue:
        """Inject keystrokes into a VM.

        Args:
            vm_id: VM identifier (UUID).
            keys: List of keystroke strings (DSL).

        Returns:
            Dict with ``keystrokesCount`` and ``message``.
        """
        return self.request(
            "POST",
            f"/vms/{vm_id}/keystrokes",
            json_body={"keystrokes": keys},
        )

    # -- installation -------------------------------------------------------

    def install(self, vm_id: str, *, source: str | None = None) -> JSONValue:
        """Start macOS installation on a VM.

        Args:
            vm_id: VM identifier (UUID).
            source: IPSW source - HTTPS URL, ``file://`` URL, or absolute path.
                    If omitted, the latest macOS is downloaded from Apple.
                    HTTP (non-HTTPS) URLs are rejected by the agent.

        Returns:
            Installation status dict.
        """
        body: dict[str, Any] = {}
        if source is not None:
            body["source"] = source
        return self.request(
            "POST",
            f"/vms/{vm_id}/install",
            json_body=body or None,
            expected_status=202,
        )

    def install_status(self, vm_id: str) -> JSONValue:
        """Get macOS installation status.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            Installation status dict with progress info.
        """
        return self.request("GET", f"/vms/{vm_id}/install/status")

    # -- SSH ----------------------------------------------------------------

    def ssh_info(self, vm_id: str) -> JSONValue:
        """Get SSH connection info for a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            Dict with host, port, and status.
        """
        return self.request("GET", f"/vms/{vm_id}/ssh")

    def ssh_enable(self, vm_id: str) -> JSONValue:
        """Enable SSH forwarding for a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            SSH connection info dict.
        """
        return self.request("POST", f"/vms/{vm_id}/ssh")

    def ssh_disable(self, vm_id: str) -> JSONValue:
        """Disable SSH forwarding for a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            Status dict.
        """
        return self.request("DELETE", f"/vms/{vm_id}/ssh")

    # -- VNC ----------------------------------------------------------------

    def vnc_info(self, vm_id: str) -> JSONValue:
        """Get VNC connection info for a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            Dict with host, port, and status.
        """
        return self.request("GET", f"/vms/{vm_id}/vnc")

    def vnc_enable(self, vm_id: str) -> JSONValue:
        """Enable VNC forwarding for a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            VNC connection info dict.
        """
        return self.request("POST", f"/vms/{vm_id}/vnc")

    def vnc_disable(self, vm_id: str) -> JSONValue:
        """Disable VNC forwarding for a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            VNC status dict.
        """
        return self.request("DELETE", f"/vms/{vm_id}/vnc")

    # -- GUI ----------------------------------------------------------------

    def gui_open(self, vm_id: str) -> JSONValue:
        """Open a GUI window for a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            GUI status dict.
        """
        return self.request("POST", f"/vms/{vm_id}/gui")

    def gui_close(self, vm_id: str) -> JSONValue:
        """Close the GUI window for a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            GUI status dict.
        """
        return self.request("DELETE", f"/vms/{vm_id}/gui")

    def gui_status(self, vm_id: str) -> JSONValue:
        """Get GUI window status for a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            GUI status dict.
        """
        return self.request("GET", f"/vms/{vm_id}/gui")

    def screenshot(self, vm_id: str) -> bytes:
        """Capture a screenshot of a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            Raw PNG image bytes.
        """
        result = self.request("GET", f"/vms/{vm_id}/screenshot", expect_binary=True)
        assert isinstance(result, bytes)
        return result

    # -- monitoring ---------------------------------------------------------

    def vm_state(self, vm_id: str) -> JSONValue:
        """Get the current state of a VM.

        Args:
            vm_id: VM identifier (UUID).

        Returns:
            Dict with ``state`` and optional ``uptime``.
        """
        return self.request("GET", f"/vms/{vm_id}/state")

    def vm_events(self, vm_id: str, *, limit: int = 100) -> JSONValue:
        """Get events for a VM.

        Args:
            vm_id: VM identifier (UUID).
            limit: Maximum number of events (1-1000, default 100).

        Returns:
            Dict with ``events`` list and ``total`` count.
        """
        return self.request("GET", f"/vms/{vm_id}/events", params={"limit": limit})

    # -- images -------------------------------------------------------------

    def list_images(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> JSONValue:
        """List OCI images with optional pagination.

        Args:
            limit: Maximum number of results to return (1-1000).
            offset: Number of results to skip.

        Returns:
            Dict with ``images`` list, ``total`` count, and optional ``limit``/``offset``.
        """
        params: dict[str, Any] = {}
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        return self.request("GET", "/images", params=params or None)

    def get_image(self, image_id: str) -> JSONValue:
        """Get details for an OCI image.

        Args:
            image_id: Image identifier (UUID).

        Returns:
            Image details dict.
        """
        return self.request("GET", f"/images/{image_id}")

    def delete_image(self, image_id: str) -> None:
        """Delete an OCI image.

        Args:
            image_id: Image identifier (UUID).
        """
        self.request("DELETE", f"/images/{image_id}", expected_status=204)

    def wipe_images(self) -> JSONValue:
        """Delete all OCI images.

        Returns:
            Dict with ``deleted`` and ``failed`` counts.
        """
        return self.request("DELETE", "/images", params={"confirm": "true"})

    def pull_image(
        self,
        reference: str,
        *,
        timeout: int | None = None,
        async_: bool = False,
    ) -> JSONValue:
        """Pull an OCI image from a registry.

        Args:
            reference: Image reference (e.g. ``registry.example.com/image:tag``).
            timeout: Optional timeout in seconds.
            async_: Start the operation in the background.

        Returns:
            Image operation status dict.
        """
        body: dict[str, Any] = {"reference": reference}
        if timeout is not None:
            _operation_request_timeout(timeout, max_timeout=IMAGE_OPERATION_MAX_TIMEOUT)
            body["timeout"] = timeout
        if async_:
            body["async"] = True
        request_timeout = (
            None
            if async_
            else _operation_request_timeout(
                timeout,
                max_timeout=IMAGE_OPERATION_MAX_TIMEOUT,
            )
        )
        return self.request(
            "POST",
            "/images/pull",
            json_body=body,
            expected_status=202 if async_ else 200,
            request_timeout=request_timeout,
        )

    def list_image_operations(
        self,
        *,
        type_: str | None = None,
        active_only: bool = True,
    ) -> JSONValue:
        """List asynchronous image operations.

        Args:
            type_: Optional operation type, ``pull`` or ``push``.
            active_only: Whether to show only non-terminal operations.

        Returns:
            Dict with operations, total, activeOnly, and optional type.
        """
        if type_ is not None:
            return self._list_typed_image_operations(type_, active_only=active_only)

        pull_data = self._list_typed_image_operations("pull", active_only=active_only)
        push_data = self._list_typed_image_operations("push", active_only=active_only)
        operations = []
        if isinstance(pull_data, dict) and isinstance(pull_data.get("operations"), list):
            operations.extend(pull_data["operations"])
        if isinstance(push_data, dict) and isinstance(push_data.get("operations"), list):
            operations.extend(push_data["operations"])
        operations.sort(
            key=lambda item: str(item.get("startedAt", "")) if isinstance(item, dict) else "",
            reverse=True,
        )
        return {
            "operations": operations,
            "total": len(operations),
            "activeOnly": active_only,
            "type": None,
        }

    def _list_typed_image_operations(self, type_: str, *, active_only: bool) -> JSONValue:
        """List image operations for one operation type."""
        return self.request(
            "GET",
            f"/images/{type_}/operations",
            params={"activeOnly": str(active_only).lower()},
        )

    def image_operation(self, operation_id: str, *, type_: str | None = None) -> JSONValue:
        """Get status for an asynchronous image operation.

        Args:
            operation_id: Image operation ID.
            type_: Optional operation type, ``pull`` or ``push``.

        Returns:
            Image operation status dict.
        """
        if type_ is not None:
            return self.request("GET", f"/images/{type_}/operations/{operation_id}")
        try:
            return self.image_operation(operation_id, type_="pull")
        except APIError as exc:
            if exc.status_code != 404:
                raise
        return self.image_operation(operation_id, type_="push")

    def cancel_image_operation(self, operation_id: str, *, type_: str | None = None) -> JSONValue:
        """Cancel an asynchronous image operation.

        Args:
            operation_id: Image operation ID.
            type_: Optional operation type, ``pull`` or ``push``.

        Returns:
            Terminal image operation status dict.
        """
        if type_ is not None:
            return self.request("DELETE", f"/images/{type_}/operations/{operation_id}")
        try:
            return self.cancel_image_operation(operation_id, type_="pull")
        except APIError as exc:
            if exc.status_code != 404:
                raise
        return self.cancel_image_operation(operation_id, type_="push")

    def cancel_image_operations(self, *, type_: str | None = None) -> JSONValue:
        """Cancel active asynchronous image operations.

        Args:
            type_: Optional operation type, ``pull`` or ``push``.

        Returns:
            Dict with cancellation counts and final operation statuses.
        """
        if type_ is not None:
            return self.request("DELETE", f"/images/{type_}/operations")

        pull_data = self.request("DELETE", "/images/pull/operations")
        push_data = self.request("DELETE", "/images/push/operations")
        return _combine_image_operation_cancellations(pull_data, push_data)

    def push_image(
        self,
        reference: str,
        *,
        source: str,
        timeout: int | None = None,
        async_: bool = False,
    ) -> JSONValue:
        """Push an image to an OCI registry.

        Args:
            reference: Target image reference.
            source: Push source in the format ``'vm:<uuid>'`` or ``'image:<uuid>'``.
            timeout: Optional timeout in seconds.
            async_: Start the operation in the background.

        Returns:
            Image operation status dict.
        """
        body: dict[str, Any] = {"reference": reference, "source": source}
        if timeout is not None:
            _operation_request_timeout(timeout, max_timeout=IMAGE_OPERATION_MAX_TIMEOUT)
            body["timeout"] = timeout
        if async_:
            body["async"] = True
        request_timeout = (
            None
            if async_
            else _operation_request_timeout(
                timeout,
                max_timeout=IMAGE_OPERATION_MAX_TIMEOUT,
            )
        )
        return self.request(
            "POST",
            "/images/push",
            json_body=body,
            expected_status=202 if async_ else 200,
            request_timeout=request_timeout,
        )

    # -- registries ---------------------------------------------------------

    def registry_login(
        self,
        registry: str,
        username: str,
        password: str,
    ) -> JSONValue:
        """Authenticate to an OCI registry.

        Args:
            registry: Registry hostname.
            username: Registry username.
            password: Registry password.

        Returns:
            Login result dict.
        """
        return self.request(
            "POST",
            "/registries/login",
            json_body={"registry": registry, "username": username, "password": password},
        )

    def registry_logout(self, registry: str) -> JSONValue:
        """Remove credentials for an OCI registry.

        Args:
            registry: Registry hostname.

        Returns:
            Logout result dict.
        """
        return self.request(
            "POST",
            "/registries/logout",
            json_body={"registry": registry},
        )

    # -- jeballtofiles ---------------------------------------------------------

    def create_jeballtofile(
        self,
        name: str,
        steps: list[dict[str, Any]],
        *,
        source: str | None = None,
        cpu: int | None = None,
        memory: ResourceSize | None = None,
        disk: ResourceSize | None = None,
    ) -> JSONValue:
        """Execute a Jeballtofile blueprint.

        Validates and executes a Jeballtofile blueprint. Creates a VM and runs
        all steps asynchronously. Returns immediately with an execution ID.

        Args:
            name: VM display name (1-100 characters).
            steps: Ordered list of step dicts to execute.
            source: IPSW source for macOS installation (required when steps
                    include an ``install`` step). Accepts HTTPS URL, ``file://``
                    URL, or absolute path.
            cpu: Number of CPU cores.
            memory: Memory size (e.g. ``'8GB'``).
            disk: Disk size (e.g. ``'64GB'``).

        Returns:
            Dict with ``id``, ``vmId``, ``status``, ``currentStep``,
            ``totalSteps``, and ``message``.
        """
        body: dict[str, Any] = {"name": name, "steps": steps}
        if source is not None:
            body["source"] = source
        resources: dict[str, Any] = {}
        if cpu is not None:
            resources["cpuCount"] = cpu
        if memory is not None:
            resources["memorySize"] = memory
        if disk is not None:
            resources["diskSize"] = disk
        if resources:
            body["resources"] = resources
        return self.request("POST", "/jeballtofiles", json_body=body, expected_status=202)

    def list_jeballtofiles(self) -> JSONValue:
        """List all active and recent Jeballtofile executions.

        Returns:
            Dict with ``executions`` list and ``total`` count.
        """
        return self.request("GET", "/jeballtofiles")

    def get_jeballtofile(self, execution_id: str) -> JSONValue:
        """Get status and per-step results of a Jeballtofile execution.

        Args:
            execution_id: Execution identifier (UUID).

        Returns:
            Dict with ``id``, ``vmId``, ``status``, ``currentStep``,
            ``totalSteps``, ``stepResults``, and optional ``error``.
        """
        return self.request("GET", f"/jeballtofiles/{execution_id}")

    def delete_jeballtofile(self, execution_id: str) -> JSONValue:
        """Delete a completed, failed, or cancelled Jeballtofile execution.

        Running executions cannot be deleted - cancel them first.

        Args:
            execution_id: Execution identifier (UUID).

        Returns:
            Success response dict.
        """
        return self.request("DELETE", f"/jeballtofiles/{execution_id}")

    def cancel_jeballtofile(self, execution_id: str) -> JSONValue:
        """Request cancellation of a running Jeballtofile execution.

        The agent marks the run and current step as cancelled, then requests
        cooperative task cancellation.

        Args:
            execution_id: Execution identifier (UUID).

        Returns:
            Success response dict.
        """
        return self.request("POST", f"/jeballtofiles/{execution_id}/cancel")

    # -- system ----------------------------------------------------------------

    def system_reset(self, mode: str) -> JSONValue:
        """Reset the agent to a clean state.

        Soft mode deletes all VMs, images, and IPSW cache but keeps
        configuration and logs. Hard mode deletes everything and terminates
        the application process.

        Args:
            mode: Reset mode - ``'soft'`` or ``'hard'``.

        Returns:
            Dict with counts of deleted resources and ``willTerminate`` flag.
        """
        return self.request(
            "POST",
            "/system/reset",
            json_body={"mode": mode},
            params={"confirm": "true"},
            expected_status={200, 500},
        )

    def system_capabilities(self) -> JSONValue:
        """Get host and feature capabilities.

        Returns:
            Dict with host capability metadata and feature capability rows.
        """
        return self.request("GET", "/system/capabilities")
