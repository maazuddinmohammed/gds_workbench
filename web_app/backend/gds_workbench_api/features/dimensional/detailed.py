"""Immutable contracts for deterministic Dimensional detailed coverage."""

from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
from typing import Literal, cast

from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    AttributeAssertionSourceRecord,
    AttributePhysicalSourceRecord,
    DimensionalAssertionSourceRecord,
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalObjectSourceRecord,
    DimensionalRelationshipRecord,
    DimensionalSubmodelRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    normalize_model_key_value,
)
from gds_etl_workbench.domain.snapshots.model import DimensionalSection
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    model_validator,
)

from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentCandidateValidationError,
    AgentCandidateValidator,
    AgentValidationIssue,
    enrich_agent_output_model_definitions,
    parse_pydantic_candidate,
)

_REFERENCE_PATTERN = r"^[a-z][a-z0-9_]{0,99}$"
_VALIDATION_REF_PATTERN = r"^validation_[0-9]{5}$"
_FINDING_REF_PATTERN = r"^validation_[0-9]{5}\.finding_[0-9]{5}$"
type _ObjectIdentity = tuple[str, str, str, str, str]
type _AttributeIdentity = tuple[str, str, str, str, str, str]
type _DimensionalEntitySource = DimensionalObjectSourceRecord | DimensionalAssertionSourceRecord
type _DimensionalAttributeSource = AttributePhysicalSourceRecord | AttributeAssertionSourceRecord
type _DimensionalRecord = (
    DimensionalSubmodelRecord
    | DimensionalEntityRecord
    | DimensionalAttributeRecord
    | DimensionalRelationshipRecord
)
type _DimensionalDataset = Literal[
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
]


class DetailedDimensionalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    max_relationship_signals: int = Field(ge=1, le=50_000)
    validation_package_size: int = Field(ge=1, le=1_000)
    max_validation_packages: int = Field(ge=1, le=10_000)


def load_default_detailed_dimensional_policy() -> DetailedDimensionalPolicy:
    resource = files("gds_workbench_api").joinpath("config/dimensional_detailed.json")
    raw = resource.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("Dimensional detailed configuration is too large")
    return DetailedDimensionalPolicy.model_validate_json(raw, strict=True)


class DetailedDimensionalTopologyProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    local_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    candidate_entity_name: str = Field(min_length=1, max_length=255)
    candidate_entity_type: Literal["fact", "dimension", "bridge"]
    candidate_fact_type: (
        Literal[
            "transaction",
            "periodic_snapshot",
            "accumulating_snapshot",
            "factless",
        ]
        | None
    )
    candidate_entity_grain_definition: str | None = Field(
        min_length=1,
        max_length=2_000,
    )
    candidate_submodel_names: tuple[str, ...] = Field(max_length=100)
    source_attributes: tuple[PhysicalAttributeKey, ...] = Field(
        min_length=1,
        max_length=10_000,
    )

    @model_validator(mode="after")
    def validate_unique_values(self) -> DetailedDimensionalTopologyProposal:
        if (self.candidate_entity_type == "fact") != (self.candidate_fact_type is not None):
            raise ValueError("Dimensional fact type is required only for facts")
        if (
            self.candidate_entity_type in ("fact", "bridge")
            and self.candidate_entity_grain_definition is None
        ):
            raise ValueError("Fact and Bridge topology proposals require a grain definition")
        submodels = tuple(normalize_model_key_value(item) for item in self.candidate_submodel_names)
        attributes = tuple(_physical_attribute_key(item) for item in self.source_attributes)
        if len(submodels) != len(set(submodels)) or len(attributes) != len(set(attributes)):
            raise ValueError("Dimensional topology proposal values must be unique")
        return self


class DetailedDimensionalTopologyContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    contribution_ref: str = Field(pattern=r"^object_[0-9]{5}(?:_batch_[0-9]{5})?$")
    source_object: PhysicalObjectKey
    disposition: Literal["represented", "not_dimensional", "needs_review"]
    rationale: str = Field(min_length=1, max_length=2_000)
    proposals: tuple[DetailedDimensionalTopologyProposal, ...] = Field(max_length=200)

    @model_validator(mode="after")
    def validate_disposition(self) -> DetailedDimensionalTopologyContribution:
        if (self.disposition == "represented") != bool(self.proposals):
            raise ValueError("Represented topology contributions require proposals exclusively")
        refs = tuple(item.local_entity_ref for item in self.proposals)
        if len(refs) != len(set(refs)):
            raise ValueError("Topology proposal references must be unique")
        return self

    @property
    def proposal_refs(self) -> tuple[str, ...]:
        return tuple(
            f"{self.contribution_ref}.{proposal.local_entity_ref}" for proposal in self.proposals
        )


class DetailedDimensionalSubmodelTopology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    canonical_submodel_ref: str = Field(pattern=_REFERENCE_PATTERN)
    submodel: DimensionalSubmodelRecord = Field(repr=False)


class DetailedDimensionalEntityTopology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    canonical_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    dimensional_entity_name: str = Field(min_length=1, max_length=255)
    contribution_refs: tuple[str, ...] = Field(min_length=1, max_length=50_000)
    submodel_refs: tuple[str, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_unique_values(self) -> DetailedDimensionalEntityTopology:
        if len(self.contribution_refs) != len(set(self.contribution_refs)) or len(
            self.submodel_refs
        ) != len(set(self.submodel_refs)):
            raise ValueError("Dimensional topology Entity references must be unique")
        return self


class DetailedDimensionalTopologyReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    submodels: tuple[DetailedDimensionalSubmodelTopology, ...] = Field(max_length=20_000)
    entities: tuple[DetailedDimensionalEntityTopology, ...] = Field(max_length=20_000)
    discarded_contribution_refs: tuple[str, ...] = Field(max_length=50_000)


class DetailedDimensionalEntityDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    canonical_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    entity: DimensionalEntityRecord = Field(repr=False)
    attributes: tuple[DimensionalAttributeRecord, ...] = Field(
        min_length=1,
        max_length=10_000,
        repr=False,
    )


class DetailedDimensionalRelationshipSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    signal_ref: str = Field(pattern=r"^relationship_signal_[0-9]{5}$")
    signal_type: Literal["matching_attribute_name"]
    from_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    from_dimensional_entity_name: str = Field(min_length=1, max_length=255)
    from_dimensional_attribute_name: str = Field(min_length=1, max_length=255)
    from_source_attributes: tuple[PhysicalAttributeKey, ...] = Field(
        min_length=1,
        max_length=10_000,
    )
    to_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    to_dimensional_entity_name: str = Field(min_length=1, max_length=255)
    to_dimensional_attribute_name: str = Field(min_length=1, max_length=255)
    to_source_attributes: tuple[PhysicalAttributeKey, ...] = Field(
        min_length=1,
        max_length=10_000,
    )


class DetailedDimensionalRelationshipSignalLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    signals: tuple[DetailedDimensionalRelationshipSignal, ...] = Field(max_length=50_000)

    @property
    def signal_refs(self) -> tuple[str, ...]:
        return tuple(item.signal_ref for item in self.signals)


class DetailedDimensionalReconciliationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    submodels: tuple[DimensionalSubmodelRecord, ...] = Field(max_length=20_000)
    entities: tuple[DimensionalEntityRecord, ...] = Field(max_length=20_000)
    attributes: tuple[DimensionalAttributeRecord, ...] = Field(max_length=20_000)
    relationships: tuple[DimensionalRelationshipRecord, ...] = Field(max_length=20_000)
    reviewed_submodel_refs: tuple[str, ...] = Field(max_length=20_000)
    reviewed_entity_refs: tuple[str, ...] = Field(max_length=20_000)
    reviewed_relationship_signal_refs: tuple[str, ...] = Field(max_length=50_000)
    reviewed_applied_record_refs: tuple[str, ...] = Field(max_length=80_000)

    @model_validator(mode="after")
    def validate_nonempty_candidate(self) -> DetailedDimensionalReconciliationCandidate:
        total = (
            len(self.submodels)
            + len(self.entities)
            + len(self.attributes)
            + len(self.relationships)
        )
        if not 1 <= total <= 20_000:
            raise ValueError("Dimensional reconciliation candidates must be bounded and nonempty")
        return self


class DetailedDimensionalDraftManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    draft_record_count: int = Field(ge=1, le=20_000)
    draft_manifest_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    relationship_signal_count: int = Field(ge=0, le=50_000)
    relationship_signal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_record_count: int = Field(ge=0, le=80_000)
    applied_record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class DetailedDimensionalReconciliationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    partition_ref: str = Field(pattern=r"^reconciliation_[0-9]{5}$")
    manifest: DetailedDimensionalDraftManifest
    reviewed_relationship_signal_refs: tuple[str, ...] = Field(max_length=1_000)
    relationships: tuple[DimensionalRelationshipRecord, ...] = Field(max_length=1_000)


class DetailedDimensionalValidationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record_ref: str = Field(min_length=1, max_length=10_000)
    dataset: _DimensionalDataset
    record: _DimensionalRecord = Field(repr=False)

    @model_validator(mode="after")
    def validate_dataset(self) -> DetailedDimensionalValidationRecord:
        expected: _DimensionalDataset
        if isinstance(self.record, DimensionalSubmodelRecord):
            expected = "dimensional_submodel"
        elif isinstance(self.record, DimensionalEntityRecord):
            expected = "dimensional_entity"
        elif isinstance(self.record, DimensionalAttributeRecord):
            expected = "dimensional_attribute"
        else:
            expected = "dimensional_relationship"
        if self.dataset != expected:
            raise ValueError("Dimensional validation record dataset does not match its record")
        return self


class DetailedDimensionalValidationPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    package_ref: str = Field(pattern=_VALIDATION_REF_PATTERN)
    records: tuple[DetailedDimensionalValidationRecord, ...] = Field(
        min_length=1,
        max_length=1_000,
        repr=False,
    )
    record_digests: tuple[str, ...] = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def validate_manifest(self) -> DetailedDimensionalValidationPackage:
        expected = tuple(
            dimensional_json_digest(item.record.model_dump(mode="json")) for item in self.records
        )
        if len(self.record_refs) != len(set(self.record_refs)) or self.record_digests != expected:
            raise ValueError("Dimensional validation package manifest is invalid")
        return self

    @property
    def record_refs(self) -> tuple[str, ...]:
        return tuple(item.record_ref for item in self.records)


class DetailedDimensionalValidationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    finding_ref: str = Field(pattern=_FINDING_REF_PATTERN)
    severity: Literal["warning", "error"]
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    message: str = Field(min_length=1, max_length=500)
    record_refs: tuple[str, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_record_refs(self) -> DetailedDimensionalValidationFinding:
        if len(self.record_refs) != len(set(self.record_refs)):
            raise ValueError("Dimensional validation finding record references must be unique")
        return self


class DetailedDimensionalValidationWorkerResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    package_ref: str = Field(pattern=_VALIDATION_REF_PATTERN)
    reviewed_record_refs: tuple[str, ...] = Field(min_length=1, max_length=1_000)
    findings: tuple[DetailedDimensionalValidationFinding, ...] = Field(max_length=200)


class DetailedDimensionalValidationLead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    reviewed_package_refs: tuple[str, ...] = Field(min_length=1, max_length=10_000)
    reviewed_finding_refs: tuple[str, ...] = Field(max_length=2_000_000)
    blocking_finding_refs: tuple[str, ...] = Field(max_length=2_000_000)
    repair_brief: str | None = Field(default=None, max_length=32_768)


class DetailedDimensionalHandoffDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    next_stage: Literal["whole_model_reconciliation", "handoff"]
    validation_failures: tuple[DetailedDimensionalValidationFinding, ...] = Field(
        max_length=2_000_000
    )
    handoff_candidate: JsonValue | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_decision(self) -> DetailedDimensionalHandoffDecision:
        if self.next_stage == "whole_model_reconciliation":
            if not self.validation_failures or self.handoff_candidate is not None:
                raise ValueError("A reconciliation decision contains failures only")
        elif self.validation_failures or self.handoff_candidate is None:
            raise ValueError("A handoff decision contains one complete candidate only")
        return self


class DetailedDimensionalTopologyContributionValidator:
    def __init__(
        self,
        *,
        contribution_ref: str,
        source_object: PhysicalObjectKey,
        source_attributes: tuple[PhysicalAttributeKey, ...],
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
        if not source_attributes or len(source_attributes) > 10_000:
            raise ValueError("Dimensional topology Attribute context must be bounded and nonempty")
        expected_object = _physical_object_key(source_object)
        attribute_keys = tuple(_physical_attribute_key(item) for item in source_attributes)
        if len(attribute_keys) != len(set(attribute_keys)) or any(
            key[:5] != expected_object for key in attribute_keys
        ):
            raise ValueError("Dimensional topology Attribute context must match one source Object")
        self._contribution_ref = contribution_ref
        self._source_object = source_object
        self._source_attributes = frozenset(attribute_keys)
        _validate_result_byte_limit(max_result_bytes)
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedDimensionalTopologyContribution)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse_bounded(
            DetailedDimensionalTopologyContribution,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None:
            return _parse_failure_validation(
                DetailedDimensionalTopologyContribution,
                candidate,
                "detailed.topology_contribution_invalid",
                "The topology contribution is incomplete or outside its fixed Object.",
            )
        if not self._has_fixed_identity(parsed):
            return _validation_issue(
                "detailed.topology_contribution_invalid",
                "The topology contribution is incomplete or outside its fixed Object.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.topology_contribution_coverage_invalid",
                "Every frozen source Attribute must be assigned exactly once.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedDimensionalTopologyContribution:
        parsed = _parse_bounded(
            DetailedDimensionalTopologyContribution,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if (
            parsed is None
            or not self._has_fixed_identity(parsed)
            or not self._has_exact_coverage(parsed)
        ):
            raise AgentCandidateValidationError()
        return parsed

    def _has_fixed_identity(self, candidate: DetailedDimensionalTopologyContribution) -> bool:
        return candidate.contribution_ref == self._contribution_ref and _physical_object_key(
            candidate.source_object
        ) == _physical_object_key(self._source_object)

    def _has_exact_coverage(self, candidate: DetailedDimensionalTopologyContribution) -> bool:
        if candidate.disposition != "represented":
            return not candidate.proposals
        actual = [
            _physical_attribute_key(attribute)
            for proposal in candidate.proposals
            for attribute in proposal.source_attributes
        ]
        return len(actual) == len(set(actual)) and set(actual) == set(self._source_attributes)


class DetailedDimensionalTopologyReconciliationValidator:
    def __init__(
        self,
        *,
        contributions: tuple[DetailedDimensionalTopologyContribution, ...],
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
        if not contributions or len(contributions) > 50_000:
            raise ValueError("Dimensional topology contributions must be bounded and nonempty")
        contribution_refs = tuple(item.contribution_ref for item in contributions)
        if len(contribution_refs) != len(set(contribution_refs)):
            raise ValueError("Dimensional topology contribution references must be unique")
        self._proposals = {
            proposal_ref: proposal
            for contribution in contributions
            for proposal_ref, proposal in zip(
                contribution.proposal_refs,
                contribution.proposals,
                strict=True,
            )
        }
        if len(self._proposals) != sum(len(item.proposals) for item in contributions):
            raise ValueError("Dimensional topology proposal references must be unique")
        _validate_result_byte_limit(max_result_bytes)
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        schema = _output_schema(DetailedDimensionalTopologyReconciliation)
        _set_agent_output_constraints(schema)
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse_bounded(
            DetailedDimensionalTopologyReconciliation,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None:
            return _parse_failure_validation(
                DetailedDimensionalTopologyReconciliation,
                candidate,
                "detailed.topology_reconciliation_invalid",
                "The Dimensional topology reconciliation does not match its bounded schema.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.topology_reconciliation_coverage_invalid",
                "The Dimensional topology ledger must cover every proposal exactly once.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedDimensionalTopologyReconciliation:
        parsed = _parse_bounded(
            DetailedDimensionalTopologyReconciliation,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _has_exact_coverage(self, candidate: DetailedDimensionalTopologyReconciliation) -> bool:
        submodel_refs = tuple(item.canonical_submodel_ref for item in candidate.submodels)
        submodel_names = tuple(
            normalize_model_key_value(item.submodel.dimensional_submodel_name)
            for item in candidate.submodels
        )
        entity_refs = tuple(item.canonical_entity_ref for item in candidate.entities)
        entity_names = tuple(
            normalize_model_key_value(item.dimensional_entity_name) for item in candidate.entities
        )
        if any(
            len(values) != len(set(values))
            for values in (submodel_refs, submodel_names, entity_refs, entity_names)
        ) or any(item.submodel.dimensional_submodel_is_locked for item in candidate.submodels):
            return False

        submodel_by_ref = {
            item.canonical_submodel_ref: item.submodel for item in candidate.submodels
        }
        covered = [ref for entity in candidate.entities for ref in entity.contribution_refs] + list(
            candidate.discarded_contribution_refs
        )
        if len(covered) != len(set(covered)) or set(covered) != set(self._proposals):
            return False

        referenced_submodels: set[str] = set()
        for entity in candidate.entities:
            if any(ref not in submodel_by_ref for ref in entity.submodel_refs):
                return False
            expected_names = {
                normalize_model_key_value(name)
                for contribution_ref in entity.contribution_refs
                for name in self._proposals[contribution_ref].candidate_submodel_names
            }
            actual_names = {
                normalize_model_key_value(submodel_by_ref[reference].dimensional_submodel_name)
                for reference in entity.submodel_refs
            }
            if actual_names != expected_names:
                return False
            referenced_submodels.update(entity.submodel_refs)
        return referenced_submodels == set(submodel_refs)


class DetailedDimensionalEntityDetailValidator:
    def __init__(
        self,
        *,
        entity: DetailedDimensionalEntityTopology,
        topology: DetailedDimensionalTopologyReconciliation,
        contributions: tuple[DetailedDimensionalTopologyContribution, ...],
        assertion_record_keys: tuple[str, ...] = (),
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
        if len(assertion_record_keys) > 50_000:
            raise ValueError("Dimensional Assertion context must be bounded")
        normalized_assertion_keys = tuple(
            normalize_model_key_value(item) for item in assertion_record_keys
        )
        if len(normalized_assertion_keys) != len(set(normalized_assertion_keys)):
            raise ValueError("Dimensional Assertion context keys must be unique")
        self._assertion_record_keys = frozenset(normalized_assertion_keys)
        proposals = {
            proposal_ref: proposal
            for contribution in contributions
            for proposal_ref, proposal in zip(
                contribution.proposal_refs,
                contribution.proposals,
                strict=True,
            )
        }
        contribution_by_ref = {item.contribution_ref: item for item in contributions}
        submodel_by_ref = {
            item.canonical_submodel_ref: item.submodel for item in topology.submodels
        }
        self._entity_ref = entity.canonical_entity_ref
        self._entity_name = normalize_model_key_value(entity.dimensional_entity_name)
        self._expected_submodels = {
            normalize_model_key_value(submodel_by_ref[ref].dimensional_submodel_name)
            for ref in entity.submodel_refs
        }
        proposal_refs = entity.contribution_refs
        self._expected_objects = {
            _physical_object_key(
                contribution_by_ref[proposal_ref.split(".", maxsplit=1)[0]].source_object
            )
            for proposal_ref in proposal_refs
        }
        self._expected_attributes = {
            _physical_attribute_key(attribute)
            for proposal_ref in proposal_refs
            for attribute in proposals[proposal_ref].source_attributes
        }
        proposed_entity_shapes = {
            (
                proposals[proposal_ref].candidate_entity_type,
                proposals[proposal_ref].candidate_fact_type,
                proposals[proposal_ref].candidate_entity_grain_definition,
            )
            for proposal_ref in proposal_refs
        }
        if len(proposed_entity_shapes) != 1:
            raise ValueError(
                "One Dimensional topology Entity requires one consistent type and grain"
            )
        self._expected_entity_shape = next(iter(proposed_entity_shapes))
        _validate_result_byte_limit(max_result_bytes)
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        schema = _output_schema(DetailedDimensionalEntityDetail)
        _set_agent_output_constraints(schema)
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse_bounded(
            DetailedDimensionalEntityDetail,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None:
            return _parse_failure_validation(
                DetailedDimensionalEntityDetail,
                candidate,
                "detailed.entity_detail_invalid",
                "The Dimensional Entity detail does not match its bounded schema.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.entity_detail_coverage_invalid",
                "The Dimensional Entity detail must preserve all topology and source coverage.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedDimensionalEntityDetail:
        parsed = _parse_bounded(
            DetailedDimensionalEntityDetail,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _has_exact_coverage(self, candidate: DetailedDimensionalEntityDetail) -> bool:
        if (
            candidate.canonical_entity_ref != self._entity_ref
            or normalize_model_key_value(candidate.entity.dimensional_entity_name)
            != self._entity_name
            or (
                candidate.entity.dimensional_entity_type,
                candidate.entity.dimensional_fact_type,
                candidate.entity.dimensional_entity_grain_definition,
            )
            != self._expected_entity_shape
            or not _safe_entity(candidate.entity)
        ):
            return False
        submodels = [
            normalize_model_key_value(item.submodel_name) for item in candidate.entity.submodels
        ]
        objects = [
            _physical_object_key(item.source_object)
            for item in candidate.entity.sources
            if isinstance(item, DimensionalObjectSourceRecord)
        ]
        entity_assertions = {
            normalize_model_key_value(item.assertion_record.modeling_assertion_record_key)
            for item in candidate.entity.sources
            if isinstance(item, DimensionalAssertionSourceRecord)
        }
        attributes = [
            _physical_attribute_key(source.source_attribute)
            for record in candidate.attributes
            for source in record.sources
            if isinstance(source, AttributePhysicalSourceRecord)
        ]
        attribute_assertions = {
            normalize_model_key_value(source.assertion_record.modeling_assertion_record_key)
            for record in candidate.attributes
            for source in record.sources
            if isinstance(source, AttributeAssertionSourceRecord)
        }
        attribute_names = [
            normalize_model_key_value(item.dimensional_attribute_name)
            for item in candidate.attributes
        ]
        ordinals = [item.dimensional_attribute_ordinal_position for item in candidate.attributes]
        return (
            len(submodels) == len(set(submodels))
            and set(submodels) == self._expected_submodels
            and len(objects) == len(set(objects))
            and set(objects) == self._expected_objects
            and len(attributes) == len(set(attributes))
            and set(attributes) == self._expected_attributes
            and entity_assertions <= self._assertion_record_keys
            and attribute_assertions <= self._assertion_record_keys
            and len(attribute_names) == len(set(attribute_names))
            and len(ordinals) == len(set(ordinals))
            and all(
                normalize_model_key_value(item.dimensional_entity_name) == self._entity_name
                and _safe_attribute(item)
                and bool(item.sources)
                for item in candidate.attributes
            )
        )


class DetailedDimensionalReconciliationValidator:
    def __init__(
        self,
        *,
        topology: DetailedDimensionalTopologyReconciliation,
        entity_details: tuple[DetailedDimensionalEntityDetail, ...],
        relationship_signal_refs: tuple[str, ...],
        applied_record_refs: tuple[str, ...],
        final_validator: AgentCandidateValidator | None = None,
        max_result_bytes: int | None = 2 * 1024 * 1024,
        require_exact_base_records: bool = False,
    ) -> None:
        self._topology = topology
        self._details = entity_details
        self._submodel_refs = tuple(item.canonical_submodel_ref for item in topology.submodels)
        self._entity_refs = tuple(item.canonical_entity_ref for item in entity_details)
        topology_entity_refs = tuple(item.canonical_entity_ref for item in topology.entities)
        self._relationship_signal_refs = relationship_signal_refs
        self._applied_record_refs = applied_record_refs
        self._applied_authored_record_refs = frozenset(
            ref
            for ref in applied_record_refs
            if ref.partition(":")[0] in ("submodel", "entity", "attribute")
        )
        self._final_validator = final_validator
        _validate_result_byte_limit(max_result_bytes)
        self._max_result_bytes = max_result_bytes
        self._require_exact_base_records = require_exact_base_records
        topology_entities = {
            item.canonical_entity_ref: normalize_model_key_value(item.dimensional_entity_name)
            for item in topology.entities
        }
        detail_entities = {
            item.canonical_entity_ref: normalize_model_key_value(
                item.entity.dimensional_entity_name
            )
            for item in entity_details
        }
        if any(
            len(values) != len(set(values))
            for values in (
                self._submodel_refs,
                self._entity_refs,
                topology_entity_refs,
                relationship_signal_refs,
                applied_record_refs,
            )
        ):
            raise ValueError("Dimensional detailed reconciliation references must be unique")
        if topology_entities != detail_entities:
            raise ValueError("Dimensional Entity details must exactly match the topology")
        required_record_count = (
            len(topology.submodels)
            + len(entity_details)
            + sum(len(item.attributes) for item in entity_details)
        )
        if required_record_count > 20_000:
            raise ValueError("Dimensional detailed reconciliation context is too large")
        self._required_entity_sources = {
            _entity_record_ref(detail.entity): frozenset(
                _entity_source_identity(source) for source in detail.entity.sources
            )
            for detail in entity_details
        }
        self._required_entity_shapes = {
            _entity_record_ref(detail.entity): (
                detail.entity.dimensional_entity_type,
                detail.entity.dimensional_fact_type,
                detail.entity.dimensional_entity_grain_definition,
            )
            for detail in entity_details
        }
        self._required_attribute_sources = {
            _attribute_record_ref(attribute): frozenset(
                _attribute_source_identity(source) for source in attribute.sources
            )
            for detail in entity_details
            for attribute in detail.attributes
        }

    def output_schema(self) -> dict[str, JsonValue]:
        schema = _output_schema(DetailedDimensionalReconciliationCandidate)
        _set_agent_output_constraints(schema)
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse_bounded(
            DetailedDimensionalReconciliationCandidate,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None:
            return _parse_failure_validation(
                DetailedDimensionalReconciliationCandidate,
                candidate,
                "detailed.reconciliation_invalid",
                "The Dimensional whole-model reconciliation does not match its bounded schema.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.reconciliation_coverage_invalid",
                "The Dimensional whole-model reconciliation must review every required record.",
            )
        if self._final_validator is not None:
            return await self._final_validator.validate(_materialize(parsed))
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedDimensionalReconciliationCandidate:
        parsed = _parse_bounded(
            DetailedDimensionalReconciliationCandidate,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def materialize_validated(self, candidate: JsonValue) -> JsonValue:
        return _materialize(self.parse_validated(candidate))

    def _has_exact_coverage(self, candidate: DetailedDimensionalReconciliationCandidate) -> bool:
        if not all(
            (
                _exact_unique(candidate.reviewed_submodel_refs, self._submodel_refs),
                _exact_unique(candidate.reviewed_entity_refs, self._entity_refs),
                _exact_unique(
                    candidate.reviewed_relationship_signal_refs,
                    self._relationship_signal_refs,
                ),
                _exact_unique(
                    candidate.reviewed_applied_record_refs,
                    self._applied_record_refs,
                ),
            )
        ):
            return False
        submodel_record_refs = {_submodel_record_ref(item) for item in candidate.submodels}
        entity_record_refs = {_entity_record_ref(item) for item in candidate.entities}
        attribute_record_refs = {_attribute_record_ref(item) for item in candidate.attributes}
        relationship_record_refs = tuple(
            _relationship_record_ref(item) for item in candidate.relationships
        )
        candidate_entity_sources = {
            _entity_record_ref(item): frozenset(
                _entity_source_identity(source) for source in item.sources
            )
            for item in candidate.entities
        }
        candidate_entity_shapes = {
            _entity_record_ref(item): (
                item.dimensional_entity_type,
                item.dimensional_fact_type,
                item.dimensional_entity_grain_definition,
            )
            for item in candidate.entities
        }
        candidate_attribute_sources = {
            _attribute_record_ref(item): frozenset(
                _attribute_source_identity(source) for source in item.sources
            )
            for item in candidate.attributes
        }
        required_submodels = {
            _submodel_record_ref(item.submodel) for item in self._topology.submodels
        }
        required_entities = {_entity_record_ref(item.entity) for item in self._details}
        required_attributes = {
            _attribute_record_ref(attribute)
            for detail in self._details
            for attribute in detail.attributes
        }
        required_authored_refs = required_submodels | required_entities | required_attributes
        allowed_authored_refs = required_authored_refs | self._applied_authored_record_refs
        candidate_authored_refs = submodel_record_refs | entity_record_refs | attribute_record_refs
        required_records_match = (
            candidate_authored_refs == required_authored_refs
            if self._require_exact_base_records
            else required_authored_refs <= candidate_authored_refs
            and candidate_authored_refs <= allowed_authored_refs
        )
        return (
            len(submodel_record_refs) == len(candidate.submodels)
            and len(entity_record_refs) == len(candidate.entities)
            and len(attribute_record_refs) == len(candidate.attributes)
            and len(relationship_record_refs) == len(set(relationship_record_refs))
            and required_records_match
            and all(
                candidate_entity_sources.get(ref) == sources
                for ref, sources in self._required_entity_sources.items()
            )
            and all(
                candidate_entity_shapes.get(ref) == shape
                for ref, shape in self._required_entity_shapes.items()
            )
            and all(
                candidate_attribute_sources.get(ref) == sources
                for ref, sources in self._required_attribute_sources.items()
            )
            and all(not item.dimensional_submodel_is_locked for item in candidate.submodels)
            and all(_safe_entity(item) for item in candidate.entities)
            and all(_safe_attribute(item) for item in candidate.attributes)
            and all(not item.dimensional_relationship_is_locked for item in candidate.relationships)
        )


class DetailedDimensionalReconciliationReceiptValidator:
    """Validate one bounded relationship-review receipt against the frozen draft."""

    def __init__(
        self,
        *,
        partition_ref: str,
        manifest: DetailedDimensionalDraftManifest,
        relationship_signals: tuple[DetailedDimensionalRelationshipSignal, ...],
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
        signal_refs = tuple(item.signal_ref for item in relationship_signals)
        if len(signal_refs) != len(set(signal_refs)):
            raise ValueError("Dimensional relationship signal references must be unique")
        _validate_result_byte_limit(max_result_bytes)
        self._partition_ref = partition_ref
        self._manifest = manifest
        self._relationship_signals = relationship_signals
        self._signal_refs = signal_refs
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        schema = _output_schema(DetailedDimensionalReconciliationReceipt)
        _set_agent_output_constraints(schema)
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse_bounded(
            DetailedDimensionalReconciliationReceipt,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None:
            return _parse_failure_validation(
                DetailedDimensionalReconciliationReceipt,
                candidate,
                "detailed.reconciliation_receipt_invalid",
                "The Dimensional reconciliation receipt must preserve its exact manifest.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.reconciliation_receipt_invalid",
                "The Dimensional reconciliation receipt must preserve its exact manifest.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(
        self,
        candidate: JsonValue,
    ) -> DetailedDimensionalReconciliationReceipt:
        parsed = _parse_bounded(
            DetailedDimensionalReconciliationReceipt,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _has_exact_coverage(
        self,
        candidate: DetailedDimensionalReconciliationReceipt,
    ) -> bool:
        relationship_keys = tuple(_relationship_key(item) for item in candidate.relationships)
        allowed_endpoints = {
            frozenset(
                (
                    (
                        normalize_model_key_value(signal.from_dimensional_entity_name),
                        normalize_model_key_value(signal.from_dimensional_attribute_name),
                    ),
                    (
                        normalize_model_key_value(signal.to_dimensional_entity_name),
                        normalize_model_key_value(signal.to_dimensional_attribute_name),
                    ),
                )
            )
            for signal in self._relationship_signals
        }
        return (
            candidate.partition_ref == self._partition_ref
            and candidate.manifest == self._manifest
            and _exact_ordered_unique(
                candidate.reviewed_relationship_signal_refs, self._signal_refs
            )
            and len(relationship_keys) == len(set(relationship_keys))
            and all(not item.dimensional_relationship_is_locked for item in candidate.relationships)
            and all(
                frozenset(
                    (
                        (
                            normalize_model_key_value(item.from_dimensional_entity_name),
                            normalize_model_key_value(item.from_dimensional_attribute_name),
                        ),
                        (
                            normalize_model_key_value(item.to_dimensional_entity_name),
                            normalize_model_key_value(item.to_dimensional_attribute_name),
                        ),
                    )
                )
                in allowed_endpoints
                for item in candidate.relationships
            )
        )


class DetailedDimensionalValidationWorkerValidator:
    def __init__(
        self,
        *,
        package: DetailedDimensionalValidationPackage,
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
        _validate_result_byte_limit(max_result_bytes)
        self._package = package
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedDimensionalValidationWorkerResult)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse_bounded(
            DetailedDimensionalValidationWorkerResult,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None:
            return _parse_failure_validation(
                DetailedDimensionalValidationWorkerResult,
                candidate,
                "detailed.validation_worker_coverage_invalid",
                "The Dimensional validator worker must review its complete bounded package.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.validation_worker_coverage_invalid",
                "The Dimensional validator worker must review its complete bounded package.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedDimensionalValidationWorkerResult:
        parsed = _parse_bounded(
            DetailedDimensionalValidationWorkerResult,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _has_exact_coverage(self, candidate: DetailedDimensionalValidationWorkerResult) -> bool:
        finding_refs = tuple(item.finding_ref for item in candidate.findings)
        prefix = f"{self._package.package_ref}."
        return (
            candidate.package_ref == self._package.package_ref
            and _exact_unique(candidate.reviewed_record_refs, self._package.record_refs)
            and len(finding_refs) == len(set(finding_refs))
            and all(item.startswith(prefix) for item in finding_refs)
            and all(
                set(finding.record_refs) <= set(self._package.record_refs)
                for finding in candidate.findings
            )
        )


class DetailedDimensionalValidationLeadValidator:
    def __init__(
        self,
        *,
        worker_results: tuple[DetailedDimensionalValidationWorkerResult, ...],
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
        if not worker_results or len(worker_results) > 10_000:
            raise ValueError("Dimensional validator worker results must be bounded and nonempty")
        self._package_refs = tuple(item.package_ref for item in worker_results)
        self._findings = tuple(finding for result in worker_results for finding in result.findings)
        self._finding_refs = tuple(item.finding_ref for item in self._findings)
        self._blocking_refs = tuple(
            item.finding_ref for item in self._findings if item.severity == "error"
        )
        if len(self._package_refs) != len(set(self._package_refs)) or len(
            self._finding_refs
        ) != len(set(self._finding_refs)):
            raise ValueError("Dimensional validator worker references must be unique")
        _validate_result_byte_limit(max_result_bytes)
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedDimensionalValidationLead)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse_bounded(
            DetailedDimensionalValidationLead,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None:
            return _parse_failure_validation(
                DetailedDimensionalValidationLead,
                candidate,
                "detailed.validation_lead_coverage_invalid",
                "The Dimensional validator lead must reconcile every package and finding once.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.validation_lead_coverage_invalid",
                "The Dimensional validator lead must reconcile every package and finding once.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedDimensionalValidationLead:
        parsed = _parse_bounded(
            DetailedDimensionalValidationLead,
            candidate,
            maximum_bytes=self._max_result_bytes,
        )
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _has_exact_coverage(self, candidate: DetailedDimensionalValidationLead) -> bool:
        return (
            _exact_unique(candidate.reviewed_package_refs, self._package_refs)
            and _exact_unique(candidate.reviewed_finding_refs, self._finding_refs)
            and _exact_unique(candidate.blocking_finding_refs, self._blocking_refs)
            and ((candidate.repair_brief is not None) == bool(self._blocking_refs))
        )


def build_dimensional_relationship_signal_ledger(
    *,
    entity_details: tuple[DetailedDimensionalEntityDetail, ...],
    max_signals: int,
) -> DetailedDimensionalRelationshipSignalLedger:
    """Derive stable same-name Attribute evidence without assigning semantics."""

    if not 1 <= max_signals <= 50_000:
        raise InvalidRequestError("The Dimensional relationship signal limit is invalid.")
    entity_refs = tuple(item.canonical_entity_ref for item in entity_details)
    entity_names = tuple(
        normalize_model_key_value(item.entity.dimensional_entity_name) for item in entity_details
    )
    if len(entity_refs) != len(set(entity_refs)) or len(entity_names) != len(set(entity_names)):
        raise InvalidRequestError("Dimensional detailed Entity identities must be unique.")

    endpoints: list[
        tuple[
            str,
            DimensionalEntityRecord,
            DimensionalAttributeRecord,
            tuple[PhysicalAttributeKey, ...],
        ]
    ] = []
    groups: dict[tuple[str, str], dict[str, list[int]]] = {}
    for detail in sorted(entity_details, key=lambda item: item.canonical_entity_ref):
        normalized_attribute_names = tuple(
            normalize_model_key_value(item.dimensional_attribute_name) for item in detail.attributes
        )
        if len(normalized_attribute_names) != len(set(normalized_attribute_names)):
            raise InvalidRequestError("Dimensional detailed Attribute identities must be unique.")
        for attribute in sorted(
            detail.attributes,
            key=lambda item: normalize_model_key_value(item.dimensional_attribute_name),
        ):
            sources = _physical_attribute_sources(attribute)
            if not sources:
                continue
            endpoint_index = len(endpoints)
            endpoints.append((detail.canonical_entity_ref, detail.entity, attribute, sources))
            tokens = {
                ("modeled", normalize_model_key_value(attribute.dimensional_attribute_name)),
                *(
                    ("physical", normalize_model_key_value(source.attribute_name))
                    for source in sources
                ),
            }
            for token in sorted(tokens):
                groups.setdefault(token, {}).setdefault(detail.canonical_entity_ref, []).append(
                    endpoint_index
                )

    pairs: set[tuple[int, int]] = set()
    for token in sorted(groups):
        endpoints_by_entity = groups[token]
        grouped_entity_refs = sorted(endpoints_by_entity)
        for left_position, left_ref in enumerate(grouped_entity_refs):
            for right_ref in grouped_entity_refs[left_position + 1 :]:
                for left_index in endpoints_by_entity[left_ref]:
                    for right_index in endpoints_by_entity[right_ref]:
                        pair = (left_index, right_index)
                        if pair in pairs:
                            continue
                        if len(pairs) >= max_signals:
                            raise InvalidRequestError(
                                "Dimensional relationship evidence exceeds its configured "
                                "signal limit."
                            )
                        pairs.add(pair)

    raw = tuple(
        (*endpoints[left_index], *endpoints[right_index])
        for left_index, right_index in sorted(pairs)
    )
    signals = tuple(
        DetailedDimensionalRelationshipSignal(
            signal_ref=f"relationship_signal_{position:05d}",
            signal_type="matching_attribute_name",
            from_entity_ref=left_ref,
            from_dimensional_entity_name=left_entity.dimensional_entity_name,
            from_dimensional_attribute_name=left_attribute.dimensional_attribute_name,
            from_source_attributes=left_sources,
            to_entity_ref=right_ref,
            to_dimensional_entity_name=right_entity.dimensional_entity_name,
            to_dimensional_attribute_name=right_attribute.dimensional_attribute_name,
            to_source_attributes=right_sources,
        )
        for position, (
            left_ref,
            left_entity,
            left_attribute,
            left_sources,
            right_ref,
            right_entity,
            right_attribute,
            right_sources,
        ) in enumerate(raw, start=1)
    )
    return DetailedDimensionalRelationshipSignalLedger(signals=signals)


def merge_dimensional_topology_partitions(
    *,
    contributions: tuple[DetailedDimensionalTopologyContribution, ...],
    partitions: tuple[DetailedDimensionalTopologyReconciliation, ...],
) -> DetailedDimensionalTopologyReconciliation:
    """Merge disjoint topology partitions in original proposal order."""

    if not contributions or not partitions:
        raise AgentCandidateValidationError()
    proposals = {
        reference: proposal
        for contribution in contributions
        for reference, proposal in zip(
            contribution.proposal_refs,
            contribution.proposals,
            strict=True,
        )
    }
    proposal_order = {reference: position for position, reference in enumerate(proposals)}
    if len(proposal_order) != sum(len(item.proposals) for item in contributions):
        raise AgentCandidateValidationError()

    covered: list[str] = []
    discarded: list[str] = []
    submodels: dict[str, DimensionalSubmodelRecord] = {}
    entity_groups: dict[str, dict[str, object]] = {}
    for partition in partitions:
        submodel_by_ref = {
            item.canonical_submodel_ref: item.submodel for item in partition.submodels
        }
        for topology_entity in partition.entities:
            normalized_name = normalize_model_key_value(topology_entity.dimensional_entity_name)
            shapes = {
                (
                    proposals[reference].candidate_entity_type,
                    proposals[reference].candidate_fact_type,
                    proposals[reference].candidate_entity_grain_definition,
                )
                for reference in topology_entity.contribution_refs
            }
            if len(shapes) != 1:
                raise AgentCandidateValidationError()
            group = entity_groups.setdefault(
                normalized_name,
                {
                    "name": topology_entity.dimensional_entity_name,
                    "shape": next(iter(shapes)),
                    "contribution_refs": [],
                    "submodel_names": [],
                },
            )
            if group["shape"] != next(iter(shapes)):
                raise AgentCandidateValidationError()
            group_refs = cast(list[str], group["contribution_refs"])
            group_names = cast(list[str], group["submodel_names"])
            group_refs.extend(topology_entity.contribution_refs)
            for reference in topology_entity.submodel_refs:
                submodel = submodel_by_ref.get(reference)
                if submodel is None:
                    raise AgentCandidateValidationError()
                normalized_submodel = normalize_model_key_value(submodel.dimensional_submodel_name)
                existing = submodels.setdefault(normalized_submodel, submodel)
                if existing != submodel:
                    raise AgentCandidateValidationError()
                if normalized_submodel not in group_names:
                    group_names.append(normalized_submodel)
            covered.extend(topology_entity.contribution_refs)
        covered.extend(partition.discarded_contribution_refs)
        discarded.extend(partition.discarded_contribution_refs)

    if len(covered) != len(set(covered)) or set(covered) != set(proposal_order):
        raise AgentCandidateValidationError()
    ordered_groups = sorted(
        entity_groups.values(),
        key=lambda item: min(
            proposal_order[reference] for reference in cast(list[str], item["contribution_refs"])
        ),
    )
    ordered_submodel_names: list[str] = []
    for group in ordered_groups:
        for name in cast(list[str], group["submodel_names"]):
            if name not in ordered_submodel_names:
                ordered_submodel_names.append(name)
    submodel_ref_by_name = {
        name: f"submodel_{position:05d}"
        for position, name in enumerate(ordered_submodel_names, start=1)
    }
    candidate = cast(
        JsonValue,
        {
            "submodels": [
                {
                    "canonical_submodel_ref": submodel_ref_by_name[name],
                    "submodel": submodels[name].model_dump(mode="json"),
                }
                for name in ordered_submodel_names
            ],
            "entities": [
                {
                    "canonical_entity_ref": f"entity_{position:05d}",
                    "dimensional_entity_name": cast(str, group["name"]),
                    "contribution_refs": sorted(
                        cast(list[str], group["contribution_refs"]),
                        key=proposal_order.__getitem__,
                    ),
                    "submodel_refs": [
                        submodel_ref_by_name[name]
                        for name in cast(list[str], group["submodel_names"])
                    ],
                }
                for position, group in enumerate(ordered_groups, start=1)
            ],
            "discarded_contribution_refs": sorted(
                discarded,
                key=proposal_order.__getitem__,
            ),
        },
    )
    return DetailedDimensionalTopologyReconciliationValidator(
        contributions=contributions,
        max_result_bytes=None,
    ).parse_validated(candidate)


def merge_dimensional_entity_detail_partitions(
    *,
    entity: DetailedDimensionalEntityTopology,
    topology: DetailedDimensionalTopologyReconciliation,
    contributions: tuple[DetailedDimensionalTopologyContribution, ...],
    partitions: tuple[DetailedDimensionalEntityDetail, ...],
    assertion_record_keys: tuple[str, ...] = (),
) -> DetailedDimensionalEntityDetail:
    """Merge one Entity's disjoint detail partitions without losing coverage."""

    if not partitions or any(
        item.canonical_entity_ref != entity.canonical_entity_ref for item in partitions
    ):
        raise AgentCandidateValidationError()
    merged_entity = _merge_entity_records(tuple(item.entity for item in partitions))
    attributes: list[DimensionalAttributeRecord] = []
    names: set[str] = set()
    for partition in partitions:
        for attribute in partition.attributes:
            name = normalize_model_key_value(attribute.dimensional_attribute_name)
            if name in names:
                raise AgentCandidateValidationError()
            names.add(name)
            raw = attribute.model_dump(mode="json")
            raw["dimensional_attribute_ordinal_position"] = len(attributes) + 1
            parsed_attribute = _parse(DimensionalAttributeRecord, cast(JsonValue, raw))
            if parsed_attribute is None:
                raise AgentCandidateValidationError()
            attributes.append(parsed_attribute)
    merged = DetailedDimensionalEntityDetail(
        canonical_entity_ref=entity.canonical_entity_ref,
        entity=merged_entity,
        attributes=tuple(attributes),
    )
    return DetailedDimensionalEntityDetailValidator(
        entity=entity,
        topology=topology,
        contributions=contributions,
        assertion_record_keys=assertion_record_keys,
        max_result_bytes=None,
    ).parse_validated(cast(JsonValue, merged.model_dump(mode="json")))


def merge_dimensional_reconciliation_partitions(
    *,
    partitions: tuple[DetailedDimensionalReconciliationCandidate, ...],
    reviewed_submodel_refs: tuple[str, ...],
    reviewed_entity_refs: tuple[str, ...],
    reviewed_relationship_signal_refs: tuple[str, ...],
    reviewed_applied_record_refs: tuple[str, ...],
) -> DetailedDimensionalReconciliationCandidate:
    """Merge validated reconciliation partitions and reject coverage drift."""

    if not partitions:
        raise AgentCandidateValidationError()
    actual_submodels = tuple(
        reference for item in partitions for reference in item.reviewed_submodel_refs
    )
    actual_entities = tuple(
        reference for item in partitions for reference in item.reviewed_entity_refs
    )
    actual_signals = tuple(
        reference for item in partitions for reference in item.reviewed_relationship_signal_refs
    )
    actual_applied = tuple(
        reference for item in partitions for reference in item.reviewed_applied_record_refs
    )
    if not all(
        (
            _exact_unique(actual_submodels, reviewed_submodel_refs),
            _exact_unique(actual_entities, reviewed_entity_refs),
            _exact_unique(actual_signals, reviewed_relationship_signal_refs),
            _exact_unique(actual_applied, reviewed_applied_record_refs),
        )
    ):
        raise AgentCandidateValidationError()

    submodels: dict[str, DimensionalSubmodelRecord] = {}
    entities: dict[str, list[DimensionalEntityRecord]] = {}
    attributes: dict[tuple[str, str], DimensionalAttributeRecord] = {}
    relationships: dict[
        tuple[str, str, str, str, str, str],
        DimensionalRelationshipRecord,
    ] = {}
    for partition in partitions:
        for record in partition.submodels:
            key = normalize_model_key_value(record.dimensional_submodel_name)
            existing = submodels.setdefault(key, record)
            if existing != record:
                raise AgentCandidateValidationError()
        for record in partition.entities:
            entities.setdefault(
                normalize_model_key_value(record.dimensional_entity_name),
                [],
            ).append(record)
        for record in partition.attributes:
            key = (
                normalize_model_key_value(record.dimensional_entity_name),
                normalize_model_key_value(record.dimensional_attribute_name),
            )
            existing = attributes.setdefault(key, record)
            if existing != record:
                raise AgentCandidateValidationError()
        for record in partition.relationships:
            key = _relationship_key(record)
            existing = relationships.setdefault(key, record)
            if existing != record:
                raise AgentCandidateValidationError()
    return DetailedDimensionalReconciliationCandidate(
        submodels=tuple(submodels.values()),
        entities=tuple(_merge_entity_records(tuple(records)) for records in entities.values()),
        attributes=tuple(attributes.values()),
        relationships=tuple(relationships.values()),
        reviewed_submodel_refs=reviewed_submodel_refs,
        reviewed_entity_refs=reviewed_entity_refs,
        reviewed_relationship_signal_refs=reviewed_relationship_signal_refs,
        reviewed_applied_record_refs=reviewed_applied_record_refs,
    )


def build_dimensional_draft_manifest(
    *,
    topology: DetailedDimensionalTopologyReconciliation,
    entity_details: tuple[DetailedDimensionalEntityDetail, ...],
    relationship_ledger: DetailedDimensionalRelationshipSignalLedger,
    applied_record_refs: tuple[str, ...],
) -> DetailedDimensionalDraftManifest:
    """Digest exact ordered draft identities without embedding the full draft."""

    records = _dimensional_draft_identity_documents(
        topology=topology,
        entity_details=entity_details,
    )
    if len(applied_record_refs) != len(set(applied_record_refs)):
        raise AgentCandidateValidationError()
    signal_documents = [item.model_dump(mode="json") for item in relationship_ledger.signals]
    return DetailedDimensionalDraftManifest(
        draft_record_count=len(records),
        draft_manifest_digest=dimensional_json_digest(cast(JsonValue, records)),
        relationship_signal_count=len(relationship_ledger.signals),
        relationship_signal_digest=dimensional_json_digest(cast(JsonValue, signal_documents)),
        applied_record_count=len(applied_record_refs),
        applied_record_digest=dimensional_json_digest(cast(JsonValue, list(applied_record_refs))),
    )


def _dimensional_draft_identity_documents(
    *,
    topology: DetailedDimensionalTopologyReconciliation,
    entity_details: tuple[DetailedDimensionalEntityDetail, ...],
) -> list[JsonValue]:
    detail_by_ref = {item.canonical_entity_ref: item for item in entity_details}
    if len(detail_by_ref) != len(entity_details) or tuple(detail_by_ref) != tuple(
        item.canonical_entity_ref for item in topology.entities
    ):
        raise AgentCandidateValidationError()
    records: list[JsonValue] = []
    for item in topology.submodels:
        records.append(
            cast(
                JsonValue,
                {
                    "record_ref": _submodel_record_ref(item.submodel),
                    "record_digest": dimensional_json_digest(item.submodel.model_dump(mode="json")),
                },
            )
        )
    for entity in topology.entities:
        detail = detail_by_ref[entity.canonical_entity_ref]
        records.append(
            cast(
                JsonValue,
                {
                    "record_ref": _entity_record_ref(detail.entity),
                    "record_digest": dimensional_json_digest(detail.entity.model_dump(mode="json")),
                },
            )
        )
        records.extend(
            cast(
                JsonValue,
                {
                    "record_ref": _attribute_record_ref(attribute),
                    "record_digest": dimensional_json_digest(attribute.model_dump(mode="json")),
                },
            )
            for attribute in detail.attributes
        )
    refs = tuple(cast(str, cast(dict[str, JsonValue], item)["record_ref"]) for item in records)
    if len(refs) != len(set(refs)):
        raise AgentCandidateValidationError()
    return records


def materialize_dimensional_reviewed_candidate(
    *,
    topology: DetailedDimensionalTopologyReconciliation,
    entity_details: tuple[DetailedDimensionalEntityDetail, ...],
    relationship_ledger: DetailedDimensionalRelationshipSignalLedger,
    manifest: DetailedDimensionalDraftManifest,
    receipts: tuple[DetailedDimensionalReconciliationReceipt, ...],
    applied_record_refs: tuple[str, ...],
) -> JsonValue:
    """Merge reviewed relationships with already validated immutable base records."""

    expected_partition_refs = tuple(
        f"reconciliation_{position:05d}" for position in range(1, len(receipts) + 1)
    )
    actual_partition_refs = tuple(item.partition_ref for item in receipts)
    reviewed_signal_refs = tuple(
        reference for item in receipts for reference in item.reviewed_relationship_signal_refs
    )
    expected_manifest = build_dimensional_draft_manifest(
        topology=topology,
        entity_details=entity_details,
        relationship_ledger=relationship_ledger,
        applied_record_refs=applied_record_refs,
    )
    if (
        not receipts
        or actual_partition_refs != expected_partition_refs
        or manifest != expected_manifest
        or any(item.manifest != manifest for item in receipts)
        or not _exact_ordered_unique(reviewed_signal_refs, relationship_ledger.signal_refs)
    ):
        raise AgentCandidateValidationError()
    relationships: dict[
        tuple[str, str, str, str, str, str],
        DimensionalRelationshipRecord,
    ] = {}
    for receipt in receipts:
        for relationship in receipt.relationships:
            key = _relationship_key(relationship)
            if key in relationships:
                raise AgentCandidateValidationError()
            relationships[key] = relationship
    return cast(
        JsonValue,
        {
            "submodels": [item.submodel.model_dump(mode="json") for item in topology.submodels],
            "entities": [item.entity.model_dump(mode="json") for item in entity_details],
            "attributes": [
                attribute.model_dump(mode="json")
                for item in entity_details
                for attribute in item.attributes
            ],
            "relationships": [
                relationships[key].model_dump(mode="json") for key in sorted(relationships)
            ],
        },
    )


def build_projected_dimensional_validation_packages(
    *,
    projected_changes: tuple[StageModelChange, ...],
    package_size: int,
    max_packages: int,
) -> tuple[DetailedDimensionalValidationPackage, ...]:
    """Create stable packages from the exact code-projected Dimensional changes."""

    datasets = tuple(change.dataset for change in projected_changes)
    if len(datasets) != len(set(datasets)) or any(
        dataset
        not in (
            "dimensional_submodel",
            "dimensional_entity",
            "dimensional_attribute",
            "dimensional_relationship",
        )
        for dataset in datasets
    ):
        raise InvalidRequestError("Projected Dimensional validation input is invalid.")

    submodels: list[DimensionalSubmodelRecord] = []
    entities: list[DimensionalEntityRecord] = []
    attributes: list[DimensionalAttributeRecord] = []
    relationships: list[DimensionalRelationshipRecord] = []
    for change in projected_changes:
        for raw_record in change.records:
            candidate = cast(JsonValue, raw_record)
            if change.dataset == "dimensional_submodel":
                record = _parse(DimensionalSubmodelRecord, candidate)
                if record is None:
                    raise InvalidRequestError(
                        "Projected Dimensional validation records are invalid."
                    )
                submodels.append(record)
            elif change.dataset == "dimensional_entity":
                record = _parse(DimensionalEntityRecord, candidate)
                if record is None:
                    raise InvalidRequestError(
                        "Projected Dimensional validation records are invalid."
                    )
                entities.append(record)
            elif change.dataset == "dimensional_attribute":
                record = _parse(DimensionalAttributeRecord, candidate)
                if record is None:
                    raise InvalidRequestError(
                        "Projected Dimensional validation records are invalid."
                    )
                attributes.append(record)
            elif change.dataset == "dimensional_relationship":
                record = _parse(DimensionalRelationshipRecord, candidate)
                if record is None:
                    raise InvalidRequestError(
                        "Projected Dimensional validation records are invalid."
                    )
                relationships.append(record)

    return _package_validation_records(
        records=_validation_records_for_sections(
            submodels=submodels,
            entities=entities,
            attributes=attributes,
            relationships=relationships,
        ),
        package_size=package_size,
        max_packages=max_packages,
    )


def build_dimensional_validation_packages(
    *,
    candidate: DetailedDimensionalReconciliationCandidate,
    package_size: int,
    max_packages: int,
) -> tuple[DetailedDimensionalValidationPackage, ...]:
    """Create stable bounded packages; workers receive no writable candidate surface."""

    return _package_validation_records(
        records=_validation_records(candidate),
        package_size=package_size,
        max_packages=max_packages,
    )


def _package_validation_records(
    *,
    records: Sequence[DetailedDimensionalValidationRecord],
    package_size: int,
    max_packages: int,
) -> tuple[DetailedDimensionalValidationPackage, ...]:
    if not 1 <= package_size <= 1_000 or not 1 <= max_packages <= 10_000:
        raise InvalidRequestError("The Dimensional validation package policy is invalid.")
    packages = tuple(
        DetailedDimensionalValidationPackage(
            package_ref=f"validation_{position:05d}",
            records=tuple(records[offset : offset + package_size]),
            record_digests=tuple(
                dimensional_json_digest(item.record.model_dump(mode="json"))
                for item in records[offset : offset + package_size]
            ),
        )
        for position, offset in enumerate(range(0, len(records), package_size), start=1)
    )
    if not packages or len(packages) > max_packages:
        raise InvalidRequestError("Dimensional validation exceeds its configured package limit.")
    return packages


def decide_dimensional_detailed_handoff(
    *,
    reconciliation_validator: DetailedDimensionalReconciliationValidator,
    reconciliation_candidate: JsonValue,
    validation_lead: DetailedDimensionalValidationLead,
    worker_results: tuple[DetailedDimensionalValidationWorkerResult, ...],
) -> DetailedDimensionalHandoffDecision:
    """Route blockers only to reconciliation; otherwise expose one complete candidate."""

    reconciliation_validator.parse_validated(reconciliation_candidate)
    findings = tuple(finding for result in worker_results for finding in result.findings)
    package_refs = tuple(result.package_ref for result in worker_results)
    finding_refs = tuple(item.finding_ref for item in findings)
    blocking_refs = tuple(item.finding_ref for item in findings if item.severity == "error")
    if (
        not _exact_unique(validation_lead.reviewed_package_refs, package_refs)
        or not _exact_unique(validation_lead.reviewed_finding_refs, finding_refs)
        or not _exact_unique(validation_lead.blocking_finding_refs, blocking_refs)
        or len(package_refs) != len(set(package_refs))
        or len(finding_refs) != len(set(finding_refs))
        or ((validation_lead.repair_brief is not None) != bool(blocking_refs))
    ):
        raise AgentCandidateValidationError()
    if validation_lead.blocking_finding_refs:
        blocking = set(validation_lead.blocking_finding_refs)
        failures = tuple(finding for finding in findings if finding.finding_ref in blocking)
        if len(failures) != len(blocking):
            raise AgentCandidateValidationError()
        return DetailedDimensionalHandoffDecision(
            next_stage="whole_model_reconciliation",
            validation_failures=failures,
            handoff_candidate=None,
        )
    return DetailedDimensionalHandoffDecision(
        next_stage="handoff",
        validation_failures=(),
        handoff_candidate=reconciliation_validator.materialize_validated(reconciliation_candidate),
    )


def dimensional_applied_record_refs(section: DimensionalSection | None) -> tuple[str, ...]:
    if section is None:
        return ()
    refs = [_submodel_record_ref(item) for item in section.submodels]
    refs.extend(_entity_record_ref(item) for item in section.entities)
    refs.extend(_attribute_record_ref(item) for item in section.attributes)
    refs.extend(_relationship_record_ref(item) for item in section.relationships)
    if len(refs) != len(set(refs)):
        raise ValueError("Applied Dimensional record references must be unique")
    return tuple(sorted(refs))


def _validation_records(
    candidate: DetailedDimensionalReconciliationCandidate,
) -> list[DetailedDimensionalValidationRecord]:
    return _validation_records_for_sections(
        submodels=candidate.submodels,
        entities=candidate.entities,
        attributes=candidate.attributes,
        relationships=candidate.relationships,
    )


def _validation_records_for_sections(
    *,
    submodels: Sequence[DimensionalSubmodelRecord],
    entities: Sequence[DimensionalEntityRecord],
    attributes: Sequence[DimensionalAttributeRecord],
    relationships: Sequence[DimensionalRelationshipRecord],
) -> list[DetailedDimensionalValidationRecord]:
    records: list[DetailedDimensionalValidationRecord] = []
    for item in sorted(
        submodels,
        key=lambda value: normalize_model_key_value(value.dimensional_submodel_name),
    ):
        records.append(
            DetailedDimensionalValidationRecord(
                record_ref=_submodel_record_ref(item),
                dataset="dimensional_submodel",
                record=item,
            )
        )
    for item in sorted(
        entities,
        key=lambda value: normalize_model_key_value(value.dimensional_entity_name),
    ):
        records.append(
            DetailedDimensionalValidationRecord(
                record_ref=_entity_record_ref(item),
                dataset="dimensional_entity",
                record=item,
            )
        )
    for item in sorted(
        attributes,
        key=lambda value: (
            normalize_model_key_value(value.dimensional_entity_name),
            normalize_model_key_value(value.dimensional_attribute_name),
        ),
    ):
        records.append(
            DetailedDimensionalValidationRecord(
                record_ref=_attribute_record_ref(item),
                dataset="dimensional_attribute",
                record=item,
            )
        )
    for item in sorted(relationships, key=_relationship_key):
        records.append(
            DetailedDimensionalValidationRecord(
                record_ref=_relationship_record_ref(item),
                dataset="dimensional_relationship",
                record=item,
            )
        )
    refs = tuple(item.record_ref for item in records)
    if len(refs) != len(set(refs)):
        raise InvalidRequestError("Dimensional validation record identities must be unique.")
    return records


def _materialize(candidate: DetailedDimensionalReconciliationCandidate) -> JsonValue:
    return cast(
        JsonValue,
        {
            "submodels": [item.model_dump(mode="json") for item in candidate.submodels],
            "entities": [item.model_dump(mode="json") for item in candidate.entities],
            "attributes": [item.model_dump(mode="json") for item in candidate.attributes],
            "relationships": [item.model_dump(mode="json") for item in candidate.relationships],
        },
    )


def _merge_entity_records(
    records: tuple[DimensionalEntityRecord, ...],
) -> DimensionalEntityRecord:
    if not records:
        raise AgentCandidateValidationError()
    baseline = records[0].model_dump(mode="json")
    baseline.pop("sources")
    sources: dict[tuple[str, ...], dict[str, JsonValue]] = {}
    for record in records:
        comparable = record.model_dump(mode="json")
        raw_sources = comparable.pop("sources")
        if comparable != baseline or not isinstance(raw_sources, list):
            raise AgentCandidateValidationError()
        for source in record.sources:
            key = _entity_source_identity(source)
            raw = cast(dict[str, JsonValue], source.model_dump(mode="json"))
            existing = sources.get(key)
            if existing is not None:
                existing_without_order = {
                    name: value for name, value in existing.items() if name != "source_order"
                }
                raw_without_order = {
                    name: value for name, value in raw.items() if name != "source_order"
                }
                if existing_without_order != raw_without_order:
                    raise AgentCandidateValidationError()
                continue
            sources[key] = raw
    baseline["sources"] = [
        {**source, "source_order": position}
        for position, source in enumerate(sources.values(), start=1)
    ]
    merged = _parse(DimensionalEntityRecord, cast(JsonValue, baseline))
    if merged is None:
        raise AgentCandidateValidationError()
    return merged


def _safe_entity(entity: DimensionalEntityRecord) -> bool:
    return (
        not entity.dimensional_entity_is_locked
        and all(not item.membership_is_locked for item in entity.submodels)
        and all(not item.is_locked for item in entity.sources)
    )


def _safe_attribute(attribute: DimensionalAttributeRecord) -> bool:
    return (
        not attribute.dimensional_attribute_is_locked
        and attribute.dimensional_attribute_role not in ("technical", "audit")
        and attribute.dimensional_attribute_key_role not in ("surrogate", "foreign")
        and not attribute.dimensional_attribute_is_audit_column
        and all(not item.is_locked for item in attribute.sources)
    )


def _physical_attribute_sources(
    attribute: DimensionalAttributeRecord,
) -> tuple[PhysicalAttributeKey, ...]:
    return tuple(
        sorted(
            (
                source.source_attribute
                for source in attribute.sources
                if isinstance(source, AttributePhysicalSourceRecord)
            ),
            key=_physical_attribute_key,
        )
    )


def _relationship_key(
    item: DimensionalRelationshipRecord,
) -> tuple[str, str, str, str, str, str]:
    return (
        normalize_model_key_value(item.from_dimensional_entity_name),
        normalize_model_key_value(item.from_dimensional_attribute_name),
        normalize_model_key_value(item.to_dimensional_entity_name),
        normalize_model_key_value(item.to_dimensional_attribute_name),
        normalize_model_key_value(item.dimensional_relationship_kind),
        normalize_model_key_value(item.dimensional_relationship_role_name or ""),
    )


def _submodel_record_ref(item: DimensionalSubmodelRecord) -> str:
    return f"submodel:{normalize_model_key_value(item.dimensional_submodel_name)}"


def _entity_record_ref(item: DimensionalEntityRecord) -> str:
    return f"entity:{normalize_model_key_value(item.dimensional_entity_name)}"


def _attribute_record_ref(item: DimensionalAttributeRecord) -> str:
    return "attribute:" + json.dumps(
        (
            normalize_model_key_value(item.dimensional_entity_name),
            normalize_model_key_value(item.dimensional_attribute_name),
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _relationship_record_ref(item: DimensionalRelationshipRecord) -> str:
    return "relationship:" + json.dumps(
        _relationship_key(item),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _entity_source_identity(source: _DimensionalEntitySource) -> tuple[str, ...]:
    if isinstance(source, DimensionalObjectSourceRecord):
        return ("object", *_physical_object_key(source.source_object))
    return (
        "assertion",
        normalize_model_key_value(source.assertion_record.modeling_assertion_record_key),
    )


def _attribute_source_identity(source: _DimensionalAttributeSource) -> tuple[str, ...]:
    if isinstance(source, AttributePhysicalSourceRecord):
        return ("attribute", *_physical_attribute_key(source.source_attribute))
    return (
        "assertion",
        normalize_model_key_value(source.assertion_record.modeling_assertion_record_key),
    )


def _physical_object_key(item: PhysicalObjectKey) -> _ObjectIdentity:
    return (
        normalize_model_key_value(item.tenant_code),
        normalize_model_key_value(item.system_code),
        normalize_model_key_value(item.connection_code),
        normalize_model_key_value(item.object_schema),
        normalize_model_key_value(item.object_name),
    )


def _physical_attribute_key(item: PhysicalAttributeKey) -> _AttributeIdentity:
    return (*_physical_object_key(item), normalize_model_key_value(item.attribute_name))


def _exact_unique(actual: Sequence[str], expected: Sequence[str]) -> bool:
    return len(actual) == len(set(actual)) and set(actual) == set(expected)


def _exact_ordered_unique(actual: Sequence[str], expected: Sequence[str]) -> bool:
    return len(actual) == len(set(actual)) and tuple(actual) == tuple(expected)


def _validate_result_byte_limit(maximum_bytes: int | None) -> None:
    if maximum_bytes is not None and not 1 <= maximum_bytes <= 10 * 1024 * 1024:
        raise ValueError("Dimensional detailed result byte limit is invalid")


def dimensional_json_bytes(value: JsonValue) -> int:
    """Return deterministic canonical UTF-8 JSON bytes for a Dimensional value."""

    return len(_dimensional_json_data(value))


def dimensional_json_digest(value: JsonValue) -> str:
    """Return the SHA-256 of deterministic canonical Dimensional JSON."""

    return sha256(_dimensional_json_data(value)).hexdigest()


def _dimensional_json_data(value: JsonValue) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise AgentCandidateValidationError() from None


def _parse_bounded[CandidateT: BaseModel](
    model: type[CandidateT],
    candidate: JsonValue,
    *,
    maximum_bytes: int | None,
) -> CandidateT | None:
    if maximum_bytes is not None and dimensional_json_bytes(candidate) > maximum_bytes:
        return None
    return _parse(model, candidate)


def _parse[CandidateT: BaseModel](
    model: type[CandidateT],
    candidate: JsonValue,
) -> CandidateT | None:
    try:
        return model.model_validate_json(
            json.dumps(
                candidate,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ),
            strict=True,
        )
    except (TypeError, ValueError, ValidationError):
        return None


def _output_schema(model: type[BaseModel]) -> dict[str, JsonValue]:
    schema = cast(dict[str, JsonValue], deepcopy(model.model_json_schema()))
    enrich_agent_output_model_definitions(schema)
    return schema


def _parse_failure_validation(
    model: type[BaseModel],
    candidate: JsonValue,
    fallback_code: str,
    fallback_message: str,
) -> AgentCandidateValidation:
    _, issues = parse_pydantic_candidate(model, candidate)
    cross_field_issues = tuple(
        issue for issue in issues if issue.code == "candidate.cross_field_invalid"
    )
    if cross_field_issues:
        return AgentCandidateValidation(
            issues=tuple(
                AgentValidationIssue(
                    code=fallback_code,
                    path=issue.path,
                    message=issue.message,
                )
                for issue in cross_field_issues
            )
        )
    return _validation_issue(fallback_code, fallback_message)


def _validation_issue(code: str, message: str) -> AgentCandidateValidation:
    return AgentCandidateValidation(
        issues=(AgentValidationIssue(code=code, path=(), message=message),)
    )


def _set_agent_output_constraints(value: JsonValue) -> None:
    if isinstance(value, list):
        for child in value:
            _set_agent_output_constraints(child)
        return
    if not isinstance(value, dict):
        return
    properties = value.get("properties")
    if isinstance(properties, dict):
        for name, property_schema in properties.items():
            if isinstance(property_schema, dict) and (
                name.endswith("_is_locked") or name == "is_locked"
            ):
                property_schema["const"] = False
            elif isinstance(property_schema, dict) and name == "dimensional_attribute_role":
                property_schema["enum"] = [
                    "key",
                    "descriptor",
                    "measure",
                    "degenerate_dimension",
                    "bridge_weight",
                ]
            elif isinstance(property_schema, dict) and name == "dimensional_attribute_key_role":
                property_schema["enum"] = ["none", "business"]
            elif (
                isinstance(property_schema, dict)
                and name == "dimensional_attribute_is_audit_column"
            ):
                property_schema["const"] = False
    for child in value.values():
        _set_agent_output_constraints(child)


__all__ = [
    "DetailedDimensionalEntityDetail",
    "DetailedDimensionalEntityDetailValidator",
    "DetailedDimensionalDraftManifest",
    "DetailedDimensionalHandoffDecision",
    "DetailedDimensionalPolicy",
    "DetailedDimensionalReconciliationCandidate",
    "DetailedDimensionalReconciliationReceipt",
    "DetailedDimensionalReconciliationReceiptValidator",
    "DetailedDimensionalReconciliationValidator",
    "DetailedDimensionalRelationshipSignal",
    "DetailedDimensionalRelationshipSignalLedger",
    "DetailedDimensionalTopologyContribution",
    "DetailedDimensionalTopologyContributionValidator",
    "DetailedDimensionalTopologyReconciliation",
    "DetailedDimensionalTopologyReconciliationValidator",
    "DetailedDimensionalValidationLead",
    "DetailedDimensionalValidationLeadValidator",
    "DetailedDimensionalValidationPackage",
    "DetailedDimensionalValidationRecord",
    "DetailedDimensionalValidationWorkerResult",
    "DetailedDimensionalValidationWorkerValidator",
    "build_projected_dimensional_validation_packages",
    "build_dimensional_draft_manifest",
    "build_dimensional_relationship_signal_ledger",
    "build_dimensional_validation_packages",
    "decide_dimensional_detailed_handoff",
    "dimensional_json_bytes",
    "dimensional_json_digest",
    "load_default_detailed_dimensional_policy",
    "dimensional_applied_record_refs",
    "merge_dimensional_entity_detail_partitions",
    "merge_dimensional_reconciliation_partitions",
    "merge_dimensional_topology_partitions",
    "materialize_dimensional_reviewed_candidate",
]
