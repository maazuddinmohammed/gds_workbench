"""Transport-neutral primitives shared by Metadata and Model Change Sets."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

MAX_STAGE_CHUNK_BYTES = 450 * 1024
MAX_MODEL_STAGE_CHUNK_BYTES = 1024 * 1024
MAX_STAGE_CHUNKS = 64
MAX_STAGE_CHUNK_RECORDS = 5_000
MAX_MODEL_STAGE_PAYLOAD_BYTES = MAX_MODEL_STAGE_CHUNK_BYTES * MAX_STAGE_CHUNKS
MAX_MODEL_STAGE_FRAGMENT_BASE64_CHARACTERS = 4 * ((MAX_MODEL_STAGE_CHUNK_BYTES + 2) // 3)
SHA256_PATTERN = r"^[0-9a-f]{64}$"
MAX_AGENT_VALIDATION_ERROR_EXAMPLES = 25
MAX_AGENT_VALIDATION_ERROR_GROUPS = 100


class ChangeSetContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChangeSetValidationErrorGroup(ChangeSetContractModel):
    dataset: str
    code: str
    count: int = Field(gt=0)


def bounded_validation_outcome(value: object) -> dict[str, object] | None:
    """Bound old persisted validation documents before returning them to an agent."""
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    source = cast(Mapping[str, object], value)
    raw_errors = source.get("errors")
    errors = cast(list[object], raw_errors) if isinstance(raw_errors, list) else []
    bounded_errors: list[dict[str, object]] = []
    for item in errors[:MAX_AGENT_VALIDATION_ERROR_EXAMPLES]:
        if not isinstance(item, Mapping):
            continue
        error = cast(Mapping[str, object], item)
        fields = error.get("fields")
        raw_fields = cast(list[object], fields) if isinstance(fields, list) else []
        record_number = error.get("record_number")
        bounded_errors.append(
            {
                "code": str(error.get("code", "unknown"))[:64],
                "dataset": str(error.get("dataset", "unknown"))[:100],
                "record_number": record_number if isinstance(record_number, int) else None,
                "fields": [str(field)[:100] for field in raw_fields[:20]],
                "message": str(error.get("message", "Validation failed."))[:300],
            }
        )
    raw_groups = source.get("error_groups")
    if isinstance(raw_groups, list):
        group_documents = cast(list[object], raw_groups)
    else:
        group_counts: Counter[tuple[str, str]] = Counter()
        for item in errors:
            if not isinstance(item, Mapping):
                continue
            error = cast(Mapping[str, object], item)
            group_counts[
                (
                    str(error.get("dataset", "unknown"))[:100],
                    str(error.get("code", "unknown"))[:64],
                )
            ] += 1
        group_documents = [
            {"dataset": dataset, "code": code, "count": count}
            for (dataset, code), count in sorted(group_counts.items())
        ]
    bounded_groups: list[dict[str, object]] = []
    for item in group_documents[:MAX_AGENT_VALIDATION_ERROR_GROUPS]:
        if not isinstance(item, Mapping):
            continue
        group = cast(Mapping[str, object], item)
        count = group.get("count")
        if not isinstance(count, int) or count < 1:
            continue
        bounded_groups.append(
            {
                "dataset": str(group.get("dataset", "unknown"))[:100],
                "code": str(group.get("code", "unknown"))[:64],
                "count": count,
            }
        )
    error_count = source.get("error_count")
    if not isinstance(error_count, int) or error_count < 0:
        error_count = len(errors)
    phase = source.get("phase")
    staged_record_count = source.get("staged_record_count")
    action_review = source.get("action_review")
    raw_action_review = (
        cast(list[object], action_review)[:25] if isinstance(action_review, list) else []
    )
    bounded_action_review: list[dict[str, object]] = []
    for item in raw_action_review:
        if not isinstance(item, Mapping):
            continue
        review = cast(Mapping[str, object], item)
        raw_keys = review.get("keys")
        keys = cast(list[object], raw_keys) if isinstance(raw_keys, list) else []
        bounded_keys: list[dict[str, object]] = []
        for key_item in keys[:100]:
            if not isinstance(key_item, Mapping):
                continue
            key = cast(Mapping[str, object], key_item)
            action = key.get("action")
            natural_key = key.get("natural_key")
            if action not in {
                "insert",
                "update",
                "deactivate",
                "reactivate",
                "no_change",
            } or not isinstance(natural_key, Mapping):
                continue
            natural_key_fields = cast(Mapping[object, object], natural_key)
            bounded_natural_key: dict[str, object] = {}
            for field, field_value in list(natural_key_fields.items())[:20]:
                field_name = str(field)[:100]
                if isinstance(field_value, str):
                    bounded_natural_key[field_name] = field_value[:300]
                elif field_value is None or isinstance(field_value, (bool, int)):
                    bounded_natural_key[field_name] = field_value
            bounded_keys.append({"action": action, "natural_key": bounded_natural_key})
        action_counts: dict[str, int] = {}
        for count_name in (
            "insert_count",
            "update_count",
            "deactivate_count",
            "reactivate_count",
            "no_change_count",
        ):
            count = review.get(count_name)
            action_counts[count_name] = count if isinstance(count, int) and count >= 0 else 0
        bounded_action_review.append(
            {
                "dataset": str(review.get("dataset", "unknown"))[:100],
                **action_counts,
                "keys": bounded_keys,
                "keys_truncated": (
                    review.get("keys_truncated") is True or len(keys) > len(bounded_keys)
                ),
            }
        )
    return {
        "schema_version": "1.0",
        "valid": source.get("valid") is True,
        "phase": str(phase)[:50] if isinstance(phase, str) else "unknown",
        "staged_record_count": (
            staged_record_count
            if isinstance(staged_record_count, int) and staged_record_count >= 0
            else 0
        ),
        "error_count": error_count,
        "error_groups": bounded_groups,
        "errors": bounded_errors,
        "errors_truncated": (
            source.get("errors_truncated") is True
            or len(errors) > len(bounded_errors)
            or error_count > len(bounded_errors)
        ),
        "action_review": bounded_action_review,
    }


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
    "MAX_AGENT_VALIDATION_ERROR_EXAMPLES",
    "MAX_AGENT_VALIDATION_ERROR_GROUPS",
    "MAX_STAGE_CHUNK_BYTES",
    "MAX_STAGE_CHUNK_RECORDS",
    "MAX_STAGE_CHUNKS",
    "SHA256_PATTERN",
    "ChangeSetContractModel",
    "ChangeSetValidationErrorGroup",
    "bounded_validation_outcome",
    "canonical_records_bytes",
    "canonical_records_sha256",
    "decode_canonical_base64_fragment",
    "stage_batch_sha256",
]
