"""Project compact approved prompt inputs from one authorized frozen context."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from gds_etl_workbench.domain.modeling_records import normalize_model_key_value

from .context_contracts import WORKFLOW_INPUTS
from .naming import effective_naming_instructions

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
ASSERTION_FIELDS = (
    "modeling_assertion_record_key",
    "modeling_assertion_document_name",
    "modeling_assertion_record_type",
    "modeling_assertion_text",
    "modeling_assertion_details",
    "modeling_assertion_source_location",
    "modeling_assertion_confidence",
)


def natural_key(row: Mapping[str, Any], fields: tuple[str, ...] = OBJECT_FIELDS) -> tuple[Any, ...]:
    return tuple(
        normalize_model_key_value(row[field]) if isinstance(row[field], str) else row[field]
        for field in fields
    )


def model_key_fields(family: str, kind: str) -> tuple[str, ...]:
    if family == "conceptual":
        return (
            ("conceptual_object_name",)
            if kind == "object"
            else (
                "from_conceptual_object_name",
                "to_conceptual_object_name",
                "conceptual_relationship_name",
            )
        )
    if kind in {"submodel", "entity"}:
        return (f"{family}_{kind}_name",)
    if kind == "attribute":
        return (f"{family}_entity_name", f"{family}_attribute_name")
    fields = (
        f"from_{family}_entity_name",
        f"from_{family}_attribute_name",
        f"to_{family}_entity_name",
        f"to_{family}_attribute_name",
    )
    return (
        (*fields, f"{family}_relationship_name")
        if family == "logical"
        else (*fields, "dimensional_relationship_kind", "dimensional_relationship_role_name")
    )


def project_context_inputs(context: Mapping[str, Any]) -> dict[str, Any]:
    """Selection and applicable sections are already authorized by the context repository."""
    workflow = context["model_workflow"]
    values: dict[str, Any] = {
        "source_context": deepcopy(context.get("source_context", [])),
        "gds_context": deepcopy(context.get("gds_context", [])),
        "ingestion_mapping": deepcopy(context.get("ingestion_mapping", [])),
        "logical_bindings": deepcopy(context.get("logical_bindings", [])),
        "object_context": [],
        "object_attribute_context": [],
        "object_relationship_context": [],
        "modeling_assertions": [],
    }
    profiles = {
        (*natural_key(p), normalize_model_key_value(p["attribute_name"])): p
        for p in context["profiles"]
    }
    provenance = {
        (*natural_key(p), normalize_model_key_value(p["attribute_name"])): p
        for p in context.get("profile_provenance", [])
    }
    selected_keys = {natural_key(s["object"]) for s in context["selected_objects"]}
    for selected in context["selected_objects"]:
        obj = selected["object"]
        key = {name: obj[name] for name in OBJECT_FIELDS}
        values["object_context"].append(
            {**key, "object_description": obj["object_description"], "zone_code": obj["zone_code"]}
        )
        attributes: list[dict[str, Any]] = []
        for attr in selected["attributes"]:
            attribute_key = (*natural_key(attr), normalize_model_key_value(attr["attribute_name"]))
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
                {**{name: attr[name] for name in ATTRIBUTE_FIELDS}, "profile": profile}
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
            if any(natural_key(endpoint) not in selected_keys for endpoint in endpoints.values()):
                continue
            evidence = {
                name: value for name, value in rel.items() if not name.startswith("validation_")
            }
            for side, direction in (("from", "outgoing"), ("to", "incoming")):
                if natural_key(endpoints[side]) == natural_key(obj):
                    group[f"{direction}_relationships"].append(evidence)
        values["object_relationship_context"].append(group)
    docs = {
        normalize_model_key_value(d["modeling_assertion_document_name"])
        for d in context["assertion"]["documents"]
        if d["is_active"]
    }
    values["modeling_assertions"] = [
        {name: r[name] for name in ASSERTION_FIELDS}
        for r in context["assertion"]["records"]
        if r["modeling_assertion_record_status"] == "active"
        and normalize_model_key_value(r["modeling_assertion_document_name"]) in docs
        and workflow in r["modeling_assertion_applicable_layers"]
    ]
    for family in ("conceptual", "logical", "dimensional"):
        section = context["applied"].get(family)
        kinds = (
            ("object", "relationship")
            if family == "conceptual"
            else ("submodel", "entity", "attribute", "relationship")
        )
        for kind in kinds:
            plural = "entities" if kind == "entity" else kind + "s"
            rows = None if section is None else deepcopy(section[plural])
            values[f"{family}_{plural}"] = rows
            fields = model_key_fields(family, kind)
            values[f"{family}_{kind}_list"] = (
                None if rows is None else [{name: row[name] for name in fields} for row in rows]
            )
    details = context["model_details"]
    if workflow in {"logical", "dimensional"}:
        layer = "silver" if workflow == "logical" else "gold"
        values["naming_instructions"] = effective_naming_instructions(
            workflow, details[f"{layer}_model_naming_instructions"]
        )
        values["audit_columns"] = deepcopy(details[f"{layer}_model_audit_columns_template"])
        if workflow == "dimensional":
            values["technical_columns"] = deepcopy(details["gold_model_technical_columns_template"])
    return {name: values[name] for name in WORKFLOW_INPUTS[workflow]}
