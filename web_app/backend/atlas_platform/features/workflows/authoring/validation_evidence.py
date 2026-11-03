"""System-wide Validation coverage index and exact evidence for individual Checks."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

# Fixed tuple order is documented in the reader/prompt. None means missing metadata.
_FIELD_INDEX = (
    "attribute_name",
    "attribute_data_type",
    "attribute_nullability",
    "is_natural_key",
    "is_surrogate_key",
    "population",
    "is_active",
)


def validation_basis(
    values: Mapping[str, Any],
    *,
    fits: Callable[[dict[str, Any]], bool],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    core: list[dict[str, Any]] = []
    details: dict[str, list[dict[str, Any]]] = {}
    shared: dict[tuple[str, str], str] = {}

    def index_rows(kind: str, ref: str, rows: Sequence[Any]) -> None:
        # Group short index entries to avoid hundreds of tool turns, and split on
        # entry boundaries when a stage has configured a smaller per-page budget.
        offset = 0
        while offset < len(rows):
            count = min(64, len(rows) - offset)
            while True:
                card = {"kind": kind, "ref": ref, "record": {"rows": rows[offset : offset + count]}}
                if count == 1 or fits(card):
                    break
                count //= 2
            core.append(card)
            offset += count

    def reference(kind: str, record: dict[str, Any]) -> str:
        # Source coordinates or template codes alone cannot establish identity:
        # another target or branch can carry a different frozen value or rule.
        key = (kind, json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        if key not in shared:
            ref = f"r{len(shared) + 1}"
            shared[key] = ref
            if kind == "source":
                obj = record["object"]
                details[ref] = [
                    {"kind": "source_attribute", "ref": ref, "record": attr}
                    for attr in obj["attributes"]
                ]
                record = {**record, "object": {k: v for k, v in obj.items() if k != "attributes"}}
            core.append({"kind": kind, "ref": ref, "record": record})
        return shared[key]

    for i, target in enumerate(values["mapping_evidence"], 1):
        ref = f"t{i}"
        ctx = target["context"]
        meta = {k: v for k, v in ctx["target_metadata"].items() if k != "attributes"}
        for name in ("audit_columns_template", "technical_columns_template"):
            if isinstance(meta.get(name), dict):
                meta[name] = reference(name, meta[name])
        target_record = {
            **{k: v for k, v in target.items() if k != "context"},
            "target_metadata": meta,
            "source_systems": ctx["source_systems"],
            "mapping_templates": [
                reference("mapping_template", row) for row in ctx["mapping_templates"]
            ],
        }
        core.append({"kind": "target", "ref": ref, "record": target_record})
        index_rows("source_refs", ref, [reference("source", row) for row in ctx["source_metadata"]])
        attrs = ctx["target_metadata"].get("attributes", [])
        index_rows("target_fields", ref, [[a.get(k) for k in _FIELD_INDEX] for a in attrs])
        target_details = [
            {"kind": "target_attribute", "ref": ref, "record": attr} for attr in attrs
        ]
        for j, row in enumerate(cast(list[dict[str, Any]], ctx["object_transformations"]), 1):
            entity = cast(dict[str, Any] | None, row.get("entity"))
            if entity is not None and isinstance(entity.get("context_records"), list):
                entity = {
                    **entity,
                    "context_records": [reference("context", r) for r in entity["context_records"]],
                }
                row = {**row, "entity": entity}
            header = {k: v for k, v in row.items() if k != "transformation"}
            header["has_transformation"] = row.get("transformation") is not None
            object_ref = f"{ref}.o{j}"
            header["object_rule_ref"] = object_ref
            core.append({"kind": "object_rule_header", "ref": ref, "record": header})
            object_rule = {"kind": "object_transformation", "ref": ref, "record": row}
            details[object_ref] = [object_rule]
            target_details.append(object_rule)
        index_rows(
            "mapped_fields",
            ref,
            [
                [
                    r["source_system_code"],
                    r["target_attribute_name"],
                    r["transformation"] is not None,
                ]
                for r in ctx["attribute_transformations"]
            ],
        )
        target_details.extend(
            {"kind": "attribute_transformation", "ref": ref, "record": row}
            for row in ctx["attribute_transformations"]
        )
        details[ref] = target_details
    for artifact in values["current_code"]:
        header = {k: v for k, v in artifact.items() if k != "generated_code_content"}
        core.append({"kind": "code_header", "record": header})
    for group in values["applied_groups"]:
        core.append({"kind": "applied_group", "record": group})
    for i, check in enumerate(values["applied_checks"], 1):
        check_ref = f"c{i}"
        # The frozen full definition remains addressable. Explicitly keeping it
        # needs only its Group and Check names, even for very large saved SQL.
        header = {
            k: v
            for k, v in check.items()
            if k
            not in {
                "validation_query_sql",
                "validation_comparison_query_sql",
                "validation_comparison_value",
            }
        }
        core.append({"kind": "applied_check", "ref": check_ref, "record": header})
        details[check_ref] = [{"kind": "check_definition", "ref": check_ref, "record": check}]
    return core, details
