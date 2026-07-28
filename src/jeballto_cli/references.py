"""Human-friendly resource reference resolution with full pagination."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

import typer

from jeballto_cli._context import CliContext
from jeballto_cli.client import JSONValue

PageFetcher = Callable[..., JSONValue]


def _canonical_uuid(value: str) -> str | None:
    try:
        return str(UUID(value))
    except (AttributeError, ValueError):
        return None


def _list_all(fetch: PageFetcher, collection_key: str) -> list[dict[str, Any]]:
    """Read every API page while protecting against a broken pagination loop."""
    offset = 0
    resources: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    while True:
        payload = fetch(limit=1000, offset=offset)
        if not isinstance(payload, dict):
            break
        page = payload.get(collection_key)
        if not isinstance(page, list) or not page:
            break

        added = 0
        for item in page:
            if not isinstance(item, dict):
                continue
            resource_id = item.get("id")
            identity = str(resource_id) if resource_id is not None else repr(item)
            if identity in seen_ids:
                continue
            seen_ids.add(identity)
            resources.append(item)
            added += 1

        if added == 0:
            break
        offset += len(page)
        total = payload.get("total")
        if isinstance(total, int) and offset >= total:
            break
        if len(page) < 1000 and not isinstance(total, int):
            break

    return resources


def resolve_vm_id(context: CliContext, vm_ref: str) -> str:
    """Resolve a canonical VM UUID or unique VM name."""
    canonical_id = _canonical_uuid(vm_ref)
    if canonical_id is not None:
        return canonical_id

    vms = _list_all(context.client.list_vms, "vms")
    matches = [vm for vm in vms if vm.get("name") == vm_ref]
    if not matches:
        folded = vm_ref.casefold()
        matches = [vm for vm in vms if str(vm.get("name", "")).casefold() == folded]

    if len(matches) == 1:
        vm_id = matches[0].get("id")
        if isinstance(vm_id, str) and vm_id:
            return vm_id
    if len(matches) > 1:
        choices = "\n".join(f"  - {_vm_summary(vm)}" for vm in matches)
        raise typer.BadParameter(
            f"More than one VM is named '{vm_ref}'. Use an ID:\n{choices}",
            param_hint="vm",
        )
    raise typer.BadParameter(
        f"No VM named '{vm_ref}' was found. Run 'jeballto vm list' or pass an ID.",
        param_hint="vm",
    )


def resolve_image_id(context: CliContext, image_ref: str) -> str:
    """Resolve a canonical image UUID or unique OCI reference."""
    canonical_id = _canonical_uuid(image_ref)
    if canonical_id is not None:
        return canonical_id

    images = _list_all(context.client.list_images, "images")
    matches = [image for image in images if image.get("reference") == image_ref]
    if len(matches) == 1:
        image_id = matches[0].get("id")
        if isinstance(image_id, str) and image_id:
            return image_id
    if len(matches) > 1:
        choices = "\n".join(f"  - {_image_summary(image)}" for image in matches)
        raise typer.BadParameter(
            f"More than one image has reference '{image_ref}'. Use an ID:\n{choices}",
            param_hint="image",
        )
    raise typer.BadParameter(
        f"No image with reference '{image_ref}' was found. "
        "Run 'jeballto image list' or pass an ID.",
        param_hint="image",
    )


def _vm_summary(vm: dict[str, Any]) -> str:
    return f"{vm.get('name', '')} ({vm.get('state', 'unknown')}) {vm.get('id', '')}"


def _image_summary(image: dict[str, Any]) -> str:
    digest = f" {image['digest']}" if image.get("digest") else ""
    return f"{image.get('reference', '')}{digest} {image.get('id', '')}"
