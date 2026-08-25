"""Plan and validate bounded Attribute Mapper batches without persistence."""

from __future__ import annotations

import hashlib
from copy import deepcopy
from typing import Literal, Self

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.mapping_contracts import (
    Identifier,
    LowerHexDigest,
    MappingContractModel,
    MappingPackageDocumentV1,
    OptionalOrdinaryText,
    PositiveDatabaseId,
)
from gds_etl_workbench.domain.mapping_profiles import (
    canonical_mapping_json_bytes,
    mapping_package_digest,
)
from pydantic import Field, JsonValue, ValidationError, field_validator, model_validator

from gds_workbench_api.features.mapping.output_schema import (
    MappingTransformationDocumentError,
    compile_attribute_mapper_output_schema,
    validate_mapping_transformation_document,
)
from gds_workbench_api.features.mapping.preparation_contracts import (
    MappingOutputTemplate,
    MappingPreparation,
    MappingSource,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
)

_MAX_TARGET_ATTRIBUTES_PER_CHUNK = 100
_MAX_EXISTING_BINDINGS_PER_CHUNK = 500
_MAX_CHUNKS = 100


class MappingAttributeBatchPlan(MappingContractModel):
    """Immutable coverage manifest for one Attribute Mapper call."""

    schema_version: Literal["1.0"] = "1.0"
    package_ref: Identifier
    target_object_id: PositiveDatabaseId
    source_system_id: PositiveDatabaseId
    chunk_index: int = Field(ge=1, le=_MAX_CHUNKS)
    chunk_count: int = Field(ge=1, le=_MAX_CHUNKS)
    package_digest: LowerHexDigest
    coverage_manifest_digest: LowerHexDigest
    expected_target_attribute_ids: tuple[PositiveDatabaseId, ...] = Field(
        min_length=1,
        max_length=_MAX_TARGET_ATTRIBUTES_PER_CHUNK,
    )
    expected_existing_mapping_attribute_ids: tuple[PositiveDatabaseId, ...] = Field(
        max_length=_MAX_EXISTING_BINDINGS_PER_CHUNK
    )


class _AgentAttributeMapping(MappingContractModel):
    mapping_object_id: PositiveDatabaseId
    mapping_attribute_id: PositiveDatabaseId | None = None
    local_ref: Identifier | None = None
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    logical_attribute_id: PositiveDatabaseId | None = None
    dimensional_attribute_id: PositiveDatabaseId | None = None
    target_attribute_id: PositiveDatabaseId
    disposition: Literal["create", "update"]
    transformation: JsonValue

    @model_validator(mode="after")
    def validate_identity_shape(self) -> Self:
        if (self.mapping_attribute_id is None) == (self.local_ref is None):
            raise ValueError("Exactly one existing ID or new local reference is required")
        logical = self.logical_attribute_id is not None
        dimensional = self.dimensional_attribute_id is not None
        if logical == dimensional or logical != (self.modeled_entity_type == "logical_entity"):
            raise ValueError("Exactly one typed modeled Attribute is required")
        if (self.disposition == "create") != (self.local_ref is not None):
            raise ValueError("Create is reserved for new local references")
        return self

    @property
    def modeled_attribute_id(self) -> int:
        value = self.logical_attribute_id or self.dimensional_attribute_id
        if value is None:  # Guarded by validate_identity_shape.
            raise ValueError("The modeled Attribute ID is unavailable")
        return value


class _AgentTargetDisposition(MappingContractModel):
    target_attribute_id: PositiveDatabaseId
    disposition: Literal["mapped", "already_mapped", "intentionally_unmapped"]
    reason: OptionalOrdinaryText

    @model_validator(mode="after")
    def validate_reason(self) -> Self:
        if (self.reason is not None) != (self.disposition == "intentionally_unmapped"):
            raise ValueError("Only intentionally-unmapped targets require a reason")
        return self


class _AgentAttributeCoverage(MappingContractModel):
    expected_target_attribute_ids: list[PositiveDatabaseId] = Field(
        min_length=1,
        max_length=500,
    )
    returned_target_attribute_ids: list[PositiveDatabaseId] = Field(
        min_length=1,
        max_length=500,
    )
    expected_existing_mapping_attribute_ids: list[PositiveDatabaseId] = Field(max_length=500)
    returned_existing_mapping_attribute_ids: list[PositiveDatabaseId] = Field(max_length=500)

    @field_validator(
        "expected_target_attribute_ids",
        "returned_target_attribute_ids",
        "expected_existing_mapping_attribute_ids",
        "returned_existing_mapping_attribute_ids",
    )
    @classmethod
    def normalize_ids(cls, values: list[int]) -> list[int]:
        if len(values) != len(set(values)):
            raise ValueError("Attribute coverage IDs must be unique")
        return sorted(values)


class _AgentAttributeEnvelope(MappingContractModel):
    schema_version: Literal["1.0"]
    package_ref: Identifier
    target_object_id: PositiveDatabaseId
    source_system_id: PositiveDatabaseId
    chunk_index: int = Field(ge=1, le=100)
    chunk_count: int = Field(ge=1, le=100)
    package_digest: LowerHexDigest
    coverage_manifest_digest: LowerHexDigest
    attribute_mappings: list[_AgentAttributeMapping] = Field(max_length=500)
    target_attribute_dispositions: list[_AgentTargetDisposition] = Field(max_length=500)
    coverage: _AgentAttributeCoverage

    @field_validator("attribute_mappings")
    @classmethod
    def normalize_attribute_mappings(
        cls,
        values: list[_AgentAttributeMapping],
    ) -> list[_AgentAttributeMapping]:
        return sorted(
            values,
            key=lambda item: (
                item.target_attribute_id,
                item.mapping_object_id,
                item.mapping_attribute_id or 0,
                item.local_ref or "",
            ),
        )

    @field_validator("target_attribute_dispositions")
    @classmethod
    def normalize_dispositions(
        cls,
        values: list[_AgentTargetDisposition],
    ) -> list[_AgentTargetDisposition]:
        return sorted(values, key=lambda item: item.target_attribute_id)


class NormalizedMappingAttribute(MappingContractModel):
    mapping_object_id: int = Field(gt=0)
    mapping_attribute_id: int | None = Field(default=None, gt=0)
    local_ref: str | None = Field(default=None)
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
    logical_attribute_id: int | None = Field(default=None, gt=0)
    dimensional_attribute_id: int | None = Field(default=None, gt=0)
    target_attribute_id: int = Field(gt=0)
    disposition: Literal["create", "update"]
    transformation: dict[str, JsonValue]


class NormalizedTargetAttributeDisposition(MappingContractModel):
    target_attribute_id: int = Field(gt=0)
    disposition: Literal["mapped", "already_mapped", "intentionally_unmapped"]
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)


class NormalizedMappingAttributeBatch(MappingContractModel):
    schema_version: Literal["1.0"] = "1.0"
    package_ref: str
    target_object_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    chunk_index: int = Field(ge=1, le=100)
    chunk_count: int = Field(ge=1, le=100)
    package_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    coverage_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attribute_mappings: tuple[NormalizedMappingAttribute, ...] = Field(max_length=500)
    target_attribute_dispositions: tuple[NormalizedTargetAttributeDisposition, ...] = Field(
        max_length=500
    )


def build_mapping_attribute_batch_plans(
    *,
    preparation: MappingPreparation,
    package: MappingPackageDocumentV1,
) -> tuple[MappingAttributeBatchPlan, ...]:
    """Partition exact active target coverage into deterministic bounded chunks."""

    _validate_preparation_and_package(preparation, package)
    actionable_ids = _actionable_existing_ids(preparation)
    existing_by_target: dict[int, list[int]] = {}
    for header in preparation.context.headers:
        for child in header.attribute_mappings:
            if child.mapping_attribute_id in actionable_ids:
                existing_by_target.setdefault(child.target_attribute_id, []).append(
                    child.mapping_attribute_id
                )

    target_ids = [
        item.attribute_id
        for item in sorted(
            preparation.context.target.attributes,
            key=lambda item: (item.attribute_ordinal_position, item.attribute_id),
        )
        if item.is_active
    ]
    if not target_ids:
        raise ValueError("The ready Mapping preparation has no active target Attributes.")

    groups: list[tuple[list[int], list[int]]] = []
    group_targets: list[int] = []
    group_existing: list[int] = []
    for target_id in target_ids:
        target_existing = sorted(existing_by_target.get(target_id, ()))
        if len(target_existing) > _MAX_EXISTING_BINDINGS_PER_CHUNK:
            raise ValueError("One target Attribute exceeds the Mapping batch limit.")
        if group_targets and (
            len(group_targets) >= _MAX_TARGET_ATTRIBUTES_PER_CHUNK
            or len(group_existing) + len(target_existing) > _MAX_EXISTING_BINDINGS_PER_CHUNK
        ):
            groups.append((sorted(group_targets), sorted(group_existing)))
            group_targets = []
            group_existing = []
        group_targets.append(target_id)
        group_existing.extend(target_existing)
    groups.append((sorted(group_targets), sorted(group_existing)))
    if len(groups) > _MAX_CHUNKS:
        raise ValueError("Mapping Attribute coverage exceeds 100 bounded chunks.")

    digest = mapping_package_digest(package.model_dump(mode="json"))
    chunk_count = len(groups)
    plans: list[MappingAttributeBatchPlan] = []
    for chunk_index, (expected_targets, expected_existing) in enumerate(groups, 1):
        manifest = {
            "schema_version": "1.0",
            "package_ref": package.package_ref,
            "target_object_id": package.target_object_id,
            "source_system_id": package.source_system_id,
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "package_digest": digest,
            "expected_target_attribute_ids": expected_targets,
            "expected_existing_mapping_attribute_ids": expected_existing,
        }
        manifest_digest = hashlib.sha256(canonical_mapping_json_bytes(manifest)).hexdigest()
        plans.append(
            MappingAttributeBatchPlan(
                package_ref=package.package_ref,
                target_object_id=package.target_object_id,
                source_system_id=package.source_system_id,
                chunk_index=chunk_index,
                chunk_count=chunk_count,
                package_digest=digest,
                coverage_manifest_digest=manifest_digest,
                expected_target_attribute_ids=tuple(expected_targets),
                expected_existing_mapping_attribute_ids=tuple(expected_existing),
            )
        )
    return tuple(plans)


class MappingAttributeCandidateValidator:
    """Validate one exact Attribute Mapper chunk against immutable context."""

    def __init__(
        self,
        *,
        preparation: MappingPreparation,
        package: MappingPackageDocumentV1,
        batch_plan: MappingAttributeBatchPlan,
    ) -> None:
        expected_plans = build_mapping_attribute_batch_plans(
            preparation=preparation,
            package=package,
        )
        if batch_plan not in expected_plans:
            raise ValueError("The Mapping Attribute batch plan is not frozen context.")
        self._preparation = preparation
        self._package = package
        self._batch_plan = batch_plan
        self._template = _selected_attribute_template(preparation)
        self._headers = {item.mapping_object_id: item for item in preparation.context.headers}
        self._children = {
            child.mapping_attribute_id: (header, child)
            for header in preparation.context.headers
            for child in header.attribute_mappings
        }
        self._actionable_existing_ids = _actionable_existing_ids(preparation)
        self._eligible_new_header_ids = _eligible_new_header_ids(preparation)
        self._preserved_target_ids = _preserved_complete_target_ids(preparation)
        self._source_attributes_by_header = _source_attributes_by_header(
            preparation,
            package,
        )
        self._step_outputs = {item.output for item in package.steps}
        self._validate_source_column_references = _template_supports_reference_field(
            self._template,
            name="source_columns",
            data_type="array",
            array_item_type="object",
        )
        self._validate_step_output_reference = _template_supports_reference_field(
            self._template,
            name="step_output",
            data_type="string",
        )

    def output_schema(self) -> dict[str, JsonValue]:
        return deepcopy(compile_attribute_mapper_output_schema(template=self._template))

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        return AgentCandidateValidation(issues=self._normalize(candidate)[1])

    def parse_validated(self, candidate: JsonValue) -> NormalizedMappingAttributeBatch:
        normalized, issues = self._normalize(candidate)
        if normalized is None or issues:
            raise InvalidRequestError("The Mapping Attribute candidate is invalid.")
        return normalized

    def _normalize(
        self,
        candidate: JsonValue,
    ) -> tuple[
        NormalizedMappingAttributeBatch | None,
        tuple[AgentValidationIssue, ...],
    ]:
        try:
            parsed = _AgentAttributeEnvelope.model_validate(candidate, strict=True)
        except ValidationError:
            return None, (
                _issue(
                    "candidate.schema_invalid",
                    (),
                    "The candidate does not match the Attribute Mapper envelope.",
                ),
            )

        issues: list[AgentValidationIssue] = []
        expected = self._batch_plan
        if (
            parsed.package_ref != expected.package_ref
            or parsed.target_object_id != expected.target_object_id
            or parsed.source_system_id != expected.source_system_id
            or parsed.chunk_index != expected.chunk_index
            or parsed.chunk_count != expected.chunk_count
            or parsed.package_digest != expected.package_digest
            or parsed.coverage_manifest_digest != expected.coverage_manifest_digest
        ):
            issues.append(
                _issue(
                    "candidate.identity_mismatch",
                    (),
                    "The Attribute Mapper batch does not match its immutable manifest.",
                )
            )

        expected_targets = list(expected.expected_target_attribute_ids)
        expected_existing = list(expected.expected_existing_mapping_attribute_ids)
        disposition_ids = [
            item.target_attribute_id for item in parsed.target_attribute_dispositions
        ]
        returned_existing_ids = [
            item.mapping_attribute_id
            for item in parsed.attribute_mappings
            if item.mapping_attribute_id is not None
        ]
        if (
            parsed.coverage.expected_target_attribute_ids != expected_targets
            or parsed.coverage.returned_target_attribute_ids != expected_targets
            or disposition_ids != expected_targets
            or len(disposition_ids) != len(set(disposition_ids))
            or parsed.coverage.expected_existing_mapping_attribute_ids != expected_existing
            or parsed.coverage.returned_existing_mapping_attribute_ids != expected_existing
            or sorted(returned_existing_ids) != expected_existing
            or len(returned_existing_ids) != len(set(returned_existing_ids))
        ):
            issues.append(
                _issue(
                    "candidate.coverage_mismatch",
                    ("coverage",),
                    "Attribute Mapper coverage must exactly equal the frozen manifest.",
                )
            )

        normalized_mappings: list[NormalizedMappingAttribute] = []
        binding_keys: set[tuple[int, int, int]] = set()
        local_refs: set[str] = set()
        mapped_targets: set[int] = set()
        for index, mapping in enumerate(parsed.attribute_mappings):
            path = ("attribute_mappings", index)
            normalized = self._normalize_mapping(mapping, path=path, issues=issues)
            if normalized is None:
                continue
            binding_key = (
                normalized.mapping_object_id,
                normalized.logical_attribute_id or normalized.dimensional_attribute_id or 0,
                normalized.target_attribute_id,
            )
            if binding_key in binding_keys:
                issues.append(
                    _issue(
                        "candidate.binding_duplicate",
                        path,
                        "A Mapping Attribute binding may appear only once.",
                    )
                )
            binding_keys.add(binding_key)
            if normalized.local_ref is not None:
                if normalized.local_ref in local_refs:
                    issues.append(
                        _issue(
                            "candidate.local_ref_duplicate",
                            (*path, "local_ref"),
                            "A new Mapping Attribute local reference may appear only once.",
                        )
                    )
                local_refs.add(normalized.local_ref)
            mapped_targets.add(normalized.target_attribute_id)
            normalized_mappings.append(normalized)

        for index, disposition in enumerate(parsed.target_attribute_dispositions):
            target_id = disposition.target_attribute_id
            path = ("target_attribute_dispositions", index, "disposition")
            if disposition.disposition == "mapped" and target_id not in mapped_targets:
                issues.append(
                    _issue(
                        "candidate.disposition_invalid",
                        path,
                        "Mapped target coverage requires a returned Attribute mapping.",
                    )
                )
            elif disposition.disposition == "already_mapped" and (
                target_id in mapped_targets or target_id not in self._preserved_target_ids
            ):
                issues.append(
                    _issue(
                        "candidate.disposition_invalid",
                        path,
                        "Already-mapped coverage requires an authoritative preserved binding.",
                    )
                )
            elif disposition.disposition == "intentionally_unmapped" and (
                target_id in mapped_targets or target_id in self._preserved_target_ids
            ):
                issues.append(
                    _issue(
                        "candidate.disposition_invalid",
                        path,
                        "A mapped target cannot be marked intentionally unmapped.",
                    )
                )

        normalized_dispositions = tuple(
            NormalizedTargetAttributeDisposition(
                target_attribute_id=item.target_attribute_id,
                disposition=item.disposition,
                reason=item.reason,
            )
            for item in parsed.target_attribute_dispositions
        )
        normalized_batch = NormalizedMappingAttributeBatch(
            package_ref=parsed.package_ref,
            target_object_id=parsed.target_object_id,
            source_system_id=parsed.source_system_id,
            chunk_index=parsed.chunk_index,
            chunk_count=parsed.chunk_count,
            package_digest=parsed.package_digest,
            coverage_manifest_digest=parsed.coverage_manifest_digest,
            attribute_mappings=tuple(
                sorted(
                    normalized_mappings,
                    key=lambda item: (
                        item.target_attribute_id,
                        item.mapping_object_id,
                        item.mapping_attribute_id or 0,
                        item.local_ref or "",
                    ),
                )
            ),
            target_attribute_dispositions=normalized_dispositions,
        )
        return normalized_batch, tuple(issues)

    def _normalize_mapping(
        self,
        mapping: _AgentAttributeMapping,
        *,
        path: tuple[str | int, ...],
        issues: list[AgentValidationIssue],
    ) -> NormalizedMappingAttribute | None:
        if mapping.target_attribute_id not in set(self._batch_plan.expected_target_attribute_ids):
            issues.append(
                _issue(
                    "candidate.target_outside_chunk",
                    (*path, "target_attribute_id"),
                    "The target Attribute is outside this immutable chunk.",
                )
            )
        header = self._headers.get(mapping.mapping_object_id)
        if header is None:
            issues.append(
                _issue(
                    "candidate.header_unknown",
                    (*path, "mapping_object_id"),
                    "The Mapping Object header is unavailable in frozen context.",
                )
            )
            return None
        if mapping.modeled_entity_type != self._preparation.plan.modeled_entity_type:
            issues.append(
                _issue(
                    "candidate.layer_mismatch",
                    (*path, "modeled_entity_type"),
                    "The Mapping Attribute layer differs from the frozen Run.",
                )
            )
        modeled_attributes = {item.attribute_id: item for item in header.modeled_entity.attributes}
        modeled = modeled_attributes.get(mapping.modeled_attribute_id)
        if modeled is None or modeled.status != "active":
            issues.append(
                _issue(
                    "candidate.modeled_attribute_unknown",
                    path,
                    "The modeled Attribute does not resolve in its Mapping header.",
                )
            )

        if mapping.mapping_attribute_id is not None:
            current = self._children.get(mapping.mapping_attribute_id)
            if current is None:
                issues.append(
                    _issue(
                        "candidate.attribute_unknown",
                        (*path, "mapping_attribute_id"),
                        "The existing Mapping Attribute is unavailable.",
                    )
                )
            else:
                existing_header, child = current
                if mapping.mapping_attribute_id not in self._actionable_existing_ids:
                    issues.append(
                        _issue(
                            "candidate.attribute_not_actionable",
                            (*path, "mapping_attribute_id"),
                            "A preserved or locked Mapping Attribute cannot be returned.",
                        )
                    )
                if (
                    existing_header.mapping_object_id != mapping.mapping_object_id
                    or child.modeled_attribute_id != mapping.modeled_attribute_id
                    or child.target_attribute_id != mapping.target_attribute_id
                ):
                    issues.append(
                        _issue(
                            "candidate.binding_repointed",
                            path,
                            "An existing Mapping Attribute binding cannot be repointed.",
                        )
                    )
            if mapping.disposition != "update":
                issues.append(
                    _issue(
                        "candidate.disposition_invalid",
                        (*path, "disposition"),
                        "Actionable existing bindings must be updated.",
                    )
                )
        else:
            if mapping.mapping_object_id not in self._eligible_new_header_ids:
                issues.append(
                    _issue(
                        "candidate.header_not_actionable",
                        (*path, "mapping_object_id"),
                        "The selected header cannot receive a new Mapping Attribute.",
                    )
                )
            if any(
                child.modeled_attribute_id == mapping.modeled_attribute_id
                and child.target_attribute_id == mapping.target_attribute_id
                for child in header.attribute_mappings
            ):
                issues.append(
                    _issue(
                        "candidate.binding_exists",
                        path,
                        "A new local reference cannot replace an existing binding.",
                    )
                )

        try:
            transformation = validate_mapping_transformation_document(
                target_type="mapping_attribute",
                template=self._template,
                document=mapping.transformation,
            )
        except MappingTransformationDocumentError:
            issues.append(
                _issue(
                    "candidate.transformation_invalid",
                    (*path, "transformation"),
                    "The Attribute transformation does not match its frozen schema.",
                )
            )
            return None
        if not self._transformation_references_are_valid(
            mapping_object_id=mapping.mapping_object_id,
            transformation=transformation,
        ):
            issues.append(
                _issue(
                    "candidate.transformation_reference_invalid",
                    (*path, "transformation"),
                    "Transformation source columns or step output do not resolve in context.",
                )
            )

        disposition: Literal["create", "update"] = (
            "create" if mapping.disposition == "create" else "update"
        )
        return NormalizedMappingAttribute(
            mapping_object_id=mapping.mapping_object_id,
            mapping_attribute_id=mapping.mapping_attribute_id,
            local_ref=mapping.local_ref,
            modeled_entity_type=mapping.modeled_entity_type,
            logical_attribute_id=mapping.logical_attribute_id,
            dimensional_attribute_id=mapping.dimensional_attribute_id,
            target_attribute_id=mapping.target_attribute_id,
            disposition=disposition,
            transformation=transformation,
        )

    def _transformation_references_are_valid(
        self,
        *,
        mapping_object_id: int,
        transformation: dict[str, JsonValue],
    ) -> bool:
        source_columns = transformation.get("source_columns")
        if self._validate_source_column_references and source_columns is not None:
            if not isinstance(source_columns, list):
                return False
            allowed_sources = self._source_attributes_by_header.get(
                mapping_object_id,
                {},
            )
            for source_column in source_columns:
                if not isinstance(source_column, dict):
                    return False
                alias = source_column.get("source_alias")
                attribute_id = source_column.get("source_attribute_id")
                if (
                    not isinstance(alias, str)
                    or isinstance(attribute_id, bool)
                    or not isinstance(attribute_id, int)
                    or attribute_id not in allowed_sources.get(alias, set())
                ):
                    return False
        step_output = transformation.get("step_output")
        return (
            not self._validate_step_output_reference
            or step_output is None
            or (isinstance(step_output, str) and step_output in self._step_outputs)
        )


def _validate_preparation_and_package(
    preparation: MappingPreparation,
    package: MappingPackageDocumentV1,
) -> None:
    plan = preparation.plan
    context = preparation.context
    registration = preparation.registration
    if not preparation.readiness.ready:
        raise ValueError("The Mapping preparation must be ready before batching.")
    if (
        context.workflow_run_id != plan.workflow_run_id
        or context.model_id != plan.model_id
        or context.model_revision != plan.model_revision
        or context.correlation_id != plan.correlation_id
        or context.pair != plan.pair
        or context.modeled_entity_type != plan.modeled_entity_type
        or context.route != plan.route
        or context.output_template_selections != plan.output_template_selections
        or registration is None
        or (
            registration.key,
            registration.version,
            registration.schema_digest,
        )
        != (plan.profile.key, plan.profile.version, plan.profile.schema_digest)
        or package.target_object_id != plan.pair.target_object_id
        or package.source_system_id != plan.pair.source_system_id
        or package.route != plan.route
        or package.artifact_type != plan.artifact_type
        or package.pydantic_profile.key != plan.profile.key
        or package.pydantic_profile.version != plan.profile.version
        or package.pydantic_profile.schema_digest != plan.profile.schema_digest
    ):
        raise ValueError("The Mapping package does not match the frozen Header context.")

    expected_source_predecessors = {
        edge.predecessor_source_system_id
        for edge in context.dependency_graph.edges
        if edge.successor_source_system_id == plan.pair.source_system_id
    }
    returned_source_predecessors = {
        dependency.predecessor_source_system_id for dependency in package.source_system_dependencies
    }
    expected_target_predecessors = {
        edge.predecessor_target_object_id
        for edge in context.target_dependency_graph.edges
        if edge.successor_target_object_id == plan.pair.target_object_id
    }
    returned_target_predecessors = {
        dependency.predecessor_target_object_id for dependency in package.target_dependencies
    }
    active_target_attribute_ids = {
        attribute.attribute_id for attribute in context.target.attributes if attribute.is_active
    }
    if (
        returned_source_predecessors != expected_source_predecessors
        or returned_target_predecessors != expected_target_predecessors
        or not set(package.load.merge_keys) <= active_target_attribute_ids
    ):
        raise ValueError("The Mapping package differs from the frozen Header dependency graph.")

    package_digest = mapping_package_digest(package.model_dump(mode="json"))
    readiness_actions = {
        header.mapping_object_id: header.action for header in preparation.readiness.headers
    }
    for header in context.headers:
        if readiness_actions.get(header.mapping_object_id) != "preserve" or not header.is_authored:
            continue
        try:
            stored_digest = mapping_package_digest(header.mapping_package_document)
        except ValueError as exc:
            raise ValueError("A preserved Header package is invalid.") from exc
        if header.mapping_package_digest != package_digest or stored_digest != package_digest:
            raise ValueError("The Mapping package differs from a preserved frozen Header.")

    sources_by_object_id: dict[int, list[MappingSource]] = {}
    for source in context.sources:
        sources_by_object_id.setdefault(source.object.object_id, []).append(source)
    for executable_source in package.executable_sources:
        matching_sources = sources_by_object_id.get(executable_source.object_id, [])
        if not matching_sources:
            raise ValueError("A Mapping package source is outside frozen Header context.")
        batch_rule = executable_source.batch_rule
        if batch_rule is not None and not any(
            source.object.batch_attribute_name is not None
            and any(
                attribute.is_active
                and attribute.attribute_id == batch_rule.attribute_id
                and attribute.attribute_name == source.object.batch_attribute_name
                for attribute in source.object.attributes
            )
            for source in matching_sources
        ):
            raise ValueError("A Mapping package batch rule differs from frozen Header context.")


def _actionable_existing_ids(preparation: MappingPreparation) -> set[int]:
    return {
        child.mapping_attribute_id
        for header in preparation.readiness.headers
        for child in header.attribute_actions
        if child.action in {"author", "extend"}
    }


def _eligible_new_header_ids(preparation: MappingPreparation) -> set[int]:
    readiness = {item.mapping_object_id: item.action for item in preparation.readiness.headers}
    if preparation.plan.operation == "extend":
        return {
            header.mapping_object_id
            for header in preparation.context.headers
            if not header.is_locked and readiness.get(header.mapping_object_id) == "extend"
        }
    return {
        header.mapping_object_id
        for header in preparation.context.headers
        if not header.is_locked
        and readiness.get(header.mapping_object_id) in {"author", "preserve"}
    }


def _preserved_complete_target_ids(preparation: MappingPreparation) -> set[int]:
    actions = {
        child.mapping_attribute_id: child.action
        for header in preparation.readiness.headers
        for child in header.attribute_actions
    }
    return {
        child.target_attribute_id
        for header in preparation.context.headers
        for child in header.attribute_mappings
        if actions.get(child.mapping_attribute_id) == "preserve"
        and child.status == "active"
        and child.transformation_document is not None
    }


def _source_attributes_by_header(
    preparation: MappingPreparation,
    package: MappingPackageDocumentV1,
) -> dict[int, dict[str, set[int]]]:
    aliases_by_object_id: dict[int, set[str]] = {}
    for executable in package.executable_sources:
        aliases_by_object_id.setdefault(executable.object_id, set()).add(executable.alias)

    result: dict[int, dict[str, set[int]]] = {}
    for header in preparation.context.headers:
        aliases: dict[str, set[int]] = {}
        for source in preparation.context.sources:
            if source.modeled_entity_id != header.modeled_entity.entity_id:
                continue
            active_attribute_ids = {
                attribute.attribute_id
                for attribute in source.object.attributes
                if attribute.is_active
            }
            for alias in aliases_by_object_id.get(source.object.object_id, set()):
                aliases.setdefault(alias, set()).update(active_attribute_ids)
        result[header.mapping_object_id] = aliases
    return result


def _template_supports_reference_field(
    template: MappingOutputTemplate | None,
    *,
    name: str,
    data_type: str,
    array_item_type: str | None = None,
) -> bool:
    if template is None:
        return False
    return any(
        field.name == name
        and field.data_type == data_type
        and field.array_item_type == array_item_type
        for field in template.fields
    )


def _selected_attribute_template(
    preparation: MappingPreparation,
) -> MappingOutputTemplate | None:
    selection = preparation.plan.output_template_selections.mapping_attribute
    if selection is None:
        return None
    template = next(
        (
            item
            for item in preparation.context.output_templates.definitions
            if item.output_template_id == selection.output_template_id
        ),
        None,
    )
    if (
        template is None
        or template.target_type != "mapping_attribute"
        or template.schema_digest != selection.schema_digest
        or not template.schema_digest_is_valid
        or not template.is_active
    ):
        raise ValueError("The frozen Mapping Attribute output template is unavailable.")
    return template


def _issue(
    code: str,
    path: tuple[str | int, ...],
    message: str,
) -> AgentValidationIssue:
    return AgentValidationIssue(code=code, path=path, message=message)
