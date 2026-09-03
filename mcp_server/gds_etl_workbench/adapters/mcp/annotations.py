"""MCP annotations shared by Change Set tool adapters."""

from mcp.types import ToolAnnotations


def change_set_annotations(
    *,
    read_only: bool,
    idempotent: bool,
    destructive: bool = False,
) -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=read_only,
        destructive_hint=destructive,
        idempotent_hint=idempotent,
        open_world_hint=False,
    )


__all__ = ["change_set_annotations"]
