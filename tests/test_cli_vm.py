"""Tests for VM commands."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from jeballto_cli.cli import app
from tests.conftest import VM_RESPONSE

VM_ID = VM_RESPONSE["id"]


def test_vm_create(invoke: Any) -> None:
    """Create a VM and render the result."""
    result = invoke(["vm", "create", "my-vm", "--cpu", "4", "--memory", "8GB"])
    assert result.exit_code == 0
    assert "test-vm" in result.output


def test_vm_create_ephemeral(invoke: Any) -> None:
    """Create an ephemeral VM with lifetime."""
    result = invoke(
        [
            "vm",
            "create",
            "eph",
            "--cpu",
            "2",
            "--memory",
            "4GB",
            "--ephemeral",
            "--lifetime",
            "3600",
        ]
    )
    assert result.exit_code == 0


def test_vm_create_rejects_cpu_below_api_min(invoke: Any) -> None:
    """Create rejects CPU count below OpenAPI minimum."""
    result = invoke(["vm", "create", "bad-vm", "--cpu", "0"])
    assert result.exit_code != 0


def test_vm_create_rejects_lifetime_above_api_max(invoke: Any) -> None:
    """Create rejects lifetime above OpenAPI maximum."""
    result = invoke(["vm", "create", "bad-vm", "--lifetime", "604801"])
    assert result.exit_code != 0


def test_vm_create_image_with_resources(invoke: Any) -> None:
    """Create from image and patch resources afterward."""
    result = invoke(
        [
            "vm",
            "create",
            "from-image",
            "--image",
            "reg/vm:tag",
            "--cpu",
            "4",
            "--memory",
            "8GB",
        ]
    )
    assert result.exit_code == 0


def test_vm_update_name(invoke: Any) -> None:
    """Update VM name via PATCH."""
    result = invoke(["vm", "update", VM_ID, "--name", "renamed"])
    assert result.exit_code == 0


def test_vm_update_resources(invoke: Any) -> None:
    """Update VM resources via PATCH."""
    result = invoke(["vm", "update", VM_ID, "--cpu", "8", "--memory", "16GB"])
    assert result.exit_code == 0


def test_vm_update_requires_field(invoke: Any) -> None:
    """Update VM with no field fails."""
    result = invoke(["vm", "update", VM_ID])
    assert result.exit_code != 0


def test_vm_clone_ephemeral(invoke: Any) -> None:
    """Clone VM ephemeral."""
    result = invoke(["vm", "clone", VM_ID, "--name", "c", "--ephemeral"])
    assert result.exit_code == 0


def test_vm_clone_accepts_lifetime(invoke: Any) -> None:
    """Clone supports the current lifetimeSeconds API field."""
    result = invoke(
        ["vm", "clone", VM_ID, "--name", "short-lived", "--ephemeral", "--lifetime", "3600"]
    )

    assert result.exit_code == 0


def test_vm_list(invoke: Any) -> None:
    """List VMs renders a table."""
    result = invoke(["vm", "list"])
    assert result.exit_code == 0
    assert "test-vm" in result.output


def test_vm_list_rejects_invalid_pagination(invoke: Any) -> None:
    """List rejects pagination values outside OpenAPI bounds."""
    assert invoke(["vm", "list", "--limit", "0"]).exit_code != 0
    assert invoke(["vm", "list", "--offset", "-1"]).exit_code != 0


def test_vm_get(invoke: Any) -> None:
    """Get VM details."""
    result = invoke(["vm", "get", VM_ID])
    assert result.exit_code == 0
    assert "test-vm" in result.output


def test_vm_get_by_name(invoke: Any) -> None:
    """VM commands accept a unique VM name."""
    result = invoke(["vm", "get", "test-vm"])
    assert result.exit_code == 0
    assert VM_ID in result.output


def test_vm_name_not_found_gives_recovery_hint(invoke: Any) -> None:
    """Missing VM names return a human recovery hint."""
    result = invoke(["vm", "get", "missing-vm"])
    assert result.exit_code != 0
    assert result.stdout == ""
    assert "No VM named" in result.stderr
    assert "pass an ID" in result.stderr


def test_vm_delete_confirmed(invoke: Any) -> None:
    """Delete VM with --yes skips confirmation."""
    result = invoke(["vm", "delete", VM_ID, "--yes"])
    assert result.exit_code == 0
    assert "deleted" in result.output.lower()


def test_vm_delete_requires_yes_without_tty(invoke: Any) -> None:
    """Delete VM without --yes fails safely in non-interactive mode."""
    result = invoke(["vm", "delete", VM_ID])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "--yes" in result.stderr


def test_vm_delete_validation_error_is_structured_for_json(invoke: Any) -> None:
    """Machine output keeps command validation errors machine-readable."""
    result = invoke(["--output", "json", "vm", "delete", VM_ID])

    assert result.exit_code == 2
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "CLI_USAGE_ERROR"
    assert "--yes" in payload["error"]["message"]


def test_vm_wipe_confirmed(invoke: Any) -> None:
    """Wipe all VMs with --yes."""
    result = invoke(["vm", "wipe", "--yes"])
    assert result.exit_code == 0
    assert "deleted" in result.output.lower() or "2" in result.output


def test_vm_wipe_partial_failure_returns_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A partial VM wipe prints its result and exits with status one."""
    payload = {"deleted": 1, "failed": 1, "errors": ["VM remained running"]}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/v1/vms"
        return httpx.Response(200, json=payload)

    result = _invoke_with_handler(
        monkeypatch,
        ["--output", "json", "vm", "wipe", "--yes"],
        handler,
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == payload


def test_vm_start(invoke: Any) -> None:
    """Start a VM."""
    result = invoke(["vm", "start", VM_ID])
    assert result.exit_code == 0
    assert "test-vm" in result.output


def test_vm_start_by_name(invoke: Any) -> None:
    """Lifecycle commands accept VM names."""
    result = invoke(["vm", "start", "test-vm"])
    assert result.exit_code == 0


def test_vm_stop(invoke: Any) -> None:
    """Stop a VM."""
    result = invoke(["vm", "stop", VM_ID])
    assert result.exit_code == 0


def test_vm_start_and_stop_have_no_redundant_wait_flag(invoke: Any) -> None:
    """Lifecycle calls already wait at the API and reject the removed flag."""
    start = invoke(["vm", "start", VM_ID, "--wait"])
    stop = invoke(["vm", "stop", VM_ID, "--wait"])

    assert start.exit_code != 0
    assert stop.exit_code != 0
    assert "--wait" in start.stderr
    assert "--wait" in stop.stderr


def test_vm_pause(invoke: Any) -> None:
    """Pause a VM."""
    result = invoke(["vm", "pause", VM_ID])
    assert result.exit_code == 0


def test_vm_resume(invoke: Any) -> None:
    """Resume a VM."""
    result = invoke(["vm", "resume", VM_ID])
    assert result.exit_code == 0


def test_vm_clone(invoke: Any) -> None:
    """Clone a VM."""
    result = invoke(["vm", "clone", VM_ID, "--name", "cloned-vm"])
    assert result.exit_code == 0


def test_vm_exec(invoke: Any) -> None:
    """Execute a command and its arguments in a VM."""
    result = invoke(["vm", "exec", VM_ID, "echo", "hello"])
    assert result.exit_code == 0
    assert result.stdout == "hello\n"


def test_vm_exec_by_name(invoke: Any) -> None:
    """Exec accepts a unique VM name."""
    result = invoke(["vm", "exec", "test-vm", "echo", "hello"])
    assert result.exit_code == 0
    assert "hello" in result.output


def test_vm_exec_accepts_command_options_after_separator(invoke: Any) -> None:
    """A separator lets guest command flags pass through unchanged."""
    result = invoke(["vm", "exec", VM_ID, "--", "printf", "--help"])

    assert result.exit_code == 0


def test_vm_exec_machine_output_is_complete(invoke: Any) -> None:
    """Structured exec output includes exit and truncation metadata."""
    result = invoke(["--output", "json", "vm", "exec", VM_ID, "echo", "hello"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["exitCode"] == 0
    assert payload["stdout"] == "hello\n"
    assert payload["stdoutTruncated"] is False
    assert payload["stderrTruncated"] is False
    assert result.stderr == ""


def test_vm_exec_details_shows_complete_human_response(invoke: Any) -> None:
    """Details mode exposes exec metadata instead of only streaming guest output."""
    result = invoke(["--details", "vm", "exec", VM_ID, "echo", "hello"])

    assert result.exit_code == 0
    assert "exitCode: 0" in result.stdout
    assert "stdoutTruncated: False" in result.stdout


def test_vm_exec_propagates_guest_exit_and_warns_on_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exec returns the guest code and keeps truncation warnings on stderr."""
    payload = {
        "vmId": VM_ID,
        "exitCode": 7,
        "stdout": "partial output\n",
        "stderr": "",
        "stdoutTruncated": True,
        "stderrTruncated": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/vms/{VM_ID}/execute"
        return httpx.Response(200, json=payload)

    result = _invoke_with_handler(
        monkeypatch,
        ["vm", "exec", VM_ID, "long-command"],
        handler,
    )

    assert result.exit_code == 7
    assert result.stdout == "partial output\n"
    assert "stdout" in result.stderr
    assert "truncated" in result.stderr


def test_vm_keystrokes(invoke: Any) -> None:
    """Inject keystrokes into a VM."""
    result = invoke(["vm", "keystrokes", VM_ID, "hello", "<enter>"])
    assert result.exit_code == 0


def test_vm_state(invoke: Any) -> None:
    """Get VM state."""
    result = invoke(["vm", "state", VM_ID])
    assert result.exit_code == 0
    assert "running" in result.output


def test_vm_events(invoke: Any) -> None:
    """Get VM events."""
    result = invoke(["vm", "events", VM_ID])
    assert result.exit_code == 0
    assert "VM_CREATED" in result.output


def test_vm_events_json_preserves_envelope(invoke: Any) -> None:
    """Structured event output keeps total and event data."""
    result = invoke(["--output", "json", "vm", "events", VM_ID])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["total"] == 1
    assert "data" in payload["events"][0]
    assert result.stderr == ""


def test_vm_events_rejects_limit_above_api_max(invoke: Any) -> None:
    """Events rejects limit above OpenAPI maximum."""
    result = invoke(["vm", "events", VM_ID, "--limit", "1001"])
    assert result.exit_code != 0


def test_vm_list_json(invoke: Any) -> None:
    """List VMs with its full JSON pagination envelope."""
    result = invoke(["--output", "json", "vm", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["vms"][0]["name"] == "test-vm"
    assert payload["total"] == 1
    assert payload["limit"] == 100
    assert payload["offset"] == 0
    assert result.stderr == ""


# -- SSH subcommands -------------------------------------------------------


def test_vm_ssh_info(invoke: Any) -> None:
    """Get SSH info."""
    result = invoke(["vm", "ssh", "info", VM_ID])
    assert result.exit_code == 0
    assert "2222" in result.output
    assert "ready" in result.output


def test_vm_ssh_info_by_name(invoke: Any) -> None:
    """SSH commands accept a unique VM name."""
    result = invoke(["vm", "ssh", "info", "test-vm"])
    assert result.exit_code == 0
    assert "2222" in result.output


def test_vm_ssh_enable(invoke: Any) -> None:
    """Enable SSH."""
    result = invoke(["vm", "ssh", "enable", VM_ID])
    assert result.exit_code == 0


def test_vm_ssh_disable(invoke: Any) -> None:
    """Disable SSH."""
    result = invoke(["vm", "ssh", "disable", VM_ID])
    assert result.exit_code == 0


# -- VNC subcommands -------------------------------------------------------


def test_vm_vnc_info(invoke: Any) -> None:
    """Get VNC info."""
    result = invoke(["vm", "vnc", "info", VM_ID])
    assert result.exit_code == 0
    assert "5901" in result.output
    assert "ready" in result.output


def test_vm_vnc_info_by_name(invoke: Any) -> None:
    """VNC commands accept a unique VM name."""
    result = invoke(["vm", "vnc", "info", "test-vm"])
    assert result.exit_code == 0
    assert "5901" in result.output


def test_vm_vnc_enable(invoke: Any) -> None:
    """Enable VNC."""
    result = invoke(["vm", "vnc", "enable", VM_ID])
    assert result.exit_code == 0


def test_vm_vnc_disable(invoke: Any) -> None:
    """Disable VNC."""
    result = invoke(["vm", "vnc", "disable", VM_ID])
    assert result.exit_code == 0


# -- GUI subcommands -------------------------------------------------------


def test_vm_gui_open(invoke: Any) -> None:
    """Open GUI."""
    result = invoke(["vm", "gui", "open", VM_ID])
    assert result.exit_code == 0


def test_vm_gui_open_by_name(invoke: Any) -> None:
    """GUI commands accept a unique VM name."""
    result = invoke(["vm", "gui", "open", "test-vm"])
    assert result.exit_code == 0


def test_vm_gui_close(invoke: Any) -> None:
    """Close GUI."""
    result = invoke(["vm", "gui", "close", VM_ID])
    assert result.exit_code == 0


def test_vm_gui_status(invoke: Any) -> None:
    """Get GUI status."""
    result = invoke(["vm", "gui", "status", VM_ID])
    assert result.exit_code == 0


def test_vm_screenshot_top_level(invoke: Any, tmp_path: Any) -> None:
    """Capture screenshot with the top-level VM command."""
    out = tmp_path / "shot-top.png"
    result = invoke(["vm", "screenshot", "test-vm", "--output-file", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG")


def test_vm_screenshot_refuses_overwrite_without_force(invoke: Any, tmp_path: Any) -> None:
    """Screenshot protects existing files and supports explicit replacement."""
    out = tmp_path / "existing.png"
    out.write_bytes(b"keep")

    refused = invoke(["vm", "screenshot", VM_ID, "--output-file", str(out)])
    replaced = invoke(["vm", "screenshot", VM_ID, "--output-file", str(out), "--force"])

    assert refused.exit_code != 0
    assert "already exists" in refused.stderr
    assert replaced.exit_code == 0
    assert out.read_bytes().startswith(b"\x89PNG")


def test_vm_gui_help_hides_screenshot(invoke: Any) -> None:
    """Screenshot is not advertised under GUI anymore."""
    result = invoke(["vm", "gui", "--help"])
    assert result.exit_code == 0
    assert "screenshot" not in result.output


def test_vm_help_uses_grouped_gui_and_install(invoke: Any) -> None:
    """Primary help keeps GUI and install commands grouped."""
    result = invoke(["vm", "--help"])
    assert result.exit_code == 0
    assert "install" in result.output
    assert "gui" in result.output
    assert "install-macos" not in result.output
    assert "install-status" not in result.output
    assert "window-status" not in result.output


# -- install subcommands ---------------------------------------------------


def test_vm_install_start(invoke: Any) -> None:
    """Start macOS installation and wait by default."""
    result = invoke(["vm", "install", "start", VM_ID])
    assert result.exit_code == 0
    assert "completed" in result.stdout
    assert "Install 100%" in result.stderr


def test_vm_install_start_detach(invoke: Any) -> None:
    """Detached installation returns its initial status immediately."""
    result = invoke(["--output", "json", "vm", "install", "start", VM_ID, "--detach"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "completed"
    assert result.stderr == ""


def test_vm_install_status(invoke: Any) -> None:
    """Get install status."""
    result = invoke(["vm", "install", "status", VM_ID])
    assert result.exit_code == 0
    assert "completed" in result.output.lower() or "complete" in result.output.lower()


def test_vm_install_status_by_name(invoke: Any) -> None:
    """Install commands accept a unique VM name."""
    result = invoke(["vm", "install", "status", "test-vm"])
    assert result.exit_code == 0
    assert "completed" in result.output.lower() or "complete" in result.output.lower()


@pytest.mark.parametrize("terminal_status", ["not_started", "failed", "cancelled", "interrupted"])
def test_vm_install_non_success_terminal_states_return_one(
    monkeypatch: pytest.MonkeyPatch,
    terminal_status: str,
) -> None:
    """Every non-success install terminal state exits promptly with status one."""
    initial = {
        "vmId": VM_ID,
        "status": "installing",
        "progress": 0.25,
        "message": "Installing.",
    }
    final = {
        "vmId": VM_ID,
        "status": terminal_status,
        "progress": 0.25,
        "message": "Installation did not complete.",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(202, json=initial)
        assert request.url.path.endswith("/install/status")
        return httpx.Response(200, json=final)

    result = _invoke_with_handler(
        monkeypatch,
        ["--output", "json", "vm", "install", "start", VM_ID],
        handler,
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["status"] == terminal_status


def test_vm_leftover_commands_are_removed(invoke: Any) -> None:
    """Old hidden VM shortcuts are not part of the CLI surface."""
    for args in (
        ["vm", "ls"],
        ["vm", "show", VM_ID],
        ["vm", "rm", VM_ID],
        ["vm", "execute", VM_ID, "echo", "hello"],
        ["vm", "open", VM_ID],
        ["vm", "close", VM_ID],
        ["vm", "window-status", VM_ID],
        ["vm", "install-macos", VM_ID],
        ["vm", "install-status", VM_ID],
        ["vm", "gui", "screenshot", VM_ID],
    ):
        result = invoke(args)
        assert result.exit_code != 0


def _invoke_with_handler(
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    handler: Any,
) -> Any:
    """Invoke the CLI against one local mock handler."""
    monkeypatch.setenv("JEBALLTO_BASE_URL", "http://test:8011/v1")
    monkeypatch.setenv("JEBALLTO_TOKEN", "test-token")
    original_init = httpx.Client.__init__

    def patched_init(self: httpx.Client, **kwargs: Any) -> None:
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, **kwargs)

    monkeypatch.setattr(httpx.Client, "__init__", patched_init)
    return CliRunner().invoke(app, args)
