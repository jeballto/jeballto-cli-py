"""Tests for human-friendly resource reference resolution."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
import typer

from jeballto_cli.references import resolve_image_id, resolve_vm_id


class _FakeClient:
    def __init__(
        self,
        *,
        vms: list[dict[str, Any]] | None = None,
        images: list[dict[str, Any]] | None = None,
        page_size: int = 1000,
    ) -> None:
        self._vms = vms or []
        self._images = images or []
        self._page_size = page_size
        self.vm_offsets: list[int] = []
        self.image_offsets: list[int] = []

    def list_vms(self, *, limit: int, offset: int) -> dict[str, Any]:
        self.vm_offsets.append(offset)
        size = min(limit, self._page_size)
        return {
            "vms": self._vms[offset : offset + size],
            "total": len(self._vms),
            "limit": size,
            "offset": offset,
        }

    def list_images(self, *, limit: int, offset: int) -> dict[str, Any]:
        self.image_offsets.append(offset)
        size = min(limit, self._page_size)
        return {
            "images": self._images[offset : offset + size],
            "total": len(self._images),
            "limit": size,
            "offset": offset,
        }


def _context(client: Any) -> Any:
    return cast(Any, SimpleNamespace(client=client))


def test_canonical_uuid_is_returned_without_api_lookup() -> None:
    """UUID references are normalized locally and do not trigger a list request."""
    client = _FakeClient()

    resolved = resolve_vm_id(_context(client), "550E8400-E29B-41D4-A716-446655440000")

    assert resolved == "550e8400-e29b-41d4-a716-446655440000"
    assert client.vm_offsets == []


def test_resolve_vm_name_from_later_page() -> None:
    """A VM name can resolve beyond the first API page."""
    client = _FakeClient(
        vms=[
            {"id": "11111111-1111-4111-8111-111111111111", "name": "first"},
            {"id": "22222222-2222-4222-8222-222222222222", "name": "dev"},
        ],
        page_size=1,
    )

    resolved = resolve_vm_id(_context(client), "dev")

    assert resolved == "22222222-2222-4222-8222-222222222222"
    assert client.vm_offsets == [0, 1]


def test_resolve_vm_name_uses_case_insensitive_fallback() -> None:
    """VM names tolerate case differences when no exact match exists."""
    client = _FakeClient(vms=[{"id": "11111111-1111-4111-8111-111111111111", "name": "Developer"}])

    assert resolve_vm_id(_context(client), "developer") == "11111111-1111-4111-8111-111111111111"


def test_resolve_vm_id_reports_duplicate_names() -> None:
    """Duplicate VM names require the user to select a concrete ID."""
    client = _FakeClient(
        vms=[
            {"id": "11111111-1111-4111-8111-111111111111", "name": "dev", "state": "running"},
            {"id": "22222222-2222-4222-8222-222222222222", "name": "dev", "state": "stopped"},
        ]
    )

    with pytest.raises(typer.BadParameter) as exc_info:
        resolve_vm_id(_context(client), "dev")

    message = str(exc_info.value)
    assert "More than one VM is named" in message
    assert "11111111-1111-4111-8111-111111111111" in message
    assert "22222222-2222-4222-8222-222222222222" in message
    assert "Use an ID" in message


def test_missing_vm_has_discovery_hint() -> None:
    """A missing VM reference points to the list command."""
    with pytest.raises(typer.BadParameter, match="jeballto vm list"):
        resolve_vm_id(_context(_FakeClient()), "missing")


def test_resolve_image_reference_from_later_page() -> None:
    """An OCI reference can resolve beyond the first API page."""
    client = _FakeClient(
        images=[
            {
                "id": "33333333-3333-4333-8333-333333333333",
                "reference": "registry.example.com/other:latest",
            },
            {
                "id": "44444444-4444-4444-8444-444444444444",
                "reference": "registry.example.com/image:latest",
            },
        ],
        page_size=1,
    )

    resolved = resolve_image_id(_context(client), "registry.example.com/image:latest")

    assert resolved == "44444444-4444-4444-8444-444444444444"
    assert client.image_offsets == [0, 1]


def test_resolve_image_id_reports_duplicate_references() -> None:
    """Duplicate image references require the user to select a concrete ID."""
    client = _FakeClient(
        images=[
            {
                "id": "33333333-3333-4333-8333-333333333333",
                "reference": "registry.example.com/image:latest",
                "digest": "sha256:first",
            },
            {
                "id": "44444444-4444-4444-8444-444444444444",
                "reference": "registry.example.com/image:latest",
                "digest": "sha256:second",
            },
        ]
    )

    with pytest.raises(typer.BadParameter) as exc_info:
        resolve_image_id(_context(client), "registry.example.com/image:latest")

    message = str(exc_info.value)
    assert "More than one image has reference" in message
    assert "33333333-3333-4333-8333-333333333333" in message
    assert "44444444-4444-4444-8444-444444444444" in message
    assert "Use an ID" in message


class _RepeatingClient:
    """Simulate an API that ignores offsets and repeats the same page."""

    def __init__(self) -> None:
        self.calls = 0

    def list_vms(self, *, limit: int, offset: int) -> dict[str, Any]:
        self.calls += 1
        return {
            "vms": [{"id": "11111111-1111-4111-8111-111111111111", "name": "first"}],
            "total": 2,
            "limit": limit,
            "offset": offset,
        }


def test_pagination_stops_when_api_repeats_the_same_page() -> None:
    """A broken API page loop cannot make reference resolution hang."""
    client = _RepeatingClient()

    with pytest.raises(typer.BadParameter, match="No VM named"):
        resolve_vm_id(_context(client), "missing")

    assert client.calls == 2
