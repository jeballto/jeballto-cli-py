"""VM management commands - CRUD, lifecycle, execute, keystrokes, state, events."""

from __future__ import annotations

import json
import shlex
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from jeballto_cli._context import CliContext, require_context
from jeballto_cli.commands.vm_gui import app as gui_app
from jeballto_cli.commands.vm_install import app as install_app
from jeballto_cli.commands.vm_ssh import app as ssh_app
from jeballto_cli.commands.vm_vnc import app as vnc_app
from jeballto_cli.references import resolve_vm_id
from jeballto_cli.render import render_output
from jeballto_cli.settings import OutputFormat
from jeballto_cli.ui import confirm_action, format_bytes, format_duration, has_failures
from jeballto_cli.validation import require_int_range

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")

app.add_typer(install_app, name="install", help="Install macOS in a VM.")
app.add_typer(ssh_app, name="ssh", help="Show or change SSH access.")
app.add_typer(vnc_app, name="vnc", help="Show or change VNC access.")
app.add_typer(gui_app, name="gui", help="Open, close, or inspect the VM window.")


# -- CRUD -------------------------------------------------------------------


@app.command()
def create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="Name for the new VM.")],
    cpu: Annotated[int | None, typer.Option("--cpu", help="CPU cores for the VM.")] = None,
    memory: Annotated[
        str | None, typer.Option("--memory", help="Memory for the VM, such as 8GB.")
    ] = None,
    disk: Annotated[str | None, typer.Option("--disk", help="Disk size, such as 64GB.")] = None,
    image: Annotated[
        str | None, typer.Option("--image", help="Create from this image reference.")
    ] = None,
    ephemeral: Annotated[
        bool,
        typer.Option("--ephemeral", help="Delete the VM when it finishes or fails."),
    ] = False,
    lifetime: Annotated[
        int | None,
        typer.Option(
            "--lifetime",
            help="Stop after this many running seconds. Ephemeral VMs are then deleted.",
        ),
    ] = None,
) -> None:
    """Create a VM."""
    context = require_context(ctx)
    cpu = require_int_range(cpu, name="--cpu", minimum=1, maximum=32)
    lifetime = require_int_range(lifetime, name="--lifetime", minimum=1, maximum=604800)
    resource_updates = cpu is not None or memory is not None or disk is not None
    data = context.client.create_vm(
        name,
        cpu=None if image and resource_updates else cpu,
        memory=None if image and resource_updates else memory,
        disk=None if image and resource_updates else disk,
        image=image,
        ephemeral=ephemeral or None,
        lifetime_seconds=lifetime,
    )
    if image and resource_updates:
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            raise typer.BadParameter("Agent response did not include a VM id for resource update.")
        vm_id = data["id"]
        try:
            data = context.client.update_vm(
                vm_id,
                cpu=cpu,
                memory=memory,
                disk=disk,
            )
        except KeyboardInterrupt:
            context.error_console.print(
                f"VM {vm_id} was created. Inspect it before retrying the resource update.",
                highlight=False,
            )
            raise
        except Exception:
            try:
                context.client.delete_vm(vm_id, force=True)
            except Exception as cleanup_error:
                context.error_console.print(
                    f"Warning: VM {vm_id} was created but cleanup also failed: {cleanup_error}",
                    highlight=False,
                    markup=False,
                )
            raise
    _render_vm_response(context, data, title="VM Created", detailed=False)


@app.command()
def update(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Rename the VM.")] = None,
    cpu: Annotated[int | None, typer.Option("--cpu", help="Set CPU cores.")] = None,
    memory: Annotated[
        str | None, typer.Option("--memory", help="Set memory, such as 16GB.")
    ] = None,
    disk: Annotated[
        str | None,
        typer.Option("--disk", help="Grow disk to this size, such as 128GB."),
    ] = None,
) -> None:
    """Rename a VM or change its resources."""
    context = require_context(ctx)
    cpu = require_int_range(cpu, name="--cpu", minimum=1, maximum=32)
    vm_id = resolve_vm_id(context, vm)
    if name is None and cpu is None and memory is None and disk is None:
        raise typer.BadParameter("Provide at least one of --name/--cpu/--memory/--disk.")
    data = context.client.update_vm(
        vm_id,
        name=name,
        cpu=cpu,
        memory=memory,
        disk=disk,
    )
    _render_vm_response(context, data, title="VM Updated", detailed=False)


@app.command("list")
def list_vms(
    ctx: typer.Context,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-l", help="Show at most this many VMs."),
    ] = None,
    offset: Annotated[int | None, typer.Option("--offset", help="Skip this many VMs.")] = None,
) -> None:
    """List VMs."""
    context = require_context(ctx)
    limit = require_int_range(limit, name="--limit", minimum=1, maximum=1000)
    offset = require_int_range(offset, name="--offset", minimum=0)
    data = context.client.list_vms(limit=limit, offset=offset)
    if isinstance(data, dict):
        vms = data.get("vms", [])
        if context.human_output and isinstance(vms, list):
            _print_vm_list(context, vms)
            _print_vm_page_summary(context, data, len(vms))
            return
        render_output(context.console, data, output_format=context.settings.output, title="VMs")
    else:
        render_output(context.console, data, output_format=context.settings.output, title="VMs")


def _print_vm_list(context: CliContext, vms: list[object]) -> None:
    """Print a compact scan view for VMs."""
    if not vms:
        context.console.print("No VMs found.", highlight=False)
        return

    context.console.print("[bold]VMs[/]")
    for index, vm in enumerate(vms, start=1):
        if not isinstance(vm, dict):
            continue
        name = vm.get("name") or "(unnamed)"
        state = vm.get("state") or "unknown"
        vm_id = vm.get("id") or ""
        resources = vm.get("resources")
        resource_text = _vm_resource_text(resources)
        network = vm.get("network")
        ssh_port = network.get("sshPort") if isinstance(network, dict) else None
        vnc_port = network.get("vncPort") if isinstance(network, dict) else None
        expires_at = vm.get("expiresAt")
        updated = vm.get("updatedAt")
        context.console.print(f"{index}. {name} - {state}", highlight=False)
        context.console.print(f"   id: {vm_id}", highlight=False)
        if resource_text:
            context.console.print(f"   resources: {resource_text}", highlight=False)
        ports = [
            text
            for text in (
                f"SSH {ssh_port}" if ssh_port else None,
                f"VNC {vnc_port}" if vnc_port else None,
            )
            if text
        ]
        if ports:
            context.console.print(f"   access: {', '.join(ports)}", highlight=False)
        if expires_at:
            context.console.print(f"   expires: {expires_at}", highlight=False)
        if updated:
            context.console.print(f"   updated: {updated}", highlight=False)


def _print_vm_page_summary(
    context: CliContext,
    payload: dict[str, object],
    shown: int,
) -> None:
    """Show the next offset when more VMs are available."""
    total = payload.get("total")
    offset = payload.get("offset")
    if isinstance(total, int) and isinstance(offset, int) and offset + shown < total:
        context.console.print(
            f"Showing {offset + 1}-{offset + shown} of {total}. Use --offset {offset + shown}.",
            highlight=False,
        )


def _render_vm_response(
    context: CliContext,
    data: object,
    *,
    title: str,
    detailed: bool,
) -> None:
    """Render a VM response with a polished default summary."""
    if context.human_output and isinstance(data, dict):
        if detailed:
            _print_vm_detail(context, data, title=title)
        else:
            _print_vm_summary(context, data, title=title)
        return
    render_output(context.console, data, output_format=context.settings.output, title=title)


def _print_vm_summary(context: CliContext, vm: dict[str, object], *, title: str) -> None:
    """Print a VM action result with only the fields needed next."""
    name = vm.get("name") or "(unnamed)"
    state = vm.get("state") or "unknown"
    context.console.print(f"{title}: {name} ({state})", highlight=False)
    vm_id = vm.get("id")
    if vm_id:
        context.console.print(f"id: {vm_id}", highlight=False)
    resources = _vm_resource_text(vm.get("resources"))
    if resources:
        context.console.print(f"resources: {resources}", highlight=False)


def _print_vm_detail(context: CliContext, vm: dict[str, object], *, title: str) -> None:
    """Print one VM as readable key-value lines."""
    resources = _vm_resource_text(vm.get("resources"))
    network = vm.get("network")
    mac_address = network.get("macAddress") if isinstance(network, dict) else None
    ssh_port = network.get("sshPort") if isinstance(network, dict) else None
    vnc_port = network.get("vncPort") if isinstance(network, dict) else None
    nat_ip = network.get("natIP") if isinstance(network, dict) else None
    context.console.print(f"[bold]{title}[/]")
    for key, value in (
        ("name", vm.get("name")),
        ("id", vm.get("id")),
        ("state", vm.get("state")),
        ("resources", resources),
        ("mac", mac_address),
        ("nat IP", nat_ip),
        ("ssh port", ssh_port),
        ("vnc port", vnc_port),
        ("gui", _format_open_state(vm.get("guiOpen"))),
        ("ephemeral", _format_bool(vm.get("ephemeral"))),
        ("uptime", format_duration(vm.get("uptime"))),
        ("lifetime", format_duration(vm.get("lifetimeSeconds"))),
        ("expires", vm.get("expiresAt")),
        ("created", vm.get("createdAt")),
        ("updated", vm.get("updatedAt")),
    ):
        if value not in (None, ""):
            context.console.print(f"{key}: {value}", highlight=False)


def _format_bool(value: object) -> str | None:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return None


def _format_open_state(value: object) -> str | None:
    if value is True:
        return "open"
    if value is False:
        return "closed"
    return None


def _vm_resource_text(resources: object) -> str | None:
    if not isinstance(resources, dict):
        return None
    cpu = resources.get("cpuCount")
    memory = resources.get("memorySize")
    disk = resources.get("diskSize")
    parts = []
    if cpu:
        parts.append(f"{cpu} CPU")
    if memory:
        parts.append(format_bytes(memory) or str(memory))
    if disk:
        parts.append(f"{format_bytes(disk) or disk} disk")
    return ", ".join(parts) or None


@app.command()
def get(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Show one VM."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.get_vm(vm_id)
    _render_vm_response(context, data, title="VM", detailed=True)


@app.command()
def delete(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
    force: Annotated[bool, typer.Option("--force", help="Stop the VM first if needed.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
) -> None:
    """Delete a VM."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    confirm_action(context, f"Delete VM {vm} ({vm_id})?", yes=yes)
    context.client.delete_vm(vm_id, force=force)
    result = {"success": True, "vmId": vm_id}
    if context.human_output:
        context.console.print("VM deleted.", highlight=False)
    else:
        render_output(context.console, result, output_format=context.settings.output)


@app.command()
def wipe(
    ctx: typer.Context,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
) -> None:
    """Delete every VM."""
    context = require_context(ctx)
    confirm_action(context, "Force-delete every VM?", yes=yes)
    data = context.client.wipe_vms()
    if context.human_output and isinstance(data, dict):
        deleted = data.get("deleted", 0)
        failed = data.get("failed", 0)
        context.console.print(f"VMs deleted: {deleted}", highlight=False)
        if failed:
            context.console.print(f"failed: {failed}", highlight=False)
        if data.get("errors"):
            context.console.print(f"errors: {data['errors']}", highlight=False, markup=False)
    else:
        render_output(
            context.console, data, output_format=context.settings.output, title="Wipe Result"
        )
    if has_failures(data):
        raise typer.Exit(code=1)


# -- lifecycle --------------------------------------------------------------


@app.command()
def start(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Start a VM."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = _call_vm_lifecycle(context, vm, lambda: context.client.start_vm(vm_id))
    _render_vm_response(context, data, title="VM Started", detailed=False)


@app.command()
def stop(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Stop a VM."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = _call_vm_lifecycle(context, vm, lambda: context.client.stop_vm(vm_id))
    _render_vm_response(context, data, title="VM Stopped", detailed=False)


@app.command()
def pause(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Pause a VM."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = _call_vm_lifecycle(context, vm, lambda: context.client.pause_vm(vm_id))
    _render_vm_response(context, data, title="VM Paused", detailed=False)


@app.command()
def resume(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Resume a paused VM."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = _call_vm_lifecycle(context, vm, lambda: context.client.resume_vm(vm_id))
    _render_vm_response(context, data, title="VM Resumed", detailed=False)


@app.command()
def clone(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM to copy, by name or ID.")],
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the copy.")],
    cpu: Annotated[int | None, typer.Option("--cpu", help="CPU cores for the copy.")] = None,
    memory: Annotated[
        str | None, typer.Option("--memory", help="Memory for the copy, such as 8GB.")
    ] = None,
    disk: Annotated[str | None, typer.Option("--disk", help="Disk size for the copy.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Stop the source VM if needed.")] = False,
    ephemeral: Annotated[
        bool, typer.Option("--ephemeral", help="Delete the copy when it finishes or fails.")
    ] = False,
    lifetime: Annotated[
        int | None,
        typer.Option(
            "--lifetime",
            help="Stop after this many running seconds. Ephemeral clones are then deleted.",
        ),
    ] = None,
) -> None:
    """Copy a VM."""
    context = require_context(ctx)
    cpu = require_int_range(cpu, name="--cpu", minimum=1, maximum=32)
    lifetime = require_int_range(lifetime, name="--lifetime", minimum=1, maximum=604800)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.clone_vm(
        vm_id,
        name,
        cpu=cpu,
        memory=memory,
        disk=disk,
        force=force,
        ephemeral=ephemeral or None,
        lifetime_seconds=lifetime,
    )
    _render_vm_response(context, data, title="VM Cloned", detailed=False)


# -- execute & keystrokes ---------------------------------------------------


@app.command("exec")
def execute(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
    command: Annotated[
        list[str],
        typer.Argument(help="Command and arguments to run. Use -- before command options."),
    ],
    user: Annotated[str, typer.Option("--user", help="Login user inside the VM.")] = "admin",
    password: Annotated[
        str | None,
        typer.Option(
            "--password",
            help="Login password. Prefer --password-stdin or JEBALLTO_SSH_PASSWORD.",
            envvar="JEBALLTO_SSH_PASSWORD",
        ),
    ] = None,
    password_stdin: Annotated[
        bool,
        typer.Option("--password-stdin", help="Read the SSH password from stdin."),
    ] = False,
    timeout: Annotated[
        int | None, typer.Option("--timeout", help="Stop command after this many seconds.")
    ] = None,
) -> None:
    """Run a command inside a VM."""
    context = require_context(ctx)
    if not command:
        raise typer.BadParameter("Provide a command to run.", param_hint="command")
    if password is not None and password_stdin:
        raise typer.BadParameter("Use --password or --password-stdin, not both.")
    if password_stdin:
        password = sys.stdin.read().rstrip("\r\n")
        if not password:
            raise typer.BadParameter(
                "stdin did not contain a password.", param_hint="--password-stdin"
            )
    timeout = require_int_range(timeout, name="--timeout", minimum=1, maximum=600)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.execute(
        vm_id,
        shlex.join(command),
        user=user,
        password=password,
        timeout=timeout,
    )
    if isinstance(data, dict) and context.human_output:
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")
        exit_code = data.get("exitCode", 0)
        if stdout:
            sys.stdout.write(stdout)
        if stderr:
            sys.stderr.write(stderr)
        _warn_if_output_truncated(context, data)
        raise typer.Exit(code=_guest_exit_code(exit_code))
    render_output(context.console, data, output_format=context.settings.output)
    if isinstance(data, dict):
        _warn_if_output_truncated(context, data)
        raise typer.Exit(code=_guest_exit_code(data.get("exitCode")))


@app.command()
def keystrokes(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
    keys: Annotated[list[str], typer.Argument(help="Keys to send, such as hello <enter>.")],
) -> None:
    """Send keystrokes to a VM."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.keystrokes(vm_id, keys)
    if context.human_output and isinstance(data, dict):
        count = data.get("keystrokesCount") or len(keys)
        context.console.print(f"Keystrokes sent: {count}", highlight=False)
        message = data.get("message")
        if message:
            context.console.print(f"message: {message}", highlight=False, markup=False)
        return
    render_output(context.console, data, output_format=context.settings.output, title="Keystrokes")


@app.command()
def screenshot(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
    output_file: Annotated[
        Path | None,
        typer.Option(
            "--output-file",
            "-o",
            help="Where to save the PNG. Defaults to <vm>.png.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace the output file if it already exists."),
    ] = False,
) -> None:
    """Save a VM screenshot as PNG."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    image_bytes = context.client.screenshot(vm_id)
    dest = output_file or Path(f"{vm}.png")
    try:
        with dest.open("wb" if force else "xb") as output:
            output.write(image_bytes)
    except FileExistsError as exc:
        raise typer.BadParameter(
            f"Output file already exists: {dest}. Use --force to replace it.",
            param_hint="--output-file",
        ) from exc
    result = {"path": str(dest), "bytes": len(image_bytes), "vmId": vm_id}
    if context.human_output:
        context.console.print(f"Screenshot saved: {dest}", highlight=False, markup=False)
    else:
        render_output(context.console, result, output_format=context.settings.output)


# -- monitoring -------------------------------------------------------------


@app.command()
def state(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
) -> None:
    """Show whether a VM is running, stopped, or paused."""
    context = require_context(ctx)
    vm_id = resolve_vm_id(context, vm)
    data = context.client.vm_state(vm_id)
    if context.human_output and isinstance(data, dict):
        state_value = data.get("state") or "unknown"
        context.console.print(f"VM state: {state_value}", highlight=False)
        uptime = data.get("uptime")
        if uptime is not None:
            context.console.print(
                f"uptime: {format_duration(uptime) or uptime}",
                highlight=False,
            )
        return
    render_output(context.console, data, output_format=context.settings.output, title="VM State")


@app.command()
def events(
    ctx: typer.Context,
    vm: Annotated[str, typer.Argument(help="VM name or ID.")],
    limit: Annotated[
        int, typer.Option("--limit", "-l", help="Show at most this many events.")
    ] = 100,
    watch: Annotated[bool, typer.Option("--watch", help="Keep watching for new events.")] = False,
) -> None:
    """Show recent VM events."""
    context = require_context(ctx)
    limit = require_int_range(limit, name="--limit", minimum=1, maximum=1000) or limit
    vm_id = resolve_vm_id(context, vm)
    if not watch:
        data = context.client.vm_events(vm_id, limit=limit)
        if isinstance(data, dict):
            events_data = data.get("events", [])
            if context.human_output and isinstance(events_data, list):
                _print_event_list(context, events_data)
                return
            render_output(
                context.console, data, output_format=context.settings.output, title="Events"
            )
        else:
            render_output(
                context.console,
                data,
                output_format=context.settings.output,
                title="Events",
            )
        return

    if context.settings.output not in {OutputFormat.HUMAN, OutputFormat.JSONL}:
        raise typer.BadParameter(
            "--watch requires --output human or --output jsonl.",
            param_hint="--output",
        )

    seen: set[str] = set()
    try:
        while True:
            data = context.client.vm_events(vm_id, limit=limit)
            event_list = data.get("events", []) if isinstance(data, dict) else []
            for event in event_list:
                if not isinstance(event, dict):
                    continue
                key = json.dumps(event, sort_keys=True, ensure_ascii=False)
                if key not in seen:
                    seen.add(key)
                    if context.human_output:
                        _print_event(context, event)
                        continue
                    render_output(
                        context.console,
                        event,
                        output_format=context.settings.output,
                        title=None,
                    )
            time.sleep(2)
    except KeyboardInterrupt:
        raise typer.Exit(code=130) from None


# -- helpers ----------------------------------------------------------------


def _call_vm_lifecycle(
    context: CliContext,
    vm_ref: str,
    action: Callable[[], object],
) -> object:
    """Run a blocking lifecycle request with recovery guidance on interrupt."""
    try:
        return action()
    except KeyboardInterrupt:
        context.error_console.print(
            "The agent may still be changing VM state. Inspect it with: "
            f"jeballto vm get {shlex.quote(vm_ref)}",
            highlight=False,
            markup=False,
        )
        raise typer.Exit(code=130) from None


def _print_event_list(context: CliContext, events: list[object]) -> None:
    """Print VM events in a compact scan view."""
    if not events:
        context.console.print("No VM events found.", highlight=False)
        return
    context.console.print("[bold]Events[/]")
    for event in events:
        if isinstance(event, dict):
            _print_event(context, event)


def _print_event(context: CliContext, event: dict[str, object]) -> None:
    """Print one VM event as a single readable line."""
    timestamp = event.get("timestamp") or "unknown time"
    event_type = event.get("type") or "event"
    data = event.get("data")
    details: list[str] = []
    if isinstance(data, dict):
        old_state = data.get("from")
        new_state = data.get("to")
        if old_state or new_state:
            details.append(f"{old_state or '?'} -> {new_state or '?'}")
        for key in ("message", "error", "port", "phase"):
            value = data.get(key)
            if value not in (None, ""):
                details.append(str(value))
        progress = data.get("progress")
        if progress is not None:
            from jeballto_cli.ui import format_progress

            progress_text = format_progress(_number(progress))
            if progress_text:
                details.append(progress_text)
    line = f"{timestamp} {event_type}"
    if details:
        line = f"{line}: {', '.join(details)}"
    context.console.print(line, highlight=False, markup=False)


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _warn_if_output_truncated(context: CliContext, data: dict[str, object]) -> None:
    truncated = []
    if data.get("stdoutTruncated") is True:
        truncated.append("stdout")
    if data.get("stderrTruncated") is True:
        truncated.append("stderr")
    if truncated:
        raw_stderr = data.get("stderr")
        if (
            context.human_output
            and isinstance(raw_stderr, str)
            and raw_stderr
            and not raw_stderr.endswith(("\n", "\r"))
        ):
            sys.stderr.write("\n")
        context.error_console.print(
            f"Warning: {', '.join(truncated)} exceeded the 5 MiB capture limit and was truncated.",
            highlight=False,
        )


def _guest_exit_code(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 255:
        return value
    return 1
