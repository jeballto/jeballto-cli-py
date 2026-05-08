"""VM management commands - CRUD, lifecycle, execute, keystrokes, state, events."""

from __future__ import annotations

import sys
import time
from typing import Annotated

import typer

from jeballto_cli._context import require_context
from jeballto_cli.commands.vm_gui import app as gui_app
from jeballto_cli.commands.vm_install import app as install_app
from jeballto_cli.commands.vm_ssh import app as ssh_app
from jeballto_cli.commands.vm_vnc import app as vnc_app
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")

app.add_typer(install_app, name="install", help="macOS installation.")
app.add_typer(ssh_app, name="ssh", help="SSH forwarding.")
app.add_typer(vnc_app, name="vnc", help="VNC forwarding.")
app.add_typer(gui_app, name="gui", help="GUI window management.")


# -- CRUD -------------------------------------------------------------------


@app.command()
def create(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="VM display name.")],
    cpu: Annotated[
        int | None, typer.Option("--cpu", min=1, max=32, help="Number of CPU cores.")
    ] = None,
    memory: Annotated[
        str | None, typer.Option("--memory", help="Memory size (e.g. '8GB').")
    ] = None,
    disk: Annotated[str | None, typer.Option("--disk", help="Disk size (e.g. '64GB').")] = None,
    image: Annotated[
        str | None, typer.Option("--image", help="OCI image reference to restore from.")
    ] = None,
    ephemeral: Annotated[
        bool,
        typer.Option("--ephemeral", help="Auto-delete VM on terminal state."),
    ] = False,
    lifetime: Annotated[
        int | None,
        typer.Option(
            "--lifetime",
            min=1,
            max=604800,
            help="Max lifetime in seconds from first RUNNING (1-604800).",
        ),
    ] = None,
) -> None:
    """Create a new virtual machine."""
    context = require_context(ctx)
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
        data = context.client.update_vm(
            data["id"],
            cpu=cpu,
            memory=memory,
            disk=disk,
        )
    render_output(context.console, data, output_format=context.settings.output, title="VM Created")


@app.command()
def update(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="New VM name.")] = None,
    cpu: Annotated[
        int | None, typer.Option("--cpu", min=1, max=32, help="New CPU count.")
    ] = None,
    memory: Annotated[
        str | None, typer.Option("--memory", help="New memory size (e.g. '16GB').")
    ] = None,
    disk: Annotated[
        str | None,
        typer.Option("--disk", help="New disk size (grow only, e.g. '128GB')."),
    ] = None,
) -> None:
    """Update VM name and/or resources. VM must be stopped for resource change."""
    context = require_context(ctx)
    if name is None and cpu is None and memory is None and disk is None:
        raise typer.BadParameter("Provide at least one of --name/--cpu/--memory/--disk.")
    data = context.client.update_vm(
        vm_id,
        name=name,
        cpu=cpu,
        memory=memory,
        disk=disk,
    )
    render_output(context.console, data, output_format=context.settings.output, title="VM Updated")


@app.command("list")
def list_vms(
    ctx: typer.Context,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-l", min=1, max=1000, help="Max results to return (1-1000)."),
    ] = None,
    offset: Annotated[
        int | None, typer.Option("--offset", min=0, help="Number of results to skip.")
    ] = None,
) -> None:
    """List all virtual machines."""
    context = require_context(ctx)
    data = context.client.list_vms(limit=limit, offset=offset)
    if isinstance(data, dict):
        render_output(
            context.console,
            data.get("vms", []),
            output_format=context.settings.output,
            title="VMs",
        )
    else:
        render_output(context.console, data, output_format=context.settings.output, title="VMs")


@app.command("ls", hidden=True)
def list_vms_alias(
    ctx: typer.Context,
    limit: Annotated[
        int | None,
        typer.Option("--limit", "-l", min=1, max=1000, help="Max results to return (1-1000)."),
    ] = None,
    offset: Annotated[
        int | None, typer.Option("--offset", min=0, help="Number of results to skip.")
    ] = None,
) -> None:
    """List all virtual machines (alias for 'list')."""
    list_vms(ctx, limit=limit, offset=offset)


@app.command()
def get(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Get details for a virtual machine."""
    context = require_context(ctx)
    data = context.client.get_vm(vm_id)
    render_output(context.console, data, output_format=context.settings.output, title="VM")


@app.command("show", hidden=True)
def get_alias(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Get details for a virtual machine (alias for 'get')."""
    get(ctx, vm_id)


@app.command()
def delete(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    force: Annotated[bool, typer.Option("--force", help="Force delete a running VM.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")] = False,
) -> None:
    """Delete a virtual machine."""
    context = require_context(ctx)
    if not yes:
        typer.confirm(f"Delete VM {vm_id}?", abort=True)
    context.client.delete_vm(vm_id, force=force)
    context.console.print("[green]VM deleted.[/]")


@app.command("rm", hidden=True)
def delete_alias(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    force: Annotated[bool, typer.Option("--force", help="Force delete a running VM.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")] = False,
) -> None:
    """Delete a virtual machine (alias for 'delete')."""
    delete(ctx, vm_id, force=force, yes=yes)


@app.command()
def wipe(
    ctx: typer.Context,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Confirm wipe.")] = False,
) -> None:
    """Delete ALL virtual machines."""
    context = require_context(ctx)
    if not yes:
        typer.confirm("This will delete ALL VMs. Continue?", abort=True)
    data = context.client.wipe_vms()
    render_output(context.console, data, output_format=context.settings.output, title="Wipe Result")


# -- lifecycle --------------------------------------------------------------


@app.command()
def start(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    wait: Annotated[
        bool, typer.Option("--wait", "-w", help="Wait until the VM is running.")
    ] = False,
) -> None:
    """Start a virtual machine."""
    context = require_context(ctx)
    data = context.client.start_vm(vm_id)
    if wait:
        context.console.print("Waiting for VM to reach RUNNING state...")
        _poll_state(context, vm_id, "running")
    render_output(context.console, data, output_format=context.settings.output, title="VM")


@app.command()
def stop(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    wait: Annotated[
        bool, typer.Option("--wait", "-w", help="Wait until the VM is stopped.")
    ] = False,
) -> None:
    """Stop a virtual machine."""
    context = require_context(ctx)
    data = context.client.stop_vm(vm_id)
    if wait:
        context.console.print("Waiting for VM to reach STOPPED state...")
        _poll_state(context, vm_id, "stopped")
    render_output(context.console, data, output_format=context.settings.output, title="VM")


@app.command()
def pause(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Pause a virtual machine."""
    context = require_context(ctx)
    data = context.client.pause_vm(vm_id)
    render_output(context.console, data, output_format=context.settings.output, title="VM")


@app.command()
def resume(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Resume a paused virtual machine."""
    context = require_context(ctx)
    data = context.client.resume_vm(vm_id)
    render_output(context.console, data, output_format=context.settings.output, title="VM")


@app.command()
def clone(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="Source VM identifier (UUID).")],
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the cloned VM.")],
    cpu: Annotated[
        int | None, typer.Option("--cpu", min=1, max=32, help="Override CPU count.")
    ] = None,
    memory: Annotated[
        str | None, typer.Option("--memory", help="Override memory (e.g. '8GB').")
    ] = None,
    disk: Annotated[str | None, typer.Option("--disk", help="Override disk (e.g. '64GB').")] = None,
    force: Annotated[bool, typer.Option("--force", help="Auto-stop source VM if running.")] = False,
    ephemeral: Annotated[
        bool, typer.Option("--ephemeral", help="Auto-delete clone on terminal state.")
    ] = False,
) -> None:
    """Clone a virtual machine."""
    context = require_context(ctx)
    data = context.client.clone_vm(
        vm_id,
        name,
        cpu=cpu,
        memory=memory,
        disk=disk,
        force=force,
        ephemeral=ephemeral or None,
    )
    render_output(context.console, data, output_format=context.settings.output, title="VM Cloned")


# -- execute & keystrokes ---------------------------------------------------


@app.command()
def execute(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    command: Annotated[str, typer.Argument(help="Shell command to run.")],
    user: Annotated[str, typer.Option("--user", help="SSH user.")] = "admin",
    password: Annotated[str | None, typer.Option("--password", help="SSH password.")] = None,
    timeout: Annotated[
        int | None, typer.Option("--timeout", min=1, max=600, help="Command timeout in seconds.")
    ] = None,
) -> None:
    """Execute a command inside a VM via SSH."""
    context = require_context(ctx)
    data = context.client.execute(
        vm_id,
        command,
        user=user,
        password=password,
        timeout=timeout,
    )
    if isinstance(data, dict):
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")
        exit_code = data.get("exitCode", 0)
        if stdout:
            sys.stdout.write(stdout)
        if stderr:
            sys.stderr.write(stderr)
        raise typer.Exit(code=exit_code or 0)
    render_output(context.console, data, output_format=context.settings.output)


@app.command("exec", hidden=True)
def execute_alias(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    command: Annotated[str, typer.Argument(help="Shell command to run.")],
    user: Annotated[str, typer.Option("--user", help="SSH user.")] = "admin",
    password: Annotated[str | None, typer.Option("--password", help="SSH password.")] = None,
    timeout: Annotated[
        int | None, typer.Option("--timeout", min=1, max=600, help="Command timeout in seconds.")
    ] = None,
) -> None:
    """Execute a command inside a VM via SSH (alias for 'execute')."""
    execute(ctx, vm_id, command, user=user, password=password, timeout=timeout)


@app.command()
def keystrokes(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    keys: Annotated[list[str], typer.Argument(help="Keystroke strings (DSL).")],
) -> None:
    """Inject keystrokes into a virtual machine."""
    context = require_context(ctx)
    data = context.client.keystrokes(vm_id, keys)
    render_output(context.console, data, output_format=context.settings.output, title="Keystrokes")


# -- monitoring -------------------------------------------------------------


@app.command()
def state(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
) -> None:
    """Get the current state of a virtual machine."""
    context = require_context(ctx)
    data = context.client.vm_state(vm_id)
    render_output(context.console, data, output_format=context.settings.output, title="VM State")


@app.command()
def events(
    ctx: typer.Context,
    vm_id: Annotated[str, typer.Argument(help="VM identifier (UUID).")],
    limit: Annotated[
        int, typer.Option("--limit", "-l", min=1, max=1000, help="Max events (1-1000).")
    ] = 100,
    watch: Annotated[
        bool, typer.Option("--watch", help="Continuously poll for new events.")
    ] = False,
) -> None:
    """Get events for a virtual machine."""
    context = require_context(ctx)
    if not watch:
        data = context.client.vm_events(vm_id, limit=limit)
        if isinstance(data, dict):
            render_output(
                context.console,
                data.get("events", []),
                output_format=context.settings.output,
                title="Events",
            )
        else:
            render_output(
                context.console,
                data,
                output_format=context.settings.output,
                title="Events",
            )
        return

    seen: set[str] = set()
    try:
        while True:
            data = context.client.vm_events(vm_id, limit=limit)
            event_list = data.get("events", []) if isinstance(data, dict) else []
            for event in event_list:
                if not isinstance(event, dict):
                    continue
                key = f"{event.get('timestamp')}:{event.get('type')}"
                if key not in seen:
                    seen.add(key)
                    render_output(
                        context.console,
                        event,
                        output_format=context.settings.output,
                        title=None,
                    )
            time.sleep(2)
    except KeyboardInterrupt:
        pass


# -- helpers ----------------------------------------------------------------


def _poll_state(
    context: object,
    vm_id: str,
    target: str,
    *,
    poll_interval: float = 1.0,
    max_wait: float = 300.0,
) -> None:
    """Poll VM state until it reaches the target.

    Args:
        context: The ``CliContext`` instance.
        vm_id: VM identifier (UUID).
        target: Target state string (lowercase).
        poll_interval: Seconds between polls.
        max_wait: Maximum seconds to wait before giving up.
    """
    from jeballto_cli._context import CliContext

    assert isinstance(context, CliContext)
    elapsed = 0.0
    while elapsed < max_wait:
        data = context.client.vm_state(vm_id)
        if isinstance(data, dict) and str(data.get("state", "")).lower() == target:
            context.console.print(f"[green]VM is now {target}.[/]")
            return
        time.sleep(poll_interval)
        elapsed += poll_interval
    context.console.print(f"[yellow]Timed out waiting for {target} state.[/]")
