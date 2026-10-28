"""Project compact approved prompt inputs from one authorized frozen context."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from gds_etl_workbench.domain.modeling_records import normalize_project_key_value

from gds_workbench_api.features.context.context import (
    select_context_records,
    with_cited_context_records,
)

from .audit_policy import effective_audit_template
from .context_contracts import WORKFLOW_INPUTS
from .gold_policy import effective_gold_templates
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


def natural_key(row: Mapping[str, Any], fields: tuple[str, ...] = OBJECT_FIELDS) -> tuple[Any, ...]:
    return tuple(
        normalize_project_key_value(row[field]) if isinstance(row[field], str) else row[field]
        for field in fields
    )


def project_key_fields(family: str, kind: str) -> tuple[str, ...]:
    if kind == "entity":
        return (f"{family}_entity_schema_name", f"{family}_entity_name")
    if kind == "attribute":
        return (f"{family}_entity_schema_name", f"{family}_entity_name", f"{family}_attribute_name")
    # A Relationship is identified by its child foreign-key Attribute.
    return (
        f"from_{family}_entity_schema_name",
        f"from_{family}_entity_name",
        f"from_{family}_attribute_name",
    )


def project_context_inputs(
    context: Mapping[str, Any], *, context_source_scope: Sequence[Mapping[str, Any]] = ()
) -> dict[str, Any]:
    """Selection and applicable sections are already authorized by the context repository."""
    workflow = context["project_workflow"]
    # Logical and Dimensional Optimize calls have their own input set.
    input_set = (
        f"{workflow}_optimize" if context.get("workflow_operation") == "optimize" else workflow
    )
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
        workflow=workflow,
    )
    for family in ("logical", "dimensional") if workflow == "dimensional" else ("logical",):
        section = context["applied"].get(family)
        for plural in ("entities", "attributes", "relationships"):
            values[f"{family}_{plural}"] = None if section is None else deepcopy(section[plural])
    if workflow in {"logical", "subject_area"}:
        # Answers cite selected Objects by these short ids; the backend numbers them the same way.
        values["table_index"] = [
            {"table": f"t{position}", **{name: selected["object"][name] for name in OBJECT_FIELDS}}
            for position, selected in enumerate(context["selected_objects"], start=1)
        ]
    if workflow == "subject_area":
        values.update(_subject_area_inputs(context))
    if workflow == "logical":
        table_ids = {
            natural_key(selected["object"]): f"t{position}"
            for position, selected in enumerate(context["selected_objects"], start=1)
        }
        if input_set == "logical_optimize":
            values.update(_logical_optimize_inputs(context, table_ids, values["context_records"]))
        else:
            values.update(_logical_build_inputs(context, table_ids, values["context_records"]))
    if workflow == "dimensional":
        if input_set == "dimensional_optimize":
            values.update(_dimensional_optimize_inputs(context, values["context_records"]))
        else:
            values.update(_dimensional_build_inputs(context, values["context_records"]))
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
    return {name: values[name] for name in WORKFLOW_INPUTS[input_set]}


_KEY_FLAGS = ("registered_is_natural_key", "is_surrogate_key", "is_natural_key", "is_primary_key")
_KEY_PROFILE_FIELDS = (
    "row_scope",
    "row_count",
    "non_null_count",
    "null_count",
    "distinct_count",
    "min_data_length",
    "max_data_length",
)
_SAVED_VALIDATION_FIELDS = (
    "validation_result",
    "validation_source_non_null_count",
    "validation_source_distinct_count",
    "validation_target_non_null_count",
    "validation_target_distinct_count",
    "validation_source_missing_target_count",
    "validation_unused_target_count",
    "validation_duplicate_target_key_count",
)


def analysis_table_inputs(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Prompt inputs for a per-table Analysis run: one set per selected table, in order.

    Tables are cited by short ids (t1, t2, ...) in selection order. Every set shares the
    source, placement and Context inputs and one key directory of all selected tables;
    only the focus table, its lineage and the saved findings touching it differ.
    """
    shared = context.get("prompt_inputs") or project_context_inputs(context)
    objects, groups = shared["object_context"], shared["object_attribute_context"]
    table_ids = {
        natural_key(item): f"t{position}" for position, item in enumerate(objects, start=1)
    }
    # Where each table's data comes from: a source table's own System, a Bronze table's
    # through ingestion lineage. Look-alike tables of different Systems are not related.
    origins: dict[tuple[Any, ...], set[str]] = {}
    for link in shared["ingestion_mapping"]:
        origins.setdefault(natural_key(link["target"]), set()).add(link["source"]["system_code"])
    # A Bronze table that keeps every load names its batch column (GDSBatchID), so its
    # business keys repeat once per load without being history.
    batch_columns = {
        natural_key(selected["object"]): selected["object"].get("batch_attribute_name")
        for selected in context.get("selected_objects", [])
    }
    tables: list[tuple[str, dict[str, Any]]] = []
    directory: list[dict[str, Any]] = []
    for position, (item, group) in enumerate(zip(objects, groups, strict=True), start=1):
        table_id = f"t{position}"
        table = {
            "table": table_id,
            **{name: item[name] for name in (*OBJECT_FIELDS, "object_description", "zone_code")},
            "source_systems": sorted(
                {item["system_code"]}
                if item["zone_code"] == "source"
                else origins.get(natural_key(item), set())
            ),
            "batch_attribute_name": batch_columns.get(natural_key(item)),
        }
        key_columns: list[dict[str, Any]] = []
        for attribute in group["attributes"]:
            profile = attribute["profile"]
            # Every non-null value distinct; operational columns count only when flagged.
            unique = bool(
                profile
                and profile["non_null_count"]
                and profile["distinct_count"] == profile["non_null_count"]
                and not attribute["is_meta_data"]
            )
            if unique or any(attribute.get(flag) for flag in _KEY_FLAGS):
                key_columns.append(
                    {
                        "attribute_name": attribute["attribute_name"],
                        "attribute_description": attribute["attribute_description"],
                        "attribute_data_type": attribute["attribute_data_type"],
                        "attribute_inferred_data_type": attribute["attribute_inferred_data_type"],
                        **{flag: attribute.get(flag) for flag in _KEY_FLAGS},
                        "profile": None
                        if profile is None
                        else {name: profile[name] for name in _KEY_PROFILE_FIELDS},
                    }
                )
        directory.append(
            {
                **table,
                "key_columns": key_columns,
                # Without a key flag or Profile, only a description can say which column
                # identifies the table's rows, so the model needs it to point here.
                "other_columns": []
                if key_columns
                else [
                    {
                        name: attribute[name]
                        for name in (
                            "attribute_name",
                            "attribute_description",
                            "attribute_data_type",
                            "attribute_inferred_data_type",
                        )
                    }
                    for attribute in group["attributes"]
                ],
            }
        )
        tables.append((table_id, {**table, "attributes": group["attributes"]}))

    saved: dict[str, list[dict[str, Any]]] = {table_id: [] for table_id, _ in tables}
    for relationship in context["analysis_relationships"]:
        source, target = (
            table_ids.get(
                natural_key({name: relationship[f"{side}_{name}"] for name in OBJECT_FIELDS})
            )
            for side in ("from", "to")
        )
        # A finding with an endpoint outside the run cannot change in it.
        if source is None or target is None:
            continue
        finding = {
            "from": f"{source}.{relationship['from_attribute_name']}",
            "to": f"{target}.{relationship['to_attribute_name']}",
            "relationship_kind": relationship["relationship_kind"],
            "inferred_cardinality": relationship["inferred_cardinality"],
            "analysis_result_status": relationship["analysis_result_status"],
            "analysis_result_is_locked": relationship["analysis_result_is_locked"],
            **{name: relationship[name] for name in _SAVED_VALIDATION_FIELDS},
        }
        saved[source].append(finding)
        if target != source:
            saved[target].append(finding)
    return [
        {
            "source_context": shared["source_context"],
            "gds_context": shared["gds_context"],
            "context_records": shared["context_records"],
            "key_directory": directory,
            "focus_table": table,
            "ingestion_mapping": [
                entry
                for entry in shared["ingestion_mapping"]
                if table_id
                in (
                    table_ids.get(natural_key(entry["source"])),
                    table_ids.get(natural_key(entry["target"])),
                )
            ],
            "saved_relationships": saved[table_id],
        }
        for table_id, table in tables
    ]


# Strongest measured result first; null is unvalidated, not disproven.
_VALIDATION_STRENGTH: dict[str | None, int] = {
    "supported": 3,
    "inconclusive": 2,
    None: 1,
    "unsupported": 0,
}


def _subject_area_inputs(context: Mapping[str, Any]) -> dict[str, Any]:
    """Compact evidence for the run's Objects, cited by table_index id."""
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
    # Active members this run leaves out; they keep their membership.
    other_counts: dict[str, int] = {}
    for membership in applied["tables"]:
        name = normalize_project_key_value(membership["subject_area_name"])
        if natural_key(membership) in table_ids:
            memberships.setdefault(name, []).append(membership)
        elif membership["subject_area_table_is_active"]:
            other_counts[name] = other_counts.get(name, 0) + 1

    def ordered(ids: list[str]) -> list[str]:
        return sorted(ids, key=lambda table: int(table[1:]))

    # Where each table's data comes from: a source table's own System, a Bronze table's
    # through ingestion lineage. One subject from several Systems belongs in one area.
    origins: dict[tuple[Any, ...], set[str]] = {}
    for link in context.get("ingestion_mapping", []):
        origins.setdefault(natural_key(link["target"]), set()).add(link["source"]["system_code"])

    return {
        "scope_tables": [
            {
                "table": table_ids[natural_key(item["object"])],
                "description": item["object"]["object_description"],
                "source_systems": sorted(
                    {item["object"]["system_code"]}
                    if item["object"]["zone_code"] == "source"
                    else origins.get(natural_key(item["object"]), set())
                ),
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
                "is_active": area["subject_area_is_active"],
                "is_locked": area["subject_area_is_locked"],
                "tables": ordered(
                    [
                        table_ids[natural_key(membership)]
                        for membership in rows
                        if membership["subject_area_table_is_active"]
                    ]
                ),
                "locked_tables": ordered(
                    [
                        table_ids[natural_key(membership)]
                        for membership in rows
                        if membership["subject_area_table_is_locked"]
                    ]
                ),
                "other_table_count": other_counts.get(
                    normalize_project_key_value(area["subject_area_name"]), 0
                ),
            }
            for area in applied["areas"]
            for rows in (
                memberships.get(normalize_project_key_value(area["subject_area_name"]), []),
            )
        ],
    }


# ---------------------------------------------------------------------------
# Logical and Dimensional Build slices and Optimize findings.
# A Build call sees its Subject Area's Objects, the Entities already built from them in
# full, their neighbours in short form and a one-line directory of everything else, so
# the input stops growing with the model. Optimize sees the whole model in short form
# plus deterministic findings, and full records only for the Entities they name.
# ---------------------------------------------------------------------------
type _Key = tuple[str, ...]


def _entity_key(record: Mapping[str, Any], family: str, prefix: str = "") -> _Key:
    return (
        normalize_project_key_value(record[f"{prefix}{family}_entity_schema_name"]),
        normalize_project_key_value(record[f"{prefix}{family}_entity_name"]),
    )


def _label(record: Mapping[str, Any], family: str, prefix: str = "") -> str:
    schema = record[f"{prefix}{family}_entity_schema_name"]
    return f"{schema}.{record[f'{prefix}{family}_entity_name']}"


def _first_sentence(text: str) -> str:
    sentence = text.strip().split(". ", 1)[0].rstrip(".")
    return (sentence[:197] + "...") if len(sentence) > 200 else sentence + "."


def _active_section(context: Mapping[str, Any], family: str) -> dict[str, list[dict[str, Any]]]:
    section: Mapping[str, Any] = context["applied"].get(family) or {}
    flag = {"entities": "entity", "attributes": "attribute", "relationships": "relationship"}
    return {
        plural: [row for row in section.get(plural, []) if row[f"{family}_{kind}_is_active"]]
        for plural, kind in flag.items()
    }


def _attributes_by_entity(
    attributes: Sequence[Mapping[str, Any]], family: str
) -> dict[_Key, list[Mapping[str, Any]]]:
    grouped: dict[_Key, list[Mapping[str, Any]]] = {}
    for attribute in attributes:
        grouped.setdefault(_entity_key(attribute, family), []).append(attribute)
    for rows in grouped.values():
        rows.sort(key=lambda row: row[f"{family}_attribute_ordinal_position"])
    return grouped


def _natural_keys(attributes: Sequence[Mapping[str, Any]], family: str) -> list[dict[str, Any]]:
    return [
        {"name": row[f"{family}_attribute_name"], "type": row[f"{family}_attribute_data_type"]}
        for row in attributes
        if row[f"{family}_attribute_is_natural_key"]
    ]


def _entity_areas(context: Mapping[str, Any]) -> dict[_Key, set[str]]:
    """Subject Area names by physical Object key, from active memberships."""
    applied: Mapping[str, Any] = context["applied"].get("subject_area") or {
        "areas": [],
        "tables": [],
    }
    active = {
        normalize_project_key_value(area["subject_area_name"]): area["subject_area_name"]
        for area in applied["areas"]
        if area["subject_area_is_active"]
    }
    areas: dict[_Key, set[str]] = {}
    for member in applied["tables"]:
        name = active.get(normalize_project_key_value(member["subject_area_name"]))
        if name is not None and member["subject_area_table_is_active"]:
            areas.setdefault(natural_key(member), set()).add(name)
    return areas


def _object_sources(entity: Mapping[str, Any]) -> list[_Key]:
    return [
        natural_key(source["source_object"])
        for source in entity["sources"]
        if source["support_source_type"] == "object" and source["is_active"]
    ]


def _compact_logical(
    entities: Sequence[Mapping[str, Any]],
    attributes: Mapping[_Key, list[Mapping[str, Any]]],
    relationships: Sequence[Mapping[str, Any]],
    table_ids: Mapping[_Key, str],
) -> dict[str, Any]:
    """Saved Entities in the answer's own language: t-ids, t1.column, {"context": id}."""
    compact: list[dict[str, Any]] = []
    for entity in entities:
        sources: list[Any] = []
        other = 0
        for source in entity["sources"]:
            if not source["is_active"]:
                continue
            if source["support_source_type"] == "context_record":
                sources.append({"context": source["context_record"]["context_record_id"]})
            elif natural_key(source["source_object"]) in table_ids:
                sources.append(table_ids[natural_key(source["source_object"])])
            else:
                other += 1
        compact_attributes: list[dict[str, Any]] = []
        for attribute in attributes.get(_entity_key(entity, "logical"), []):
            # The backend owns generated keys and audit columns.
            if (
                attribute["logical_attribute_is_surrogate_key"]
                or attribute["logical_attribute_is_audit_column"]
            ):
                continue
            refs: list[Any] = []
            for source in attribute["sources"]:
                if not source["is_active"]:
                    continue
                if source["support_source_type"] == "context_record":
                    refs.append({"context": source["context_record"]["context_record_id"]})
                elif natural_key(source["source_attribute"]) in table_ids:
                    table = table_ids[natural_key(source["source_attribute"])]
                    refs.append(f"{table}.{source['source_attribute']['attribute_name']}")
            compact_attributes.append(
                {
                    "name": attribute["logical_attribute_name"],
                    "type": attribute["logical_attribute_data_type"],
                    "nullable": attribute["logical_attribute_is_nullable"],
                    "natural_key": attribute["logical_attribute_is_natural_key"],
                    "from": refs,
                    "definition": attribute["logical_attribute_definition"],
                    "is_locked": attribute["logical_attribute_is_locked"],
                }
            )
        compact.append(
            {
                "schema": entity["logical_entity_schema_name"],
                "name": entity["logical_entity_name"],
                "type": entity["logical_entity_type"],
                "definition": entity["logical_entity_definition"],
                "grain": entity["logical_entity_grain"],
                "is_locked": entity["logical_entity_is_locked"],
                "sources": sources,
                "other_source_count": other,
                "attributes": compact_attributes,
            }
        )
    return {
        "entities": compact,
        "relationships": [
            {
                "from": {
                    "schema": row["from_logical_entity_schema_name"],
                    "entity": row["from_logical_entity_name"],
                    "attribute": row["from_logical_attribute_name"],
                },
                "to": {
                    "schema": row["to_logical_entity_schema_name"],
                    "entity": row["to_logical_entity_name"],
                },
                "cardinality": row["logical_relationship_cardinality"],
                "basis": row["logical_relationship_basis"],
                "is_locked": row["logical_relationship_is_locked"],
            }
            for row in relationships
        ],
    }


def _neighbors_and_directory(
    entities: Sequence[Mapping[str, Any]],
    attributes: Mapping[_Key, list[Mapping[str, Any]]],
    *,
    family: str,
    focus: set[_Key],
    linked: Mapping[_Key, set[str]],
    grain_field: str,
    type_field: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    neighbors: list[dict[str, Any]] = []
    directory: list[dict[str, Any]] = []
    for entity in entities:
        key = _entity_key(entity, family)
        if key in focus:
            continue
        if key in linked:
            neighbors.append(
                {
                    "schema": entity[f"{family}_entity_schema_name"],
                    "name": entity[f"{family}_entity_name"],
                    "type": entity[type_field],
                    "grain": entity[grain_field],
                    "natural_keys": _natural_keys(attributes.get(key, []), family),
                    "linked_via": sorted(linked[key]),
                }
            )
        else:
            directory.append(
                {
                    "schema": entity[f"{family}_entity_schema_name"],
                    "name": entity[f"{family}_entity_name"],
                    "type": entity[type_field],
                    "summary": _first_sentence(entity[f"{family}_entity_definition"]),
                }
            )
    return neighbors, directory


def _logical_build_inputs(
    context: Mapping[str, Any],
    table_ids: Mapping[_Key, str],
    context_records: list[dict[str, Any]],
) -> dict[str, Any]:
    model = _active_section(context, "logical")
    attributes = _attributes_by_entity(model["attributes"], "logical")
    existing = [
        entity
        for entity in model["entities"]
        if any(key in table_ids for key in _object_sources(entity))
    ]
    focus = {_entity_key(entity, "logical") for entity in existing}
    touching = [
        row
        for row in model["relationships"]
        if _entity_key(row, "logical", "from_") in focus
        or _entity_key(row, "logical", "to_") in focus
    ]
    linked: dict[_Key, set[str]] = {}
    for row in touching:
        for side in ("from_", "to_"):
            linked.setdefault(_entity_key(row, "logical", side), set()).add("relationship")
    # Tables that Analysis links to this area's tables, outside the area.
    linked_tables: set[_Key] = set()
    for relationship in context["analysis_relationships"]:
        if relationship["analysis_result_status"] != "active":
            continue
        ends = [
            natural_key({name: relationship[f"{side}_{name}"] for name in OBJECT_FIELDS})
            for side in ("from", "to")
        ]
        if any(end in table_ids for end in ends):
            linked_tables.update(end for end in ends if end not in table_ids)
    for entity in model["entities"]:
        if any(key in linked_tables for key in _object_sources(entity)):
            linked.setdefault(_entity_key(entity, "logical"), set()).add("analysis")
    neighbors, directory = _neighbors_and_directory(
        model["entities"],
        attributes,
        family="logical",
        focus=focus,
        linked=linked,
        grain_field="logical_entity_grain",
        type_field="logical_entity_type",
    )
    area: Mapping[str, Any] = context.get("build_subject_area") or {}
    return {
        "subject_area_context": {
            "name": area.get("name", ""),
            "definition": area.get("definition", ""),
            "input_count": len(table_ids),
        },
        "existing_entities": _compact_logical(existing, attributes, touching, table_ids),
        "neighbor_entities": neighbors,
        "entity_directory": directory,
        "logical_entity_types": _active_types(context, "logical", "logical_entity_type"),
        "context_records": _with_cited_context(
            context, context_records, existing, attributes, "logical"
        ),
    }


def _with_cited_context(
    context: Mapping[str, Any],
    context_records: list[dict[str, Any]],
    shown: Sequence[Mapping[str, Any]],
    attributes: Mapping[_Key, list[Mapping[str, Any]]],
    family: str,
) -> list[dict[str, Any]]:
    """Routed records plus every active record the shown Entities or their Attributes cite."""
    cited = {
        source["context_record"]["context_record_id"]
        for entity in shown
        for source in (
            *entity["sources"],
            *(
                source
                for attribute in attributes.get(_entity_key(entity, family), [])
                for source in attribute["sources"]
            ),
        )
        if source["support_source_type"] == "context_record" and source["is_active"]
    }
    return with_cited_context_records(context["context"], context_records, cited)


def _active_types(context: Mapping[str, Any], family: str, prefix: str) -> list[dict[str, Any]]:
    section: Mapping[str, Any] = context["applied"].get(family) or {}
    rows = section.get("entity_types" if family == "logical" else "fact_types", [])
    return [
        {"code": row[f"{prefix}_code"], "description": row[f"{prefix}_description"]}
        for row in rows
        if row[f"{prefix}_is_active"]
    ]


def _folded(name: str) -> str:
    return "".join(character for character in name.casefold() if character.isalnum())


def _normalized_name(name: str, system_codes: Sequence[str] = ()) -> str:
    folded = _folded(name)
    # One subject named once per source System (CRMCustomer, Customer_ERP) is one name.
    for code in system_codes:
        if len(folded) > len(code) and folded.startswith(code):
            folded = folded[len(code) :]
            break
        if len(folded) > len(code) and folded.endswith(code):
            folded = folded[: -len(code)]
            break
    return folded[:-1] if folded.endswith("s") and len(folded) > 3 else folded


def _source_system_codes(context: Mapping[str, Any]) -> list[str]:
    """Folded source System codes, longest first, so per-System names group together."""
    codes = {_folded(str(source["system_code"])) for source in context.get("source_context", [])}
    return sorted((code for code in codes if len(code) > 1), key=len, reverse=True)


def _name_variants(
    labels: Sequence[tuple[str, str]], kind: str, system_codes: Sequence[str] = ()
) -> list[dict[str, Any]]:
    """Group labels whose last name part differs only by case, separators, a plural s or a
    leading or trailing source System code from system_codes."""
    groups: dict[str, set[str]] = {}
    for label, name in labels:
        groups.setdefault(_normalized_name(name, system_codes), set()).add(label)
    return [
        {"kind": kind, "names": sorted(names)}
        for names in groups.values()
        if len({name.rsplit(".", 1)[-1] for name in names}) > 1
    ]


def _type_conflicts(
    entities_attributes: Mapping[_Key, list[Mapping[str, Any]]],
    labels: Mapping[_Key, str],
    relationships: Sequence[Mapping[str, Any]],
    family: str,
) -> list[dict[str, Any]]:
    by_attribute = {
        (*key, normalize_project_key_value(row[f"{family}_attribute_name"])): row
        for key, rows in entities_attributes.items()
        for row in rows
    }
    conflicts: list[dict[str, Any]] = []
    for row in relationships:
        child = by_attribute.get(
            (
                *_entity_key(row, family, "from_"),
                normalize_project_key_value(row[f"from_{family}_attribute_name"]),
            )
        )
        parent = by_attribute.get(
            (
                *_entity_key(row, family, "to_"),
                normalize_project_key_value(row[f"to_{family}_attribute_name"]),
            )
        )
        if (
            child
            and parent
            and child[f"{family}_attribute_data_type"].casefold()
            != parent[f"{family}_attribute_data_type"].casefold()
        ):
            conflicts.append(
                {
                    "kind": "relationship_key",
                    "attribute": row[f"from_{family}_attribute_name"],
                    "values": [
                        {
                            "entity": _label(row, family, side),
                            "attribute": row[f"{side}{family}_attribute_name"],
                            "type": end[f"{family}_attribute_data_type"],
                        }
                        for side, end in (("from_", child), ("to_", parent))
                    ],
                }
            )
    shared: dict[str, list[dict[str, Any]]] = {}
    for key, rows in entities_attributes.items():
        for row in rows:
            if (
                row[f"{family}_attribute_is_surrogate_key"]
                or row[f"{family}_attribute_is_audit_column"]
            ):
                continue
            shared.setdefault(
                normalize_project_key_value(row[f"{family}_attribute_name"]), []
            ).append(
                {
                    "entity": labels[key],
                    "attribute": row[f"{family}_attribute_name"],
                    "type": row[f"{family}_attribute_data_type"],
                }
            )
    conflicts.extend(
        {"kind": "shared_name", "attribute": values[0]["attribute"], "values": values}
        for values in shared.values()
        if len({value["type"].casefold() for value in values}) > 1
    )
    return conflicts


def _logical_optimize_inputs(
    context: Mapping[str, Any],
    table_ids: Mapping[_Key, str],
    context_records: list[dict[str, Any]],
) -> dict[str, Any]:
    model = _active_section(context, "logical")
    attributes = _attributes_by_entity(model["attributes"], "logical")
    entities = {_entity_key(entity, "logical"): entity for entity in model["entities"]}
    labels = {key: _label(entity, "logical") for key, entity in entities.items()}
    object_areas = _entity_areas(context)
    tables_of = {key: set(_object_sources(entity)) for key, entity in entities.items()}
    related = {
        frozenset((_entity_key(row, "logical", "from_"), _entity_key(row, "logical", "to_")))
        for row in model["relationships"]
    }
    unlinked: list[dict[str, Any]] = []
    for relationship in context["analysis_relationships"]:
        # People review links; a validation result never hides an active one.
        if relationship["analysis_result_status"] != "active":
            continue
        ends = {
            side: natural_key({name: relationship[f"{side}_{name}"] for name in OBJECT_FIELDS})
            for side in ("from", "to")
        }
        if not all(end in table_ids for end in ends.values()):
            continue
        sides = {
            side: sorted(key for key, tables in tables_of.items() if end in tables)
            for side, end in ends.items()
        }
        if (
            not sides["from"]
            or not sides["to"]
            or any(
                frozenset((source, target)) in related or source == target
                for source in sides["from"]
                for target in sides["to"]
            )
        ):
            continue
        unlinked.append(
            {
                "from": f"{table_ids[ends['from']]}.{relationship['from_attribute_name']}",
                "to": f"{table_ids[ends['to']]}.{relationship['to_attribute_name']}",
                "validation_result": relationship["validation_result"],
                "from_entities": [labels[key] for key in sides["from"]],
                "to_entities": [labels[key] for key in sides["to"]],
            }
        )
    type_conflicts = _type_conflicts(attributes, labels, model["relationships"], "logical")
    name_variants = _name_variants(
        [(label, entities[key]["logical_entity_name"]) for key, label in labels.items()],
        "entity",
        _source_system_codes(context),
    ) + _name_variants(
        [
            (f"{labels[key]}.{row['logical_attribute_name']}", row["logical_attribute_name"])
            for key, rows in attributes.items()
            for row in rows
            if not row["logical_attribute_is_surrogate_key"]
            and not row["logical_attribute_is_audit_column"]
        ],
        "attribute",
    )
    named = (
        {name for item in (*unlinked,) for name in (*item["from_entities"], *item["to_entities"])}
        | {value["entity"] for item in type_conflicts for value in item["values"]}
        | {
            name.rsplit(".", 1)[0] if item["kind"] == "attribute" else name
            for item in name_variants
            for name in item["names"]
        }
    )
    # A merge also renames the children's foreign keys (ERPCustomerID -> CustomerID),
    # so Entities that point at an Entity name variant are shown in full too.
    variant_entities = {
        name for item in name_variants if item["kind"] == "entity" for name in item["names"]
    }
    named |= {
        _label(row, "logical", "from_")
        for row in model["relationships"]
        if _label(row, "logical", "to_") in variant_entities
    }
    detail_keys = [key for key, label in labels.items() if label in named]
    details = [entities[key] for key in detail_keys]
    return {
        "model_summary": {
            "entities": [
                {
                    "schema": entity["logical_entity_schema_name"],
                    "name": entity["logical_entity_name"],
                    "type": entity["logical_entity_type"],
                    "grain": entity["logical_entity_grain"],
                    "subject_areas": sorted(
                        {name for table in tables_of[key] for name in object_areas.get(table, ())}
                    ),
                    "keys": _natural_keys(attributes.get(key, []), "logical"),
                    "attribute_count": len(attributes.get(key, [])),
                    "sources": sorted(
                        (table_ids[table] for table in tables_of[key] if table in table_ids),
                        key=lambda table: int(table[1:]),
                    ),
                    "is_locked": entity["logical_entity_is_locked"],
                }
                for key, entity in entities.items()
            ],
            "relationships": [
                {
                    "from": f"{_label(row, 'logical', 'from_')}."
                    f"{row['from_logical_attribute_name']}",
                    "to": _label(row, "logical", "to_"),
                    "cardinality": row["logical_relationship_cardinality"],
                }
                for row in model["relationships"]
            ],
        },
        "unlinked_analysis_edges": unlinked,
        "type_conflicts": type_conflicts,
        "name_variants": name_variants,
        "entity_details": _compact_logical(
            details,
            attributes,
            [
                row
                for row in model["relationships"]
                if _entity_key(row, "logical", "from_") in detail_keys
                or _entity_key(row, "logical", "to_") in detail_keys
            ],
            table_ids,
        ),
        "logical_entity_types": _active_types(context, "logical", "logical_entity_type"),
        "context_records": _with_cited_context(
            context, context_records, details, attributes, "logical"
        ),
    }


def _dimensional_build_inputs(
    context: Mapping[str, Any], context_records: list[dict[str, Any]]
) -> dict[str, Any]:
    model = _active_section(context, "dimensional")
    attributes = _attributes_by_entity(model["attributes"], "dimensional")
    area_logical = {
        _entity_key(item["entity"], "logical") for item in context["selected_logical_entities"]
    }

    def logical_sources(entity: Mapping[str, Any]) -> set[_Key]:
        return {
            _entity_key(source["source_logical_entity"], "logical")
            for source in entity["sources"]
            if source["support_source_type"] == "logical_entity" and source["is_active"]
        }

    existing = [entity for entity in model["entities"] if logical_sources(entity) & area_logical]
    focus = {_entity_key(entity, "dimensional") for entity in existing}
    touching = [
        row
        for row in model["relationships"]
        if _entity_key(row, "dimensional", "from_") in focus
        or _entity_key(row, "dimensional", "to_") in focus
    ]
    linked: dict[_Key, set[str]] = {}
    for row in touching:
        for side in ("from_", "to_"):
            linked.setdefault(_entity_key(row, "dimensional", side), set()).add("relationship")
    neighbors, directory = _neighbors_and_directory(
        model["entities"],
        attributes,
        family="dimensional",
        focus=focus,
        linked=linked,
        grain_field="dimensional_entity_grain_definition",
        type_field="dimensional_entity_type",
    )
    area: Mapping[str, Any] = context.get("build_subject_area") or {}
    logical_links = [
        {
            "from": f"{_label(row, 'logical', 'from_')}.{row['from_logical_attribute_name']}",
            "to": _label(row, "logical", "to_"),
            "cardinality": row["logical_relationship_cardinality"],
        }
        for row in _active_section(context, "logical")["relationships"]
        if _entity_key(row, "logical", "from_") in area_logical
        or _entity_key(row, "logical", "to_") in area_logical
    ]
    return {
        "subject_area_context": {
            "name": area.get("name", ""),
            "definition": area.get("definition", ""),
            "input_count": len(context["selected_logical_entities"]),
        },
        "logical_links": logical_links,
        "existing_entities": {
            "entities": deepcopy(existing),
            # Model order, so every worker renders the same prompt.
            "attributes": [
                deepcopy(row)
                for entity in existing
                for row in attributes.get(_entity_key(entity, "dimensional"), [])
            ],
            "relationships": deepcopy(touching),
        },
        "neighbor_entities": neighbors,
        "entity_directory": directory,
        "dimensional_fact_types": _active_types(context, "dimensional", "dimensional_fact_type"),
        "context_records": _with_cited_context(
            context, context_records, existing, attributes, "dimensional"
        ),
    }


def _dimensional_optimize_inputs(
    context: Mapping[str, Any], context_records: list[dict[str, Any]]
) -> dict[str, Any]:
    model = _active_section(context, "dimensional")
    attributes = _attributes_by_entity(model["attributes"], "dimensional")
    entities = {_entity_key(entity, "dimensional"): entity for entity in model["entities"]}
    labels = {key: _label(entity, "dimensional") for key, entity in entities.items()}
    logical = _active_section(context, "logical")
    logical_tables = {
        _entity_key(entity, "logical"): set(_object_sources(entity))
        for entity in logical["entities"]
    }
    object_areas = _entity_areas(context)
    sources_of = {
        key: [
            source["source_logical_entity"]
            for source in entity["sources"]
            if source["support_source_type"] == "logical_entity" and source["is_active"]
        ]
        for key, entity in entities.items()
    }
    same_source: dict[_Key, list[str]] = {}
    for key, entity in entities.items():
        if entity["dimensional_entity_type"] == "dimension":
            for source in sources_of[key]:
                same_source.setdefault(_entity_key(source, "logical"), []).append(labels[key])
    name_variants = _name_variants(
        [(label, entities[key]["dimensional_entity_name"]) for key, label in labels.items()],
        "entity",
        _source_system_codes(context),
    )
    conformance = [
        {"reason": "same_logical_source", "dimensions": sorted(names)}
        for names in same_source.values()
        if len(names) > 1
    ] + [{"reason": "name_variant", "dimensions": item["names"]} for item in name_variants]
    type_conflicts = _type_conflicts(attributes, labels, model["relationships"], "dimensional")
    named = {name for item in conformance for name in item["dimensions"]} | {
        value["entity"] for item in type_conflicts for value in item["values"]
    }
    # A list in model order, so every worker renders the same prompt.
    detail = [key for key, label in labels.items() if label in named]

    def areas(key: _Key) -> list[str]:
        # A Dimensional Entity's areas come through its Logical sources' tables.
        tables = {
            table
            for source in sources_of[key]
            for table in logical_tables.get(_entity_key(source, "logical"), ())
        }
        return sorted({name for table in tables for name in object_areas.get(table, ())})

    return {
        "model_summary": {
            "entities": [
                {
                    "schema": entity["dimensional_entity_schema_name"],
                    "name": entity["dimensional_entity_name"],
                    "type": entity["dimensional_entity_type"],
                    "fact_type": entity["dimensional_fact_type"],
                    "grain": entity["dimensional_entity_grain_definition"],
                    "subject_areas": areas(key),
                    "keys": _natural_keys(attributes.get(key, []), "dimensional"),
                    "attribute_count": len(attributes.get(key, [])),
                    "logical_sources": sorted(
                        _label(source, "logical") for source in sources_of[key]
                    ),
                    "is_locked": entity["dimensional_entity_is_locked"],
                }
                for key, entity in entities.items()
            ],
            "relationships": [
                {
                    "from": f"{_label(row, 'dimensional', 'from_')}."
                    f"{row['from_dimensional_attribute_name']}",
                    "to": _label(row, "dimensional", "to_"),
                    "role": row["dimensional_relationship_role_name"],
                }
                for row in model["relationships"]
            ],
        },
        "conformance_candidates": conformance,
        "type_conflicts": type_conflicts,
        "name_variants": name_variants
        + _name_variants(
            [
                (
                    f"{labels[key]}.{row['dimensional_attribute_name']}",
                    row["dimensional_attribute_name"],
                )
                for key, rows in attributes.items()
                for row in rows
                if not row["dimensional_attribute_is_surrogate_key"]
                and not row["dimensional_attribute_is_audit_column"]
            ],
            "attribute",
        ),
        "entity_details": {
            "entities": [deepcopy(entities[key]) for key in detail],
            "attributes": [deepcopy(row) for key in detail for row in attributes.get(key, [])],
            "relationships": [
                deepcopy(row)
                for row in model["relationships"]
                if _entity_key(row, "dimensional", "from_") in detail
                or _entity_key(row, "dimensional", "to_") in detail
            ],
        },
        "dimensional_fact_types": _active_types(context, "dimensional", "dimensional_fact_type"),
        "context_records": _with_cited_context(
            context, context_records, [entities[key] for key in detail], attributes, "dimensional"
        ),
    }
