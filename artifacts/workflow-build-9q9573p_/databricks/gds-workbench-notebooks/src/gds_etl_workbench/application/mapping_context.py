"""One natural-key Mapping consumer projection shared by MCP and authoring."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

_DOCUMENT_FIELDS = {
    "transformation",
    "transformation_document",
    "mapping_transformation_document",
    "attribute_mapping_transformation_document",
    "audit_columns_template",
    "technical_columns_template",
    "example",
    "validation_comparison_value",
}


def without_internal_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [without_internal_fields(item) for item in cast(list[Any], value)]
    if not isinstance(value, dict):
        return deepcopy(value)
    return {
        name: deepcopy(item) if name in _DOCUMENT_FIELDS else without_internal_fields(item)
        for name, item in cast(dict[str, Any], value).items()
        if not name.endswith("_id")
        and name not in {"ids", "schema_digest", "schema_digest_is_valid"}
    }


def project_mapping_inputs(context: dict[str, Any]) -> dict[str, Any]:
    systems = {row["source_system_id"]: row["system_code"] for row in context["source_systems"]}
    objects = {row["mapping_object_id"]: row for row in context["object_mappings"]}
    sources: list[dict[str, Any]] = []
    for row in context["physical_sources"]:
        sources.append(
            {
                **without_internal_fields(row),
                "source_system_code": systems[row["selected_source_system_id"]],
            }
        )
    object_mappings: list[dict[str, Any]] = []
    for row in context["object_mappings"]:
        object_mappings.append(
            {
                **without_internal_fields(row),
                "source_system_code": systems[row["source_system_id"]],
            }
        )
    attributes: list[dict[str, Any]] = []
    for row in context["attribute_mappings"]:
        entity = objects[row["mapping_object_id"]]["entity"]
        attributes.append(
            {
                **without_internal_fields(row),
                "source_system_code": systems[row["source_system_id"]],
                "modeled_entity_type": entity["entity_type"],
                "modeled_entity_name": entity["entity_name"],
            }
        )
    target = without_internal_fields(context["target"])
    audit_template: dict[str, Any] = target.get("audit_columns_template") or {}
    framework = {
        str(column["semantic_name"]).strip().casefold()
        for column in audit_template.get("columns", [])
        if str(column.get("semantic_name", "")).strip().casefold() != "sourcesystemid"
    }
    technical: dict[str, Any] = target.get("technical_columns_template") or {}
    history: dict[str, Any] = technical.get("type_2", {})
    framework.update(
        str(cast(dict[str, Any], column)["semantic_name"]).strip().casefold()
        for column in history.values()
        if isinstance(column, dict) and "semantic_name" in column
    )
    for attribute in target.get("attributes", []):
        if "is_surrogate_key" not in attribute:
            continue  # Preserve compatibility with previously frozen workflow contexts.
        name = attribute["attribute_name"].strip().casefold()
        attribute["population"] = (
            "database"
            if attribute["is_surrogate_key"]
            else "framework"
            if name in framework
            else "mapping"
        )
    return {
        "target_metadata": target,
        "source_metadata": sources,
        "source_systems": [
            {**without_internal_fields(row), "source_system_value": row["source_system_id"]}
            for row in context["source_systems"]
        ],
        "object_transformations": object_mappings,
        "attribute_transformations": attributes,
    }


OBJECT_FIELDS = ("tenant_code", "system_code", "connection_code", "object_schema", "object_name")


def mapping_context_issues(values: dict[str, Any]) -> list[str]:
    """Check resolved references, physical names and branch coverage, without guessing semantics."""

    def key(row: dict[str, Any]) -> tuple[str, ...]:
        return tuple(str(row.get(field, "")).strip().casefold() for field in OBJECT_FIELDS)

    target = values["target_metadata"]
    sources = {key(row["object"]): row["object"] for row in values["source_metadata"]}
    sources[key(target)] = target
    issues: set[str] = set()
    for obj in sources.values():
        source = str(obj.get("zone_code", "")).strip().casefold() == "source"
        coordinates = (
            (obj.get("foreign_catalog"), obj.get("fc_object_schema"), obj.get("fc_object_name"))
            if source
            else (obj.get("tenant_catalog"), obj.get("object_schema"), obj.get("object_name"))
        )
        if not all(isinstance(value, str) and value.strip() for value in coordinates):
            issues.add("query_coordinates_missing")
        if source and any(
            not isinstance(attribute.get("fc_attribute_name"), str)
            or not attribute["fc_attribute_name"].strip()
            for attribute in obj.get("attributes", [])
            if attribute.get("is_active", True)
        ):
            issues.add("query_attribute_coordinates_missing")
        if obj.get("batch_attribute_name") and not any(
            str(attribute.get("attribute_name", "")).strip().casefold()
            == str(obj["batch_attribute_name"]).strip().casefold()
            for attribute in obj.get("attributes", [])
            if attribute.get("is_active", True)
        ):
            issues.add("batch_attribute_missing")
    for row in values["object_transformations"]:
        document = row.get("transformation")
        if not isinstance(document, dict):
            issues.add("mapping_document_not_canonical")
            continue
        document = cast(dict[str, Any], document)
        if "source_objects" not in document:
            issues.add("mapping_document_not_canonical")
            continue
        if document["source_objects"] is None:
            continue
        if not isinstance(document["source_objects"], list):
            issues.add("mapping_document_not_canonical")
            continue
        for reference in cast(list[Any], document["source_objects"]):
            if (
                not isinstance(reference, dict)
                or key(cast(dict[str, Any], reference)) not in sources
            ):
                issues.add("mapping_source_object_missing_or_ineligible")
    for row in values["attribute_transformations"]:
        document = row.get("transformation")
        if not isinstance(document, dict):
            issues.add("mapping_document_not_canonical")
            continue
        document = cast(dict[str, Any], document)
        references = document.get("source_attributes")
        if references is None:
            continue  # Canonical generated/constant columns may have no source.
        if not isinstance(references, list):
            issues.add("mapping_document_not_canonical")
            continue
        for reference in cast(list[Any], references):
            obj = (
                sources.get(key(cast(dict[str, Any], reference)))
                if isinstance(reference, dict)
                else None
            )
            if obj is None or not any(
                str(attribute.get("attribute_name", "")).strip().casefold()
                == str(cast(dict[str, Any], reference).get("attribute_name", "")).strip().casefold()
                for attribute in obj.get("attributes", [])
                if attribute.get("is_active", True)
            ):
                issues.add("mapping_source_attribute_missing_or_ineligible")
    expected = {
        (row["system_code"].strip().casefold(), attribute["attribute_name"].strip().casefold())
        for row in values["source_systems"]
        for attribute in target.get("attributes", [])
        if attribute.get("is_active", True)
    }
    actual = {
        (
            row["source_system_code"].strip().casefold(),
            row["target_attribute_name"].strip().casefold(),
        )
        for row in values["attribute_transformations"]
    }
    if actual != expected:
        issues.add("mapping_attribute_coverage_incomplete")
    return sorted(issues)
