"""One natural-key Mapping consumer projection shared by MCP and authoring."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

OPAQUE_CONTEXT_DOCUMENT_FIELDS = frozenset(
    {
        "modeling_assertion_details",
        "modeling_assertion_source_location",
        "transformation",
        "transformation_document",
        "mapping_transformation_document",
        "attribute_mapping_transformation_document",
        "audit_columns_template",
        "technical_columns_template",
        "example",
        "validation_comparison_value",
    }
)


def is_internal_context_field(name: str) -> bool:
    """Keep payload and schema projections on the same metadata boundary."""
    return name.endswith("_id") or name in {"ids", "schema_digest", "schema_digest_is_valid"}


def without_internal_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [without_internal_fields(item) for item in cast(list[Any], value)]
    if not isinstance(value, dict):
        return deepcopy(value)
    return {
        name: deepcopy(item)
        if name in OPAQUE_CONTEXT_DOCUMENT_FIELDS
        else without_internal_fields(item)
        for name, item in cast(dict[str, Any], value).items()
        if not is_internal_context_field(name)
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
                "output_template_code": row.get("output_template_code"),
                "source_system_code": systems[row["source_system_id"]],
            }
        )
    attributes: list[dict[str, Any]] = []
    for row in context["attribute_mappings"]:
        entity = objects[row["mapping_object_id"]]["entity"]
        attributes.append(
            {
                **without_internal_fields(row),
                "output_template_code": row.get("output_template_code"),
                "source_system_code": systems[row["source_system_id"]],
                "modeled_entity_type": entity["entity_type"],
                "modeled_entity_schema_name": entity["entity_schema_name"],
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
    used_template_codes = {row["output_template_code"] for row in (*object_mappings, *attributes)}
    return {
        "target_metadata": target,
        "source_metadata": sources,
        "source_systems": [
            {**without_internal_fields(row), "source_system_value": row["source_system_id"]}
            for row in context["source_systems"]
        ],
        "object_transformations": object_mappings,
        "attribute_transformations": attributes,
        "mapping_templates": [
            without_internal_fields(template)
            for template in context.get("mapping_templates", [])
            if template["code"] in used_template_codes
        ],
    }


OBJECT_FIELDS = ("tenant_code", "system_code", "connection_code", "object_schema", "object_name")

# Shared consumer/authoring policy: custom template field names never imply
# built-in reference semantics. None retains default and recognized legacy shapes.
MAPPING_REFERENCE_TEMPLATE_CODES = {
    "mapping_object": frozenset(
        {
            "mapping_object_default",
            "mapping_logical_object_default",
            "mapping_dimensional_object_default",
        }
    ),
    "mapping_attribute": frozenset(
        {
            "mapping_attribute_default",
            "mapping_logical_attribute_default",
            "mapping_dimensional_attribute_default",
        }
    ),
}


def mapping_context_issues(values: dict[str, Any]) -> list[str]:
    """Check resolved references, physical names and branch coverage, without guessing semantics."""

    def key(row: dict[str, Any]) -> tuple[str, ...]:
        return tuple(str(row.get(field, "")).strip().casefold() for field in OBJECT_FIELDS)

    target = values["target_metadata"]
    sources = {key(row["object"]): row["object"] for row in values["source_metadata"]}
    modeled_sources = {
        layer: {
            (
                obj[f"{layer}_entity_schema_name"].strip().casefold(),
                obj[f"{layer}_entity_name"].strip().casefold(),
            ): obj
            for row in values["source_metadata"]
            if f"{layer}_entity_name" in (obj := row["object"])
        }
        for layer in ("logical", "dimensional")
    }
    dimensional = target.get("modeled_entity_type") == "dimensional_entity"

    def current_source(reference: Any, system_code: str) -> dict[str, Any] | None:
        if not isinstance(reference, dict):
            return None
        reference = cast(dict[str, Any], reference)
        entity_type = reference.get("entity_type")
        if entity_type is not None:
            if entity_type not in (
                ("logical_entity", "dimensional_entity") if dimensional else ("logical_entity",)
            ):
                return None
            layer = "logical" if entity_type == "logical_entity" else "dimensional"
            reference_key = tuple(
                str(reference.get(field, "")).strip().casefold()
                for field in ("entity_schema_name", "entity_name")
            )
            for source_row in values["source_metadata"]:
                obj = source_row["object"]
                if source_row["source_system_code"].strip().casefold() != system_code:
                    continue
                if reference_key == (
                    str(obj.get(f"{layer}_entity_schema_name", "")).strip().casefold(),
                    str(obj.get(f"{layer}_entity_name", "")).strip().casefold(),
                ) and all(reference_key):
                    return obj
            return None
        if dimensional:
            return None
        for source_row in values["source_metadata"]:
            obj = source_row["object"]
            if (
                source_row["source_system_code"].strip().casefold() == system_code
                and all(key(reference))
                and key(reference) == key(obj)
                and not obj.get("modeled_entity_type")
            ):
                return obj
        return None

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
        template_code = row.get("output_template_code")
        if (
            template_code is not None
            and str(template_code).strip().casefold()
            not in MAPPING_REFERENCE_TEMPLATE_CODES["mapping_object"]
        ):
            continue
        document = cast(dict[str, Any], document)
        required_sources = "source_logical_entities" if dimensional else "source_objects"
        if "source_tables" in document:
            references = document["source_tables"]
            if not isinstance(references, list):
                issues.add("mapping_document_not_canonical")
            else:
                for reference in cast(list[Any], references):
                    if (
                        current_source(reference, row["source_system_code"].strip().casefold())
                        is None
                    ):
                        issues.add("mapping_source_object_missing_or_ineligible")
        elif required_sources not in document and not row.get("output_template_code"):
            issues.add("mapping_document_not_canonical")
        for source_field in (
            "source_objects",
            "source_logical_entities",
            "source_dimensional_entities",
        ):
            references = document.get(source_field)
            if references is None:
                continue
            if not isinstance(references, list):
                issues.add("mapping_document_not_canonical")
                continue
            if references and (
                (dimensional and source_field == "source_objects")
                or (not dimensional and source_field == "source_dimensional_entities")
            ):
                issues.add("mapping_source_object_missing_or_ineligible")
                continue
            for reference in cast(list[Any], references):
                if not isinstance(reference, dict):
                    issues.add("mapping_source_object_missing_or_ineligible")
                    continue
                reference = cast(dict[str, Any], reference)
                layer = (
                    "dimensional" if source_field == "source_dimensional_entities" else "logical"
                )
                eligible = (
                    (
                        str(reference.get(f"{layer}_entity_schema_name", "")).strip().casefold(),
                        str(reference.get(f"{layer}_entity_name", "")).strip().casefold(),
                    )
                    in modeled_sources[layer]
                    if source_field != "source_objects"
                    else key(reference) in sources
                )
                if not eligible:
                    issues.add("mapping_source_object_missing_or_ineligible")
    for row in values["attribute_transformations"]:
        document = row.get("transformation")
        if not isinstance(document, dict):
            issues.add("mapping_document_not_canonical")
            continue
        template_code = row.get("output_template_code")
        if (
            template_code is not None
            and str(template_code).strip().casefold()
            not in MAPPING_REFERENCE_TEMPLATE_CODES["mapping_attribute"]
        ):
            continue
        document = cast(dict[str, Any], document)
        if "source_columns" in document and document["source_columns"] is not None:
            references = document["source_columns"]
            if not isinstance(references, list):
                issues.add("mapping_document_not_canonical")
            else:
                for reference in cast(list[Any], references):
                    obj = current_source(reference, row["source_system_code"].strip().casefold())
                    attribute_name = (
                        str(cast(dict[str, Any], reference).get("attribute_name", ""))
                        .strip()
                        .casefold()
                        if isinstance(reference, dict)
                        else ""
                    )
                    if (
                        obj is None
                        or not attribute_name
                        or not any(
                            str(attribute.get("attribute_name", "")).strip().casefold()
                            == attribute_name
                            for attribute in obj.get("attributes", [])
                            if attribute.get("is_active", True)
                        )
                    ):
                        issues.add("mapping_source_attribute_missing_or_ineligible")
        for source_field in (
            "source_attributes",
            "source_logical_attributes",
            "source_dimensional_attributes",
        ):
            references = document.get(source_field)
            if references is None:
                continue  # Generated/constant columns may have no source.
            if not isinstance(references, list):
                issues.add("mapping_document_not_canonical")
                continue
            if references and (
                (dimensional and source_field == "source_attributes")
                or (not dimensional and source_field == "source_dimensional_attributes")
            ):
                issues.add("mapping_source_attribute_missing_or_ineligible")
                continue
            modeled = source_field != "source_attributes"
            layer = "dimensional" if source_field == "source_dimensional_attributes" else "logical"
            for reference in cast(list[Any], references):
                if not isinstance(reference, dict):
                    issues.add("mapping_source_attribute_missing_or_ineligible")
                    continue
                reference = cast(dict[str, Any], reference)
                obj = (
                    modeled_sources[layer].get(
                        (
                            str(reference.get(f"{layer}_entity_schema_name", ""))
                            .strip()
                            .casefold(),
                            str(reference.get(f"{layer}_entity_name", "")).strip().casefold(),
                        )
                    )
                    if modeled
                    else sources.get(key(reference))
                )
                attribute_name = reference.get(
                    f"{layer}_attribute_name" if modeled else "attribute_name", ""
                )
                if obj is None or not any(
                    str(attribute.get("attribute_name", "")).strip().casefold()
                    == str(attribute_name).strip().casefold()
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
