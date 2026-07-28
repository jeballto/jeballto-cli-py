"""System-level operation commands."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

import typer

from jeballto_cli._context import CliContext, require_context
from jeballto_cli.keychain import KeychainError, delete_token
from jeballto_cli.render import render_output
from jeballto_cli.settings import TokenSource
from jeballto_cli.ui import confirm_action, has_failures, yes_no

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


class ResetMode(StrEnum):
    """Supported system reset modes."""

    soft = "soft"
    hard = "hard"


@app.command()
def capabilities(ctx: typer.Context) -> None:
    """Show what this host can run."""
    context = require_context(ctx)
    data = context.client.system_capabilities()
    if context.human_output and isinstance(data, dict):
        _print_capabilities(context, data)
        return
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="System Capabilities",
    )


@app.command()
def reset(
    ctx: typer.Context,
    mode: Annotated[
        ResetMode,
        typer.Argument(help="Use soft to keep settings, or hard to wipe everything."),
    ],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation.")] = False,
) -> None:
    """Delete local Jeballto state.

    [bold]soft[/] - Cancels active work and deletes all VMs, images, and IPSW cache.
    Keeps configuration and logs.

    [bold]hard[/] - Also deletes config, logs, the API token, registry credentials,
    and all other agent state. The process terminates only after full success.

    Requires --yes to confirm, since this operation is destructive and cannot be undone.
    """
    context = require_context(ctx)
    warning = (
        f"Perform a {mode.value} reset, cancel active work, and force-delete every VM and image?"
    )
    if mode == ResetMode.hard:
        warning = (
            "Perform a hard reset, including active work, config, logs, API token, "
            "registry credentials, VMs, images, and caches?"
        )
    confirm_action(context, warning, yes=yes)

    data = context.client.system_reset(mode.value)
    if context.human_output and isinstance(data, dict):
        _print_reset_result(context, data)
    else:
        render_output(
            context.console,
            data,
            output_format=context.settings.output,
            title="System Reset",
        )
    failed = _reset_failed(data)
    if mode == ResetMode.hard and not failed:
        _delete_obsolete_cli_token(context)
    if failed:
        raise typer.Exit(code=1)


def _print_capabilities(context: CliContext, data: dict[str, object]) -> None:
    context.console.print("[bold]System Capabilities[/]")
    host = data.get("host")
    if isinstance(host, dict):
        arch = host.get("architecture")
        version = host.get("macOSVersion")
        virtualization = yes_no(host.get("virtualizationSupported"))
        max_vms = host.get("maxConcurrentVMs")
        context.console.print(
            f"host: {arch or 'unknown'}, macOS {version or 'unknown'}, "
            f"virtualization {virtualization}, max VMs {max_vms or 'unknown'}",
            highlight=False,
        )
    features = data.get("features")
    if isinstance(features, list):
        context.console.print("features:", highlight=False)
        for feature in features:
            if not isinstance(feature, dict):
                continue
            name = feature.get("id") or "feature"
            status = feature.get("status") or "unknown"
            enabled = yes_no(feature.get("enabled"))
            lifecycle = feature.get("lifecycle")
            minimum_os = feature.get("minimumOS")
            suffix_parts = [str(lifecycle)] if lifecycle else []
            if minimum_os:
                suffix_parts.append(f"min macOS {minimum_os}")
            suffix = f", {', '.join(suffix_parts)}" if suffix_parts else ""
            context.console.print(
                f"  {name}: {status}, enabled {enabled}{suffix}",
                highlight=False,
            )
            reason = feature.get("reason")
            if reason:
                context.console.print(f"    reason: {reason}", highlight=False, markup=False)
            deprecation = feature.get("deprecation")
            if isinstance(deprecation, dict):
                since = deprecation.get("since")
                message = deprecation.get("message")
                context.console.print(
                    f"    deprecated since {since}: {message}",
                    highlight=False,
                    markup=False,
                )


def _print_reset_result(context: CliContext, data: dict[str, object]) -> None:
    mode = data.get("mode") or "reset"
    context.console.print(f"System reset: {mode}", highlight=False)
    context.console.print(
        f"VMs deleted: {data.get('vmsDeleted', 0)} (failed: {data.get('vmsFailed', 0)})",
        highlight=False,
    )
    context.console.print(
        f"images deleted: {data.get('imagesDeleted', 0)} (failed: {data.get('imagesFailed', 0)})",
        highlight=False,
    )
    context.console.print(
        f"IPSW cache cleared: {yes_no(data.get('ipswCacheCleared'))}",
        highlight=False,
    )
    context.console.print(
        f"config deleted: {yes_no(data.get('configDeleted'))}",
        highlight=False,
    )
    context.console.print(
        f"logs deleted: {yes_no(data.get('logsDeleted'))}",
        highlight=False,
    )
    if data.get("willTerminate"):
        context.console.print("agent will terminate: yes", highlight=False)
    errors = data.get("errors")
    if errors:
        context.console.print(f"errors: {errors}", highlight=False, markup=False)


def _reset_failed(data: object) -> bool:
    if has_failures(data, count_fields=("vmsFailed", "imagesFailed")):
        return True
    if not isinstance(data, dict):
        return False
    if data.get("ipswCacheCleared") is False:
        return True
    return data.get("mode") == ResetMode.hard.value and data.get("willTerminate") is not True


def _delete_obsolete_cli_token(context: CliContext) -> None:
    """Remove the CLI copy after a hard reset deletes the agent token."""
    if context.settings.token_source != TokenSource.KEYCHAIN:
        return
    try:
        deleted = delete_token(context.settings.base_url)
    except KeychainError as exc:
        context.error_console.print(
            f"Warning: hard reset succeeded, but the old CLI Keychain token remains: {exc}",
            highlight=False,
            markup=False,
        )
        return
    if deleted and context.human_output:
        context.console.print("CLI Keychain token deleted.", highlight=False)
