"""Normalize one Analysis inference candidate without granting validation authority."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Annotated, cast

from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.application.change_sets.model_validation import (
    validate_staged_records,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    ANALYSIS_VALIDATION_FIELDS,
    AnalysisResultRecord,
    Code100,
    Confidence,
    Name400,
    NonblankText,
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
    AgentValidationIssue,
    model_validation_issues,
)


class AnalysisInferenceRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    from_tenant_code: Code100
    from_system_code: Code100
    from_connection_code: Code100
    from_object_schema: Name400
    from_object_name: Name400
    from_attribute_name: Name400
    to_tenant_code: Code100
    to_system_code: Code100
    to_connection_code: Code100
    to_object_schema: Name400
    to_object_name: Name400
    to_attribute_name: Name400
    relationship_kind: Annotated[
        str,
        StringConstraints(min_length=1, max_length=100, pattern=r"\S"),
    ]
    relationship_confidence: Confidence
    relationship_basis: NonblankText


class _AnalysisInferenceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    relationships: list[AnalysisInferenceRelationship] = Field(max_length=20_000)


class _NormalizedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    relationships: tuple[AnalysisResultRecord, ...]
    issues: tuple[AgentValidationIssue, ...]


class AnalysisInferenceCandidateValidator:
    """Enforce immutable selection, row locks, and inference-owned fields."""

    def __init__(
        self,
        *,
        selected_attribute_keys: tuple[PhysicalAttributeKey, ...],
        applied: tuple[AnalysisResultRecord, ...],
    ) -> None:
        if not selected_attribute_keys or len(selected_attribute_keys) > 50_000:
            raise ValueError("Analysis selection must be bounded and nonempty")
        selected = {_attribute_key(item) for item in selected_attribute_keys}
        if len(selected) != len(selected_attribute_keys):
            raise ValueError("Selected Analysis Attributes must be unique")
        applied_by_key = {_relationship_key(item): item for item in applied}
        if len(applied_by_key) != len(applied):
            raise ValueError("Applied Analysis relationships must be unique")
        self._selected_attribute_keys = selected
        self._applied = applied_by_key

    def output_schema(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            deepcopy(_AnalysisInferenceCandidate.model_json_schema()),
        )

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        return AgentCandidateValidation(issues=self._normalize(candidate).issues)

    def parse_validated(self, candidate: JsonValue) -> tuple[StageModelChange, ...]:
        normalized = self._normalize(candidate)
        if normalized.issues:
            raise InvalidRequestError("The Analysis inference candidate is invalid.")
        changed = [
            record.model_dump(mode="json")
            for record in normalized.relationships
            if self._applied.get(_relationship_key(record)) != record
        ]
        if not changed:
            return ()
        return (StageModelChange(dataset="analysis_result", records=changed),)

    def _normalize(self, candidate: JsonValue) -> _NormalizedCandidate:
        parsed = _parse_candidate(candidate)
        if parsed is None:
            return _NormalizedCandidate(
                relationships=(),
                issues=(
                    AgentValidationIssue(
                        code="candidate.schema_invalid",
                        path=(),
                        message="The candidate does not match the Analysis schema.",
                    ),
                ),
            )

        issues: list[AgentValidationIssue] = []
        seen: dict[tuple[str, ...], tuple[int, tuple[str, str]]] = {}
        raw_records: list[dict[str, object]] = []
        for index, candidate_record in enumerate(parsed.relationships):
            key = _relationship_key(candidate_record)
            content = (
                candidate_record.relationship_confidence,
                candidate_record.relationship_basis,
            )
            if key in seen:
                if seen[key][1] != content:
                    issues.append(
                        AgentValidationIssue(
                            code="candidate.relationship_duplicate",
                            path=("relationships", index),
                            message="Duplicate relationship has conflicting confidence or basis.",
                        )
                    )
                continue
            seen[key] = (index, content)
            existing = self._applied.get(key)
            merged = _merge_record(candidate_record, existing)
            unchanged_applied = existing is not None and merged == existing.model_dump(mode="json")
            if not unchanged_applied and (
                _endpoint_key(candidate_record, "from") not in self._selected_attribute_keys
                or _endpoint_key(candidate_record, "to") not in self._selected_attribute_keys
            ):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.endpoint_outside_selection",
                        path=("relationships", index),
                        message=(
                            "Both Analysis endpoints must belong to the immutable run selection."
                        ),
                    )
                )
            raw_records.append(merged)

        records, model_issues = validate_staged_records(
            "analysis_result",
            raw_records,
        )
        candidate_indexes = tuple(index for index, _ in seen.values())
        for issue in model_validation_issues(model_issues):
            path = issue.path
            if len(path) > 1 and isinstance(path[1], int):
                path = ("relationships", candidate_indexes[path[1]], *path[2:])
            else:
                path = ("relationships", *path[1:])
            issues.append(issue.model_copy(update={"path": path}))
        relationships = cast(tuple[AnalysisResultRecord, ...], records)
        for record in relationships:
            key = _relationship_key(record)
            existing = self._applied.get(key)
            if existing is not None and existing.analysis_result_is_locked and existing != record:
                issues.append(
                    AgentValidationIssue(
                        code="candidate.record_locked",
                        path=("relationships", seen[key][0]),
                        message="A locked Analysis relationship cannot be changed.",
                    )
                )
        return _NormalizedCandidate(
            relationships=relationships,
            issues=tuple(issues),
        )


def _parse_candidate(candidate: JsonValue) -> _AnalysisInferenceCandidate | None:
    try:
        return _AnalysisInferenceCandidate.model_validate_json(
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


def _merge_record(
    candidate: AnalysisInferenceRelationship,
    existing: AnalysisResultRecord | None,
) -> dict[str, object]:
    merged = cast(dict[str, object], candidate.model_dump(mode="json"))
    merged["relationship_kind"] = (
        normalize_model_key_value(candidate.relationship_kind)
        if existing is None
        else existing.relationship_kind
    )
    for field_name in ANALYSIS_VALIDATION_FIELDS:
        merged[field_name] = None if existing is None else getattr(existing, field_name)
    merged["analysis_result_status"] = (
        "active" if existing is None else existing.analysis_result_status
    )
    merged["analysis_result_is_locked"] = (
        False if existing is None else existing.analysis_result_is_locked
    )
    return merged


def _relationship_key(
    record: AnalysisInferenceRelationship | AnalysisResultRecord,
) -> tuple[str, ...]:
    return (
        *_endpoint_key(record, "from"),
        *_endpoint_key(record, "to"),
        normalize_model_key_value(record.relationship_kind),
    )


def _endpoint_key(
    record: AnalysisInferenceRelationship | AnalysisResultRecord,
    endpoint: str,
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


__all__ = [
    "AnalysisInferenceCandidateValidator",
    "AnalysisInferenceRelationship",
]
