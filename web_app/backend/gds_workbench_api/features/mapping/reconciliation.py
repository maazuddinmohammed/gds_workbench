"""Reconcile flexible Mapping output into Entity-owned Model Change records."""

from __future__ import annotations

from typing import Literal, cast

from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.application.change_sets.model_validation import validate_staged_records
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    MappingAttributeRecord,
    MappingObjectRecord,
)
from pydantic import ValidationError

from .contracts import CompleteMappingCandidateV1
from .preparation_contracts import (
    ExistingMappingAttribute,
    ExistingMappingHeader,
    MappingPreparation,
)
from .semantics import validate_mapping_references


class MappingCandidateReconciler:
    """Derive identity/status server-side and stage only effective deltas."""

    def __init__(self, *, preparation: MappingPreparation) -> None:
        if not preparation.readiness.ready:
            raise ValueError("Mapping reconciliation requires a ready preparation")
        self._preparation = preparation

    def reconcile(
        self,
        *,
        candidate: CompleteMappingCandidateV1,
    ) -> tuple[StageModelChange, ...]:
        header = self._preparation.context.headers[0]
        readiness = self._preparation.readiness.headers[0]
        object_actionable = readiness.action in {"author", "extend"}
        object_document = (
            candidate.object_mapping.mapping_transformation_document
            if candidate.object_mapping is not None
            else None
        )
        has_output = object_document is not None or any(
            item.attribute_mapping_transformation_document is not None
            for item in candidate.attribute_mappings
        )
        if candidate.outcome == "no_applicable_source" and has_output:
            raise InvalidRequestError("A no-source outcome cannot contain transformations.")
        if has_output and (
            not self._preparation.context.sources
            and not self._preparation.context.source_system.is_default
        ):
            raise InvalidRequestError("No eligible source is available for this Mapping output.")
        if object_document is not None and not object_actionable:
            raise InvalidRequestError("Mapping output cannot replace preserved Object logic.")

        actionable_attribute_ids = {
            item.modeled_attribute_id
            for item in readiness.attribute_actions
            if item.action in {"author", "extend"}
        }
        modeled_attributes = {
            item.attribute_name.casefold(): item
            for item in header.modeled_entity.attributes
            if item.attribute_id in actionable_attribute_ids
        }
        returned_names = {
            item.modeled_attribute_name.casefold() for item in candidate.attribute_mappings
        }
        if not returned_names <= set(modeled_attributes):
            raise InvalidRequestError(
                "Mapping output can include only selected, unlocked modeled Attributes."
            )

        validate_mapping_references(self._preparation, candidate)

        # Omitted selected transformations are cleared on regeneration. A new
        # pair needs useful output; do not manufacture empty parent/child rows.
        object_records: list[dict[str, object]] = []
        existing_parent = header.mapping_object_id is not None
        preserved_attributes = any(
            item.action == "preserve" for item in readiness.attribute_actions
        )
        if existing_parent or has_output:
            current = _current_object_record(self._preparation, header)
            next_document = (
                header.transformation_document
                if not object_actionable
                or (preserved_attributes and header.transformation_document is not None)
                else object_document
            )
            authored = MappingObjectRecord(
                modeled_entity_type=self._preparation.plan.modeled_entity_type,
                modeled_entity_schema_name=header.modeled_entity.entity_schema_name,
                modeled_entity_name=header.modeled_entity.entity_name,
                source_system_code=self._preparation.context.source_system.system_code,
                output_template_code=(
                    _output_template_code(
                        self._preparation,
                        self._preparation.plan.output_template_selections.mapping_object,
                    )
                    if object_actionable
                    else _template_code_by_id(
                        self._preparation,
                        header.output_template_id,
                    )
                ),
                object_dependency_order=(
                    candidate.object_mapping.object_dependency_order
                    if candidate.object_mapping is not None and object_document is not None
                    else header.object_dependency_order
                ),
                mapping_transformation_document=cast(dict[str, object] | None, next_document),
                object_mapping_status="active" if has_output else header.status,
                object_mapping_is_locked=header.is_locked,
            )
            if authored != current and object_actionable:
                object_records.append(cast(dict[str, object], authored.model_dump(mode="json")))

        existing_by_modeled_id = {
            item.modeled_attribute_id: item for item in header.attribute_mappings
        }
        returned = {
            item.modeled_attribute_name.casefold(): item.attribute_mapping_transformation_document
            for item in candidate.attribute_mappings
        }
        attribute_records: list[dict[str, object]] = []
        for name, modeled in modeled_attributes.items():
            existing = existing_by_modeled_id.get(modeled.attribute_id)
            if existing is None:
                raise InvalidRequestError("The modeled Mapping Attribute context is unavailable.")
            document = returned.get(name)
            if document is None and existing.mapping_attribute_id is None:
                continue
            authored = MappingAttributeRecord(
                modeled_entity_type=self._preparation.plan.modeled_entity_type,
                modeled_entity_schema_name=header.modeled_entity.entity_schema_name,
                modeled_entity_name=header.modeled_entity.entity_name,
                modeled_attribute_name=modeled.attribute_name,
                source_system_code=self._preparation.context.source_system.system_code,
                output_template_code=_output_template_code(
                    self._preparation,
                    self._preparation.plan.output_template_selections.mapping_attribute,
                ),
                attribute_mapping_transformation_document=cast(dict[str, object] | None, document),
                attribute_mapping_status="active" if document is not None else existing.status,
                attribute_mapping_is_locked=existing.is_locked,
            )
            current = _current_attribute_record(self._preparation, header, existing)
            if authored != current:
                attribute_records.append(cast(dict[str, object], authored.model_dump(mode="json")))

        changes: list[StageModelChange] = []
        if object_records:
            changes.append(
                StageModelChange(
                    dataset="mapping_object",
                    records=_validate_records("mapping_object", object_records),
                )
            )
        if attribute_records:
            changes.append(
                StageModelChange(
                    dataset="mapping_attribute",
                    records=_validate_records("mapping_attribute", attribute_records),
                )
            )
        return tuple(changes)

    def reconcile_preserved(self) -> tuple[StageModelChange, ...]:
        header = self._preparation.readiness.headers[0]
        if header.action != "preserve" or any(
            item.action != "preserve" for item in header.attribute_actions
        ):
            raise InvalidRequestError("Mapping output is required for actionable context.")
        return ()


def _current_object_record(
    preparation: MappingPreparation,
    header: ExistingMappingHeader,
) -> MappingObjectRecord | None:
    if header.mapping_object_id is None:
        return None
    return MappingObjectRecord(
        modeled_entity_type=preparation.plan.modeled_entity_type,
        modeled_entity_schema_name=header.modeled_entity.entity_schema_name,
        modeled_entity_name=header.modeled_entity.entity_name,
        source_system_code=preparation.context.source_system.system_code,
        output_template_code=_template_code_by_id(preparation, header.output_template_id),
        object_dependency_order=header.object_dependency_order,
        mapping_transformation_document=cast(
            dict[str, object] | None,
            header.transformation_document,
        ),
        object_mapping_status=header.status,
        object_mapping_is_locked=header.is_locked,
    )


def _current_attribute_record(
    preparation: MappingPreparation,
    header: ExistingMappingHeader,
    existing: ExistingMappingAttribute,
) -> MappingAttributeRecord | None:
    if existing.mapping_attribute_id is None:
        return None
    modeled = next(
        item
        for item in header.modeled_entity.attributes
        if item.attribute_id == existing.modeled_attribute_id
    )
    return MappingAttributeRecord(
        modeled_entity_type=preparation.plan.modeled_entity_type,
        modeled_entity_schema_name=header.modeled_entity.entity_schema_name,
        modeled_entity_name=header.modeled_entity.entity_name,
        modeled_attribute_name=modeled.attribute_name,
        source_system_code=preparation.context.source_system.system_code,
        output_template_code=_template_code_by_id(preparation, existing.output_template_id),
        attribute_mapping_transformation_document=cast(
            dict[str, object] | None,
            existing.transformation_document,
        ),
        attribute_mapping_status=existing.status,
        attribute_mapping_is_locked=existing.is_locked,
    )


def _output_template_code(preparation: MappingPreparation, selection: object) -> str | None:
    template_id = getattr(selection, "output_template_id", None)
    return _template_code_by_id(preparation, template_id)


def _template_code_by_id(
    preparation: MappingPreparation,
    output_template_id: int | None,
) -> str | None:
    if output_template_id is None:
        return None
    matches = [
        item
        for item in preparation.context.output_templates.definitions
        if item.output_template_id == output_template_id
    ]
    if len(matches) != 1:
        raise InvalidRequestError("Mapping output-template identity is unavailable.")
    return matches[0].code


def _validate_records(
    dataset: Literal["mapping_object", "mapping_attribute"],
    documents: list[dict[str, object]],
) -> list[dict[str, object]]:
    try:
        records, issues = validate_staged_records(dataset, documents)
    except ValidationError:
        raise InvalidRequestError("Mapping record validation failed.") from None
    if issues or len(records) != len(documents):
        raise InvalidRequestError("Mapping record validation failed.")
    return [cast(dict[str, object], item.model_dump(mode="json")) for item in records]
