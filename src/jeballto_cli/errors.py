"""User-facing CLI error mapping and recovery hints."""

from __future__ import annotations

from typing import Any

import click
import typer
import yaml
from rich.text import Text
from typer.core import TyperGroup

from jeballto_cli._context import CliContext
from jeballto_cli.client import APIError
from jeballto_cli.settings import OutputFormat


class CLIError(Exception):
    """Expected local or remote operation failure with an optional recovery hint."""

    def __init__(self, message: str, *, hint: str | None = None, exit_code: int = 1) -> None:
        self.message = message
        self.hint = hint
        self.exit_code = exit_code
        super().__init__(message)


_CODE_HINTS = {
    "CAPABILITY_UNAVAILABLE": "Run 'jeballto system capabilities' to inspect host support.",
    "EXECUTE_TIMEOUT": "Increase 'jeballto vm exec --timeout' and retry if the command is safe.",
    "IMAGE_IN_USE": "Stop or delete the VM using this image, then retry.",
    "INVALID_RESPONSE": "Check the agent version and logs, then retry the request.",
    "INVALID_REFERENCE": "Check the registry host, repository, tag, or sha256 digest.",
    "INVALID_STATE": "Run 'jeballto vm get <vm>' and retry from a supported VM state.",
    "MAINTENANCE_IN_PROGRESS": "Wait for the current reset or wipe operation, then retry.",
    "REGISTRY_AUTH_FAILED": "Check the credentials with 'jeballto registry login <host>'.",
    "REGISTRY_AUTH_TIMEOUT": "Check registry connectivity, then retry the login.",
    "REGISTRY_UNAVAILABLE": "Check registry connectivity and its configured protocol.",
    "SSH_NOT_CONFIGURED": "Run 'jeballto vm ssh enable <vm>' before executing commands.",
    "TOO_MANY_IMAGE_OPERATIONS": (
        "Wait for a transfer or inspect it with 'jeballto image operation list --active'."
    ),
    "UNSUPPORTED_IMAGE_FORMAT": "Use an image created with Jeballto VM Bundle Format v1.",
    "VM_LIMIT_REACHED": "Stop an active VM before starting another one.",
}


def _api_hint(error: APIError) -> str | None:
    hint = _CODE_HINTS.get(error.code)
    if hint:
        return hint
    if error.code == "REQUEST_TIMEOUT":
        return "Increase --request-timeout for this API request and retry."
    if error.code == "NETWORK_ERROR":
        return "Check that Jeballto is running and verify --base-url."
    if error.status_code == 401:
        return "Copy the token from the Jeballto menu-bar app, then run 'jeballto auth login'."
    if error.status_code == 404:
        return "List the resource again. It may have been renamed or deleted."
    if error.status_code == 409:
        return "Inspect the current resource state, resolve the conflict, and retry."
    if error.status_code == 429:
        return "Wait briefly before retrying the request."
    if error.status_code == 413:
        return "Reduce the request size and retry."
    if error.status_code == 503:
        return "The agent is temporarily unavailable. Check capabilities or retry shortly."
    if error.status_code == 504:
        return "The agent operation timed out. Inspect its current status before retrying."
    return None


def _error_payload(error: APIError, hint: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": error.code,
        "message": error.message,
        "status": error.status_code,
    }
    if error.details:
        body["details"] = error.details
    if hint:
        body["hint"] = hint
    return {"error": body}


def _print_structured_error(
    context: CliContext,
    error: APIError,
    hint: str | None,
) -> None:
    payload = _error_payload(error, hint)
    if context.settings.output in {OutputFormat.JSON, OutputFormat.JSONL}:
        import json

        indent = 2 if context.settings.output == OutputFormat.JSON else None
        separators = None if indent else (",", ":")
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=indent,
            separators=separators,
            allow_nan=False,
        )
        context.error_console.file.write(f"{serialized}\n")
        context.error_console.file.flush()
        return
    context.error_console.file.write(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))
    context.error_console.file.flush()


def _print_human_error(
    context: CliContext,
    message: str,
    *,
    code: str | None = None,
    status: int | None = None,
    details: dict[str, Any] | None = None,
    hint: str | None = None,
) -> None:
    context.error_console.print(Text.assemble(("Error:", "bold red"), f" {message}"))
    if code and context.settings.details:
        status_text = f", HTTP {status}" if status else ""
        context.error_console.print(f"code: {code}{status_text}", highlight=False)
        if details:
            context.error_console.print("details:", highlight=False)
            context.error_console.print(
                yaml.safe_dump(details, sort_keys=False, allow_unicode=True).rstrip(),
                markup=False,
                highlight=False,
            )
    if hint:
        context.error_console.print(Text.assemble(("Hint:", "bold"), f" {hint}"))


def _print_local_error(
    context: CliContext,
    message: str,
    *,
    hint: str | None = None,
) -> None:
    if context.settings.output == OutputFormat.HUMAN:
        _print_human_error(context, message, hint=hint)
        return
    error = APIError(status_code=0, code="CLI_ERROR", message=message)
    _print_structured_error(context, error, hint)


class ErrorHandlingGroup(TyperGroup):
    """Root command group that turns runtime failures into stable CLI errors."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except typer.Exit:
            raise
        except click.ClickException as error:
            context = ctx.find_object(CliContext)
            if context is None or context.settings.output == OutputFormat.HUMAN:
                raise
            structured_error = APIError(
                status_code=0,
                code="CLI_USAGE_ERROR",
                message=error.format_message(),
            )
            _print_structured_error(context, structured_error, None)
            raise typer.Exit(code=error.exit_code) from error
        except click.Abort:
            raise
        except APIError as error:
            context = ctx.find_object(CliContext)
            if context is None:
                raise
            hint = _api_hint(error)
            if context.settings.output == OutputFormat.HUMAN:
                _print_human_error(
                    context,
                    error.message,
                    code=error.code,
                    status=error.status_code,
                    details=error.details,
                    hint=hint,
                )
            else:
                _print_structured_error(context, error, hint)
            raise typer.Exit(code=1) from error
        except CLIError as error:
            context = ctx.find_object(CliContext)
            if context is None or context.settings.debug:
                raise
            _print_local_error(context, error.message, hint=error.hint)
            raise typer.Exit(code=error.exit_code) from error
        except (OSError, ValueError) as error:
            context = ctx.find_object(CliContext)
            if context is None or context.settings.debug:
                raise
            _print_local_error(
                context,
                str(error),
                hint="Rerun with --debug if you need a traceback.",
            )
            raise typer.Exit(code=1) from error
        except Exception as error:
            context = ctx.find_object(CliContext)
            if context is None or context.settings.debug:
                raise
            _print_local_error(
                context,
                f"Unexpected CLI failure: {error}",
                hint="Rerun with --debug, then report the traceback if the problem persists.",
            )
            raise typer.Exit(code=1) from error
