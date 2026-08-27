"""Reconcile complete Mapping worker output into one atomic staged delta."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.mapping_contracts import MappingPackageDocumentV1
from gds_etl_workbench.domain.mapping_profiles import mapping_package_digest
from gds_etl_workbench.domain.modeling_records import (
    MappingAttributeRecord,
    MappingObjectRecord,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from gds_etl_workbench.tools.change_sets.model_validation import (
    validate_staged_records,
)
from pydantic import JsonValue, ValidationError

from gds_workbench_api.features.mapping.attribute_candidate import (
    MappingAttributeBatchPlan,
    MappingAttributeCandidateValidator,
    NormalizedMappingAttribute,
    NormalizedMappingAttributeBatch,
    build_mapping_attribute_batch_plans,
)
from gds_workbench_api.features.mapping.candidate import (
    MappingHeaderCandidateValidator,
    NormalizedMappingHeader,
    NormalizedMappingHeaderCandidate,
)
from gds_workbench_api.features.mapping.preparation_contracts import (
    ExistingMappingAttribute,
    ExistingMappingHeader,
    MappingPreparation,
)


class MappingCandidateReconciler:
    """Require complete worker coverage and emit only validated true deltas."""

    def __init__(self, *, preparation: MappingPreparation) -> None:
        if not preparation.readiness.ready:
            raise ValueError("Mapping reconciliation requires a ready preparation.")
        self._preparation = preparation

    def reconcile(
        self,
        *,
        header: NormalizedMappingHeaderCandidate,
        attribute_batches: Sequence[NormalizedMappingAttributeBatch],
    ) -> tuple[StageModelChange, ...]:
        header, batches = _revalidate_normalized_inputs(header, attribute_batches)
        self._validate_package(header)
        _revalidate_header_semantics(preparation=self._preparation, header=header)
        plans = build_mapping_attribute_batch_plans(
            preparation=self._preparation,
            package=header.package,
        )
        self._validate_complete_batches(
            plans=plans,
            batches=batches,
            package=header.package,
            package_digest=header.package_digest,
        )
        self._validate_global_attribute_identity(batches)

        object_documents = self._object_deltas(header)
        attribute_documents = self._attribute_deltas(batches)
        changes: list[StageModelChange] = []
        if object_documents:
            changes.append(
                StageModelChange(
                    dataset="mapping_object",
                    records=_validate_records("mapping_object", object_documents),
                )
            )
        if attribute_documents:
            changes.append(
                StageModelChange(
                    dataset="mapping_attribute",
                    records=_validate_records(
                        "mapping_attribute",
                        attribute_documents,
                    ),
                )
            )
        return tuple(changes)

    def reconcile_preserved(self) -> tuple[StageModelChange, ...]:
        """Return an explicit no-change result only for wholly preserved context."""
        readiness = self._preparation.readiness
        if (
            readiness.package_action != "preserve"
            or any(header.action != "preserve" for header in readiness.headers)
            or any(
                child.action != "preserve"
                for header in readiness.headers
                for child in header.attribute_actions
            )
        ):
            raise InvalidRequestError(
                "Mapping reconciliation requires agent output for actionable context."
            )
        return ()

    def _validate_package(self, header: NormalizedMappingHeaderCandidate) -> None:
        plan = self._preparation.plan
        context = self._preparation.context
        actual_digest = mapping_package_digest(header.package.model_dump(mode="json"))
        expected_header_ids = tuple(sorted(item.mapping_object_id for item in context.headers))
        readiness_actions = {
            item.mapping_object_id: item.action for item in self._preparation.readiness.headers
        }
        actionable_header_ids = tuple(
            sorted(
                item_id
                for item_id, action in readiness_actions.items()
                if action in {"author", "extend"}
            )
        )
        returned_header_ids = tuple(item.mapping_object_id for item in header.headers)
        if (
            header.package_digest != actual_digest
            or header.package.target_object_id != plan.pair.target_object_id
            or header.package.source_system_id != plan.pair.source_system_id
            or header.package.route != plan.route
            or header.package.artifact_type != plan.artifact_type
            or header.package.pydantic_profile.key != plan.profile.key
            or header.package.pydantic_profile.version != plan.profile.version
            or header.package.pydantic_profile.schema_digest != plan.profile.schema_digest
            or header.coverage.expected_mapping_object_ids != expected_header_ids
            or header.coverage.returned_mapping_object_ids != actionable_header_ids
            or returned_header_ids != actionable_header_ids
        ):
            raise InvalidRequestError(
                "Mapping reconciliation package identity or header coverage changed."
            )

    def _validate_complete_batches(
        self,
        *,
        plans: tuple[MappingAttributeBatchPlan, ...],
        batches: tuple[NormalizedMappingAttributeBatch, ...],
        package: MappingPackageDocumentV1,
        package_digest: str,
    ) -> None:
        if len(plans) != len(batches):
            raise InvalidRequestError(
                "Mapping reconciliation requires every complete Attribute batch."
            )
        batches_by_index = {item.chunk_index: item for item in batches}
        if len(batches_by_index) != len(batches):
            raise InvalidRequestError(
                "Mapping reconciliation requires every complete Attribute batch once."
            )
        expected_target_ids: list[int] = []
        returned_target_ids: list[int] = []
        for plan in plans:
            batch = batches_by_index.get(plan.chunk_index)
            if batch is None:
                raise InvalidRequestError(
                    "Mapping reconciliation requires every complete Attribute batch."
                )
            if (
                batch.package_ref != plan.package_ref
                or batch.target_object_id != plan.target_object_id
                or batch.source_system_id != plan.source_system_id
                or batch.chunk_index != plan.chunk_index
                or batch.chunk_count != plan.chunk_count
                or batch.package_digest != package_digest
                or batch.package_digest != plan.package_digest
                or batch.coverage_manifest_digest != plan.coverage_manifest_digest
            ):
                raise InvalidRequestError(
                    "Mapping reconciliation Attribute batch package identity changed."
                )
            _revalidate_attribute_semantics(
                preparation=self._preparation,
                package=package,
                plan=plan,
                batch=batch,
            )
            expected_target_ids.extend(plan.expected_target_attribute_ids)
            returned_target_ids.extend(
                item.target_attribute_id for item in batch.target_attribute_dispositions
            )
        if returned_target_ids != expected_target_ids or len(returned_target_ids) != len(
            set(returned_target_ids)
        ):
            raise InvalidRequestError(
                "Mapping reconciliation requires complete target Attribute coverage."
            )

    def _validate_global_attribute_identity(
        self,
        batches: tuple[NormalizedMappingAttributeBatch, ...],
    ) -> None:
        local_refs: list[str] = []
        binding_keys: list[tuple[int, int, int]] = []
        existing_ids: list[int] = []
        for batch in batches:
            for mapping in batch.attribute_mappings:
                if mapping.local_ref is not None:
                    local_refs.append(mapping.local_ref)
                if mapping.mapping_attribute_id is not None:
                    existing_ids.append(mapping.mapping_attribute_id)
                modeled_attribute_id = (
                    mapping.logical_attribute_id or mapping.dimensional_attribute_id or 0
                )
                binding_keys.append(
                    (
                        mapping.mapping_object_id,
                        modeled_attribute_id,
                        mapping.target_attribute_id,
                    )
                )
        if (
            len(local_refs) != len(set(local_refs))
            or len(existing_ids) != len(set(existing_ids))
            or len(binding_keys) != len(set(binding_keys))
        ):
            raise InvalidRequestError(
                "Mapping reconciliation requires complete unique Attribute bindings."
            )

    def _object_deltas(
        self,
        header_candidate: NormalizedMappingHeaderCandidate,
    ) -> list[dict[str, object]]:
        context_headers = {
            item.mapping_object_id: item for item in self._preparation.context.headers
        }
        result: list[dict[str, object]] = []
        for candidate in header_candidate.headers:
            existing = context_headers[candidate.mapping_object_id]
            try:
                authored = _mapping_object_record(
                    preparation=self._preparation,
                    existing=existing,
                    candidate=candidate,
                    package=header_candidate,
                )
                current = _current_mapping_object_record(
                    preparation=self._preparation,
                    existing=existing,
                )
            except ValidationError:
                raise InvalidRequestError(
                    "Mapping reconciliation failed shared record validation."
                ) from None
            selection = self._preparation.plan.output_template_selections.mapping_object
            selected_template_id = None if selection is None else selection.output_template_id
            if authored != current or existing.output_template_id != selected_template_id:
                result.append(cast(dict[str, object], authored.model_dump(mode="json")))
        return result

    def _attribute_deltas(
        self,
        batches: tuple[NormalizedMappingAttributeBatch, ...],
    ) -> list[dict[str, object]]:
        context_headers = {
            item.mapping_object_id: item for item in self._preparation.context.headers
        }
        children = {
            child.mapping_attribute_id: (header, child)
            for header in self._preparation.context.headers
            for child in header.attribute_mappings
        }
        result: list[dict[str, object]] = []
        mappings = sorted(
            (mapping for batch in batches for mapping in batch.attribute_mappings),
            key=lambda item: (
                item.target_attribute_id,
                item.mapping_object_id,
                item.mapping_attribute_id or 0,
                item.local_ref or "",
            ),
        )
        for candidate in mappings:
            header = context_headers.get(candidate.mapping_object_id)
            if header is None:
                raise InvalidRequestError("Mapping reconciliation Attribute header is unavailable.")
            current_pair: tuple[ExistingMappingHeader, ExistingMappingAttribute] | None = None
            if candidate.mapping_attribute_id is not None:
                current_pair = children.get(candidate.mapping_attribute_id)
                if current_pair is None:
                    raise InvalidRequestError(
                        "Mapping reconciliation existing Attribute is unavailable."
                    )
            try:
                authored = _mapping_attribute_record(
                    preparation=self._preparation,
                    header=header,
                    candidate=candidate,
                    existing=None if current_pair is None else current_pair[1],
                )
                current = (
                    None
                    if current_pair is None
                    else _current_mapping_attribute_record(
                        preparation=self._preparation,
                        header=current_pair[0],
                        existing=current_pair[1],
                    )
                )
            except ValidationError:
                raise InvalidRequestError(
                    "Mapping reconciliation failed shared record validation."
                ) from None
            selection = self._preparation.plan.output_template_selections.mapping_attribute
            selected_template_id = None if selection is None else selection.output_template_id
            template_changed = (
                current_pair is not None
                and current_pair[1].output_template_id != selected_template_id
            )
            if authored != current or template_changed:
                result.append(cast(dict[str, object], authored.model_dump(mode="json")))
        return result


def _mapping_object_record(
    *,
    preparation: MappingPreparation,
    existing: ExistingMappingHeader,
    candidate: NormalizedMappingHeader,
    package: NormalizedMappingHeaderCandidate,
) -> MappingObjectRecord:
    target = preparation.context.target
    return MappingObjectRecord(
        tenant_code=target.tenant_code,
        system_code=target.system_code,
        connection_code=target.connection_code,
        object_schema=target.object_schema,
        object_name=target.object_name,
        source_system_code=preparation.context.source_system.system_code,
        modeled_entity_type=preparation.plan.modeled_entity_type,
        modeled_entity_name=existing.modeled_entity.entity_name,
        object_dependency_order=existing.object_dependency_order,
        artifact_type=package.package.artifact_type,
        artifact_generation_instructions=(package.package.artifact_generation_instructions),
        mapping_profile_key=package.package.pydantic_profile.key,
        mapping_profile_version=package.package.pydantic_profile.version,
        mapping_package_document=cast(
            dict[str, object],
            package.package.model_dump(mode="json"),
        ),
        object_mapping_transformation_document=cast(dict[str, object], candidate.transformation),
        object_mapping_status=existing.status,
        object_mapping_is_locked=existing.is_locked,
    )


def _current_mapping_object_record(
    *,
    preparation: MappingPreparation,
    existing: ExistingMappingHeader,
) -> MappingObjectRecord:
    target = preparation.context.target
    return MappingObjectRecord(
        tenant_code=target.tenant_code,
        system_code=target.system_code,
        connection_code=target.connection_code,
        object_schema=target.object_schema,
        object_name=target.object_name,
        source_system_code=preparation.context.source_system.system_code,
        modeled_entity_type=preparation.plan.modeled_entity_type,
        modeled_entity_name=existing.modeled_entity.entity_name,
        object_dependency_order=existing.object_dependency_order,
        artifact_type=existing.artifact_type,
        artifact_generation_instructions=existing.artifact_generation_instructions,
        mapping_profile_key=(None if existing.profile is None else existing.profile.key),
        mapping_profile_version=(None if existing.profile is None else existing.profile.version),
        mapping_package_document=cast(
            dict[str, object] | None,
            existing.mapping_package_document,
        ),
        object_mapping_transformation_document=cast(
            dict[str, object] | None,
            existing.transformation_document,
        ),
        object_mapping_status=existing.status,
        object_mapping_is_locked=existing.is_locked,
    )


def _mapping_attribute_record(
    *,
    preparation: MappingPreparation,
    header: ExistingMappingHeader,
    candidate: NormalizedMappingAttribute,
    existing: ExistingMappingAttribute | None,
) -> MappingAttributeRecord:
    target = preparation.context.target
    target_attribute = next(
        (item for item in target.attributes if item.attribute_id == candidate.target_attribute_id),
        None,
    )
    modeled_attribute_id = candidate.logical_attribute_id or candidate.dimensional_attribute_id
    modeled_attribute = next(
        (
            item
            for item in header.modeled_entity.attributes
            if item.attribute_id == modeled_attribute_id
        ),
        None,
    )
    if target_attribute is None or modeled_attribute is None:
        raise InvalidRequestError("Mapping reconciliation Attribute identity is unavailable.")
    return MappingAttributeRecord(
        tenant_code=target.tenant_code,
        system_code=target.system_code,
        connection_code=target.connection_code,
        object_schema=target.object_schema,
        object_name=target.object_name,
        attribute_name=target_attribute.attribute_name,
        source_system_code=preparation.context.source_system.system_code,
        modeled_entity_type=preparation.plan.modeled_entity_type,
        modeled_entity_name=header.modeled_entity.entity_name,
        modeled_attribute_name=modeled_attribute.attribute_name,
        attribute_mapping_transformation_document=cast(
            dict[str, object],
            candidate.transformation,
        ),
        attribute_mapping_status="active" if existing is None else existing.status,
        attribute_mapping_is_locked=False if existing is None else existing.is_locked,
    )


def _current_mapping_attribute_record(
    *,
    preparation: MappingPreparation,
    header: ExistingMappingHeader,
    existing: ExistingMappingAttribute,
) -> MappingAttributeRecord:
    target = preparation.context.target
    target_attribute = next(
        item for item in target.attributes if item.attribute_id == existing.target_attribute_id
    )
    modeled_attribute = next(
        item
        for item in header.modeled_entity.attributes
        if item.attribute_id == existing.modeled_attribute_id
    )
    return MappingAttributeRecord(
        tenant_code=target.tenant_code,
        system_code=target.system_code,
        connection_code=target.connection_code,
        object_schema=target.object_schema,
        object_name=target.object_name,
        attribute_name=target_attribute.attribute_name,
        source_system_code=preparation.context.source_system.system_code,
        modeled_entity_type=preparation.plan.modeled_entity_type,
        modeled_entity_name=header.modeled_entity.entity_name,
        modeled_attribute_name=modeled_attribute.attribute_name,
        attribute_mapping_transformation_document=cast(
            dict[str, object] | None,
            existing.transformation_document,
        ),
        attribute_mapping_status=existing.status,
        attribute_mapping_is_locked=existing.is_locked,
    )


def _validate_records(
    dataset: Literal["mapping_object", "mapping_attribute"],
    documents: list[dict[str, object]],
) -> list[dict[str, object]]:
    records, issues = validate_staged_records(dataset, documents)
    if issues or len(records) != len(documents):
        raise InvalidRequestError("Mapping reconciliation failed shared record validation.")
    return [cast(dict[str, object], item.model_dump(mode="json")) for item in records]


def _revalidate_normalized_inputs(
    header: NormalizedMappingHeaderCandidate,
    batches: Sequence[NormalizedMappingAttributeBatch],
) -> tuple[
    NormalizedMappingHeaderCandidate,
    tuple[NormalizedMappingAttributeBatch, ...],
]:
    try:
        normalized_header = NormalizedMappingHeaderCandidate.model_validate(
            header.model_dump(mode="python"),
            strict=True,
        )
        normalized_batches = tuple(
            NormalizedMappingAttributeBatch.model_validate(
                item.model_dump(mode="python"),
                strict=True,
            )
            for item in batches
        )
    except AttributeError, TypeError, ValueError, ValidationError:
        raise InvalidRequestError(
            "Mapping reconciliation failed normalized candidate validation."
        ) from None
    return normalized_header, normalized_batches


def _revalidate_attribute_semantics(
    *,
    preparation: MappingPreparation,
    package: MappingPackageDocumentV1,
    plan: MappingAttributeBatchPlan,
    batch: NormalizedMappingAttributeBatch,
) -> None:
    document = cast(
        JsonValue,
        {
            **batch.model_dump(mode="json"),
            "coverage": {
                "expected_target_attribute_ids": list(plan.expected_target_attribute_ids),
                "returned_target_attribute_ids": list(plan.expected_target_attribute_ids),
                "expected_existing_mapping_attribute_ids": list(
                    plan.expected_existing_mapping_attribute_ids
                ),
                "returned_existing_mapping_attribute_ids": list(
                    plan.expected_existing_mapping_attribute_ids
                ),
            },
        },
    )
    try:
        validator = MappingAttributeCandidateValidator(
            preparation=preparation,
            package=package,
            batch_plan=plan,
        )
        validated = validator.parse_validated(document)
    except InvalidRequestError, ValueError:
        raise InvalidRequestError(
            "Mapping reconciliation Attribute semantic validation failed."
        ) from None
    if validated != batch:
        raise InvalidRequestError("Mapping reconciliation Attribute semantic validation failed.")


def _revalidate_header_semantics(
    *,
    preparation: MappingPreparation,
    header: NormalizedMappingHeaderCandidate,
) -> None:
    document = cast(
        JsonValue,
        {
            "schema_version": header.schema_version,
            "package": header.package.model_dump(mode="json"),
            "headers": [item.model_dump(mode="json") for item in header.headers],
            "coverage": {
                "expected_mapping_object_ids": list(header.coverage.expected_mapping_object_ids),
                "returned_mapping_object_ids": list(header.coverage.returned_mapping_object_ids),
            },
        },
    )
    try:
        validated = MappingHeaderCandidateValidator(preparation=preparation).parse_validated(
            document
        )
    except InvalidRequestError:
        raise InvalidRequestError(
            "Mapping reconciliation Header semantic validation failed."
        ) from None
    if validated != header:
        raise InvalidRequestError("Mapping reconciliation Header semantic validation failed.")
