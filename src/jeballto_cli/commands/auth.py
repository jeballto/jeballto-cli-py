"""API token onboarding and verification commands."""

from __future__ import annotations

from dataclasses import replace
from typing import Annotated

import typer

from jeballto_cli._context import require_context
from jeballto_cli.client import APIError, JeballtoClient
from jeballto_cli.errors import CLIError
from jeballto_cli.keychain import KeychainError, delete_token, save_token, validate_token
from jeballto_cli.render import render_output
from jeballto_cli.settings import TokenSource

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.command()
def login(
    ctx: typer.Context,
    token: Annotated[
        str | None,
        typer.Option(
            "--token",
            help="API token copied from the Jeballto menu-bar app.",
            envvar="JEBALLTO_TOKEN",
        ),
    ] = None,
) -> None:
    """Verify and save an API token in the macOS Keychain."""
    context = require_context(ctx)
    resolved_token = token
    if resolved_token is None and context.settings.token_source in {
        TokenSource.ARGUMENT,
        TokenSource.ENVIRONMENT,
    }:
        resolved_token = context.settings.token
    if resolved_token is None:
        if context.settings.no_input:
            raise typer.BadParameter(
                "Pass --token when --no-input is enabled.",
                param_hint="--token",
            )
        resolved_token = typer.prompt("API token", hide_input=True, err=True)

    try:
        resolved_token = validate_token(resolved_token)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--token") from exc

    verification_settings = replace(
        context.settings,
        token=resolved_token,
        token_source=TokenSource.ARGUMENT,
    )
    with JeballtoClient(verification_settings) as client:
        client.auth_verify()

    try:
        save_token(context.settings.base_url, resolved_token)
    except KeychainError as exc:
        raise CLIError(
            str(exc),
            hint="Unlock your login Keychain and retry.",
        ) from exc

    result = {
        "status": "authenticated",
        "baseUrl": context.settings.base_url,
        "storedIn": "macOS Keychain",
    }
    if context.human_output:
        context.console.print("Authentication configured.", highlight=False)
        context.console.print(
            f"agent: {context.settings.base_url}",
            highlight=False,
            markup=False,
        )
        context.console.print("stored in: macOS Keychain", highlight=False)
    else:
        render_output(context.console, result, output_format=context.settings.output)


@app.command()
def status(ctx: typer.Context) -> None:
    """Show token source and verify access to the agent."""
    context = require_context(ctx)
    authenticated = False
    if context.settings.token is not None:
        try:
            context.client.auth_verify()
            authenticated = True
        except APIError as exc:
            if exc.status_code != 401:
                raise

    result = {
        "status": "authenticated" if authenticated else "not_authenticated",
        "baseUrl": context.settings.base_url,
        "tokenSource": context.settings.token_source.value,
    }
    if context.human_output:
        context.console.print(f"Auth: {result['status']}", highlight=False)
        context.console.print(
            f"agent: {context.settings.base_url}",
            highlight=False,
            markup=False,
        )
        context.console.print(
            f"token source: {context.settings.token_source.value}", highlight=False
        )
        if not authenticated:
            context.error_console.print(
                "Copy the token from the Jeballto menu-bar app, then run 'jeballto auth login'.",
                highlight=False,
            )
    else:
        render_output(context.console, result, output_format=context.settings.output)
    if not authenticated:
        raise typer.Exit(code=1)


@app.command()
def logout(ctx: typer.Context) -> None:
    """Delete the saved Keychain token for this agent URL."""
    context = require_context(ctx)
    try:
        deleted = delete_token(context.settings.base_url)
    except KeychainError as exc:
        raise CLIError(
            str(exc),
            hint="Unlock your login Keychain and retry.",
        ) from exc

    result = {
        "success": True,
        "deleted": deleted,
        "baseUrl": context.settings.base_url,
    }
    if context.human_output:
        message = "Saved token deleted." if deleted else "No saved token was found."
        context.console.print(message, highlight=False)
        if context.settings.token_source in {TokenSource.ARGUMENT, TokenSource.ENVIRONMENT}:
            context.error_console.print(
                "A token passed by flag or environment remains active for this process.",
                highlight=False,
            )
    else:
        render_output(context.console, result, output_format=context.settings.output)
