"""Shared safety bounds for normalized Modeling Assertion content."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

ASSERTION_DOCUMENT_METADATA_MAX_BYTES = 65_536
ASSERTION_RECORD_DETAILS_MAX_BYTES = 262_144
ASSERTION_RECORD_SOURCE_LOCATION_MAX_BYTES = 65_536
ASSERTION_RECORD_TEXT_MAX_CHARACTERS = 262_144
ASSERTION_SECTION_MAX_BYTES = 4 * 1024 * 1024

_FORBIDDEN_JSON_KEYS = frozenset(
    {
        "binary_content",
        "connection_string",
        "content",
        "credentials",
        "file_content",
        "payload",
        "physical_rows",
        "prompt",
        "raw",
        "raw_content",
        "raw_physical_rows",
        "raw_prompt",
        "raw_rows",
        "raw_tool_output",
        "rows",
        "secret",
        "token",
        "tool_output",
        "workbook_content",
        "worksheet_content",
    }
)


def validate_assertion_json(
    value: Mapping[str, object],
    *,
    maximum_bytes: int | None,
    label: str,
) -> None:
    """Reject prohibited JSON; optionally enforce the Assertion storage envelope."""
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} is not safe JSON") from error
    if maximum_bytes is not None and len(encoded) > maximum_bytes:
        raise ValueError(f"{label} is too large")

    node_count = 0
    pending: list[tuple[object, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        node_count += 1
        if maximum_bytes is not None and (node_count > 4096 or depth > 12):
            raise ValueError(f"{label} is too complex")
        if maximum_bytes is not None and isinstance(item, str) and len(item) > 32_768:
            raise ValueError(f"{label} contains an oversized string")
        if isinstance(item, list):
            pending.extend((child, depth + 1) for child in cast(list[object], item))
        elif isinstance(item, dict):
            for key, child in cast(dict[object, object], item).items():
                if not isinstance(key, str):
                    raise ValueError(f"{label} is not safe JSON")
                normalized_key = key.strip(" ").lower().replace("-", "_")
                compact_key = normalized_key.replace("_", "")
                if (
                    normalized_key in _FORBIDDEN_JSON_KEYS
                    or "secret" in compact_key
                    or "credential" in compact_key
                    or "connectionstring" in compact_key
                    or "rawprompt" in compact_key
                    or "rawrows" in compact_key
                    or "tooloutput" in compact_key
                    or "filecontent" in compact_key
                    or "workbookcontent" in compact_key
                    or "worksheetcontent" in compact_key
                ):
                    raise ValueError(f"{label} contains prohibited raw content")
                pending.append((child, depth + 1))


__all__ = [
    "ASSERTION_DOCUMENT_METADATA_MAX_BYTES",
    "ASSERTION_RECORD_DETAILS_MAX_BYTES",
    "ASSERTION_RECORD_SOURCE_LOCATION_MAX_BYTES",
    "ASSERTION_RECORD_TEXT_MAX_CHARACTERS",
    "ASSERTION_SECTION_MAX_BYTES",
    "validate_assertion_json",
]
