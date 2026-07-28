"""Agent runtime configuration commands."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated

import typer

from jeballto_cli._context import CliContext, require_context
from jeballto_cli.render import render_output
from jeballto_cli.validation import require_int_range

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


class LogLevel(StrEnum):
    """Log levels accepted by the agent."""

    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"


@app.command()
def get(ctx: typer.Context) -> None:
    """Show current agent settings."""
    context = require_context(ctx)
    data = context.client.get_config()
    if context.human_output and isinstance(data, dict):
        _print_config(context, data, title="Config")
        return
    render_output(context.console, data, output_format=context.settings.output, title="Config")


@app.command("set")
def set_config(
    ctx: typer.Context,
    data: Annotated[
        str | None,
        typer.Option("--json", "-j", help="Raw config JSON to apply."),
    ] = None,
    log_level: Annotated[
        LogLevel | None,
        typer.Option("--log-level", help="Log level to use."),
    ] = None,
    retention_days: Annotated[
        int | None, typer.Option("--retention-days", help="Keep logs for this many days.")
    ] = None,
    max_total_size: Annotated[
        str | None, typer.Option("--max-total-size", help="Maximum log size, such as 2GB.")
    ] = None,
    timezone: Annotated[
        str | None,
        typer.Option(
            "--timezone",
            help="Timezone for logs, such as UTC.",
        ),
    ] = None,
    system_timezone: Annotated[
        bool,
        typer.Option("--system-timezone", help="Use the system timezone for logs."),
    ] = False,
    ssh_port_start: Annotated[
        int | None,
        typer.Option(
            "--ssh-start",
            help="First SSH port to use.",
        ),
    ] = None,
    ssh_port_end: Annotated[
        int | None,
        typer.Option(
            "--ssh-end",
            help="Last SSH port to use.",
        ),
    ] = None,
    auto_enable_ssh_forwarding: Annotated[
        bool | None,
        typer.Option(
            "--ssh-forwarding/--no-ssh-forwarding",
            help="Turn SSH forwarding on for new VMs.",
        ),
    ] = None,
    vnc_port_start: Annotated[
        int | None,
        typer.Option(
            "--vnc-start",
            help="First VNC port to use.",
        ),
    ] = None,
    vnc_port_end: Annotated[
        int | None,
        typer.Option(
            "--vnc-end",
            help="Last VNC port to use.",
        ),
    ] = None,
    default_registry: Annotated[
        str | None,
        typer.Option(
            "--registry",
            help="Registry to use when an image has no host.",
        ),
    ] = None,
    clear_default_registry: Annotated[
        bool,
        typer.Option(
            "--clear-default-registry",
            help="Require every image reference to include a registry.",
        ),
    ] = False,
    insecure_registry: Annotated[
        list[str] | None,
        typer.Option(
            "--insecure-registry",
            help="Replace the HTTP registry list. Repeat for more registries.",
        ),
    ] = None,
    clear_insecure_registries: Annotated[
        bool,
        typer.Option(
            "--clear-insecure-registries",
            help="Remove every plain-HTTP registry exception.",
        ),
    ] = False,
    max_blob_transfers: Annotated[
        int | None,
        typer.Option(
            "--blob-transfers",
            help="Parallel registry blob transfers.",
        ),
    ] = None,
    max_compressions: Annotated[
        int | None,
        typer.Option(
            "--compressions",
            help="Parallel image compression jobs.",
        ),
    ] = None,
    max_decompressions: Annotated[
        int | None,
        typer.Option(
            "--decompressions",
            help="Parallel image decompression jobs.",
        ),
    ] = None,
    max_disk_writes: Annotated[
        int | None,
        typer.Option(
            "--disk-writes",
            help="Parallel image write jobs.",
        ),
    ] = None,
) -> None:
    """Change agent settings.

    Pass a raw JSON object via --json, or use individual flags.
    """
    context = require_context(ctx)
    retention_days = require_int_range(
        retention_days,
        name="--retention-days",
        minimum=1,
    )
    ssh_port_start = require_int_range(
        ssh_port_start,
        name="--ssh-start",
        minimum=1024,
        maximum=65535,
    )
    ssh_port_end = require_int_range(
        ssh_port_end,
        name="--ssh-end",
        minimum=1024,
        maximum=65535,
    )
    vnc_port_start = require_int_range(
        vnc_port_start,
        name="--vnc-start",
        minimum=1024,
        maximum=65535,
    )
    vnc_port_end = require_int_range(
        vnc_port_end,
        name="--vnc-end",
        minimum=1024,
        maximum=65535,
    )
    max_blob_transfers = require_int_range(
        max_blob_transfers,
        name="--blob-transfers",
        minimum=1,
        maximum=64,
    )
    max_compressions = require_int_range(
        max_compressions,
        name="--compressions",
        minimum=1,
        maximum=32,
    )
    max_decompressions = require_int_range(
        max_decompressions,
        name="--decompressions",
        minimum=1,
        maximum=8,
    )
    max_disk_writes = require_int_range(
        max_disk_writes,
        name="--disk-writes",
        minimum=1,
        maximum=4,
    )
    if ssh_port_start is not None and ssh_port_end is not None and ssh_port_start > ssh_port_end:
        raise typer.BadParameter("--ssh-start cannot be greater than --ssh-end.")
    if vnc_port_start is not None and vnc_port_end is not None and vnc_port_start > vnc_port_end:
        raise typer.BadParameter("--vnc-start cannot be greater than --vnc-end.")
    if timezone is not None and system_timezone:
        raise typer.BadParameter("Use --timezone or --system-timezone, not both.")
    if default_registry is not None and clear_default_registry:
        raise typer.BadParameter("Use --registry or --clear-default-registry, not both.")
    if insecure_registry is not None and clear_insecure_registries:
        raise typer.BadParameter(
            "Use --insecure-registry or --clear-insecure-registries, not both."
        )

    updates: dict[str, object]
    if data:
        try:
            raw_updates = json.loads(data)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"Invalid JSON: {exc}") from exc
        if not isinstance(raw_updates, dict):
            raise typer.BadParameter("--json must contain a JSON object.", param_hint="--json")
        updates = raw_updates
    else:
        updates = {}

    if system_timezone or any(
        value is not None for value in (log_level, retention_days, max_total_size, timezone)
    ):
        logging = _section(updates, "logging")
        if log_level is not None:
            logging["level"] = log_level.value
        if retention_days is not None:
            logging["retentionDays"] = retention_days
        if max_total_size is not None:
            logging["maxTotalSize"] = max_total_size
        if timezone is not None or system_timezone:
            logging["timezone"] = timezone or None

    if (
        ssh_port_start is not None
        or ssh_port_end is not None
        or auto_enable_ssh_forwarding is not None
        or vnc_port_start is not None
        or vnc_port_end is not None
    ):
        networking = _section(updates, "networking")
        if ssh_port_start is not None:
            networking["sshPortRangeStart"] = ssh_port_start
        if ssh_port_end is not None:
            networking["sshPortRangeEnd"] = ssh_port_end
        if auto_enable_ssh_forwarding is not None:
            networking["autoEnableSSHForwarding"] = auto_enable_ssh_forwarding
        if vnc_port_start is not None:
            networking["vncPortRangeStart"] = vnc_port_start
        if vnc_port_end is not None:
            networking["vncPortRangeEnd"] = vnc_port_end

    if (
        default_registry is not None
        or clear_default_registry
        or insecure_registry is not None
        or clear_insecure_registries
        or max_blob_transfers is not None
        or max_compressions is not None
        or max_decompressions is not None
        or max_disk_writes is not None
    ):
        images = _section(updates, "images")
        if default_registry is not None or clear_default_registry:
            images["defaultRegistry"] = default_registry or None
        if insecure_registry is not None or clear_insecure_registries:
            images["insecureRegistries"] = insecure_registry or []
        if max_blob_transfers is not None:
            images["maxParallelImageBlobTransfers"] = max_blob_transfers
        if max_compressions is not None:
            images["maxParallelImageCompressions"] = max_compressions
        if max_decompressions is not None:
            images["maxParallelImageDecompressions"] = max_decompressions
        if max_disk_writes is not None:
            images["maxParallelImageDiskWrites"] = max_disk_writes

    if not updates:
        raise typer.BadParameter("Provide --json or at least one config flag.")

    result = context.client.update_config(updates)
    if context.human_output and isinstance(result, dict):
        context.console.print("Config updated.", highlight=False)
        if "networking" in updates:
            context.error_console.print(
                "Networking changes take effect after the agent restarts.",
                highlight=False,
            )
        return
    render_output(
        context.console,
        result,
        output_format=context.settings.output,
        title="Config Updated",
    )


def _section(updates: dict[str, object], name: str) -> dict[str, object]:
    existing = updates.setdefault(name, {})
    if not isinstance(existing, dict):
        raise typer.BadParameter(f"Config section '{name}' must be a JSON object.")
    return existing


def _print_config(context: CliContext, data: dict[str, object], *, title: str) -> None:
    """Print config as grouped human settings."""
    context.console.print(f"[bold]{title}[/]")
    api = data.get("api")
    if isinstance(api, dict):
        host = api.get("host")
        port = api.get("port")
        endpoint = f"{host}:{port}" if host and port else host or port
        context.console.print("[bold]api[/]")
        if endpoint:
            context.console.print(f"  endpoint: {endpoint}", highlight=False, markup=False)
        _print_setting(context, "concurrent requests", api.get("maxConcurrentRequests"))

    logging = data.get("logging")
    if isinstance(logging, dict):
        context.console.print("[bold]logging[/]")
        _print_setting(context, "level", logging.get("level"))
        _print_setting(context, "file logs", _yes_no(logging.get("enableFileLogging")))
        _print_setting(context, "retention", _days(logging.get("retentionDays")))
        _print_setting(context, "max size", logging.get("maxTotalSize"))
        _print_setting(context, "timezone", logging.get("timezone") or "system")

    networking = data.get("networking")
    if isinstance(networking, dict):
        ssh = _range_text(networking.get("sshPortRangeStart"), networking.get("sshPortRangeEnd"))
        vnc = _range_text(networking.get("vncPortRangeStart"), networking.get("vncPortRangeEnd"))
        auto_ssh = _yes_no(networking.get("autoEnableSSHForwarding"))
        context.console.print("[bold]networking[/]")
        _print_setting(context, "ssh ports", ssh)
        _print_setting(context, "auto ssh", auto_ssh)
        _print_setting(context, "vnc ports", vnc)

    images = data.get("images")
    if isinstance(images, dict):
        insecure = images.get("insecureRegistries")
        insecure_text = (
            ", ".join(str(item) for item in insecure) if isinstance(insecure, list) else None
        )
        context.console.print("[bold]images[/]")
        _print_setting(context, "registry", images.get("defaultRegistry") or "none")
        _print_setting(context, "insecure registries", insecure_text or "none")
        _print_setting(context, "blob transfers", images.get("maxParallelImageBlobTransfers"))
        _print_setting(context, "compressions", images.get("maxParallelImageCompressions"))
        _print_setting(context, "decompressions", images.get("maxParallelImageDecompressions"))
        _print_setting(context, "disk writes", images.get("maxParallelImageDiskWrites"))


def _print_setting(context: CliContext, label: str, value: object) -> None:
    if value is None or value == "":
        return
    context.console.print(f"  {label}: {value}", highlight=False, markup=False)


def _yes_no(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


def _days(value: object) -> str | None:
    if value is None:
        return None
    return f"{value} days"


def _range_text(start: object, end: object) -> str | None:
    if start is None and end is None:
        return None
    if start == end:
        return str(start)
    return f"{start}-{end}"
