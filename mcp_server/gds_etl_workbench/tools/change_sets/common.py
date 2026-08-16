"""Small primitives shared by governed Metadata and Model Change Sets."""

from __future__ import annotations

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict


class ChangeSetContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


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
