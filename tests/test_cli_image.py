"""Tests for image commands."""

from __future__ import annotations

from typing import Any

from tests.conftest import IMAGE_RESPONSE

IMAGE_ID = IMAGE_RESPONSE["id"]


def test_image_list(invoke: Any) -> None:
    """List images."""
    result = invoke(["--output", "json", "image", "list"])
    assert result.exit_code == 0
    assert "registry.example.com" in result.output


def test_image_ls_alias(invoke: Any) -> None:
    """The 'ls' alias works."""
    result = invoke(["image", "ls"])
    assert result.exit_code == 0


def test_image_get(invoke: Any) -> None:
    """Get image details."""
    result = invoke(["--output", "json", "image", "get", IMAGE_ID])
    assert result.exit_code == 0
    assert "registry.example.com" in result.output


def test_image_show_alias(invoke: Any) -> None:
    """The 'show' alias works."""
    result = invoke(["image", "show", IMAGE_ID])
    assert result.exit_code == 0


def test_image_delete_confirmed(invoke: Any) -> None:
    """Delete image with --yes."""
    result = invoke(["image", "delete", IMAGE_ID, "--yes"])
    assert result.exit_code == 0
    assert "deleted" in result.output.lower()


def test_image_delete_abort(invoke: Any) -> None:
    """Delete image without --yes can be aborted."""
    result = invoke(["image", "delete", IMAGE_ID], input="n\n")
    assert result.exit_code != 0


def test_image_wipe_confirmed(invoke: Any) -> None:
    """Wipe all images with --yes."""
    result = invoke(["image", "wipe", "--yes"])
    assert result.exit_code == 0


def test_image_pull(invoke: Any) -> None:
    """Pull an image."""
    result = invoke(["image", "pull", "registry.example.com/image:latest"])
    assert result.exit_code == 0
    assert "pulled" in result.output.lower() or "registry" in result.output.lower()


def test_image_pull_with_timeout(invoke: Any) -> None:
    """Pull an image with command timeout."""
    result = invoke(["image", "pull", "registry.example.com/image:latest", "--timeout", "3600"])
    assert result.exit_code == 0


def test_image_push_with_vm(invoke: Any) -> None:
    """Push an image from a VM source."""
    result = invoke(
        [
            "image",
            "push",
            "registry.example.com/image:latest",
            "--vm",
            "550e8400-e29b-41d4-a716-446655440000",
        ]
    )
    assert result.exit_code == 0


def test_image_push_no_source(invoke: Any) -> None:
    """Push without --vm or --image fails."""
    result = invoke(["image", "push", "registry.example.com/image:latest"])
    assert result.exit_code != 0


def test_image_push_both_sources(invoke: Any) -> None:
    """Push with both --vm and --image fails."""
    result = invoke(
        [
            "image",
            "push",
            "registry.example.com/image:latest",
            "--vm",
            "aaa",
            "--image",
            "bbb",
        ]
    )
    assert result.exit_code != 0
