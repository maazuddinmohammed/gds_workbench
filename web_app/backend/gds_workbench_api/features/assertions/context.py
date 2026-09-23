"""Compact, scope-aware Assertion evidence shared by modeling and Mapping prompts."""

from collections.abc import Mapping, Sequence
from typing import Any

from gds_etl_workbench.domain.modeling_records import normalize_model_key_value

ASSERTION_FIELDS = (
    "modeling_assertion_record_key",
    "modeling_assertion_document_name",
    "modeling_assertion_record_type",
    "modeling_assertion_text",
    "modeling_assertion_details",
    "modeling_assertion_source_location",
    "modeling_assertion_confidence",
)


def project_assertions(
    section: Mapping[str, Any],
    *,
    source_scope: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Model-wide requirements apply everywhere; scoped documents require a matching source."""
    scope = {
        (
            normalize_model_key_value(str(row["tenant_code"])),
            normalize_model_key_value(str(row["system_code"])),
        )
        for row in source_scope
        if row.get("tenant_code") and row.get("system_code")
    }
    documents: set[str] = set()
    for document in section["documents"]:
        tenant = document.get("tenant_code")
        system = document.get("system_code")
        if document["is_active"] and (
            not tenant
            and not system
            or any(
                (not tenant or normalize_model_key_value(tenant) == t)
                and (not system or normalize_model_key_value(system) == s)
                for t, s in scope
            )
        ):
            documents.add(normalize_model_key_value(document["modeling_assertion_document_name"]))
    return [
        {name: record[name] for name in ASSERTION_FIELDS}
        for record in section["records"]
        if record["modeling_assertion_record_status"] == "active"
        and normalize_model_key_value(record["modeling_assertion_document_name"]) in documents
    ]
