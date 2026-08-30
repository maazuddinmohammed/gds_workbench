"""Bounded contracts for staged detailed Analysis inference."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from importlib.resources import files
from typing import Annotated, Literal, cast

from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    PhysicalAttributeKey,
    normalize_model_key_value,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
)

from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentCandidateValidationError,
    AgentValidationIssue,
)

from .candidate import (
    AnalysisInferenceCandidateValidator,
    AnalysisInferenceRelationship,
)

_REFERENCE = r"^[a-z][a-z0-9_]{0,99}$"
_CODE = r"^[a-z][a-z0-9_.-]{0,99}$"
_BoundedText = Annotated[str, StringConstraints(min_length=1, max_length=2_000, pattern=r"\S")]


class _DetailedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DetailedAnalysisPolicy(_DetailedModel):
    schema_version: Literal["1.0"] = "1.0"
    max_object_pairs: int = Field(ge=1, le=20_000)
    max_candidate_slices: int = Field(ge=1, le=20_000)
    max_candidates_per_slice: int = Field(ge=1, le=2_000)
    max_total_candidates: int = Field(ge=1, le=20_000)
    max_review_findings: int = Field(ge=1, le=1_000)


class DetailedAnalysisEvidenceSignal(_DetailedModel):
    signal_type: Literal[
        "name",
        "data_type",
        "profile",
        "assertion",
        "applied_analysis",
    ]
    signal_detail: _BoundedText


class DetailedAnalysisEndpointCandidate(_DetailedModel):
    candidate_ref: str = Field(pattern=_REFERENCE, max_length=100)
    left_attribute: PhysicalAttributeKey
    right_attribute: PhysicalAttributeKey
    evidence_signals: tuple[DetailedAnalysisEvidenceSignal, ...] = Field(
        min_length=1,
        max_length=20,
    )


class DetailedAnalysisSliceCoverage(_DetailedModel):
    slice_ref: str = Field(pattern=_REFERENCE, max_length=100)
    disposition: Literal["candidates_found", "no_candidate", "needs_review"]


class DetailedAnalysisCandidateFinderResult(_DetailedModel):
    schema_version: Literal["1.0"] = "1.0"
    coverage: DetailedAnalysisSliceCoverage
    candidates: tuple[DetailedAnalysisEndpointCandidate, ...] = Field(max_length=2_000)


class DetailedAnalysisResolutionDecision(_DetailedModel):
    candidate_ref: str = Field(pattern=_REFERENCE, max_length=100)
    disposition: Literal["relationship", "no_relationship", "needs_review"]
    relationship: AnalysisInferenceRelationship | None
    rationale: _BoundedText


class DetailedAnalysisResolutionResult(_DetailedModel):
    schema_version: Literal["1.0"] = "1.0"
    decisions: tuple[DetailedAnalysisResolutionDecision, ...] = Field(max_length=2_000)


class DetailedAnalysisCandidateCoverage(_DetailedModel):
    candidate_ref: str = Field(pattern=_REFERENCE, max_length=100)
    disposition: Literal["accepted", "rejected", "merged", "needs_review"]


class DetailedAnalysisAppliedCoverage(_DetailedModel):
    applied_record_ref: str = Field(pattern=_REFERENCE, max_length=100)
    disposition: Literal["preserved"]


class DetailedAnalysisReconciliationResult(_DetailedModel):
    schema_version: Literal["1.0"] = "1.0"
    candidate_coverage: tuple[DetailedAnalysisCandidateCoverage, ...] = Field(max_length=20_000)
    applied_record_coverage: tuple[DetailedAnalysisAppliedCoverage, ...] = Field(max_length=20_000)
    relationships: tuple[AnalysisInferenceRelationship, ...] = Field(max_length=20_000)


class DetailedAnalysisReviewFinding(_DetailedModel):
    finding_ref: str = Field(pattern=_REFERENCE, max_length=100)
    severity: Literal["warning", "blocker"]
    code: str = Field(pattern=_CODE, max_length=100)
    subject_ref: str = Field(pattern=_REFERENCE, max_length=100)
    message: _BoundedText


class DetailedAnalysisReviewResult(_DetailedModel):
    schema_version: Literal["1.0"] = "1.0"
    reviewed_relationship_refs: tuple[str, ...] = Field(max_length=20_000)
    reviewed_applied_record_refs: tuple[str, ...] = Field(max_length=20_000)
    findings: tuple[DetailedAnalysisReviewFinding, ...] = Field(max_length=1_000)


class DetailedAnalysisCandidateFinderValidator:
    def __init__(
        self,
        *,
        slice_ref: str,
        allowed_attributes: tuple[PhysicalAttributeKey, ...] | None = None,
        left_attributes: tuple[PhysicalAttributeKey, ...] | None = None,
        right_attributes: tuple[PhysicalAttributeKey, ...] | None = None,
        max_candidates: int = 2_000,
        max_result_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        if allowed_attributes is not None:
            if left_attributes is not None or right_attributes is not None:
                raise ValueError("Detailed Analysis slice Attributes are ambiguous")
            left_attributes = allowed_attributes
            right_attributes = allowed_attributes
        if (
            not slice_ref
            or len(slice_ref) > 100
            or left_attributes is None
            or right_attributes is None
            or not 1 <= max_candidates <= 2_000
            or not 1 <= max_result_bytes <= 10 * 1024 * 1024
        ):
            raise ValueError("Detailed Analysis slice is invalid")
        left = {_attribute_key(item) for item in left_attributes}
        right = {_attribute_key(item) for item in right_attributes}
        if len(left) != len(left_attributes) or len(right) != len(right_attributes):
            raise ValueError("Detailed Analysis slice Attributes must be unique")
        self._slice_ref = slice_ref
        self._left_attributes = left
        self._right_attributes = right
        self._max_candidates = max_candidates
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedAnalysisCandidateFinderResult)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse(DetailedAnalysisCandidateFinderResult, candidate)
        if parsed is None or not self._is_valid(parsed):
            return _issue(
                "detailed.candidate_finder_coverage_invalid",
                "The candidate-finder result does not exactly cover its bounded slice.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedAnalysisCandidateFinderResult:
        parsed = _parse(DetailedAnalysisCandidateFinderResult, candidate)
        if parsed is None or not self._is_valid(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _is_valid(self, candidate: DetailedAnalysisCandidateFinderResult) -> bool:
        if candidate.coverage.slice_ref != self._slice_ref:
            return False
        if len(candidate.candidates) > self._max_candidates:
            return False
        if bool(candidate.candidates) != (candidate.coverage.disposition == "candidates_found"):
            return False
        refs = tuple(item.candidate_ref for item in candidate.candidates)
        pairs = tuple(
            tuple(
                sorted((_attribute_key(item.left_attribute), _attribute_key(item.right_attribute)))
            )
            for item in candidate.candidates
        )
        return (
            _json_bytes(candidate.model_dump(mode="json")) <= self._max_result_bytes
            and len(refs) == len(set(refs))
            and all(reference.startswith(f"{self._slice_ref}_candidate_") for reference in refs)
            and len(pairs) == len(set(pairs))
            and all(
                (
                    (
                        _attribute_key(item.left_attribute) in self._left_attributes
                        and _attribute_key(item.right_attribute) in self._right_attributes
                    )
                    or (
                        _attribute_key(item.left_attribute) in self._right_attributes
                        and _attribute_key(item.right_attribute) in self._left_attributes
                    )
                )
                and _attribute_key(item.left_attribute) != _attribute_key(item.right_attribute)
                for item in candidate.candidates
            )
        )


class DetailedAnalysisRelationshipResolverValidator:
    def __init__(
        self,
        *,
        candidates: tuple[DetailedAnalysisEndpointCandidate, ...],
        max_result_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        refs = [item.candidate_ref for item in candidates]
        if len(refs) != len(set(refs)):
            raise ValueError("Detailed Analysis candidate references must be unique")
        self._candidates = {item.candidate_ref: item for item in candidates}
        if not 1 <= max_result_bytes <= 10 * 1024 * 1024:
            raise ValueError("Detailed Analysis result byte limit is invalid")
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedAnalysisResolutionResult)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse(DetailedAnalysisResolutionResult, candidate)
        if parsed is None or not self._is_valid(parsed):
            return _issue(
                "detailed.relationship_resolution_coverage_invalid",
                "The relationship resolver must decide every supplied candidate exactly once.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedAnalysisResolutionResult:
        parsed = _parse(DetailedAnalysisResolutionResult, candidate)
        if parsed is None or not self._is_valid(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _is_valid(self, candidate: DetailedAnalysisResolutionResult) -> bool:
        if _json_bytes(candidate.model_dump(mode="json")) > self._max_result_bytes:
            return False
        decisions = {item.candidate_ref: item for item in candidate.decisions}
        if len(decisions) != len(candidate.decisions) or set(decisions) != set(self._candidates):
            return False
        for reference, decision in decisions.items():
            relationship = decision.relationship
            if (decision.disposition == "relationship") != (relationship is not None):
                return False
            if relationship is None:
                continue
            source = self._candidates[reference]
            expected = {
                _attribute_key(source.left_attribute),
                _attribute_key(source.right_attribute),
            }
            actual = {
                _relationship_endpoint_key(relationship, "from"),
                _relationship_endpoint_key(relationship, "to"),
            }
            if actual != expected:
                return False
        return True


class DetailedAnalysisReconciliationValidator:
    def __init__(
        self,
        *,
        decisions: tuple[DetailedAnalysisResolutionDecision, ...],
        applied_by_ref: Mapping[str, AnalysisResultRecord],
        final_validator: AnalysisInferenceCandidateValidator,
        max_result_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        decision_refs = [item.candidate_ref for item in decisions]
        if len(decision_refs) != len(set(decision_refs)):
            raise ValueError("Detailed Analysis decision references must be unique")
        if len(applied_by_ref) != len(set(applied_by_ref)):
            raise ValueError("Detailed Analysis applied references must be unique")
        self._decisions = {item.candidate_ref: item for item in decisions}
        self._applied_by_ref = dict(applied_by_ref)
        self._final_validator = final_validator
        if not 1 <= max_result_bytes <= 10 * 1024 * 1024:
            raise ValueError("Detailed Analysis result byte limit is invalid")
        self._max_result_bytes = max_result_bytes

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedAnalysisReconciliationResult)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse(DetailedAnalysisReconciliationResult, candidate)
        if parsed is None or not self._has_exact_coverage(parsed):
            return _issue(
                "detailed.reconciliation_coverage_invalid",
                "The reconciler must review every candidate and applied record exactly once.",
            )
        return await self._final_validator.validate(self._materialize(parsed))

    def parse_validated(self, candidate: JsonValue) -> DetailedAnalysisReconciliationResult:
        parsed = _parse(DetailedAnalysisReconciliationResult, candidate)
        if parsed is None or not self._has_exact_coverage(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def materialize_validated(self, candidate: JsonValue) -> JsonValue:
        return self._materialize(self.parse_validated(candidate))

    def _has_exact_coverage(self, candidate: DetailedAnalysisReconciliationResult) -> bool:
        if _json_bytes(candidate.model_dump(mode="json")) > self._max_result_bytes:
            return False
        candidate_coverage = {
            item.candidate_ref: item.disposition for item in candidate.candidate_coverage
        }
        applied_coverage = {
            item.applied_record_ref: item.disposition for item in candidate.applied_record_coverage
        }
        if (
            len(candidate_coverage) != len(candidate.candidate_coverage)
            or set(candidate_coverage) != set(self._decisions)
            or len(applied_coverage) != len(candidate.applied_record_coverage)
            or set(applied_coverage) != set(self._applied_by_ref)
        ):
            return False
        relationship_keys = {_relationship_key(item) for item in candidate.relationships}
        allowed_relationship_keys: set[tuple[str, ...]] = set()
        for reference, decision in self._decisions.items():
            if decision.relationship is None:
                if candidate_coverage[reference] in {"accepted", "merged"}:
                    return False
                continue
            expected_key = _relationship_key(decision.relationship)
            accepted = candidate_coverage[reference] in {"accepted", "merged"}
            if accepted != (expected_key in relationship_keys):
                return False
            if accepted:
                allowed_relationship_keys.add(expected_key)
        for reference, applied in self._applied_by_ref.items():
            expected_key = _relationship_key(applied)
            if applied_coverage[reference] != "preserved":
                return False
            allowed_relationship_keys.add(expected_key)
        return relationship_keys <= allowed_relationship_keys

    def _materialize(self, candidate: DetailedAnalysisReconciliationResult) -> JsonValue:
        accepted_keys: set[tuple[str, ...]] = set()
        for item in candidate.candidate_coverage:
            relationship = self._decisions[item.candidate_ref].relationship
            if item.disposition in {"accepted", "merged"} and relationship is not None:
                accepted_keys.add(_relationship_key(relationship))
        return cast(
            JsonValue,
            {
                "relationships": [
                    item.model_dump(mode="json")
                    for item in candidate.relationships
                    if _relationship_key(item) in accepted_keys
                ]
            },
        )


class DetailedAnalysisReviewerValidator:
    def __init__(
        self,
        *,
        relationships: tuple[
            AnalysisInferenceRelationship | AnalysisResultRecord,
            ...,
        ],
        applied_record_refs: tuple[str, ...],
        relationship_refs: tuple[str, ...] | None = None,
        max_findings: int = 1_000,
        max_result_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        if not 1 <= max_findings <= 1_000:
            raise ValueError("Detailed Analysis review finding limit is invalid")
        self._relationship_refs = relationship_refs or tuple(
            f"relationship_{position:05d}" for position, _ in enumerate(relationships, start=1)
        )
        if len(self._relationship_refs) != len(relationships) or len(
            self._relationship_refs
        ) != len(set(self._relationship_refs)):
            raise ValueError("Detailed Analysis relationship references must be unique")
        if len(applied_record_refs) != len(set(applied_record_refs)):
            raise ValueError("Detailed Analysis applied references must be unique")
        self._applied_record_refs = applied_record_refs
        self._max_findings = max_findings
        if not 1 <= max_result_bytes <= 10 * 1024 * 1024:
            raise ValueError("Detailed Analysis result byte limit is invalid")
        self._max_result_bytes = max_result_bytes

    @property
    def relationship_refs(self) -> tuple[str, ...]:
        return self._relationship_refs

    def output_schema(self) -> dict[str, JsonValue]:
        return _output_schema(DetailedAnalysisReviewResult)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        parsed = _parse(DetailedAnalysisReviewResult, candidate)
        if parsed is None or not self._is_valid(parsed):
            return _issue(
                "detailed.analysis_review_coverage_invalid",
                "The reviewer must cover every reconciled and applied record exactly once.",
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> DetailedAnalysisReviewResult:
        parsed = _parse(DetailedAnalysisReviewResult, candidate)
        if parsed is None or not self._is_valid(parsed):
            raise AgentCandidateValidationError()
        return parsed

    def _is_valid(self, candidate: DetailedAnalysisReviewResult) -> bool:
        if _json_bytes(candidate.model_dump(mode="json")) > self._max_result_bytes:
            return False
        relationship_refs = candidate.reviewed_relationship_refs
        applied_refs = candidate.reviewed_applied_record_refs
        known_subjects = set(self._relationship_refs) | set(self._applied_record_refs)
        finding_refs = [item.finding_ref for item in candidate.findings]
        return (
            _exact_unique(relationship_refs, self._relationship_refs)
            and _exact_unique(applied_refs, self._applied_record_refs)
            and len(finding_refs) == len(set(finding_refs))
            and len(candidate.findings) <= self._max_findings
            and all(item.subject_ref in known_subjects for item in candidate.findings)
        )


def load_default_detailed_analysis_policy() -> DetailedAnalysisPolicy:
    resource = files("gds_workbench_api").joinpath("config/analysis_detailed.json")
    raw = resource.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("Detailed Analysis configuration is too large")
    return DetailedAnalysisPolicy.model_validate_json(raw, strict=True)


def analysis_applied_records_by_ref(
    records: tuple[AnalysisResultRecord, ...],
) -> dict[str, AnalysisResultRecord]:
    ordered = sorted(records, key=_relationship_key)
    return {f"applied_{position:05d}": record for position, record in enumerate(ordered, start=1)}


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
    return cast(dict[str, JsonValue], deepcopy(model.model_json_schema()))


def _issue(code: str, message: str) -> AgentCandidateValidation:
    return AgentCandidateValidation(
        issues=(AgentValidationIssue(code=code, path=(), message=message),)
    )


def _json_bytes(value: JsonValue) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def _attribute_key(record: PhysicalAttributeKey) -> tuple[str, ...]:
    return tuple(
        normalize_model_key_value(getattr(record, field))
        for field in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
            "attribute_name",
        )
    )


def _relationship_endpoint_key(
    record: AnalysisInferenceRelationship | AnalysisResultRecord,
    endpoint: Literal["from", "to"],
) -> tuple[str, ...]:
    return tuple(
        normalize_model_key_value(getattr(record, f"{endpoint}_{field}"))
        for field in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
            "attribute_name",
        )
    )


def _relationship_key(
    record: AnalysisInferenceRelationship | AnalysisResultRecord,
) -> tuple[str, ...]:
    return (
        *_relationship_endpoint_key(record, "from"),
        *_relationship_endpoint_key(record, "to"),
        normalize_model_key_value(record.relationship_kind),
    )


def _exact_unique(actual: Sequence[str], expected: Sequence[str]) -> bool:
    return len(actual) == len(set(actual)) and set(actual) == set(expected)


__all__ = [
    "DetailedAnalysisCandidateFinderResult",
    "DetailedAnalysisCandidateFinderValidator",
    "DetailedAnalysisPolicy",
    "DetailedAnalysisEndpointCandidate",
    "DetailedAnalysisReconciliationValidator",
    "DetailedAnalysisRelationshipResolverValidator",
    "DetailedAnalysisResolutionDecision",
    "DetailedAnalysisReviewerValidator",
    "analysis_applied_records_by_ref",
    "load_default_detailed_analysis_policy",
]
