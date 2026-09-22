"""Check declared Mapping references without pretending to execute arbitrary rules."""

from collections.abc import Mapping
from typing import Any

from gds_etl_workbench.domain.errors import InvalidRequestError

from gds_workbench_api.features.workflows.authoring.context_inputs import OBJECT_FIELDS, natural_key

from .contracts import CompleteMappingCandidateV1
from .preparation_contracts import MappingPreparation


def validate_mapping_references(
    preparation: MappingPreparation, candidate: CompleteMappingCandidateV1
) -> None:
    header = preparation.context.headers[0]
    object_document = (
        candidate.object_mapping.mapping_transformation_document
        if candidate.object_mapping
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
        and header.transformation_document is not None
        and object_document != header.transformation_document
    ):
        raise InvalidRequestError(
            "Keep existing Object logic unchanged while Attributes are locked or unselected. "
            "Changing joins or grain requires explicitly selecting all affected Attributes."
        )
    available = {
        natural_key(source.object.model_dump()): {
            attribute.attribute_name.strip().casefold()
            for attribute in source.object.attributes
            if attribute.is_active
        }
        for source in preparation.context.sources
    }
    aliases: set[str] = set()
    used: set[tuple[Any, ...]] = set()
    # Existing documents may use an older/custom shape. Validate new references,
    # without forcing a schema conversion when the Object document is unchanged.
    declared = (
        object_document.get("source_objects")
        if object_document and object_document != header.transformation_document
        else None
    )
    if declared is not None:
        if not isinstance(declared, list):
            raise InvalidRequestError("Object source_objects must be an array or null.")
        for source in declared:
            if not isinstance(source, Mapping) or any(
                not isinstance(value := source.get(key), str) or not value.strip()
                for key in (*OBJECT_FIELDS, "alias")
            ):
                raise InvalidRequestError(
                    "Each source Object needs its complete natural key and alias."
                )
            key = natural_key(source)
            alias_value = source["alias"]
            assert isinstance(alias_value, str)
            alias = alias_value.strip().casefold()
            if key not in available or alias in aliases:
                raise InvalidRequestError(
                    "Source Objects must be eligible and aliases must be unique."
                )
            used.add(key)
            aliases.add(alias)
    for attribute in candidate.attribute_mappings:
        sources = attribute.attribute_mapping_transformation_document.get("source_attributes")
        if sources is None:
            continue
        if not isinstance(sources, list):
            raise InvalidRequestError("Attribute source_attributes must be an array or null.")
        for source in sources:
            if not isinstance(source, Mapping) or any(
                not isinstance(value := source.get(key), str) or not value.strip()
                for key in (*OBJECT_FIELDS, "attribute_name")
            ):
                raise InvalidRequestError("Each source Attribute needs its complete natural key.")
            key = natural_key(source)
            attribute_name = source["attribute_name"]
            assert isinstance(attribute_name, str)
            if (
                key not in available
                or attribute_name.strip().casefold() not in available[key]
                or (declared is not None and key not in used)
            ):
                raise InvalidRequestError(
                    "A declared source Attribute is unavailable or absent from the Object sources."
                )
