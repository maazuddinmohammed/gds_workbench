"""Immutable contracts for deterministic Logical detailed coverage."""

from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
from typing import Literal, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    AttributePhysicalSourceRecord,
    LogicalAssertionSourceRecord,
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalObjectSourceRecord,
    LogicalRelationshipRecord,
    LogicalSubmodelRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    normalize_model_key_value,
)
from gds_etl_workbench.tools.snapshots.model.contracts import LogicalSection
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
type _LogicalRecord = (
    LogicalSubmodelRecord | LogicalEntityRecord | LogicalAttributeRecord | LogicalRelationshipRecord
)
type _LogicalDataset = Literal[
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
]


class DetailedLogicalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    max_relationship_signals: int = Field(ge=1, le=50_000)
    validation_package_size: int = Field(ge=1, le=1_000)
    max_validation_packages: int = Field(ge=1, le=10_000)


def load_default_detailed_logical_policy() -> DetailedLogicalPolicy:
    resource = files("gds_workbench_api").joinpath("config/logical_detailed.json")
    raw = resource.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("Logical detailed configuration is too large")
    return DetailedLogicalPolicy.model_validate_json(raw, strict=True)


class DetailedLogicalTopologyProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    local_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    candidate_entity_name: str = Field(min_length=1, max_length=255)
    candidate_entity_type: Literal[
        "core",
        "reference",
        "transaction",
        "event",
        "bridge",
        "history",
        "snapshot",
        "association",
        "aggregate",
        "other",
    ]
    candidate_entity_grain: str = Field(min_length=1, max_length=2_000)
    candidate_submodel_names: tuple[str, ...] = Field(max_length=100)
    source_attributes: tuple[PhysicalAttributeKey, ...] = Field(
        min_length=1,
        max_length=10_000,
    )

    @model_validator(mode="after")
    def validate_unique_values(self) -> DetailedLogicalTopologyProposal:
        submodels = tuple(normalize_model_key_value(item) for item in self.candidate_submodel_names)
        attributes = tuple(_physical_attribute_key(item) for item in self.source_attributes)
        if len(submodels) != len(set(submodels)) or len(attributes) != len(set(attributes)):
            raise ValueError("Logical topology proposal values must be unique")
        return self


class DetailedLogicalTopologyContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    contribution_ref: str = Field(pattern=r"^object_[0-9]{5}(?:_batch_[0-9]{5})?$")
    source_object: PhysicalObjectKey
    disposition: Literal["represented", "not_logical", "needs_review"]
    rationale: str = Field(min_length=1, max_length=2_000)
    proposals: tuple[DetailedLogicalTopologyProposal, ...] = Field(max_length=200)

    @model_validator(mode="after")
    def validate_disposition(self) -> DetailedLogicalTopologyContribution:
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


class DetailedLogicalSubmodelTopology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    canonical_submodel_ref: str = Field(pattern=_REFERENCE_PATTERN)
    submodel: LogicalSubmodelRecord = Field(repr=False)


class DetailedLogicalEntityTopology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    canonical_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    logical_entity_name: str = Field(min_length=1, max_length=255)
    contribution_refs: tuple[str, ...] = Field(min_length=1, max_length=50_000)
    submodel_refs: tuple[str, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_unique_values(self) -> DetailedLogicalEntityTopology:
        if len(self.contribution_refs) != len(set(self.contribution_refs)) or len(
            self.submodel_refs
        ) != len(set(self.submodel_refs)):
            raise ValueError("Logical topology Entity references must be unique")
        return self


class DetailedLogicalTopologyReconciliation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    submodels: tuple[DetailedLogicalSubmodelTopology, ...] = Field(max_length=20_000)
    entities: tuple[DetailedLogicalEntityTopology, ...] = Field(max_length=20_000)
    discarded_contribution_refs: tuple[str, ...] = Field(max_length=50_000)


class DetailedLogicalEntityDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    canonical_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    entity: LogicalEntityRecord = Field(repr=False)
    attributes: tuple[LogicalAttributeRecord, ...] = Field(
        min_length=1,
        max_length=10_000,
        repr=False,
    )


class DetailedLogicalRelationshipSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    signal_ref: str = Field(pattern=r"^relationship_signal_[0-9]{5}$")
    signal_type: Literal["matching_attribute_name"]
    from_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    from_logical_entity_name: str = Field(min_length=1, max_length=255)
    from_logical_attribute_name: str = Field(min_length=1, max_length=255)
    from_source_attributes: tuple[PhysicalAttributeKey, ...] = Field(
        min_length=1,
        max_length=1_000,
    )
    to_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    to_logical_entity_name: str = Field(min_length=1, max_length=255)
    to_logical_attribute_name: str = Field(min_length=1, max_length=255)
    to_source_attributes: tuple[PhysicalAttributeKey, ...] = Field(
        min_length=1,
        max_length=1_000,
    )


class DetailedLogicalRelationshipSignalLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    signals: tuple[DetailedLogicalRelationshipSignal, ...] = Field(max_length=50_000)

    @property
    def signal_refs(self) -> tuple[str, ...]:
        return tuple(item.signal_ref for item in self.signals)


class DetailedLogicalReconciliationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    submodels: tuple[LogicalSubmodelRecord, ...] = Field(max_length=20_000)
    entities: tuple[LogicalEntityRecord, ...] = Field(max_length=20_000)
    attributes: tuple[LogicalAttributeRecord, ...] = Field(max_length=20_000)
    relationships: tuple[LogicalRelationshipRecord, ...] = Field(max_length=20_000)
    reviewed_submodel_refs: tuple[str, ...] = Field(max_length=20_000)
    reviewed_entity_refs: tuple[str, ...] = Field(max_length=20_000)
    reviewed_relationship_signal_refs: tuple[str, ...] = Field(max_length=50_000)
    reviewed_applied_record_refs: tuple[str, ...] = Field(max_length=80_000)

    @model_validator(mode="after")
    def validate_size(self) -> DetailedLogicalReconciliationCandidate:
        total = (
            len(self.submodels)
            + len(self.entities)
            + len(self.attributes)
            + len(self.relationships)
        )
        if total > 20_000:
            raise ValueError("Logical reconciliation candidates must be bounded")
        return self


class DetailedLogicalValidationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    record_ref: str = Field(min_length=1, max_length=1_000)
    dataset: _LogicalDataset
    record: _LogicalRecord = Field(repr=False)

    @model_validator(mode="after")
    def validate_dataset(self) -> DetailedLogicalValidationRecord:
        expected: _LogicalDataset
        if isinstance(self.record, LogicalSubmodelRecord):
            expected = "logical_submodel"
        elif isinstance(self.record, LogicalEntityRecord):
            expected = "logical_entity"
        elif isinstance(self.record, LogicalAttributeRecord):
            expected = "logical_attribute"
        else:
            expected = "logical_relationship"
        if self.dataset != expected:
            raise ValueError("Logical validation record dataset does not match its record")
        return self


class DetailedLogicalValidationPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    package_ref: str = Field(pattern=_VALIDATION_REF_PATTERN)
    records: tuple[DetailedLogicalValidationRecord, ...] = Field(
        min_length=1,
        max_length=1_000,
        repr=False,
    )
    record_digests: tuple[str, ...] = Field(default=(), max_length=1_000)

    @model_validator(mode="after")
    def validate_manifest(self) -> DetailedLogicalValidationPackage:
        expected = tuple(
            logical_json_digest(item.record.model_dump(mode="json")) for item in self.records
        )
        if len(self.record_refs) != len(set(self.record_refs)) or (
            self.record_digests and self.record_digests != expected
        ):
            raise ValueError("Logical validation package manifest is invalid")
        return self

    @property
    def record_refs(self) -> tuple[str, ...]:
        return tuple(item.record_ref for item in self.records)


class DetailedLogicalValidationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    finding_ref: str = Field(pattern=_FINDING_REF_PATTERN)
    severity: Literal["warning", "error"]
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    message: str = Field(min_length=1, max_length=500)
    record_refs: tuple[str, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_record_refs(self) -> DetailedLogicalValidationFinding:
        if len(self.record_refs) != len(set(self.record_refs)):
            raise ValueError("Logical validation finding record references must be unique")
        return self


class DetailedLogicalValidationWorkerResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    package_ref: str = Field(pattern=_VALIDATION_REF_PATTERN)
    reviewed_record_refs: tuple[str, ...] = Field(min_length=1, max_length=1_000)
    findings: tuple[DetailedLogicalValidationFinding, ...] = Field(max_length=200)


class DetailedLogicalValidationLead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    reviewed_package_refs: tuple[str, ...] = Field(min_length=1, max_length=10_000)
    reviewed_finding_refs: tuple[str, ...] = Field(max_length=2_000_000)
    blocking_finding_refs: tuple[str, ...] = Field(max_length=2_000_000)
    repair_brief: str | None = Field(default=None, max_length=32_768)


class DetailedLogicalHandoffDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    next_stage: Literal["whole_model_reconciliation", "handoff"]
    validation_failures: tuple[DetailedLogicalValidationFinding, ...] = Field(max_length=2_000_000)
    handoff_candidate: JsonValue | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_decision(self) -> DetailedLogicalHandoffDecision:
        if self.next_stage == "whole_model_reconciliation":
            if not self.validation_failures or self.handoff_candidate is not None:
                raise ValueError("A reconciliation decision contains failures only")
        elif self.validation_failures or self.handoff_candidate is None:
            raise ValueError("A handoff decision contains one complete candidate only")
        return self


class DetailedLogicalTopologyContributionValidator:
    def __init__(
        self,
        *,
        contribution_ref: str,
        source_object: PhysicalObjectKey,
        source_attributes: tuple[PhysicalAttributeKey, ...],
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
        if not source_attributes or len(source_attributes) > 10_000:
            raise ValueError("Logical topology Attribute context must be bounded and nonempty")
        expected_object = _physical_object_key(source_object)
        attribute_keys = tuple(_physical_attribute_key(item) for item in source_attributes)
        if len(attribute_keys) != len(set(attribute_keys)) or any(
            key[:5] != expected_object for key in attribute_keys
        ):
            raise ValueError("Logical topology Attribute context must match one source Object")
        _validate_result_byte_limit(max_result_bytes)
        self._contribution_ref = contribution_ref
        self._source_object = source_object
        self._source_attributes = frozenset(attribute_keys)
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedLogicalTopologyContribution)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = self._parse(candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedLogicalTopologyContribution,
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

    def parse_validated(self, candidate: JsonValue) -> DetailedLogicalTopologyContribution:
        parsed = self._parse(candidate)
        if (
            parsed is None
            or not self._has_fixed_identity(parsed)
            or not self._has_exact_coverage(parsed)
        ):
            raise AgentCandidateValidationError()
        return parsed

    def _has_fixed_identity(self, candidate: DetailedLogicalTopologyContribution) -> bool:
        return candidate.contribution_ref == self._contribution_ref and _physical_object_key(
            candidate.source_object
        ) == _physical_object_key(self._source_object)

    def _has_exact_coverage(self, candidate: DetailedLogicalTopologyContribution) -> bool:
        if candidate.disposition != "represented":
            return not candidate.proposals
        actual = [
            _physical_attribute_key(attribute)
            for proposal in candidate.proposals
            for attribute in proposal.source_attributes
        ]
        return len(actual) == len(set(actual)) and set(actual) == set(self._source_attributes)

    def _parse(self, candidate: JsonValue) -> DetailedLogicalTopologyContribution | None:
        if (
            self._max_result_bytes is not None
            and logical_json_bytes(candidate) > self._max_result_bytes
        ):
            return None
        return _parse(DetailedLogicalTopologyContribution, candidate)


class DetailedLogicalTopologyReconciliationValidator:
    def __init__(
        self,
        *,
        contributions: tuple[DetailedLogicalTopologyContribution, ...],
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
        if not contributions or len(contributions) > 50_000:
            raise ValueError("Logical topology contributions must be bounded and nonempty")
        contribution_refs = tuple(item.contribution_ref for item in contributions)
        if len(contribution_refs) != len(set(contribution_refs)):
            raise ValueError("Logical topology contribution references must be unique")
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
            raise ValueError("Logical topology proposal references must be unique")
        _validate_result_byte_limit(max_result_bytes)
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedLogicalTopologyReconciliation)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = self._parse(candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedLogicalTopologyReconciliation,
                candidate,
                "detailed.topology_reconciliation_invalid",
                "The Logical topology reconciliation does not match its bounded schema.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.topology_reconciliation_coverage_invalid",
                "The Logical topology ledger must cover every proposal exactly once.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedLogicalTopologyReconciliation:
        parsed = self._parse(candidate)
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _has_exact_coverage(self, candidate: DetailedLogicalTopologyReconciliation) -> bool:
        submodel_refs = tuple(item.canonical_submodel_ref for item in candidate.submodels)
        submodel_names = tuple(
            normalize_model_key_value(item.submodel.logical_submodel_name)
            for item in candidate.submodels
        )
        entity_refs = tuple(item.canonical_entity_ref for item in candidate.entities)
        entity_names = tuple(
            normalize_model_key_value(item.logical_entity_name) for item in candidate.entities
        )
        if any(
            len(values) != len(set(values))
            for values in (submodel_refs, submodel_names, entity_refs, entity_names)
        ) or any(item.submodel.logical_submodel_is_locked for item in candidate.submodels):
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
                normalize_model_key_value(submodel_by_ref[reference].logical_submodel_name)
                for reference in entity.submodel_refs
            }
            if actual_names != expected_names:
                return False
            referenced_submodels.update(entity.submodel_refs)
        return referenced_submodels == set(submodel_refs)

    def _parse(self, candidate: JsonValue) -> DetailedLogicalTopologyReconciliation | None:
        if (
            self._max_result_bytes is not None
            and logical_json_bytes(candidate) > self._max_result_bytes
        ):
            return None
        return _parse(DetailedLogicalTopologyReconciliation, candidate)


class DetailedLogicalEntityDetailValidator:
    def __init__(
        self,
        *,
        entity: DetailedLogicalEntityTopology,
        topology: DetailedLogicalTopologyReconciliation,
        contributions: tuple[DetailedLogicalTopologyContribution, ...],
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
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
        self._entity_name = normalize_model_key_value(entity.logical_entity_name)
        self._expected_submodels = {
            normalize_model_key_value(submodel_by_ref[ref].logical_submodel_name)
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
        _validate_result_byte_limit(max_result_bytes)
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        schema = _output_schema(DetailedLogicalEntityDetail)
        _set_lock_fields_false(schema)
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = self._parse(candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedLogicalEntityDetail,
                candidate,
                "detailed.entity_detail_invalid",
                "The Logical Entity detail does not match its bounded schema.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.entity_detail_coverage_invalid",
                "The Logical Entity detail must preserve all topology and source coverage.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedLogicalEntityDetail:
        parsed = self._parse(candidate)
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _has_exact_coverage(self, candidate: DetailedLogicalEntityDetail) -> bool:
        if (
            candidate.canonical_entity_ref != self._entity_ref
            or normalize_model_key_value(candidate.entity.logical_entity_name) != self._entity_name
            or not _safe_entity(candidate.entity)
        ):
            return False
        submodels = [
            normalize_model_key_value(item.submodel_name) for item in candidate.entity.submodels
        ]
        objects = [
            _physical_object_key(item.source_object)
            for item in candidate.entity.sources
            if isinstance(item, LogicalObjectSourceRecord)
        ]
        attributes = [
            _physical_attribute_key(source.source_attribute)
            for record in candidate.attributes
            for source in record.sources
            if isinstance(source, AttributePhysicalSourceRecord)
        ]
        attribute_names = [
            normalize_model_key_value(item.logical_attribute_name) for item in candidate.attributes
        ]
        ordinals = [item.logical_attribute_ordinal_position for item in candidate.attributes]
        return (
            len(submodels) == len(set(submodels))
            and set(submodels) == self._expected_submodels
            and len(objects) == len(set(objects))
            and set(objects) == self._expected_objects
            and len(attributes) == len(set(attributes))
            and set(attributes) == self._expected_attributes
            and len(attribute_names) == len(set(attribute_names))
            and len(ordinals) == len(set(ordinals))
            and all(
                normalize_model_key_value(item.logical_entity_name) == self._entity_name
                and _safe_attribute(item)
                for item in candidate.attributes
            )
        )

    def _parse(self, candidate: JsonValue) -> DetailedLogicalEntityDetail | None:
        if (
            self._max_result_bytes is not None
            and logical_json_bytes(candidate) > self._max_result_bytes
        ):
            return None
        return _parse(DetailedLogicalEntityDetail, candidate)


class DetailedLogicalReconciliationValidator:
    def __init__(
        self,
        *,
        topology: DetailedLogicalTopologyReconciliation,
        entity_details: tuple[DetailedLogicalEntityDetail, ...],
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
        self._relationship_signal_refs = relationship_signal_refs
        self._applied_record_refs = applied_record_refs
        self._final_validator = final_validator
        _validate_result_byte_limit(max_result_bytes)
        self._max_result_bytes = max_result_bytes
        self._require_exact_base_records = require_exact_base_records
        if any(
            len(values) != len(set(values))
            for values in (
                self._submodel_refs,
                self._entity_refs,
                relationship_signal_refs,
                applied_record_refs,
            )
        ):
            raise ValueError("Logical detailed reconciliation references must be unique")

    def output_schema(self) -> dict[str, JsonValue]:
        schema = _output_schema(DetailedLogicalReconciliationCandidate)
        _set_lock_fields_false(schema)
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = self._parse(candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedLogicalReconciliationCandidate,
                candidate,
                "detailed.reconciliation_invalid",
                "The Logical whole-model reconciliation does not match its bounded schema.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.reconciliation_coverage_invalid",
                "The Logical whole-model reconciliation must review every required record.",
            )
        if self._final_validator is not None:
            return await self._final_validator.validate(_materialize(parsed))
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedLogicalReconciliationCandidate:
        parsed = self._parse(candidate)
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def materialize_validated(self, candidate: JsonValue) -> JsonValue:
        return _materialize(self.parse_validated(candidate))

    def _has_exact_coverage(self, candidate: DetailedLogicalReconciliationCandidate) -> bool:
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
        submodel_names = {
            normalize_model_key_value(item.logical_submodel_name) for item in candidate.submodels
        }
        entity_names = {
            normalize_model_key_value(item.logical_entity_name) for item in candidate.entities
        }
        attribute_keys = {
            (
                normalize_model_key_value(item.logical_entity_name),
                normalize_model_key_value(item.logical_attribute_name),
            )
            for item in candidate.attributes
        }
        required_submodels = {
            normalize_model_key_value(item.submodel.logical_submodel_name)
            for item in self._topology.submodels
        }
        required_entities = {
            normalize_model_key_value(item.entity.logical_entity_name) for item in self._details
        }
        required_attributes = {
            (
                normalize_model_key_value(attribute.logical_entity_name),
                normalize_model_key_value(attribute.logical_attribute_name),
            )
            for detail in self._details
            for attribute in detail.attributes
        }
        candidate_entity_by_name = {
            normalize_model_key_value(item.logical_entity_name): item for item in candidate.entities
        }
        candidate_attribute_by_key = {
            (
                normalize_model_key_value(item.logical_entity_name),
                normalize_model_key_value(item.logical_attribute_name),
            ): item
            for item in candidate.attributes
        }
        required_records_match = (
            required_submodels == submodel_names
            and required_entities == entity_names
            and required_attributes == attribute_keys
            if self._require_exact_base_records
            else required_submodels <= submodel_names
            and required_entities <= entity_names
            and required_attributes <= attribute_keys
        )
        return (
            required_records_match
            and all(
                _reconciliation_entity_sources_match(
                    required=detail.entity,
                    candidate=candidate_entity_by_name[
                        normalize_model_key_value(detail.entity.logical_entity_name)
                    ],
                )
                for detail in self._details
            )
            and all(
                _physical_attribute_sources(attribute)
                == _physical_attribute_sources(
                    candidate_attribute_by_key[
                        (
                            normalize_model_key_value(attribute.logical_entity_name),
                            normalize_model_key_value(attribute.logical_attribute_name),
                        )
                    ]
                )
                for detail in self._details
                for attribute in detail.attributes
            )
            and len(submodel_names) == len(candidate.submodels)
            and len(entity_names) == len(candidate.entities)
            and len(attribute_keys) == len(candidate.attributes)
            and all(not item.logical_submodel_is_locked for item in candidate.submodels)
            and all(_safe_entity(item) for item in candidate.entities)
            and all(_safe_attribute(item) for item in candidate.attributes)
            and all(not item.logical_relationship_is_locked for item in candidate.relationships)
        )

    def _parse(self, candidate: JsonValue) -> DetailedLogicalReconciliationCandidate | None:
        if (
            self._max_result_bytes is not None
            and logical_json_bytes(candidate) > self._max_result_bytes
        ):
            return None
        return _parse(DetailedLogicalReconciliationCandidate, candidate)


class DetailedLogicalValidationWorkerValidator:
    def __init__(
        self,
        *,
        package: DetailedLogicalValidationPackage,
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
        _validate_result_byte_limit(max_result_bytes)
        self._package = package
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedLogicalValidationWorkerResult)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = self._parse(candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedLogicalValidationWorkerResult,
                candidate,
                "detailed.validation_worker_coverage_invalid",
                "The Logical validator worker must review its complete bounded package.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.validation_worker_coverage_invalid",
                "The Logical validator worker must review its complete bounded package.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedLogicalValidationWorkerResult:
        parsed = self._parse(candidate)
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _has_exact_coverage(self, candidate: DetailedLogicalValidationWorkerResult) -> bool:
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

    def _parse(self, candidate: JsonValue) -> DetailedLogicalValidationWorkerResult | None:
        if (
            self._max_result_bytes is not None
            and logical_json_bytes(candidate) > self._max_result_bytes
        ):
            return None
        return _parse(DetailedLogicalValidationWorkerResult, candidate)


class DetailedLogicalValidationLeadValidator:
    def __init__(
        self,
        *,
        worker_results: tuple[DetailedLogicalValidationWorkerResult, ...],
        max_result_bytes: int | None = 2 * 1024 * 1024,
    ) -> None:
        if not worker_results or len(worker_results) > 10_000:
            raise ValueError("Logical validator worker results must be bounded and nonempty")
        self._package_refs = tuple(item.package_ref for item in worker_results)
        self._findings = tuple(finding for result in worker_results for finding in result.findings)
        self._finding_refs = tuple(item.finding_ref for item in self._findings)
        self._blocking_refs = tuple(
            item.finding_ref for item in self._findings if item.severity == "error"
        )
        if len(self._package_refs) != len(set(self._package_refs)) or len(
            self._finding_refs
        ) != len(set(self._finding_refs)):
            raise ValueError("Logical validator worker references must be unique")
        _validate_result_byte_limit(max_result_bytes)
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedLogicalValidationLead)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = self._parse(candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedLogicalValidationLead,
                candidate,
                "detailed.validation_lead_coverage_invalid",
                "The Logical validator lead must reconcile every package and finding once.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.validation_lead_coverage_invalid",
                "The Logical validator lead must reconcile every package and finding once.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedLogicalValidationLead:
        parsed = self._parse(candidate)
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _has_exact_coverage(self, candidate: DetailedLogicalValidationLead) -> bool:
        return (
            _exact_unique(candidate.reviewed_package_refs, self._package_refs)
            and _exact_unique(candidate.reviewed_finding_refs, self._finding_refs)
            and _exact_unique(candidate.blocking_finding_refs, self._blocking_refs)
            and ((candidate.repair_brief is not None) == bool(self._blocking_refs))
        )

    def _parse(self, candidate: JsonValue) -> DetailedLogicalValidationLead | None:
        if (
            self._max_result_bytes is not None
            and logical_json_bytes(candidate) > self._max_result_bytes
        ):
            return None
        return _parse(DetailedLogicalValidationLead, candidate)


def build_logical_relationship_signal_ledger(
    *,
    entity_details: tuple[DetailedLogicalEntityDetail, ...],
    max_signals: int,
) -> DetailedLogicalRelationshipSignalLedger:
    """Derive stable same-name Attribute evidence without assigning semantics."""

    if not 1 <= max_signals <= 50_000:
        raise InvalidRequestError("The Logical relationship signal limit is invalid.")
    entity_refs = tuple(item.canonical_entity_ref for item in entity_details)
    entity_names = tuple(
        normalize_model_key_value(item.entity.logical_entity_name) for item in entity_details
    )
    if len(entity_refs) != len(set(entity_refs)) or len(entity_names) != len(set(entity_names)):
        raise InvalidRequestError("Logical detailed Entity identities must be unique.")

    details = sorted(entity_details, key=lambda item: item.canonical_entity_ref)
    raw: list[
        tuple[
            str,
            LogicalEntityRecord,
            LogicalAttributeRecord,
            tuple[PhysicalAttributeKey, ...],
            str,
            LogicalEntityRecord,
            LogicalAttributeRecord,
            tuple[PhysicalAttributeKey, ...],
        ]
    ] = []
    for left_index, left in enumerate(details):
        for right in details[left_index + 1 :]:
            for left_attribute in sorted(
                left.attributes,
                key=lambda item: normalize_model_key_value(item.logical_attribute_name),
            ):
                left_sources = _physical_attribute_sources(left_attribute)
                if not left_sources:
                    continue
                for right_attribute in sorted(
                    right.attributes,
                    key=lambda item: normalize_model_key_value(item.logical_attribute_name),
                ):
                    right_sources = _physical_attribute_sources(right_attribute)
                    if not right_sources or not _matching_attribute_signal(
                        left_attribute,
                        left_sources,
                        right_attribute,
                        right_sources,
                    ):
                        continue
                    raw.append(
                        (
                            left.canonical_entity_ref,
                            left.entity,
                            left_attribute,
                            left_sources,
                            right.canonical_entity_ref,
                            right.entity,
                            right_attribute,
                            right_sources,
                        )
                    )
    if len(raw) > max_signals:
        raise InvalidRequestError(
            "Logical relationship evidence exceeds its configured signal limit."
        )
    signals = tuple(
        DetailedLogicalRelationshipSignal(
            signal_ref=f"relationship_signal_{position:05d}",
            signal_type="matching_attribute_name",
            from_entity_ref=left_ref,
            from_logical_entity_name=left_entity.logical_entity_name,
            from_logical_attribute_name=left_attribute.logical_attribute_name,
            from_source_attributes=left_sources,
            to_entity_ref=right_ref,
            to_logical_entity_name=right_entity.logical_entity_name,
            to_logical_attribute_name=right_attribute.logical_attribute_name,
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
    return DetailedLogicalRelationshipSignalLedger(signals=signals)


def merge_logical_topology_partitions(
    *,
    contributions: tuple[DetailedLogicalTopologyContribution, ...],
    partitions: tuple[DetailedLogicalTopologyReconciliation, ...],
) -> DetailedLogicalTopologyReconciliation:
    """Merge disjoint topology partitions in original proposal order."""

    if not contributions or not partitions:
        raise AgentCandidateValidationError()
    ordered_proposal_refs = tuple(
        reference for contribution in contributions for reference in contribution.proposal_refs
    )
    proposal_order = {
        reference: position for position, reference in enumerate(ordered_proposal_refs)
    }
    if len(proposal_order) != sum(len(item.proposals) for item in contributions):
        raise AgentCandidateValidationError()

    covered: list[str] = []
    discarded: list[str] = []
    submodel_records: dict[str, LogicalSubmodelRecord] = {}
    entity_groups: dict[str, dict[str, object]] = {}
    for partition in partitions:
        submodel_by_ref = {
            item.canonical_submodel_ref: item.submodel for item in partition.submodels
        }
        for topology_entity in partition.entities:
            normalized_name = normalize_model_key_value(topology_entity.logical_entity_name)
            group = entity_groups.setdefault(
                normalized_name,
                {
                    "name": topology_entity.logical_entity_name,
                    "contribution_refs": [],
                    "submodel_names": [],
                },
            )
            group_refs = cast(list[str], group["contribution_refs"])
            group_names = cast(list[str], group["submodel_names"])
            group_refs.extend(topology_entity.contribution_refs)
            for reference in topology_entity.submodel_refs:
                submodel = submodel_by_ref.get(reference)
                if submodel is None:
                    raise AgentCandidateValidationError()
                normalized_submodel = normalize_model_key_value(submodel.logical_submodel_name)
                existing = submodel_records.get(normalized_submodel)
                if existing is not None and existing != submodel:
                    raise AgentCandidateValidationError()
                submodel_records.setdefault(normalized_submodel, submodel)
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
                    "submodel": submodel_records[name].model_dump(mode="json"),
                }
                for name in ordered_submodel_names
            ],
            "entities": [
                {
                    "canonical_entity_ref": f"entity_{position:05d}",
                    "logical_entity_name": cast(str, group["name"]),
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
    return DetailedLogicalTopologyReconciliationValidator(
        contributions=contributions,
        max_result_bytes=None,
    ).parse_validated(candidate)


def merge_logical_entity_detail_partitions(
    *,
    entity: DetailedLogicalEntityTopology,
    topology: DetailedLogicalTopologyReconciliation,
    contributions: tuple[DetailedLogicalTopologyContribution, ...],
    partitions: tuple[DetailedLogicalEntityDetail, ...],
) -> DetailedLogicalEntityDetail:
    """Merge one Entity's disjoint detail partitions without losing source order."""

    if not partitions or any(
        item.canonical_entity_ref != entity.canonical_entity_ref for item in partitions
    ):
        raise AgentCandidateValidationError()
    merged_entity = _merge_entity_records(tuple(item.entity for item in partitions))
    attributes: dict[str, list[LogicalAttributeRecord]] = {}
    for partition in partitions:
        for attribute in partition.attributes:
            name = normalize_model_key_value(attribute.logical_attribute_name)
            attributes.setdefault(name, []).append(attribute)
    merged_attributes: list[LogicalAttributeRecord] = []
    for records in attributes.values():
        merged_attribute = _merge_attribute_records(tuple(records))
        raw = merged_attribute.model_dump(mode="json")
        raw["logical_attribute_ordinal_position"] = len(merged_attributes) + 1
        merged_attributes.append(
            LogicalAttributeRecord.model_validate_json(
                json.dumps(raw, ensure_ascii=False, separators=(",", ":")),
                strict=True,
            )
        )
    merged = DetailedLogicalEntityDetail(
        canonical_entity_ref=entity.canonical_entity_ref,
        entity=merged_entity,
        attributes=tuple(merged_attributes),
    )
    return DetailedLogicalEntityDetailValidator(
        entity=entity,
        topology=topology,
        contributions=contributions,
        max_result_bytes=None,
    ).parse_validated(cast(JsonValue, merged.model_dump(mode="json")))


def merge_logical_reconciliation_partitions(
    *,
    partitions: tuple[DetailedLogicalReconciliationCandidate, ...],
    reviewed_submodel_refs: tuple[str, ...],
    reviewed_entity_refs: tuple[str, ...],
    reviewed_relationship_signal_refs: tuple[str, ...],
    reviewed_applied_record_refs: tuple[str, ...],
) -> DetailedLogicalReconciliationCandidate:
    """Merge byte-bounded reconciliation results with strict identity checks."""

    if not partitions:
        raise AgentCandidateValidationError()
    submodels: dict[str, LogicalSubmodelRecord] = {}
    entities: dict[str, list[LogicalEntityRecord]] = {}
    attributes: dict[tuple[str, str], LogicalAttributeRecord] = {}
    relationships: dict[tuple[str, str, str, str, str], LogicalRelationshipRecord] = {}
    for partition in partitions:
        for record in partition.submodels:
            key = normalize_model_key_value(record.logical_submodel_name)
            if key in submodels and submodels[key] != record:
                raise AgentCandidateValidationError()
            submodels.setdefault(key, record)
        for record in partition.entities:
            entities.setdefault(normalize_model_key_value(record.logical_entity_name), []).append(
                record
            )
        for record in partition.attributes:
            key = (
                normalize_model_key_value(record.logical_entity_name),
                normalize_model_key_value(record.logical_attribute_name),
            )
            if key in attributes and attributes[key] != record:
                raise AgentCandidateValidationError()
            attributes.setdefault(key, record)
        for record in partition.relationships:
            key = _relationship_key(record)
            if key in relationships and relationships[key] != record:
                raise AgentCandidateValidationError()
            relationships.setdefault(key, record)
    return DetailedLogicalReconciliationCandidate(
        submodels=tuple(submodels.values()),
        entities=tuple(_merge_entity_records(tuple(records)) for records in entities.values()),
        attributes=tuple(attributes.values()),
        relationships=tuple(relationships.values()),
        reviewed_submodel_refs=reviewed_submodel_refs,
        reviewed_entity_refs=reviewed_entity_refs,
        reviewed_relationship_signal_refs=reviewed_relationship_signal_refs,
        reviewed_applied_record_refs=reviewed_applied_record_refs,
    )


def build_logical_validation_packages(
    *,
    candidate: DetailedLogicalReconciliationCandidate,
    package_size: int,
    max_packages: int,
) -> tuple[DetailedLogicalValidationPackage, ...]:
    """Create stable bounded packages; workers receive no writable candidate surface."""

    if not 1 <= package_size <= 1_000 or not 1 <= max_packages <= 10_000:
        raise InvalidRequestError("The Logical validation package policy is invalid.")
    records = _validation_records(candidate)
    packages = tuple(
        DetailedLogicalValidationPackage(
            package_ref=f"validation_{position:05d}",
            records=tuple(records[offset : offset + package_size]),
            record_digests=tuple(
                logical_json_digest(item.record.model_dump(mode="json"))
                for item in records[offset : offset + package_size]
            ),
        )
        for position, offset in enumerate(range(0, len(records), package_size), start=1)
    )
    if not packages or len(packages) > max_packages:
        raise InvalidRequestError("Logical validation exceeds its configured package limit.")
    return packages


def logical_validation_records(
    candidate: DetailedLogicalReconciliationCandidate,
) -> tuple[DetailedLogicalValidationRecord, ...]:
    """Return the deterministic validation record order for byte-safe packaging."""

    return tuple(_validation_records(candidate))


def decide_logical_detailed_handoff(
    *,
    reconciliation_validator: DetailedLogicalReconciliationValidator,
    reconciliation_candidate: JsonValue,
    validation_lead: DetailedLogicalValidationLead,
    worker_results: tuple[DetailedLogicalValidationWorkerResult, ...],
) -> DetailedLogicalHandoffDecision:
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
        return DetailedLogicalHandoffDecision(
            next_stage="whole_model_reconciliation",
            validation_failures=failures,
            handoff_candidate=None,
        )
    return DetailedLogicalHandoffDecision(
        next_stage="handoff",
        validation_failures=(),
        handoff_candidate=reconciliation_validator.materialize_validated(reconciliation_candidate),
    )


def logical_applied_record_refs(section: LogicalSection | None) -> tuple[str, ...]:
    if section is None:
        return ()
    refs = [
        f"submodel:{normalize_model_key_value(item.logical_submodel_name)}"
        for item in section.submodels
    ]
    refs.extend(
        f"entity:{normalize_model_key_value(item.logical_entity_name)}" for item in section.entities
    )
    refs.extend(
        "attribute:"
        f"{normalize_model_key_value(item.logical_entity_name)}|"
        f"{normalize_model_key_value(item.logical_attribute_name)}"
        for item in section.attributes
    )
    refs.extend(
        "relationship:"
        f"{normalize_model_key_value(item.from_logical_entity_name)}|"
        f"{normalize_model_key_value(item.from_logical_attribute_name)}|"
        f"{normalize_model_key_value(item.to_logical_entity_name)}|"
        f"{normalize_model_key_value(item.to_logical_attribute_name)}|"
        f"{normalize_model_key_value(item.logical_relationship_name)}"
        for item in section.relationships
    )
    if len(refs) != len(set(refs)):
        raise ValueError("Applied Logical record references must be unique")
    return tuple(sorted(refs))


def _validation_records(
    candidate: DetailedLogicalReconciliationCandidate,
) -> list[DetailedLogicalValidationRecord]:
    records: list[DetailedLogicalValidationRecord] = []
    for item in sorted(
        candidate.submodels,
        key=lambda value: normalize_model_key_value(value.logical_submodel_name),
    ):
        records.append(
            DetailedLogicalValidationRecord(
                record_ref=f"submodel:{normalize_model_key_value(item.logical_submodel_name)}",
                dataset="logical_submodel",
                record=item,
            )
        )
    for item in sorted(
        candidate.entities,
        key=lambda value: normalize_model_key_value(value.logical_entity_name),
    ):
        records.append(
            DetailedLogicalValidationRecord(
                record_ref=f"entity:{normalize_model_key_value(item.logical_entity_name)}",
                dataset="logical_entity",
                record=item,
            )
        )
    for item in sorted(
        candidate.attributes,
        key=lambda value: (
            normalize_model_key_value(value.logical_entity_name),
            normalize_model_key_value(value.logical_attribute_name),
        ),
    ):
        records.append(
            DetailedLogicalValidationRecord(
                record_ref=(
                    "attribute:"
                    f"{normalize_model_key_value(item.logical_entity_name)}|"
                    f"{normalize_model_key_value(item.logical_attribute_name)}"
                ),
                dataset="logical_attribute",
                record=item,
            )
        )
    for item in sorted(candidate.relationships, key=_relationship_key):
        key = _relationship_key(item)
        records.append(
            DetailedLogicalValidationRecord(
                record_ref="relationship:" + "|".join(key),
                dataset="logical_relationship",
                record=item,
            )
        )
    refs = tuple(item.record_ref for item in records)
    if len(refs) != len(set(refs)):
        raise InvalidRequestError("Logical validation record identities must be unique.")
    return records


def _materialize(candidate: DetailedLogicalReconciliationCandidate) -> JsonValue:
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
    records: tuple[LogicalEntityRecord, ...],
) -> LogicalEntityRecord:
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
            key = _entity_source_key(source)
            raw = cast(dict[str, JsonValue], source.model_dump(mode="json"))
            existing = sources.get(key)
            if existing is not None:
                existing_without_order = {k: v for k, v in existing.items() if k != "source_order"}
                raw_without_order = {k: v for k, v in raw.items() if k != "source_order"}
                if existing_without_order != raw_without_order:
                    raise AgentCandidateValidationError()
                continue
            sources[key] = raw
    baseline["sources"] = [
        {**source, "source_order": position}
        for position, source in enumerate(sources.values(), start=1)
    ]
    return LogicalEntityRecord.model_validate_json(
        json.dumps(baseline, ensure_ascii=False, separators=(",", ":")),
        strict=True,
    )


def _merge_attribute_records(
    records: tuple[LogicalAttributeRecord, ...],
) -> LogicalAttributeRecord:
    if not records:
        raise AgentCandidateValidationError()
    baseline = records[0].model_dump(mode="json")
    baseline.pop("sources")
    baseline.pop("logical_attribute_ordinal_position")
    sources: dict[tuple[str, ...], dict[str, JsonValue]] = {}
    for record in records:
        comparable = record.model_dump(mode="json")
        comparable.pop("logical_attribute_ordinal_position")
        raw_sources = comparable.pop("sources")
        if comparable != baseline or not isinstance(raw_sources, list):
            raise AgentCandidateValidationError()
        for source in record.sources:
            if isinstance(source, AttributePhysicalSourceRecord):
                key = ("attribute", *_physical_attribute_key(source.source_attribute))
            else:
                key = (
                    "assertion",
                    normalize_model_key_value(
                        source.assertion_record.modeling_assertion_record_key
                    ),
                )
            raw = cast(dict[str, JsonValue], source.model_dump(mode="json"))
            existing = sources.get(key)
            if existing is not None:
                existing_without_order = {
                    key: value for key, value in existing.items() if key != "source_order"
                }
                raw_without_order = {
                    key: value for key, value in raw.items() if key != "source_order"
                }
                if existing_without_order != raw_without_order:
                    raise AgentCandidateValidationError()
                continue
            sources[key] = raw
    baseline["logical_attribute_ordinal_position"] = 1
    baseline["sources"] = [
        {**source, "source_order": position}
        for position, source in enumerate(sources.values(), start=1)
    ]
    return LogicalAttributeRecord.model_validate_json(
        json.dumps(baseline, ensure_ascii=False, separators=(",", ":")),
        strict=True,
    )


def _entity_source_key(
    source: LogicalObjectSourceRecord | LogicalAssertionSourceRecord,
) -> tuple[str, ...]:
    if isinstance(source, LogicalObjectSourceRecord):
        return ("object", *_physical_object_key(source.source_object))
    return (
        "assertion",
        normalize_model_key_value(source.assertion_record.modeling_assertion_record_key),
    )


def _safe_entity(entity: LogicalEntityRecord) -> bool:
    return (
        not entity.logical_entity_is_locked
        and all(not item.membership_is_locked for item in entity.submodels)
        and all(not item.is_locked for item in entity.sources)
    )


def _safe_attribute(attribute: LogicalAttributeRecord) -> bool:
    return (
        not attribute.logical_attribute_is_locked
        and not attribute.logical_attribute_is_audit_column
        and all(not item.is_locked for item in attribute.sources)
    )


def _reconciliation_entity_sources_match(
    *,
    required: LogicalEntityRecord,
    candidate: LogicalEntityRecord,
) -> bool:
    required_submodels = {
        normalize_model_key_value(item.submodel_name) for item in required.submodels
    }
    candidate_submodels = {
        normalize_model_key_value(item.submodel_name) for item in candidate.submodels
    }
    required_objects = tuple(
        sorted(
            _physical_object_key(item.source_object)
            for item in required.sources
            if isinstance(item, LogicalObjectSourceRecord)
        )
    )
    candidate_objects = tuple(
        sorted(
            _physical_object_key(item.source_object)
            for item in candidate.sources
            if isinstance(item, LogicalObjectSourceRecord)
        )
    )
    return required_submodels == candidate_submodels and required_objects == candidate_objects


def _matching_attribute_signal(
    left: LogicalAttributeRecord,
    left_sources: tuple[PhysicalAttributeKey, ...],
    right: LogicalAttributeRecord,
    right_sources: tuple[PhysicalAttributeKey, ...],
) -> bool:
    if normalize_model_key_value(left.logical_attribute_name) == normalize_model_key_value(
        right.logical_attribute_name
    ):
        return True
    left_names = {normalize_model_key_value(item.attribute_name) for item in left_sources}
    right_names = {normalize_model_key_value(item.attribute_name) for item in right_sources}
    return bool(left_names & right_names)


def _physical_attribute_sources(
    attribute: LogicalAttributeRecord,
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
    item: LogicalRelationshipRecord,
) -> tuple[str, str, str, str, str]:
    return (
        normalize_model_key_value(item.from_logical_entity_name),
        normalize_model_key_value(item.from_logical_attribute_name),
        normalize_model_key_value(item.to_logical_entity_name),
        normalize_model_key_value(item.to_logical_attribute_name),
        normalize_model_key_value(item.logical_relationship_name),
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


def _validate_result_byte_limit(maximum_bytes: int | None) -> None:
    if maximum_bytes is not None and not 1 <= maximum_bytes <= 10 * 1024 * 1024:
        raise ValueError("Logical detailed result byte limit is invalid")


def logical_json_bytes(value: JsonValue) -> int:
    """Return deterministic canonical UTF-8 JSON bytes for a Logical value."""

    return len(_logical_json_data(value))


def logical_json_digest(value: JsonValue) -> str:
    """Return the SHA-256 of deterministic canonical UTF-8 Logical JSON."""

    return sha256(_logical_json_data(value)).hexdigest()


def _logical_json_data(value: JsonValue) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise AgentCandidateValidationError() from None


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


def _set_lock_fields_false(value: JsonValue) -> None:
    if isinstance(value, list):
        for child in value:
            _set_lock_fields_false(child)
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
    for child in value.values():
        _set_lock_fields_false(child)


__all__ = [
    "DetailedLogicalEntityDetail",
    "DetailedLogicalEntityDetailValidator",
    "DetailedLogicalHandoffDecision",
    "DetailedLogicalPolicy",
    "DetailedLogicalReconciliationCandidate",
    "DetailedLogicalReconciliationValidator",
    "DetailedLogicalRelationshipSignalLedger",
    "DetailedLogicalTopologyContribution",
    "DetailedLogicalTopologyContributionValidator",
    "DetailedLogicalTopologyReconciliation",
    "DetailedLogicalTopologyReconciliationValidator",
    "DetailedLogicalValidationLead",
    "DetailedLogicalValidationLeadValidator",
    "DetailedLogicalValidationPackage",
    "DetailedLogicalValidationWorkerResult",
    "DetailedLogicalValidationWorkerValidator",
    "build_logical_relationship_signal_ledger",
    "build_logical_validation_packages",
    "decide_logical_detailed_handoff",
    "load_default_detailed_logical_policy",
    "logical_json_bytes",
    "logical_json_digest",
    "logical_applied_record_refs",
    "logical_validation_records",
    "merge_logical_entity_detail_partitions",
    "merge_logical_reconciliation_partitions",
    "merge_logical_topology_partitions",
]
