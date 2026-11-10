"""Check declared Mapping references without pretending to execute arbitrary rules."""

from collections.abc import Mapping
from typing import Any

from atlas_mcp.application.mapping_context import MAPPING_REFERENCE_TEMPLATE_CODES
from atlas_mcp.domain.errors import InvalidRequestError
from pydantic import JsonValue

from atlas_platform.features.workflows.authoring.context_inputs import OBJECT_FIELDS, natural_key

from .batch_rules import validate_object_batch_rules
from .contracts import CompleteMappingCandidateV1, MappingUnresolvedIssue
from .preparation_contracts import MappingModeledEntity, MappingPreparation


def _reference_template_ids(preparation: MappingPreparation) -> dict[str, set[int | None]]:
    # No selection uses the standard source declarations. Custom templates are opaque.
    return {
        kind: {
            None,
            *(
                item.output_template_id
                for item in preparation.context.output_templates.definitions
                if item.code.strip().casefold() in codes
            ),
        }
        for kind, codes in MAPPING_REFERENCE_TEMPLATE_CODES.items()
    }


def defer_circular_sources(
    preparation: MappingPreparation, candidate: CompleteMappingCandidateV1
) -> tuple[CompleteMappingCandidateV1, bool, set[str]]:
    """Keep saved logic when a proposed rule needs a circular parent."""
    deferred_fields = {
        name.casefold() for name in preparation.readiness.deferred_dependency_attributes
    }
    parent_ids = set(preparation.readiness.deferred_dependency_parent_ids)
    if not deferred_fields and not parent_ids:
        return candidate, False, set()
    layer = preparation.context.modeled_entity_type
    parents = {
        (obj.entity_schema_name.strip().casefold(), obj.entity_name.strip().casefold())
        for source in preparation.context.sources
        if isinstance(obj := source.object, MappingModeledEntity)
        and obj.entity_type == layer
        and obj.entity_id in parent_ids
    }
    templates = _reference_template_ids(preparation)
    selections = preparation.plan.output_template_selections
    family = layer.removesuffix("_entity")

    def declares_parent(
        document: dict[str, JsonValue] | None, kind: str, template_id: int | None
    ) -> bool:
        if not document or template_id not in templates[kind] or not parents:
            return False
        object_level = kind == "mapping_object"
        for field, schema_key, name_key, unified in (
            (
                "source_tables" if object_level else "source_columns",
                "entity_schema_name",
                "entity_name",
                True,
            ),
            (
                f"source_{family}_entities" if object_level else f"source_{family}_attributes",
                f"{family}_entity_schema_name",
                f"{family}_entity_name",
                False,
            ),
        ):
            refs = document.get(field)
            if not isinstance(refs, list):
                continue
            for ref in refs:
                if not isinstance(ref, dict) or (unified and ref.get("entity_type") != layer):
                    continue
                schema, name = ref.get(schema_key), ref.get(name_key)
                if (
                    isinstance(schema, str)
                    and isinstance(name, str)
                    and (schema.strip().casefold(), name.strip().casefold()) in parents
                ):
                    return True
        return False

    header = preparation.context.headers[0]
    target_fields = {a.attribute_id: a.attribute_name for a in header.modeled_entity.attributes}
    saved = {target_fields[a.modeled_attribute_id].casefold(): a for a in header.attribute_mappings}
    proposed = {a.modeled_attribute_name.casefold(): a for a in candidate.attribute_mappings}
    issues = list(candidate.issues)
    seen = {(issue.code, issue.modeled_attribute_name) for issue in issues}

    def warn(name: str | None) -> None:
        key = ("missing_join_evidence", name)
        if len(issues) < 200 and key not in seen:
            issues.append(
                MappingUnresolvedIssue(code="missing_join_evidence", modeled_attribute_name=name)
            )
            seen.add(key)

    obj = candidate.object_mapping
    object_doc = obj.mapping_transformation_document if obj else None
    obj_id = selections.mapping_object.output_template_id if selections.mapping_object else None
    attr_id = (
        selections.mapping_attribute.output_template_id if selections.mapping_attribute else None
    )
    circular_object = declares_parent(object_doc, "mapping_object", obj_id)
    retain_object = circular_object or (
        object_doc is None
        and declares_parent(
            header.transformation_document, "mapping_object", header.output_template_id
        )
    )
    if circular_object and object_doc != header.transformation_document:
        warn(None)
    retained_fields: set[str] = set()
    skip_fields = deferred_fields.copy()
    for name, existing in saved.items():
        item = proposed.get(name)
        doc = item.attribute_mapping_transformation_document if item else None
        circular_field = declares_parent(doc, "mapping_attribute", attr_id)
        saved_circular = doc is None and declares_parent(
            existing.transformation_document, "mapping_attribute", existing.output_template_id
        )
        if name in deferred_fields or circular_field or saved_circular:
            skip_fields.add(name)
            if existing.transformation_document is not None:
                retained_fields.add(name)
            if doc is not None and doc != existing.transformation_document:
                warn(target_fields[existing.modeled_attribute_id])
    # A retained field can rely on the old aliases or row grain. Do not change
    # its rowset when another part of the proposed Mapping was withheld.
    if retained_fields and object_doc != header.transformation_document:
        retain_object = True
        if object_doc is not None:
            warn(None)
    normalized = candidate.model_copy(
        update={
            "issues": tuple(issues),
            "object_mapping": None if retain_object else obj,
            "attribute_mappings": tuple(
                item
                for item in candidate.attribute_mappings
                if item.modeled_attribute_name.casefold() not in skip_fields
            ),
        }
    )
    return normalized, retain_object and header.transformation_document is not None, retained_fields


def validate_mapping_references(
    preparation: MappingPreparation, candidate: CompleteMappingCandidateV1
) -> None:
    header = preparation.context.headers[0]
    template_ids = _reference_template_ids(preparation)
    builtin_references = {
        kind: (selection.output_template_id if selection else None) in template_ids[kind]
        for kind, selection in (
            ("mapping_object", preparation.plan.output_template_selections.mapping_object),
            ("mapping_attribute", preparation.plan.output_template_selections.mapping_attribute),
        )
    }
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
    if (
        builtin_references["mapping_object"]
        and object_document is not None
        and object_document != header.transformation_document
    ):
        validate_object_batch_rules(preparation, object_document)
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
