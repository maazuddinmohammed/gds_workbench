"""Reconcile flexible Mapping output into binding-oriented Model Change records."""

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

from gds_workbench_api.features.workflows.authoring.context_inputs import natural_key

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
        if candidate.outcome == "no_applicable_source":
            if (
                candidate.object_mapping is not None
                or candidate.attribute_mappings
                or candidate.issues
            ):
                raise InvalidRequestError(
                    "A no-source outcome cannot contain transformations or issues."
                )
            known_source = any(
                source.source_mapping_id is not None for source in self._preparation.context.sources
            )
            snapshot = self._preparation.snapshot
            if snapshot is not None:
                layer = (
                    "logical"
                    if self._preparation.plan.route == "logical_to_silver"
                    else "dimensional"
                )
                section = snapshot.logical if layer == "logical" else snapshot.dimensional
                source_keys = {
                    natural_key(source.object.model_dump())
                    for source in self._preparation.context.sources
                }
                known_source |= any(
                    source.status == "active"
                    and source.support_source_type == "attribute"
                    and natural_key(source.source_attribute.model_dump()) in source_keys
                    for attribute in section.attributes
                    if getattr(attribute, f"{layer}_entity_name").casefold()
                    == header.modeled_entity.entity_name.casefold()
                    and getattr(attribute, f"{layer}_attribute_status") == "active"
                    for source in attribute.sources
                )
            if header.is_authored or known_source:
                raise InvalidRequestError(
                    "Known source evidence or an existing Mapping requires complete authoring. "
                    "Report missing transformation evidence instead of skipping the target."
                )
            return ()
        if not self._preparation.context.sources:
            raise InvalidRequestError(
                "No physical source is available; return no_applicable_source."
            )
        readiness = self._preparation.readiness.headers[0]
        object_actionable = readiness.action in {"author", "extend"}
        if object_actionable != (candidate.object_mapping is not None):
            raise InvalidRequestError(
                "Mapping output must include exactly the actionable Object transformation."
            )

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
        if returned_names != set(modeled_attributes):
            raise InvalidRequestError(
                "Mapping output must cover every actionable bound Attribute exactly once."
            )

        validate_mapping_references(self._preparation, candidate)

        object_records: list[dict[str, object]] = []
        if candidate.object_mapping is not None:
            authored = MappingObjectRecord(
                modeled_entity_type=self._preparation.plan.modeled_entity_type,
                modeled_entity_name=header.modeled_entity.entity_name,
                source_system_code=self._preparation.context.source_system.system_code,
                output_template_code=_output_template_code(
                    self._preparation,
                    self._preparation.plan.output_template_selections.mapping_object,
                ),
                object_dependency_order=candidate.object_mapping.object_dependency_order,
                mapping_transformation_document=cast(
                    dict[str, object], candidate.object_mapping.mapping_transformation_document
                ),
                object_mapping_status="active",
                object_mapping_is_locked=header.is_locked,
            )
            current = _current_object_record(self._preparation, header)
            if authored != current:
                object_records.append(cast(dict[str, object], authored.model_dump(mode="json")))

        existing_by_modeled_id = {
            item.modeled_attribute_id: item for item in header.attribute_mappings
        }
        attribute_records: list[dict[str, object]] = []
        for item in candidate.attribute_mappings:
            modeled = modeled_attributes[item.modeled_attribute_name.casefold()]
            existing = existing_by_modeled_id.get(modeled.attribute_id)
            if existing is None:
                raise InvalidRequestError("The bound Mapping Attribute context is unavailable.")
            authored = MappingAttributeRecord(
                modeled_entity_type=self._preparation.plan.modeled_entity_type,
                modeled_entity_name=header.modeled_entity.entity_name,
                modeled_attribute_name=modeled.attribute_name,
                source_system_code=self._preparation.context.source_system.system_code,
                output_template_code=_output_template_code(
                    self._preparation,
                    self._preparation.plan.output_template_selections.mapping_attribute,
                ),
                attribute_mapping_transformation_document=cast(
                    dict[str, object], item.attribute_mapping_transformation_document
                ),
                attribute_mapping_status="active",
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
    if not header.is_authored:
        return None
    return MappingObjectRecord(
        modeled_entity_type=preparation.plan.modeled_entity_type,
        modeled_entity_name=header.modeled_entity.entity_name,
        source_system_code=preparation.context.source_system.system_code,
        output_template_code=_template_code_by_id(preparation, header.output_template_id),
        object_dependency_order=header.object_dependency_order,
        mapping_transformation_document=cast(
            dict[str, object],
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
    if existing.mapping_attribute_id is None or existing.transformation_document is None:
        return None
    modeled = next(
        item
        for item in header.modeled_entity.attributes
        if item.attribute_id == existing.modeled_attribute_id
    )
    return MappingAttributeRecord(
        modeled_entity_type=preparation.plan.modeled_entity_type,
        modeled_entity_name=header.modeled_entity.entity_name,
        modeled_attribute_name=modeled.attribute_name,
        source_system_code=preparation.context.source_system.system_code,
        output_template_code=_template_code_by_id(preparation, existing.output_template_id),
        attribute_mapping_transformation_document=cast(
            dict[str, object],
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
