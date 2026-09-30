"""Check declared Mapping references without pretending to execute arbitrary rules."""

from collections.abc import Mapping
from typing import Any

from gds_etl_workbench.application.mapping_context import MAPPING_REFERENCE_TEMPLATE_CODES
from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.context_inputs import OBJECT_FIELDS, natural_key

from .contracts import CompleteMappingCandidateV1
from .preparation_contracts import MappingModeledEntity, MappingPreparation


def validate_mapping_references(
    preparation: MappingPreparation, candidate: CompleteMappingCandidateV1
) -> None:
    header = preparation.context.headers[0]
    builtin_references: dict[str, bool] = {}
    for kind, selection in (
        ("mapping_object", preparation.plan.output_template_selections.mapping_object),
        ("mapping_attribute", preparation.plan.output_template_selections.mapping_attribute),
    ):
        builtin_references[kind] = selection is None or any(
            template.output_template_id == selection.output_template_id
            and template.code.strip().casefold() in MAPPING_REFERENCE_TEMPLATE_CODES[kind]
            for template in preparation.context.output_templates.definitions
        )
    object_document = (
        candidate.object_mapping.mapping_transformation_document
        if candidate.object_mapping
        and candidate.object_mapping.mapping_transformation_document is not None
        else header.transformation_document
    )
    preserved = {
        item.modeled_attribute_id
        for item in preparation.readiness.headers[0].attribute_actions
        if item.action == "preserve"
    }
    # Flexible/custom documents cannot prove an arbitrary rewrite preserves a field's
    # row grain. Keep the existing relational logic whenever any field is protected.
    if (
        preserved
        and candidate.object_mapping
        and candidate.object_mapping.mapping_transformation_document is not None
        and (
            header.transformation_document is not None
            or any(
                attribute.modeled_attribute_id in preserved
                and attribute.transformation_document is not None
                for attribute in header.attribute_mappings
            )
        )
        and object_document != header.transformation_document
    ):
        raise InvalidRequestError(
            "Keep existing Object logic unchanged while Attributes are locked or unselected. "
            "Changing joins or grain requires explicitly selecting all affected Attributes."
        )
    logical_fields = ("logical_entity_schema_name", "logical_entity_name")
    available: dict[tuple[Any, ...], set[str]] = {}
    for source in preparation.context.sources:
        if isinstance(source.object, MappingModeledEntity):
            layer = source.object.entity_type.removesuffix("_entity")
            available[
                (
                    layer,
                    source.object.entity_schema_name.strip().casefold(),
                    source.object.entity_name.strip().casefold(),
                )
            ] = {
                attribute.attribute_name.strip().casefold()
                for attribute in source.object.attributes
                if attribute.status == "active"
            }
        else:
            available[("physical", *natural_key(source.object.model_dump(), OBJECT_FIELDS))] = {
                attribute.attribute_name.strip().casefold()
                for attribute in source.object.attributes
                if attribute.is_active
            }
    aliases: set[str] = set()
    # A Logical transformation can join Input Scope Objects with modeled Logical lookups.
    # Dimensional transformations join modeled Logical sources with peer Gold lookups.
    # Eligible context never supplies physical keys for that route.
    for kind, fields, objects_field, attributes_field, attribute_field in (
        ("physical", OBJECT_FIELDS, "source_objects", "source_attributes", "attribute_name"),
        (
            "logical",
            logical_fields,
            "source_logical_entities",
            "source_logical_attributes",
            "logical_attribute_name",
        ),
        (
            "dimensional",
            ("dimensional_entity_schema_name", "dimensional_entity_name"),
            "source_dimensional_entities",
            "source_dimensional_attributes",
            "dimensional_attribute_name",
        ),
    ):
        used: set[tuple[Any, ...]] = set()
        # Preserve unchanged legacy/custom documents without forcing schema conversion.
        declared = (
            object_document.get(objects_field)
            if builtin_references["mapping_object"]
            and object_document
            and object_document != header.transformation_document
            else None
        )
        if declared is not None:
            if not isinstance(declared, list):
                raise InvalidRequestError("Declared Mapping sources must be an array or null.")
            for source in declared:
                if not isinstance(source, Mapping) or any(
                    not isinstance(value := source.get(key), str) or not value.strip()
                    for key in (*fields, "alias")
                ):
                    raise InvalidRequestError(
                        "Each Mapping source needs its complete natural key and alias."
                    )
                key = (kind, *natural_key(source, fields))
                alias_value = source["alias"]
                assert isinstance(alias_value, str)
                alias = alias_value.strip().casefold()
                if key not in available or alias in aliases:
                    raise InvalidRequestError(
                        "Mapping sources must be eligible and aliases must be unique."
                    )
                used.add(key)
                aliases.add(alias)
        for attribute in candidate.attribute_mappings:
            if (
                not builtin_references["mapping_attribute"]
                or attribute.attribute_mapping_transformation_document is None
            ):
                continue
            sources = attribute.attribute_mapping_transformation_document.get(attributes_field)
            if sources is None:
                continue
            if not isinstance(sources, list):
                raise InvalidRequestError("Declared Attribute sources must be an array or null.")
            for source in sources:
                if not isinstance(source, Mapping) or any(
                    not isinstance(value := source.get(key), str) or not value.strip()
                    for key in (*fields, attribute_field)
                ):
                    raise InvalidRequestError(
                        "Each source Attribute needs its complete natural key."
                    )
                key = (kind, *natural_key(source, fields))
                attribute_name = source[attribute_field]
                assert isinstance(attribute_name, str)
                if (
                    key not in available
                    or attribute_name.strip().casefold() not in available[key]
                    or (declared is not None and key not in used)
                ):
                    raise InvalidRequestError(
                        "A declared source Attribute is unavailable "
                        "or absent from its Entity sources."
                    )

    # The layer-specific defaults use one source list for physical and modeled
    # references. Keep the legacy fields above readable without rewriting history.
    tables_declared = (
        builtin_references["mapping_object"]
        and object_document is not None
        and object_document != header.transformation_document
        and "source_tables" in object_document
    )
    source_lists: list[tuple[str, JsonValue]] = []
    if tables_declared:
        assert object_document is not None
        source_lists.append(("source_tables", object_document["source_tables"]))
    source_lists.extend(
        ("source_columns", attribute.attribute_mapping_transformation_document["source_columns"])
        for attribute in candidate.attribute_mappings
        if builtin_references["mapping_attribute"]
        and attribute.attribute_mapping_transformation_document is not None
        and "source_columns" in attribute.attribute_mapping_transformation_document
    )
    table_keys: set[tuple[Any, ...]] = set()
    for field, references in source_lists:
        if field == "source_columns" and references is None:
            continue
        if not isinstance(references, list):
            raise InvalidRequestError(f"Mapping {field} must be an array.")
        for source in references:
            if not isinstance(source, Mapping):
                raise InvalidRequestError("Each Mapping source must be an object.")
            entity_type = source.get("entity_type")
            if entity_type in ("logical_entity", "dimensional_entity"):
                kind = str(entity_type).removesuffix("_entity")
                key_fields = ("entity_schema_name", "entity_name")
            elif "entity_type" not in source:
                kind = "physical"
                key_fields = OBJECT_FIELDS
            else:
                raise InvalidRequestError("Mapping source Entity type is invalid.")
            required = (*key_fields, "attribute_name") if field == "source_columns" else key_fields
            if any(
                not isinstance(source.get(key), str) or not str(source[key]).strip()
                for key in required
            ):
                raise InvalidRequestError("Each Mapping source needs its complete natural key.")
            key = (kind, *natural_key(source, key_fields))
            if key not in available:
                raise InvalidRequestError("Mapping sources must be eligible for this layer.")
            if field == "source_tables":
                table_keys.add(key)
            elif str(source["attribute_name"]).strip().casefold() not in available[key] or (
                tables_declared and key not in table_keys
            ):
                raise InvalidRequestError(
                    "A declared source Attribute is unavailable or absent from its Entity sources."
                )
