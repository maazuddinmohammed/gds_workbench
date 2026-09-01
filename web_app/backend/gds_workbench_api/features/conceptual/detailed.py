"""Run-local contracts for deterministic Conceptual detailed coverage."""

from __future__ import annotations

import json
from collections.abc import Sequence
from copy import deepcopy
from importlib.resources import files
from typing import Literal, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ConceptualObjectRecord,
    ConceptualRelationshipRecord,
    ObjectSupportRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    normalize_model_key_value,
)
from gds_etl_workbench.tools.snapshots.model.contracts import ConceptualSection
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
type _PhysicalObjectIdentity = tuple[str, str, str, str, str]


class DetailedConceptualPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    max_relationship_packages: int = Field(ge=1, le=20_000)


def load_default_detailed_conceptual_policy() -> DetailedConceptualPolicy:
    resource = files("gds_workbench_api").joinpath("config/conceptual_detailed.json")
    raw = resource.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("Conceptual detailed configuration is too large")
    return DetailedConceptualPolicy.model_validate_json(raw, strict=True)


class DetailedEntityProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    local_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    object: ConceptualObjectRecord = Field(repr=False)


class DetailedObjectContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    contribution_ref: str = Field(pattern=_REFERENCE_PATTERN)
    source_object: PhysicalObjectKey
    disposition: Literal["represented", "not_conceptual", "needs_review"]
    rationale: str = Field(min_length=1, max_length=2_000)
    proposals: tuple[DetailedEntityProposal, ...] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_disposition(self) -> DetailedObjectContribution:
        if (self.disposition == "represented") != bool(self.proposals):
            raise ValueError("Represented contributions require proposals exclusively")
        refs = tuple(proposal.local_entity_ref for proposal in self.proposals)
        if len(refs) != len(set(refs)):
            raise ValueError("Contribution proposal references must be unique")
        return self

    @property
    def proposal_refs(self) -> tuple[str, ...]:
        return tuple(
            f"{self.contribution_ref}.{proposal.local_entity_ref}" for proposal in self.proposals
        )


class DetailedConsolidatedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    canonical_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    contribution_refs: tuple[str, ...] = Field(min_length=1, max_length=50_000)
    candidate_names: tuple[str, ...] = Field(min_length=1, max_length=1_000)

    @model_validator(mode="after")
    def validate_unique_values(self) -> DetailedConsolidatedEntity:
        if len(self.contribution_refs) != len(set(self.contribution_refs)):
            raise ValueError("Consolidated contribution references must be unique")
        normalized_names = tuple(normalize_model_key_value(name) for name in self.candidate_names)
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("Consolidated candidate names must be unique")
        return self


class DetailedEntityConsolidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entities: tuple[DetailedConsolidatedEntity, ...] = Field(max_length=20_000)
    discarded_contribution_refs: tuple[str, ...] = Field(max_length=50_000)


class DetailedEntityDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    canonical_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    object: ConceptualObjectRecord = Field(repr=False)


class DetailedRelationshipSignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    signal_type: Literal["matching_attribute", "analysis_relationship"]
    from_attribute: PhysicalAttributeKey
    to_attribute: PhysicalAttributeKey
    relationship_kind: str | None = Field(default=None, max_length=100)
    relationship_confidence: Literal["low", "medium", "high"] | None = None
    validation_result: Literal["supported", "inconclusive", "unsupported"] | None = None


class DetailedRelationshipPackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    package_ref: str = Field(pattern=r"^relationship_[0-9]{5}$")
    from_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    to_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    signals: tuple[DetailedRelationshipSignal, ...] = Field(
        min_length=1,
        max_length=1_000,
    )


class DetailedRelationshipRefinement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    package_ref: str = Field(pattern=r"^relationship_[0-9]{5}$")
    disposition: Literal["proposed", "no_relationship", "needs_review"]
    rationale: str = Field(min_length=1, max_length=2_000)
    relationship: ConceptualRelationshipRecord | None

    @model_validator(mode="after")
    def validate_disposition(self) -> DetailedRelationshipRefinement:
        if (self.disposition == "proposed") != (self.relationship is not None):
            raise ValueError("Only proposed refinements contain a relationship")
        return self


class DetailedEntityCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    canonical_entity_ref: str = Field(pattern=_REFERENCE_PATTERN)
    conceptual_object_name: str = Field(min_length=1, max_length=255)


class DetailedReconciliationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    objects: tuple[ConceptualObjectRecord, ...] = Field(max_length=20_000)
    relationships: tuple[ConceptualRelationshipRecord, ...] = Field(max_length=20_000)
    entity_coverage: tuple[DetailedEntityCoverage, ...] = Field(max_length=20_000)
    reviewed_relationship_package_refs: tuple[str, ...] = Field(max_length=20_000)
    reviewed_applied_record_refs: tuple[str, ...] = Field(max_length=40_000)


class DetailedObjectContributionValidator:
    def __init__(
        self,
        *,
        contribution_ref: str,
        source_object: PhysicalObjectKey,
    ) -> None:
        self._contribution_ref = contribution_ref
        self._source_object = source_object

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedObjectContribution)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse(DetailedObjectContribution, candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedObjectContribution,
                candidate,
                "detailed.object_contribution_invalid",
                "The Object contribution is incomplete or outside its fixed source.",
            )
        if not self._is_valid(parsed):
            return _validation_issue(
                "detailed.object_contribution_invalid",
                "The Object contribution is incomplete or outside its fixed source.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedObjectContribution:
        parsed = _parse(DetailedObjectContribution, candidate)
        if parsed is None or not self._is_valid(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _is_valid(self, candidate: DetailedObjectContribution) -> bool:
        if candidate.contribution_ref != self._contribution_ref or _physical_key(
            candidate.source_object
        ) != _physical_key(self._source_object):
            return False
        expected = _physical_key(self._source_object)
        for proposal in candidate.proposals:
            object_supports = _object_support_keys(proposal.object)
            if expected not in object_supports or any(
                value != expected for value in object_supports
            ):
                return False
            if not _agent_authored_object_is_safe(proposal.object):
                return False
        return True


class DetailedEntityConsolidationValidator:
    def __init__(
        self,
        *,
        contributions: tuple[DetailedObjectContribution, ...],
    ) -> None:
        self._proposals = {
            proposal_ref: proposal
            for contribution in contributions
            for proposal_ref, proposal in zip(
                contribution.proposal_refs,
                contribution.proposals,
                strict=True,
            )
        }
        expected_count = sum(len(item.proposals) for item in contributions)
        if len(self._proposals) != expected_count:
            raise ValueError("Detailed contribution references must be unique")

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedEntityConsolidation)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse(DetailedEntityConsolidation, candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedEntityConsolidation,
                candidate,
                "detailed.entity_consolidation_invalid",
                "The entity consolidation does not match its bounded schema.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.entity_consolidation_coverage_invalid",
                "Every contribution proposal must be assigned or discarded exactly once.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedEntityConsolidation:
        parsed = _parse(DetailedEntityConsolidation, candidate)
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _has_exact_coverage(self, candidate: DetailedEntityConsolidation) -> bool:
        canonical_refs = tuple(item.canonical_entity_ref for item in candidate.entities)
        if len(canonical_refs) != len(set(canonical_refs)):
            return False
        covered = [
            contribution_ref
            for entity in candidate.entities
            for contribution_ref in entity.contribution_refs
        ] + list(candidate.discarded_contribution_refs)
        if len(covered) != len(set(covered)) or set(covered) != set(self._proposals):
            return False
        for entity in candidate.entities:
            expected_names = {
                normalize_model_key_value(self._proposals[reference].object.conceptual_object_name)
                for reference in entity.contribution_refs
            }
            actual_names = {normalize_model_key_value(name) for name in entity.candidate_names}
            if expected_names != actual_names:
                return False
        return True


class DetailedEntityDetailValidator:
    def __init__(
        self,
        *,
        entity: DetailedConsolidatedEntity,
        contributions: tuple[DetailedObjectContribution, ...],
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
        self._entity_ref = entity.canonical_entity_ref
        self._expected_supports = {
            support_key
            for reference in entity.contribution_refs
            for support_key in _object_support_keys(proposals[reference].object)
        }

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedEntityDetail)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse(DetailedEntityDetail, candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedEntityDetail,
                candidate,
                "detailed.entity_detail_invalid",
                "The detailed entity does not match its bounded schema.",
            )
        if not self._is_valid(parsed):
            return _validation_issue(
                "detailed.entity_detail_support_invalid",
                "The detailed entity must preserve every consolidated physical support.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedEntityDetail:
        parsed = _parse(DetailedEntityDetail, candidate)
        if parsed is None or not self._is_valid(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _is_valid(self, candidate: DetailedEntityDetail) -> bool:
        return (
            candidate.canonical_entity_ref == self._entity_ref
            and _object_support_keys(candidate.object) >= self._expected_supports
            and _agent_authored_object_is_safe(candidate.object)
        )


class DetailedRelationshipRefinementValidator:
    def __init__(
        self,
        *,
        package: DetailedRelationshipPackage,
        entity_details: tuple[DetailedEntityDetail, ...],
    ) -> None:
        self._package = package
        self._entity_names = {
            item.canonical_entity_ref: item.object.conceptual_object_name for item in entity_details
        }

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedRelationshipRefinement)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse(DetailedRelationshipRefinement, candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedRelationshipRefinement,
                candidate,
                "detailed.relationship_refinement_invalid",
                "The relationship package refinement is incomplete or mismatched.",
            )
        if not self._is_valid(parsed):
            return _validation_issue(
                "detailed.relationship_refinement_invalid",
                "The relationship package refinement is incomplete or mismatched.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedRelationshipRefinement:
        parsed = _parse(DetailedRelationshipRefinement, candidate)
        if parsed is None or not self._is_valid(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _is_valid(self, candidate: DetailedRelationshipRefinement) -> bool:
        if candidate.package_ref != self._package.package_ref:
            return False
        relationship = candidate.relationship
        if relationship is None:
            return True
        expected = {
            normalize_model_key_value(self._entity_names[self._package.from_entity_ref]),
            normalize_model_key_value(self._entity_names[self._package.to_entity_ref]),
        }
        actual = {
            normalize_model_key_value(relationship.from_conceptual_object_name),
            normalize_model_key_value(relationship.to_conceptual_object_name),
        }
        return (
            actual == expected
            and not relationship.conceptual_relationship_is_locked
            and all(not support.support_is_locked for support in relationship.supports)
        )


class DetailedReconciliationValidator:
    def __init__(
        self,
        *,
        entity_details: tuple[DetailedEntityDetail, ...],
        relationship_package_refs: tuple[str, ...],
        applied_record_refs: tuple[str, ...],
        final_validator: AgentCandidateValidator | None = None,
    ) -> None:
        self._entity_refs = tuple(item.canonical_entity_ref for item in entity_details)
        self._relationship_package_refs = relationship_package_refs
        self._applied_record_refs = applied_record_refs
        self._final_validator = final_validator

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedReconciliationCandidate)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse(DetailedReconciliationCandidate, candidate)
        if parsed is None:
            return _parse_failure_validation(
                DetailedReconciliationCandidate,
                candidate,
                "detailed.reconciliation_invalid",
                "The final reconciliation does not match its bounded schema.",
            )
        if not self._has_exact_coverage(parsed):
            return _validation_issue(
                "detailed.reconciliation_coverage_invalid",
                "The final reconciliation must review every run-local and applied record.",
            )
        if self._final_validator is not None:
            return await self._final_validator.validate(_materialize(parsed))
        return AgentCandidateValidation(issues=())

    def materialize_validated(self, candidate: JsonValue) -> JsonValue:
        parsed = _parse(DetailedReconciliationCandidate, candidate)
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return _materialize(parsed)

    def _has_exact_coverage(self, candidate: DetailedReconciliationCandidate) -> bool:
        entity_refs = tuple(item.canonical_entity_ref for item in candidate.entity_coverage)
        if not _exact_unique(entity_refs, self._entity_refs):
            return False
        if not _exact_unique(
            candidate.reviewed_relationship_package_refs,
            self._relationship_package_refs,
        ) or not _exact_unique(
            candidate.reviewed_applied_record_refs,
            self._applied_record_refs,
        ):
            return False
        object_names = {
            normalize_model_key_value(item.conceptual_object_name) for item in candidate.objects
        }
        if any(
            normalize_model_key_value(item.conceptual_object_name) not in object_names
            for item in candidate.entity_coverage
        ):
            return False
        return all(_agent_authored_object_is_safe(item) for item in candidate.objects)


def derive_relationship_packages(
    *,
    entity_details: tuple[DetailedEntityDetail, ...],
    attributes: tuple[PhysicalAttributeKey, ...],
    analysis_relationships: tuple[AnalysisResultRecord, ...],
    max_packages: int,
) -> tuple[DetailedRelationshipPackage, ...]:
    """Build stable evidence packages; never infer meaning or cardinality."""

    if not 1 <= max_packages <= 20_000:
        raise ValueError("Detailed relationship package limit is invalid")
    entity_sources: dict[str, set[_PhysicalObjectIdentity]] = {}
    source_entities: dict[_PhysicalObjectIdentity, set[str]] = {}
    for detail in entity_details:
        sources = _object_support_keys(detail.object)
        entity_sources[detail.canonical_entity_ref] = sources
        for source in sources:
            source_entities.setdefault(source, set()).add(detail.canonical_entity_ref)

    signals: dict[
        tuple[str, str],
        dict[tuple[object, ...], DetailedRelationshipSignal],
    ] = {}
    attributes_by_source: dict[_PhysicalObjectIdentity, list[PhysicalAttributeKey]] = {}
    for attribute in attributes:
        attributes_by_source.setdefault(_physical_key(attribute), []).append(attribute)

    refs = sorted(entity_sources)
    for left_index, left_ref in enumerate(refs):
        for right_ref in refs[left_index + 1 :]:
            for left_source in sorted(entity_sources[left_ref]):
                for right_source in sorted(entity_sources[right_ref]):
                    if left_source == right_source:
                        continue
                    left_attributes = attributes_by_source.get(left_source, ())
                    right_attributes = attributes_by_source.get(right_source, ())
                    for left_attribute in left_attributes:
                        for right_attribute in right_attributes:
                            if normalize_model_key_value(
                                left_attribute.attribute_name
                            ) != normalize_model_key_value(right_attribute.attribute_name):
                                continue
                            _add_signal(
                                signals,
                                pair=(left_ref, right_ref),
                                signal=DetailedRelationshipSignal(
                                    signal_type="matching_attribute",
                                    from_attribute=left_attribute,
                                    to_attribute=right_attribute,
                                    relationship_kind=None,
                                    relationship_confidence=None,
                                    validation_result=None,
                                ),
                            )

    for relationship in analysis_relationships:
        if relationship.analysis_result_status not in ("active", "needs_review"):
            continue
        from_attribute = _analysis_attribute(relationship, endpoint="from")
        to_attribute = _analysis_attribute(relationship, endpoint="to")
        for from_ref in sorted(source_entities.get(_physical_key(from_attribute), ())):
            for to_ref in sorted(source_entities.get(_physical_key(to_attribute), ())):
                if from_ref == to_ref:
                    continue
                left_ref, right_ref = sorted((from_ref, to_ref))
                oriented_from, oriented_to = (
                    (from_attribute, to_attribute)
                    if from_ref == left_ref
                    else (to_attribute, from_attribute)
                )
                _add_signal(
                    signals,
                    pair=(left_ref, right_ref),
                    signal=DetailedRelationshipSignal(
                        signal_type="analysis_relationship",
                        from_attribute=oriented_from,
                        to_attribute=oriented_to,
                        relationship_kind=relationship.relationship_kind,
                        relationship_confidence=relationship.relationship_confidence,
                        validation_result=relationship.validation_result,
                    ),
                )

    if len(signals) > max_packages:
        raise InvalidRequestError(
            "Detailed relationship evidence exceeds its configured package limit."
        )
    packages: list[DetailedRelationshipPackage] = []
    for position, pair in enumerate(sorted(signals), start=1):
        pair_signals = sorted(
            signals[pair].values(),
            key=_signal_sort_key,
        )
        packages.append(
            DetailedRelationshipPackage(
                package_ref=f"relationship_{position:05d}",
                from_entity_ref=pair[0],
                to_entity_ref=pair[1],
                signals=tuple(pair_signals),
            )
        )
    return tuple(packages)


def conceptual_applied_record_refs(
    section: ConceptualSection | None,
) -> tuple[str, ...]:
    if section is None:
        return ()
    refs = [
        f"object:{normalize_model_key_value(record.conceptual_object_name)}"
        for record in section.objects
    ]
    refs.extend(
        "relationship:"
        f"{normalize_model_key_value(record.from_conceptual_object_name)}|"
        f"{normalize_model_key_value(record.to_conceptual_object_name)}|"
        f"{normalize_model_key_value(record.conceptual_relationship_name)}"
        for record in section.relationships
    )
    if len(refs) != len(set(refs)):
        raise ValueError("Applied Conceptual record references must be unique")
    return tuple(sorted(refs))


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


def _materialize(candidate: DetailedReconciliationCandidate) -> JsonValue:
    return cast(
        JsonValue,
        {
            "objects": [item.model_dump(mode="json") for item in candidate.objects],
            "relationships": [item.model_dump(mode="json") for item in candidate.relationships],
        },
    )


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


def _physical_key(value: PhysicalObjectKey) -> _PhysicalObjectIdentity:
    return (
        normalize_model_key_value(value.tenant_code),
        normalize_model_key_value(value.system_code),
        normalize_model_key_value(value.connection_code),
        normalize_model_key_value(value.object_schema),
        normalize_model_key_value(value.object_name),
    )


def _object_support_keys(
    value: ConceptualObjectRecord,
) -> set[_PhysicalObjectIdentity]:
    return {
        _physical_key(support.source_object)
        for support in value.supports
        if isinstance(support, ObjectSupportRecord)
    }


def _agent_authored_object_is_safe(value: ConceptualObjectRecord) -> bool:
    return not value.conceptual_object_is_locked and all(
        not support.support_is_locked for support in value.supports
    )


def _exact_unique(actual: Sequence[str], expected: Sequence[str]) -> bool:
    return len(actual) == len(set(actual)) and set(actual) == set(expected)


def _add_signal(
    target: dict[
        tuple[str, str],
        dict[tuple[object, ...], DetailedRelationshipSignal],
    ],
    *,
    pair: tuple[str, str],
    signal: DetailedRelationshipSignal,
) -> None:
    key = _signal_sort_key(signal)
    target.setdefault(pair, {})[key] = signal


def _signal_sort_key(signal: DetailedRelationshipSignal) -> tuple[object, ...]:
    return (
        signal.signal_type,
        *_physical_key(signal.from_attribute),
        normalize_model_key_value(signal.from_attribute.attribute_name),
        *_physical_key(signal.to_attribute),
        normalize_model_key_value(signal.to_attribute.attribute_name),
        signal.relationship_kind or "",
        signal.relationship_confidence or "",
        signal.validation_result or "",
    )


def _analysis_attribute(
    relationship: AnalysisResultRecord,
    *,
    endpoint: Literal["from", "to"],
) -> PhysicalAttributeKey:
    return PhysicalAttributeKey(
        tenant_code=getattr(relationship, f"{endpoint}_tenant_code"),
        system_code=getattr(relationship, f"{endpoint}_system_code"),
        connection_code=getattr(relationship, f"{endpoint}_connection_code"),
        object_schema=getattr(relationship, f"{endpoint}_object_schema"),
        object_name=getattr(relationship, f"{endpoint}_object_name"),
        attribute_name=getattr(relationship, f"{endpoint}_attribute_name"),
    )


__all__ = [
    "DetailedEntityConsolidation",
    "DetailedEntityConsolidationValidator",
    "DetailedEntityDetail",
    "DetailedEntityDetailValidator",
    "DetailedObjectContribution",
    "DetailedObjectContributionValidator",
    "DetailedReconciliationValidator",
    "DetailedRelationshipPackage",
    "DetailedRelationshipRefinement",
    "DetailedRelationshipRefinementValidator",
    "conceptual_applied_record_refs",
    "derive_relationship_packages",
]
