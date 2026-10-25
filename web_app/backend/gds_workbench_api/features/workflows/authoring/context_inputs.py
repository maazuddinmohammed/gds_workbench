"""Project compact approved prompt inputs from one authorized frozen context."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from gds_etl_workbench.domain.modeling_records import normalize_project_key_value

from gds_workbench_api.features.context.context import select_context_records

from .audit_policy import effective_audit_template
from .context_contracts import WORKFLOW_INPUTS
from .gold_policy import effective_gold_templates
from .naming import effective_naming_instructions
from .subject_area_policy import load_subject_area_policy

OBJECT_FIELDS = ("tenant_code", "system_code", "connection_code", "object_schema", "object_name")
ATTRIBUTE_FIELDS = (
    "attribute_name",
    "attribute_description",
    "attribute_data_type",
    "attribute_inferred_data_type",
    "attribute_nullability",
    "is_natural_key",
    "is_surrogate_key",
    "is_masking_required",
    "is_meta_data",
)


def natural_key(row: Mapping[str, Any], fields: tuple[str, ...] = OBJECT_FIELDS) -> tuple[Any, ...]:
    return tuple(
        normalize_project_key_value(row[field]) if isinstance(row[field], str) else row[field]
        for field in fields
    )


def project_key_fields(family: str, kind: str) -> tuple[str, ...]:
    if kind == "submodel":
        return (f"{family}_submodel_name",)
    if kind == "entity":
        return (f"{family}_entity_schema_name", f"{family}_entity_name")
    if kind == "attribute":
        return (f"{family}_entity_schema_name", f"{family}_entity_name", f"{family}_attribute_name")
    fields = (
        f"from_{family}_entity_schema_name",
        f"from_{family}_entity_name",
        f"from_{family}_attribute_name",
        f"to_{family}_entity_schema_name",
        f"to_{family}_entity_name",
        f"to_{family}_attribute_name",
    )
    return (
        (*fields, f"{family}_relationship_name")
        if family == "logical"
        else (*fields, "dimensional_relationship_kind", "dimensional_relationship_role_name")
    )


def project_context_inputs(
    context: Mapping[str, Any], *, context_source_scope: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """Selection and applicable sections are already authorized by the context repository."""
    workflow = context["project_workflow"]
    values: dict[str, Any] = {
        "source_context": deepcopy(context.get("source_context", [])),
        "gds_context": deepcopy(context.get("gds_context", [])),
        "ingestion_mapping": deepcopy(context.get("ingestion_mapping", [])),
        "selected_logical_entities": deepcopy(context.get("selected_logical_entities", [])),
        "object_context": [],
        "object_attribute_context": [],
        "object_relationship_context": [],
        "context_records": [],
    }
    profiles = {
        (*natural_key(p), normalize_project_key_value(p["attribute_name"])): p
        for p in context["profiles"]
    }
    provenance = {
        (*natural_key(p), normalize_project_key_value(p["attribute_name"])): p
        for p in context.get("profile_provenance", [])
    }
    physical_objects = (
        context.get("supporting_objects", [])
        if workflow == "dimensional"
        else context["selected_objects"]
    )
    selected_keys = {natural_key(s["object"]) for s in physical_objects}
    for selected in physical_objects:
        obj = selected["object"]
        key = {name: obj[name] for name in OBJECT_FIELDS}
        values["object_context"].append(
            {**key, "object_description": obj["object_description"], "zone_code": obj["zone_code"]}
        )
        attributes: list[dict[str, Any]] = []
        for attr in selected["attributes"]:
            attribute_key = (
                *natural_key(attr),
                normalize_project_key_value(attr["attribute_name"]),
            )
            saved_profile = profiles.get(attribute_key)
            profile = None
            if saved_profile is not None:
                profile = {
                    name: value
                    for name, value in saved_profile.items()
                    if name not in (*OBJECT_FIELDS, "attribute_name")
                }
                # Decimal values are JSON strings in the persisted DTO, but numeric prompt data.
                for name in (
                    "avg_data_length",
                    "percent_populated",
                    "percent_duplicates",
                    "percent_null",
                    "percent_blank",
                    "percent_distinct",
                ):
                    if profile[name] is not None:
                        profile[name] = float(profile[name])
                recorded = provenance.get(attribute_key, {})
                profile.update(
                    {
                        name: recorded.get(name)
                        for name in ("profiled_at", "row_scope", "batch_attribute_name", "batch_id")
                    }
                )
            attributes.append(
                {
                    **{name: attr[name] for name in ATTRIBUTE_FIELDS},
                    "registered_is_natural_key": attr["is_natural_key"],
                    **{
                        name: attr.get("enrichment", {}).get(name)
                        for name in ("is_natural_key", "is_primary_key", "is_nullable", "is_pii")
                    },
                    "profile": profile,
                }
            )
        values["object_attribute_context"].append(
            {
                **key,
                "attributes": attributes,
                "selected_attribute_names": [a["attribute_name"] for a in attributes],
            }
        )
        group: dict[str, Any] = {**key, "incoming_relationships": [], "outgoing_relationships": []}
        for rel in context["analysis_relationships"]:
            endpoints = {
                side: {f: rel[f"{side}_{f}"] for f in OBJECT_FIELDS} for side in ("from", "to")
            }
            if not any(natural_key(endpoint) in selected_keys for endpoint in endpoints.values()):
                continue
            # Saved relationships can contextualize an unselected endpoint without
            # adding it to the frozen Object/Attribute authoring selection.
            evidence = deepcopy(rel)
            for side, direction in (("from", "outgoing"), ("to", "incoming")):
                if natural_key(endpoints[side]) == natural_key(obj):
                    group[f"{direction}_relationships"].append(evidence)
        values["object_relationship_context"].append(group)
    values["context_records"] = select_context_records(
        context["context"],
        source_scope=[
            *context_source_scope,
            *context.get("source_context", []),
            *(item["object"] for item in physical_objects),
        ],
    )
    families = {
        "logical": ("logical",),
        "dimensional": ("logical", "dimensional"),
    }
    for family in families.get(workflow, ()):
        section = context["applied"].get(family)
        for kind in ("submodel", "entity", "attribute", "relationship"):
            plural = "entities" if kind == "entity" else kind + "s"
            rows = None if section is None else deepcopy(section[plural])
            values[f"{family}_{plural}"] = rows
            fields = project_key_fields(family, kind)
            values[f"{family}_{kind}_list"] = (
                None if rows is None else [{name: row[name] for name in fields} for row in rows]
            )
    if workflow in {"logical", "subject_area"}:
        # Answers cite selected Objects by these short ids; the backend numbers them the same way.
        values["table_index"] = [
            {"table": f"t{position}", **{name: selected["object"][name] for name in OBJECT_FIELDS}}
            for position, selected in enumerate(context["selected_objects"], start=1)
        ]
    if workflow == "subject_area":
        values.update(_subject_area_inputs(context))
    details = context["project_details"]
    if workflow in ("logical", "dimensional"):
        layer = "silver" if workflow == "logical" else "gold"
        values["coverage_threshold_percent"] = details.get(
            f"{workflow}_coverage_threshold_percent", 70 if workflow == "logical" else 60
        )
        values["naming_instructions"] = effective_naming_instructions(
            workflow, details[f"{layer}_model_naming_instructions"]
        )
        values["schemas"] = deepcopy(details[f"{workflow}_schemas"])
        values["audit_columns"] = effective_audit_template(
            details[f"{layer}_model_audit_columns_template"]
        )
        if workflow == "logical":
            values["logical_entity_scd_type"] = details.get("logical_entity_scd_type")
        if workflow == "dimensional":
            values["dimensional_entity_scd_type"] = details.get("dimensional_entity_scd_type")
            values["technical_columns"], values["audit_columns"] = effective_gold_templates(
                details["gold_model_technical_columns_template"],
                details["gold_model_audit_columns_template"],
            )
    return {name: values[name] for name in WORKFLOW_INPUTS[workflow]}


# Strongest measured result first; null is unvalidated, not disproven.
_VALIDATION_STRENGTH: dict[str | None, int] = {
    "supported": 3,
    "inconclusive": 2,
    None: 1,
    "unsupported": 0,
}


def _subject_area_inputs(context: Mapping[str, Any]) -> dict[str, Any]:
    """Compact whole-Scope evidence for one Subject Area answer, by table_index id."""
    selected = context["selected_objects"]
    table_ids = {
        natural_key(item["object"]): f"t{position}" for position, item in enumerate(selected, 1)
    }
    row_counts: dict[tuple[Any, ...], int] = {}
    for profile in context["profiles"]:
        key = natural_key(profile)
        row_counts[key] = max(row_counts.get(key, 0), profile["row_count"])
    links: dict[tuple[str, str], dict[str, Any]] = {}
    for relationship in context["analysis_relationships"]:
        if relationship["analysis_result_status"] != "active":
            continue
        source, target = (
            table_ids.get(
                natural_key({name: relationship[f"{side}_{name}"] for name in OBJECT_FIELDS})
            )
            for side in ("from", "to")
        )
        if source is None or target is None or source == target:
            continue
        result = relationship["validation_result"]
        link = links.setdefault(
            (source, target),
            {"from": source, "to": target, "validation_result": result, "edge_count": 0},
        )
        link["edge_count"] += 1
        if _VALIDATION_STRENGTH[result] > _VALIDATION_STRENGTH[link["validation_result"]]:
            link["validation_result"] = result
    applied: Mapping[str, list[Mapping[str, Any]]] = context["applied"].get("subject_area") or {
        "areas": [],
        "tables": [],
    }
    memberships: dict[str, list[Mapping[str, Any]]] = {}
    for membership in applied["tables"]:
        if natural_key(membership) in table_ids:
            name = normalize_project_key_value(membership["subject_area_name"])
            memberships.setdefault(name, []).append(membership)

    def ordered(ids: list[str]) -> list[str]:
        return sorted(ids, key=lambda table: int(table[1:]))

    return {
        "scope_tables": [
            {
                "table": table_ids[natural_key(item["object"])],
                "description": item["object"]["object_description"],
                "zone_code": item["object"]["zone_code"],
                "row_count": row_counts.get(natural_key(item["object"])),
                "column_count": len(item["attributes"]),
                "column_names": [attribute["attribute_name"] for attribute in item["attributes"]],
            }
            for item in selected
        ],
        "table_links": sorted(
            links.values(), key=lambda link: (int(link["from"][1:]), int(link["to"][1:]))
        ),
        "existing_subject_areas": [
            {
                "name": area["subject_area_name"],
                "definition": area["subject_area_definition"],
                "status": area["subject_area_status"],
                "is_locked": area["subject_area_is_locked"],
                "tables": ordered(
                    [
                        table_ids[natural_key(membership)]
                        for membership in rows
                        if membership["subject_area_table_status"] == "active"
                    ]
                ),
                "locked_tables": ordered(
                    [
                        table_ids[natural_key(membership)]
                        for membership in rows
                        if membership["subject_area_table_is_locked"]
                    ]
                ),
            }
            for area in applied["areas"]
            for rows in (
                memberships.get(normalize_project_key_value(area["subject_area_name"]), []),
            )
        ],
        "max_subject_area_columns": load_subject_area_policy().max_subject_area_columns,
    }
