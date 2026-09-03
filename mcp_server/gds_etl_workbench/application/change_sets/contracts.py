"""Transport-neutral primitives shared by Metadata and Model Change Sets."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json

from pydantic import BaseModel, ConfigDict

MAX_STAGE_CHUNK_BYTES = 450 * 1024
MAX_MODEL_STAGE_CHUNK_BYTES = 1024 * 1024
MAX_STAGE_CHUNKS = 64
MAX_STAGE_CHUNK_RECORDS = 5_000
MAX_MODEL_STAGE_PAYLOAD_BYTES = MAX_MODEL_STAGE_CHUNK_BYTES * MAX_STAGE_CHUNKS
MAX_MODEL_STAGE_FRAGMENT_BASE64_CHARACTERS = 4 * ((MAX_MODEL_STAGE_CHUNK_BYTES + 2) // 3)
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ChangeSetContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_records_bytes(records: list[dict[str, object]]) -> bytes:
    return json.dumps(
        records,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_records_sha256(records: list[dict[str, object]]) -> str:
    return hashlib.sha256(canonical_records_bytes(records)).hexdigest()


def decode_canonical_base64_fragment(value: str) -> bytes:
    if not value or len(value) > MAX_MODEL_STAGE_FRAGMENT_BASE64_CHARACTERS:
        raise ValueError("Stage payload fragment is invalid.")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Stage payload fragment is invalid.") from None
    if (
        not decoded
        or len(decoded) > MAX_MODEL_STAGE_CHUNK_BYTES
        or base64.b64encode(decoded).decode("ascii") != value
    ):
        raise ValueError("Stage payload fragment is invalid.")
    return decoded


def stage_batch_sha256(chunk_sha256s: list[str]) -> str:
    return hashlib.sha256("".join(chunk_sha256s).encode("ascii")).hexdigest()


__all__ = [
    "MAX_MODEL_STAGE_CHUNK_BYTES",
    "MAX_MODEL_STAGE_FRAGMENT_BASE64_CHARACTERS",
    "MAX_MODEL_STAGE_PAYLOAD_BYTES",
    "MAX_STAGE_CHUNK_BYTES",
    "MAX_STAGE_CHUNK_RECORDS",
    "MAX_STAGE_CHUNKS",
    "SHA256_PATTERN",
    "ChangeSetContractModel",
    "canonical_records_bytes",
    "canonical_records_sha256",
    "decode_canonical_base64_fragment",
    "stage_batch_sha256",
]
