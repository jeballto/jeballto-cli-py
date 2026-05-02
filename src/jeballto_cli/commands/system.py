"""System-level operation commands."""

from __future__ import annotations

from typing import Annotated

import typer

from jeballto_cli._context import require_context
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command()
def reset(
    ctx: typer.Context,
    mode: Annotated[
        str,
        typer.Argument(help="Reset mode: 'soft' or 'hard'."),
    ],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")] = False,
) -> None:
    """Reset the agent to a clean state.

    [bold]soft[/] - Deletes all VMs, images, and IPSW cache. Keeps configuration and logs.

    [bold]hard[/] - Deletes everything the application stores and terminates the process.
    The next startup will be completely fresh.

    Requires --yes to confirm, since this operation is destructive and cannot be undone.
    """
    if mode not in ("soft", "hard"):
        raise typer.BadParameter("Mode must be 'soft' or 'hard'.", param_hint="mode")

    context = require_context(ctx)
    if not yes:
        warning = (
            f"This will perform a [bold red]{mode}[/] reset. All VMs and images will be deleted."
        )
        if mode == "hard":
            warning += " The agent process will terminate."
        context.console.print(warning)
        typer.confirm("Continue?", abort=True)

    data = context.client.system_reset(mode)
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="System Reset",
    )
