"""Tests for VM commands."""

from __future__ import annotations

from typing import Any

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


def test_vm_list(invoke: Any) -> None:
    """List VMs renders a table."""
    result = invoke(["vm", "list"])
    assert result.exit_code == 0
    assert "test-vm" in result.output


def test_vm_list_alias(invoke: Any) -> None:
    """The 'ls' alias works the same as 'list'."""
    result = invoke(["vm", "ls"])
    assert result.exit_code == 0
    assert "test-vm" in result.output


def test_vm_get(invoke: Any) -> None:
    """Get VM details."""
    result = invoke(["vm", "get", VM_ID])
    assert result.exit_code == 0
    assert "test-vm" in result.output


def test_vm_show_alias(invoke: Any) -> None:
    """The 'show' alias works the same as 'get'."""
    result = invoke(["vm", "show", VM_ID])
    assert result.exit_code == 0
    assert "test-vm" in result.output


def test_vm_delete_confirmed(invoke: Any) -> None:
    """Delete VM with --yes skips confirmation."""
    result = invoke(["vm", "delete", VM_ID, "--yes"])
    assert result.exit_code == 0
    assert "deleted" in result.output.lower()


def test_vm_delete_abort(invoke: Any) -> None:
    """Delete VM without --yes prompts and can be aborted."""
    result = invoke(["vm", "delete", VM_ID], input="n\n")
    assert result.exit_code != 0


def test_vm_rm_alias(invoke: Any) -> None:
    """The 'rm' alias works for delete."""
    result = invoke(["vm", "rm", VM_ID, "--yes"])
    assert result.exit_code == 0


def test_vm_wipe_confirmed(invoke: Any) -> None:
    """Wipe all VMs with --yes."""
    result = invoke(["vm", "wipe", "--yes"])
    assert result.exit_code == 0
    assert "deleted" in result.output.lower() or "2" in result.output


def test_vm_start(invoke: Any) -> None:
    """Start a VM."""
    result = invoke(["vm", "start", VM_ID])
    assert result.exit_code == 0
    assert "test-vm" in result.output


def test_vm_stop(invoke: Any) -> None:
    """Stop a VM."""
    result = invoke(["vm", "stop", VM_ID])
    assert result.exit_code == 0


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


def test_vm_execute(invoke: Any) -> None:
    """Execute a command in a VM."""
    result = invoke(["vm", "execute", VM_ID, "echo hello"])
    assert result.exit_code == 0
    assert "hello" in result.output


def test_vm_exec_alias(invoke: Any) -> None:
    """The 'exec' alias works for execute."""
    result = invoke(["vm", "exec", VM_ID, "echo hello"])
    assert result.exit_code == 0


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


def test_vm_list_json(invoke: Any) -> None:
    """List VMs with JSON output."""
    result = invoke(["--output", "json", "vm", "list"])
    assert result.exit_code == 0
    assert '"test-vm"' in result.output


# -- SSH subcommands -------------------------------------------------------


def test_vm_ssh_info(invoke: Any) -> None:
    """Get SSH info."""
    result = invoke(["vm", "ssh", "info", VM_ID])
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
    assert "5900" in result.output


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


def test_vm_gui_close(invoke: Any) -> None:
    """Close GUI."""
    result = invoke(["vm", "gui", "close", VM_ID])
    assert result.exit_code == 0


def test_vm_gui_status(invoke: Any) -> None:
    """Get GUI status."""
    result = invoke(["vm", "gui", "status", VM_ID])
    assert result.exit_code == 0


def test_vm_gui_screenshot(invoke: Any, tmp_path: Any) -> None:
    """Capture screenshot and save to file."""
    out = tmp_path / "shot.png"
    result = invoke(["vm", "gui", "screenshot", VM_ID, "--output-file", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert out.read_bytes().startswith(b"\x89PNG")


# -- install subcommands ---------------------------------------------------


def test_vm_install_start(invoke: Any) -> None:
    """Start macOS installation."""
    result = invoke(["vm", "install", "start", VM_ID])
    assert result.exit_code == 0


def test_vm_install_status(invoke: Any) -> None:
    """Get install status."""
    result = invoke(["vm", "install", "status", VM_ID])
    assert result.exit_code == 0
    assert "completed" in result.output.lower() or "complete" in result.output.lower()
