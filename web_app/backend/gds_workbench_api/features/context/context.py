"""Select active saved Context using the workflow's authorized source Systems."""

from collections.abc import Collection, Mapping, Sequence
from typing import Any

from gds_etl_workbench.domain.modeling_records import normalize_project_key_value


def select_context_records(
    section: Mapping[str, Any],
    *,
    source_scope: Sequence[Mapping[str, Any]],
    workflow: str,
) -> list[dict[str, Any]]:
    """Records of the Types routed to this workflow, from groups in scope of its Systems."""
    systems = {
        normalize_project_key_value(str(row["system_code"]))
        for row in source_scope
        if row.get("system_code")
    }
    routed_types = {
        normalize_project_key_value(context_type["context_type_name"])
        for context_type in section["types"]
        if workflow in context_type["context_type_workflows"]
    }
    groups = {
        normalize_project_key_value(group["context_group_name"]): group
        for group in section["groups"]
        if group["is_active"]
        and normalize_project_key_value(group["context_type_name"]) in routed_types
        and (
            not group["source_system_code"]
            or normalize_project_key_value(group["source_system_code"]) in systems
        )
    }
    records: list[dict[str, Any]] = []
    for record in section["records"]:
        group = groups.get(normalize_project_key_value(record["context_group_name"]))
        if record["status"] != "active" or group is None:
            continue
        records.append(
            {
                "context_record_id": record["context_record_id"],
                "context_group_name": group["context_group_name"],
                "context_type_name": group["context_type_name"],
                "context_text": record["context_text"],
                "source_reference": record["source_reference"],
            }
        )
    return records


def with_cited_context_records(
    section: Mapping[str, Any], records: list[dict[str, Any]], cited: Collection[str]
) -> list[dict[str, Any]]:
    """Add active records the shown Entities cite, whatever their Type or System."""
    present = {normalize_project_key_value(record["context_record_id"]) for record in records}
    cited_ids = {normalize_project_key_value(record_id) for record_id in cited}
    groups = {
        normalize_project_key_value(group["context_group_name"]): group
        for group in section["groups"]
        if group["is_active"]
    }
    extra: list[dict[str, Any]] = []
    for record in section["records"]:
        record_id = normalize_project_key_value(record["context_record_id"])
        group = groups.get(normalize_project_key_value(record["context_group_name"]))
        if (
            record_id in cited_ids
            and record_id not in present
            and group
            and record["status"] == "active"
        ):
            extra.append(
                {
                    "context_record_id": record["context_record_id"],
                    "context_group_name": group["context_group_name"],
                    "context_type_name": group["context_type_name"],
                    "context_text": record["context_text"],
                    "source_reference": record["source_reference"],
                }
            )
    return [*records, *extra]
