"""OCI image management commands."""

from __future__ import annotations

from typing import Annotated

import typer

from jeballto_cli._context import require_context
from jeballto_cli.render import render_output

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command("list")
def list_images(
    ctx: typer.Context,
    limit: Annotated[
        int | None, typer.Option("--limit", "-l", help="Max results to return (1-1000).")
    ] = None,
    offset: Annotated[
        int | None, typer.Option("--offset", help="Number of results to skip.")
    ] = None,
) -> None:
    """List all OCI images."""
    context = require_context(ctx)
    data = context.client.list_images(limit=limit, offset=offset)
    if isinstance(data, dict):
        render_output(
            context.console,
            data.get("images", []),
            output_format=context.settings.output,
            title="Images",
        )
    else:
        render_output(context.console, data, output_format=context.settings.output, title="Images")


@app.command("ls", hidden=True)
def list_images_alias(
    ctx: typer.Context,
    limit: Annotated[
        int | None, typer.Option("--limit", "-l", help="Max results to return (1-1000).")
    ] = None,
    offset: Annotated[
        int | None, typer.Option("--offset", help="Number of results to skip.")
    ] = None,
) -> None:
    """List all OCI images (alias for 'list')."""
    list_images(ctx, limit=limit, offset=offset)


@app.command()
def get(
    ctx: typer.Context,
    image_id: Annotated[str, typer.Argument(help="Image identifier (UUID).")],
) -> None:
    """Get details for an OCI image."""
    context = require_context(ctx)
    data = context.client.get_image(image_id)
    render_output(context.console, data, output_format=context.settings.output, title="Image")


@app.command("show", hidden=True)
def get_alias(
    ctx: typer.Context,
    image_id: Annotated[str, typer.Argument(help="Image identifier (UUID).")],
) -> None:
    """Get details for an OCI image (alias for 'get')."""
    get(ctx, image_id)


@app.command()
def delete(
    ctx: typer.Context,
    image_id: Annotated[str, typer.Argument(help="Image identifier (UUID).")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")] = False,
) -> None:
    """Delete an OCI image."""
    context = require_context(ctx)
    if not yes:
        typer.confirm(f"Delete image {image_id}?", abort=True)
    context.client.delete_image(image_id)
    context.console.print("[green]Image deleted.[/]")


@app.command("rm", hidden=True)
def delete_alias(
    ctx: typer.Context,
    image_id: Annotated[str, typer.Argument(help="Image identifier (UUID).")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")] = False,
) -> None:
    """Delete an OCI image (alias for 'delete')."""
    delete(ctx, image_id, yes=yes)


@app.command()
def wipe(
    ctx: typer.Context,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Confirm wipe.")] = False,
) -> None:
    """Delete ALL OCI images."""
    context = require_context(ctx)
    if not yes:
        typer.confirm("This will delete ALL images. Continue?", abort=True)
    data = context.client.wipe_images()
    render_output(context.console, data, output_format=context.settings.output, title="Wipe Result")


@app.command()
def pull(
    ctx: typer.Context,
    reference: Annotated[str, typer.Argument(help="Image reference (e.g. registry/image:tag).")],
    timeout: Annotated[
        int | None, typer.Option("--timeout", min=1, help="Timeout in seconds.")
    ] = None,
) -> None:
    """Pull an OCI image from a registry."""
    context = require_context(ctx)
    data = context.client.pull_image(reference, timeout=timeout)
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="Image Pulled",
    )


@app.command()
def push(
    ctx: typer.Context,
    reference: Annotated[str, typer.Argument(help="Target image reference.")],
    vm: Annotated[str | None, typer.Option("--vm", help="Source VM identifier (UUID).")] = None,
    image: Annotated[
        str | None, typer.Option("--image", help="Source image identifier (UUID).")
    ] = None,
    timeout: Annotated[
        int | None, typer.Option("--timeout", min=1, help="Timeout in seconds.")
    ] = None,
) -> None:
    """Push an image to an OCI registry.

    Provide exactly one of --vm or --image as the source.
    """
    if not vm and not image:
        raise typer.BadParameter("Provide --vm or --image as the push source.")
    if vm and image:
        raise typer.BadParameter("Provide only one of --vm or --image, not both.")
    source = f"vm:{vm}" if vm else f"image:{image}"
    context = require_context(ctx)
    data = context.client.push_image(reference, source=source, timeout=timeout)
    render_output(
        context.console,
        data,
        output_format=context.settings.output,
        title="Image Pushed",
    )
