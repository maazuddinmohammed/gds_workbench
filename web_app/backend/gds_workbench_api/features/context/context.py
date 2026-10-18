"""Select active saved Context using the workflow's authorized source Systems."""

from collections.abc import Mapping, Sequence
from typing import Any

from gds_etl_workbench.domain.modeling_records import normalize_project_key_value


def select_context_records(
    section: Mapping[str, Any],
    *,
    source_scope: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    systems = {
        normalize_project_key_value(str(row["system_code"]))
        for row in source_scope
        if row.get("system_code")
    }
    groups = {
        normalize_project_key_value(group["context_group_name"]): group
        for group in section["groups"]
        if group["is_active"]
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
