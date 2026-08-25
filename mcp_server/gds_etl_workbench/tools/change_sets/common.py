"""Small primitives shared by governed Metadata and Model Change Sets."""

from __future__ import annotations

import hashlib
import json

from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict

MAX_STAGE_CHUNK_BYTES = 450 * 1024
MAX_STAGE_CHUNKS = 64
MAX_STAGE_CHUNK_RECORDS = 5_000
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ChangeSetContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_records_sha256(records: list[dict[str, object]]) -> str:
    encoded = json.dumps(
        records,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def stage_batch_sha256(chunk_sha256s: list[str]) -> str:
    return hashlib.sha256("".join(chunk_sha256s).encode("ascii")).hexdigest()


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
