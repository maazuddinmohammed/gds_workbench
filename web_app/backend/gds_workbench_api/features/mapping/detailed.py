"""Bounded Mapping detailed-stage context and deterministic draft review."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from copy import deepcopy
from typing import Literal, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator

from gds_workbench_api.features.workflows.authoring.context import (
    reject_forbidden_provider_json,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentContextTooLargeError,
    AgentValidationIssue,
    pydantic_validation_issues,
)

from .attribute_candidate import MappingAttributeBatchPlan
from .candidate import NormalizedMappingHeaderCandidate
from .preparation_contracts import (
    MappingModeledAttribute,
    MappingPhysicalAttribute,
    MappingPhysicalObject,
    MappingPreparation,
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MappingDetailedBatchReview(_FrozenModel):
    chunk_index: int = Field(ge=1, le=100)
    coverage_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_attribute_count: int = Field(ge=1, le=100)
    existing_mapping_attribute_count: int = Field(ge=0, le=500)
    expected_target_attribute_ids: tuple[int, ...] = Field(
        min_length=1,
        max_length=100,
    )
    expected_existing_mapping_attribute_ids: tuple[int, ...] = Field(max_length=500)

    @field_validator(
        "expected_target_attribute_ids",
        "expected_existing_mapping_attribute_ids",
        mode="before",
    )
    @classmethod
    def normalize_id_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(cast(list[object], value))
        if isinstance(value, tuple):
            return cast(tuple[object, ...], value)
        raise ValueError("Mapping review IDs must be a JSON array")


class MappingDetailedReviewManifest(_FrozenModel):
    schema_version: Literal["1.0"] = "1.0"
    header_candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    draft_candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    chunk_count: int = Field(ge=1, le=100)
    batches: tuple[MappingDetailedBatchReview, ...] = Field(
        min_length=1,
        max_length=100,
    )

    @field_validator("batches", mode="before")
    @classmethod
    def normalize_json_array(
        cls,
        value: object,
    ) -> object:
        if isinstance(value, list):
            return tuple(cast(list[object], value))
        if isinstance(value, tuple):
            return cast(tuple[object, ...], value)
        raise ValueError("Mapping review batches must be a JSON array")


class MappingDetailedTargetReviewValidator:
    """Require the reviewer to return the exact bounded draft manifest."""

    def __init__(self, *, manifest: MappingDetailedReviewManifest) -> None:
        self._manifest = manifest

    def output_schema(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            deepcopy(MappingDetailedReviewManifest.model_json_schema()),
        )

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        try:
            parsed = MappingDetailedReviewManifest.model_validate(candidate, strict=True)
        except ValidationError as error:
            diagnostic = pydantic_validation_issues(error, maximum_issues=1)[0]
            return AgentCandidateValidation(
                issues=(
                    AgentValidationIssue(
                        code="candidate.review_manifest_mismatch",
                        path=diagnostic.path,
                        message=diagnostic.message,
                    ),
                )
            )
        if parsed != self._manifest:
            return AgentCandidateValidation(
                issues=(
                    AgentValidationIssue(
                        code="candidate.review_manifest_mismatch",
                        path=(),
                        message="The Mapping review receipt does not match the frozen draft.",
                    ),
                )
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> MappingDetailedReviewManifest:
        try:
            parsed = MappingDetailedReviewManifest.model_validate(candidate, strict=True)
        except ValidationError:
            raise InvalidRequestError("The Mapping target review receipt is invalid.") from None
        if parsed != self._manifest:
            raise InvalidRequestError("The Mapping target review receipt is invalid.")
        return parsed


def build_mapping_header_stage_context(
    *,
    preparation: MappingPreparation,
    maximum_bytes: int,
) -> JsonValue:
    """Project only package/header evidence; never embed Attribute inventories."""

    plan = preparation.plan
    context = preparation.context
    header_rows: list[JsonValue] = []
    preserved_packages: dict[str, JsonValue] = {}
    for header in context.headers:
        package = header.mapping_package_document
        if package is not None and header.mapping_package_digest is not None:
            preserved_packages[header.mapping_package_digest] = cast(
                JsonValue,
                deepcopy(package),
            )
        header_rows.append(
            cast(
                JsonValue,
                {
                    "mapping_object_id": header.mapping_object_id,
                    "modeled_entity": {
                        "entity_id": header.modeled_entity.entity_id,
                        "entity_name": header.modeled_entity.entity_name,
                        "entity_kind": header.modeled_entity.entity_kind,
                        "dependency_order": header.modeled_entity.dependency_order,
                        "status": header.modeled_entity.status,
                        "is_locked": header.modeled_entity.is_locked,
                    },
                    "object_dependency_order": header.object_dependency_order,
                    "artifact_type": header.artifact_type,
                    "profile": (
                        None if header.profile is None else header.profile.model_dump(mode="json")
                    ),
                    "mapping_package_digest": header.mapping_package_digest,
                    "status": header.status,
                    "is_locked": header.is_locked,
                    "output_template_id": header.output_template_id,
                },
            )
        )
    source_rows = [
        cast(
            JsonValue,
            {
                "source_mapping_id": source.source_mapping_id,
                "modeled_entity_id": source.modeled_entity_id,
                "role": source.role,
                "mapping_order": source.mapping_order,
                "is_locked": source.is_locked,
                "object": _compact_physical_object(source.object, attributes=()),
            },
        )
        for source in context.sources
    ]
    source_ids = {
        plan.pair.source_system_id,
        *(
            edge.predecessor_source_system_id
            for edge in context.dependency_graph.edges
            if edge.successor_source_system_id == plan.pair.source_system_id
        ),
    }
    target_ids = {
        plan.pair.target_object_id,
        *(
            edge.predecessor_target_object_id
            for edge in context.target_dependency_graph.edges
            if edge.successor_target_object_id == plan.pair.target_object_id
        ),
    }
    stage_context = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "run": _mapping_run(preparation),
            "source_system": context.source_system.model_dump(mode="json"),
            "source_system_dependency": context.dependency.model_dump(mode="json"),
            "source_system_dependency_graph": {
                "nodes": [
                    node.model_dump(mode="json")
                    for node in context.dependency_graph.nodes
                    if node.source_system_id in source_ids
                ],
                "edges": [
                    edge.model_dump(mode="json")
                    for edge in context.dependency_graph.edges
                    if edge.successor_source_system_id == plan.pair.source_system_id
                ],
            },
            "target_dependency_graph": {
                "nodes": [
                    node.model_dump(mode="json")
                    for node in context.target_dependency_graph.nodes
                    if node.target_object_id in target_ids
                ],
                "edges": [
                    edge.model_dump(mode="json")
                    for edge in context.target_dependency_graph.edges
                    if edge.successor_target_object_id == plan.pair.target_object_id
                ],
            },
            "target": _compact_physical_object(context.target, attributes=()),
            "sources": source_rows,
            "headers": header_rows,
            "preserved_mapping_packages": [
                preserved_packages[digest] for digest in sorted(preserved_packages)
            ],
            "authoring": context.authoring.model_dump(mode="json"),
            "readiness": {
                "package_action": preparation.readiness.package_action,
                "headers": [
                    {
                        "mapping_object_id": header.mapping_object_id,
                        "action": header.action,
                    }
                    for header in preparation.readiness.headers
                ],
            },
        },
    )
    _validate_stage_context(stage_context, maximum_bytes=maximum_bytes)
    return stage_context


def build_mapping_attribute_stage_context(
    *,
    preparation: MappingPreparation,
    header: NormalizedMappingHeaderCandidate,
    batch_plan: MappingAttributeBatchPlan,
    maximum_bytes: int,
) -> JsonValue:
    """Project exact target coverage and the largest deterministic evidence prefix."""

    expected_targets = set(batch_plan.expected_target_attribute_ids)
    expected_existing = set(batch_plan.expected_existing_mapping_attribute_ids)
    target_attributes = tuple(
        attribute
        for attribute in preparation.context.target.attributes
        if attribute.attribute_id in expected_targets
    )
    if {item.attribute_id for item in target_attributes} != expected_targets:
        raise InvalidRequestError("The Mapping Attribute batch target coverage is unavailable.")
    target_names = {item.attribute_name.casefold() for item in target_attributes}

    relevant_existing_by_header: dict[int, list[JsonValue]] = {}
    readiness_actions = {
        child.mapping_attribute_id: child.action
        for readiness in preparation.readiness.headers
        for child in readiness.attribute_actions
    }
    relevant_mapping_attribute_ids: set[int] = set()
    required_modeled_ids: set[int] = set()
    for existing_header in preparation.context.headers:
        for child in existing_header.attribute_mappings:
            if (
                child.mapping_attribute_id in expected_existing
                or child.target_attribute_id in expected_targets
            ):
                relevant_mapping_attribute_ids.add(child.mapping_attribute_id)
                required_modeled_ids.add(child.modeled_attribute_id)
                relevant_existing_by_header.setdefault(
                    existing_header.mapping_object_id,
                    [],
                ).append(
                    cast(
                        JsonValue,
                        {
                            "mapping_attribute_id": child.mapping_attribute_id,
                            "modeled_attribute_id": child.modeled_attribute_id,
                            "target_attribute_id": child.target_attribute_id,
                            "has_transformation_document": (
                                child.transformation_document is not None
                            ),
                            "readiness_action": readiness_actions.get(child.mapping_attribute_id),
                            "status": child.status,
                            "is_locked": child.is_locked,
                            "output_template_id": child.output_template_id,
                        },
                    )
                )

    modeled_records: list[tuple[int, int, MappingModeledAttribute, JsonValue]] = []
    header_rows: dict[int, dict[str, JsonValue]] = {}
    for existing_header in preparation.context.headers:
        entity = existing_header.modeled_entity
        header_rows[existing_header.mapping_object_id] = {
            "mapping_object_id": existing_header.mapping_object_id,
            "modeled_entity": {
                "entity_id": entity.entity_id,
                "entity_name": entity.entity_name,
                "entity_kind": entity.entity_kind,
                "dependency_order": entity.dependency_order,
                "status": entity.status,
                "is_locked": entity.is_locked,
                "attributes": [],
            },
            "status": existing_header.status,
            "is_locked": existing_header.is_locked,
            "attribute_mappings": relevant_existing_by_header.get(
                existing_header.mapping_object_id,
                [],
            ),
        }
        relevant = [
            item
            for item in entity.attributes
            if item.attribute_id in required_modeled_ids
            or item.attribute_name.casefold() in target_names
        ]
        if not relevant:
            relevant = [
                item for item in entity.attributes if item.status == "active" and not item.is_locked
            ][:1]
        for item in relevant:
            priority = 0 if item.attribute_id in required_modeled_ids else 1
            modeled_records.append(
                (
                    priority,
                    existing_header.mapping_object_id,
                    item,
                    cast(
                        JsonValue,
                        {
                            "attribute_id": item.attribute_id,
                            "attribute_name": item.attribute_name,
                            "attribute_data_type": item.attribute_data_type,
                            "is_nullable": item.is_nullable,
                            "ordinal_position": item.ordinal_position,
                            "is_audit_column": item.is_audit_column,
                            "status": item.status,
                            "is_locked": item.is_locked,
                        },
                    ),
                )
            )

    modeled_names = {
        item.attribute_name.casefold() for _priority, _parent_id, item, _value in modeled_records
    }
    source_records: list[tuple[int, int, MappingPhysicalAttribute, JsonValue]] = []
    source_rows: dict[int, dict[str, JsonValue]] = {}
    for source in preparation.context.sources:
        source_rows[source.source_mapping_id] = {
            "source_mapping_id": source.source_mapping_id,
            "modeled_entity_id": source.modeled_entity_id,
            "role": source.role,
            "mapping_order": source.mapping_order,
            "is_locked": source.is_locked,
            "object": _compact_physical_object(source.object, attributes=()),
        }
        relevant = [
            item
            for item in source.object.attributes
            if item.is_active and item.attribute_name.casefold() in target_names | modeled_names
        ]
        if not relevant:
            relevant = [item for item in source.object.attributes if item.is_active][:1]
        for item in relevant:
            source_records.append(
                (
                    1,
                    source.source_mapping_id,
                    item,
                    cast(JsonValue, _compact_physical_attribute(item)),
                )
            )

    evidence = sorted(
        [
            (priority, "modeled", parent_id, item.attribute_id, value)
            for priority, parent_id, item, value in modeled_records
        ]
        + [
            (priority, "source", parent_id, item.attribute_id, value)
            for priority, parent_id, item, value in source_records
        ],
        key=lambda item: (item[0], item[1], item[2], item[3]),
    )
    mandatory_count = sum(1 for item in evidence if item[0] == 0)

    def context_for(record_count: int) -> JsonValue:
        selected_headers = deepcopy(header_rows)
        selected_sources = deepcopy(source_rows)
        for _priority, kind, parent_id, _attribute_id, value in evidence[:record_count]:
            if kind == "modeled":
                entity = cast(dict[str, JsonValue], selected_headers[parent_id]["modeled_entity"])
                cast(list[JsonValue], entity["attributes"]).append(deepcopy(value))
            else:
                physical = cast(dict[str, JsonValue], selected_sources[parent_id]["object"])
                cast(list[JsonValue], physical["attributes"]).append(deepcopy(value))
        return cast(
            JsonValue,
            {
                "schema_version": "1.0",
                "mapping_context": {
                    "run": _mapping_run(preparation),
                    "target": _compact_physical_object(
                        preparation.context.target,
                        attributes=tuple(target_attributes),
                    ),
                    "sources": list(selected_sources.values()),
                    "headers": list(selected_headers.values()),
                    "readiness": {
                        "headers": [
                            {
                                "mapping_object_id": readiness.mapping_object_id,
                                "action": readiness.action,
                                "attribute_actions": [
                                    child.model_dump(mode="json")
                                    for child in readiness.attribute_actions
                                    if child.mapping_attribute_id in relevant_mapping_attribute_ids
                                ],
                            }
                            for readiness in preparation.readiness.headers
                        ]
                    },
                    "evidence_manifest": {
                        "candidate_record_count": len(evidence),
                        "included_record_count": record_count,
                        "candidate_digest": _json_digest(
                            cast(
                                JsonValue,
                                [
                                    {
                                        "priority": item[0],
                                        "kind": item[1],
                                        "parent_id": item[2],
                                        "attribute_id": item[3],
                                        "record": item[4],
                                    }
                                    for item in evidence
                                ],
                            )
                        ),
                        "included_digest": _json_digest(
                            cast(
                                JsonValue,
                                [
                                    {
                                        "priority": item[0],
                                        "kind": item[1],
                                        "parent_id": item[2],
                                        "attribute_id": item[3],
                                        "record": item[4],
                                    }
                                    for item in evidence[:record_count]
                                ],
                            )
                        ),
                    },
                },
                "validated_header": {
                    "package": {
                        "schema_version": header.package.schema_version,
                        "package_ref": header.package.package_ref,
                        "route": header.package.route,
                        "target_object_id": header.package.target_object_id,
                        "source_system_id": header.package.source_system_id,
                        "executable_sources": [
                            {
                                "object_id": source.object_id,
                                "alias": source.alias,
                            }
                            for source in header.package.executable_sources
                        ],
                        "step_outputs": [step.output for step in header.package.steps],
                    },
                    "package_digest": header.package_digest,
                },
                "batch_plan": batch_plan.model_dump(mode="json"),
            },
        )

    minimum = context_for(mandatory_count)
    _validate_stage_context(minimum, maximum_bytes=maximum_bytes)
    low = mandatory_count
    high = len(evidence)
    accepted = minimum
    while low <= high:
        record_count = (low + high) // 2
        candidate = context_for(record_count)
        if _repair_envelope_size(candidate) <= maximum_bytes:
            accepted = candidate
            low = record_count + 1
        else:
            high = record_count - 1
    reject_forbidden_provider_json(
        accepted,
        allow_identity_keys=True,
        reject_sensitive_values=True,
    )
    return accepted


def build_mapping_detailed_review_manifest(
    *,
    header_candidate: JsonValue,
    header: NormalizedMappingHeaderCandidate,
    batch_plans: Sequence[MappingAttributeBatchPlan],
    raw_batches: Sequence[JsonValue],
) -> MappingDetailedReviewManifest:
    if not batch_plans or any(
        plan.package_ref != header.package.package_ref
        or plan.package_digest != header.package_digest
        for plan in batch_plans
    ):
        raise InvalidRequestError("The Mapping draft batch package identity is invalid.")
    indexed = _index_raw_batches(raw_batches)
    expected_indexes = [plan.chunk_index for plan in batch_plans]
    if sorted(indexed) != expected_indexes:
        raise InvalidRequestError("The Mapping draft does not contain every Attribute batch once.")
    reviews: list[MappingDetailedBatchReview] = []
    ordered_batches: list[JsonValue] = []
    for plan in batch_plans:
        raw = indexed[plan.chunk_index]
        if (
            raw.get("chunk_count") != plan.chunk_count
            or raw.get("package_digest") != plan.package_digest
            or raw.get("coverage_manifest_digest") != plan.coverage_manifest_digest
        ):
            raise InvalidRequestError("The Mapping draft batch identity is invalid.")
        reviews.append(
            MappingDetailedBatchReview(
                chunk_index=plan.chunk_index,
                coverage_manifest_digest=plan.coverage_manifest_digest,
                candidate_digest=_json_digest(cast(JsonValue, raw)),
                target_attribute_count=len(plan.expected_target_attribute_ids),
                existing_mapping_attribute_count=len(plan.expected_existing_mapping_attribute_ids),
                expected_target_attribute_ids=plan.expected_target_attribute_ids,
                expected_existing_mapping_attribute_ids=(
                    plan.expected_existing_mapping_attribute_ids
                ),
            )
        )
        ordered_batches.append(cast(JsonValue, raw))
    draft = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "header": header_candidate,
            "attribute_batches": ordered_batches,
        },
    )
    return MappingDetailedReviewManifest(
        header_candidate_digest=_json_digest(header_candidate),
        package_digest=batch_plans[0].package_digest,
        draft_candidate_digest=_json_digest(draft),
        chunk_count=len(batch_plans),
        batches=tuple(reviews),
    )


def build_mapping_target_review_context(
    *,
    manifest: MappingDetailedReviewManifest,
    maximum_bytes: int,
) -> JsonValue:
    context = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "review_manifest": manifest.model_dump(mode="json"),
        },
    )
    _validate_stage_context(context, maximum_bytes=maximum_bytes)
    return context


def merge_mapping_detailed_candidate(
    *,
    header_candidate: JsonValue,
    batch_plans: Sequence[MappingAttributeBatchPlan],
    raw_batches: Sequence[JsonValue],
) -> JsonValue:
    indexed = _index_raw_batches(raw_batches)
    expected_indexes = [plan.chunk_index for plan in batch_plans]
    if sorted(indexed) != expected_indexes:
        raise InvalidRequestError("The Mapping draft does not contain every Attribute batch once.")
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "header": deepcopy(header_candidate),
            "attribute_batches": [
                deepcopy(cast(JsonValue, indexed[index])) for index in expected_indexes
            ],
        },
    )


def _mapping_run(preparation: MappingPreparation) -> JsonValue:
    plan = preparation.plan
    return cast(
        JsonValue,
        {
            "workflow_run_id": plan.workflow_run_id,
            "model_id": plan.model_id,
            "model_revision": plan.model_revision,
            "correlation_id": str(plan.correlation_id),
            "modeled_entity_type": plan.modeled_entity_type,
            "pair": plan.pair.model_dump(mode="json"),
            "operation": plan.operation,
            "coverage_mode": plan.coverage_mode,
            "route": plan.route,
            "artifact_type": plan.artifact_type,
            "profile": plan.profile.model_dump(mode="json"),
            "output_template_selections": (plan.output_template_selections.model_dump(mode="json")),
        },
    )


def _compact_physical_object(
    value: MappingPhysicalObject,
    *,
    attributes: Sequence[MappingPhysicalAttribute],
) -> dict[str, JsonValue]:
    document = cast(dict[str, JsonValue], value.model_dump(mode="json"))
    document["attributes"] = [
        cast(JsonValue, _compact_physical_attribute(item)) for item in attributes
    ]
    document.pop("object_description", None)
    return document


def _compact_physical_attribute(value: MappingPhysicalAttribute) -> dict[str, JsonValue]:
    document = cast(dict[str, JsonValue], value.model_dump(mode="json"))
    document.pop("attribute_description", None)
    return document


def _index_raw_batches(raw_batches: Sequence[JsonValue]) -> dict[int, dict[str, JsonValue]]:
    indexed: dict[int, dict[str, JsonValue]] = {}
    for raw in raw_batches:
        if not isinstance(raw, dict):
            raise InvalidRequestError("The Mapping draft Attribute batch is invalid.")
        document = cast(dict[str, JsonValue], raw)
        chunk_index = document.get("chunk_index")
        if (
            isinstance(chunk_index, bool)
            or not isinstance(chunk_index, int)
            or chunk_index in indexed
        ):
            raise InvalidRequestError("The Mapping draft Attribute batch is invalid.")
        indexed[chunk_index] = document
    return indexed


def _validate_stage_context(value: JsonValue, *, maximum_bytes: int) -> None:
    reject_forbidden_provider_json(
        value,
        allow_identity_keys=True,
        reject_sensitive_values=True,
    )
    if _repair_envelope_size(value) > maximum_bytes:
        raise AgentContextTooLargeError()


def _repair_envelope_size(value: JsonValue) -> int:
    return _json_size(cast(JsonValue, {"original_context": value, "repair": None}))


def _json_digest(value: JsonValue) -> str:
    return hashlib.sha256(_json_data(value)).hexdigest()


def _json_size(value: JsonValue) -> int:
    return len(_json_data(value))


def _json_data(value: JsonValue) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise InvalidRequestError("The Mapping detailed context is invalid.") from None


__all__ = [
    "MappingDetailedReviewManifest",
    "MappingDetailedTargetReviewValidator",
    "build_mapping_attribute_stage_context",
    "build_mapping_detailed_review_manifest",
    "build_mapping_header_stage_context",
    "build_mapping_target_review_context",
    "merge_mapping_detailed_candidate",
]
