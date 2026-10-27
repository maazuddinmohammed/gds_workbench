"""Normalize one Analysis inference candidate without granting validation authority."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Annotated, Any, cast

from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_staged_records,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    ANALYSIS_VALIDATION_FIELDS,
    AnalysisResultRecord,
    Code100,
    InferredCardinality,
    Name400,
    PhysicalAttributeKey,
    normalize_project_key_value,
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
    project_validation_issues,
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
    inferred_cardinality: InferredCardinality


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

    def parse_validated(self, candidate: JsonValue) -> tuple[StageProjectChange, ...]:
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
        return (StageProjectChange(dataset="analysis_result", records=changed),)

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
        seen: dict[tuple[str, ...], tuple[int, str]] = {}
        raw_records: list[dict[str, object]] = []
        for index, candidate_record in enumerate(parsed.relationships):
            key = _relationship_key(candidate_record)
            content = candidate_record.inferred_cardinality
            if key in seen:
                if seen[key][1] != content:
                    issues.append(
                        AgentValidationIssue(
                            code="candidate.relationship_duplicate",
                            path=("relationships", index),
                            message="Duplicate relationship has conflicting inference fields.",
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

        records, project_issues = validate_staged_records(
            "analysis_result",
            raw_records,
        )
        candidate_indexes = tuple(index for index, _ in seen.values())
        for issue in project_validation_issues(project_issues):
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


class AnalysisTableRelationship(BaseModel):
    """One per-table answer link: it starts at a focus-table column and cites `tN.column`."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    from_attribute_name: Name400
    to: Annotated[
        str,
        StringConstraints(min_length=4, max_length=430, pattern=r"^t[1-9][0-9]*\.\S"),
    ]
    relationship_kind: Annotated[
        str,
        StringConstraints(min_length=1, max_length=100, pattern=r"\S"),
    ]
    inferred_cardinality: InferredCardinality


class _AnalysisTableCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    relationships: list[AnalysisTableRelationship] = Field(max_length=2_000)


class AnalysisTableCandidateValidator:
    """Check one per-table answer against what its call showed, then as a full answer.

    Each link must start at a focus-table column and end at a column the call showed: a
    key_directory column, or a focus-table column for a self-reference. The backend then
    expands the links to full physical keys and checks them like a whole-selection answer.
    """

    def __init__(
        self,
        *,
        inputs: Mapping[str, Any],
        selected_attribute_keys: tuple[PhysicalAttributeKey, ...],
        applied: tuple[AnalysisResultRecord, ...],
    ) -> None:
        focus = inputs["focus_table"]
        self._focus = cast(str, focus["table"])
        self._keys = {
            entry["table"]: {name: entry[name] for name in _OBJECT_KEY_FIELDS}
            for entry in inputs["key_directory"]
        }
        # Columns by normalized name, so expanded records keep the registered spelling.
        self._focus_columns = {
            normalize_project_key_value(attribute["attribute_name"]): attribute["attribute_name"]
            for attribute in focus["attributes"]
        }
        self._shown = {
            entry["table"]: {
                normalize_project_key_value(column["attribute_name"]): column["attribute_name"]
                for column in (*entry["key_columns"], *entry["other_columns"])
            }
            for entry in inputs["key_directory"]
        }
        self._shown[self._focus] = {**self._shown.get(self._focus, {}), **self._focus_columns}
        self._full = AnalysisInferenceCandidateValidator(
            selected_attribute_keys=selected_attribute_keys,
            applied=applied,
        )

    def output_schema(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            deepcopy(_AnalysisTableCandidate.model_json_schema()),
        )

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        expanded, positions, issues = self._expand(candidate)
        if expanded is None:
            return AgentCandidateValidation(issues=issues)
        checked = await self._full.validate(expanded)
        return AgentCandidateValidation(
            issues=(*issues, *(_table_issue(issue, positions) for issue in checked.issues))
        )

    def parse_validated(self, candidate: JsonValue) -> tuple[StageProjectChange, ...]:
        expanded, _, issues = self._expand(candidate)
        if expanded is None or issues:
            raise InvalidRequestError("The per-table Analysis candidate is invalid.")
        return self._full.parse_validated(expanded)

    def _expand(
        self, candidate: JsonValue
    ) -> tuple[JsonValue | None, list[int], tuple[AgentValidationIssue, ...]]:
        try:
            parsed = _AnalysisTableCandidate.model_validate_json(
                json.dumps(candidate, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
                strict=True,
            )
        except TypeError, ValueError, ValidationError:
            return (
                None,
                [],
                (
                    AgentValidationIssue(
                        code="candidate.schema_invalid",
                        path=(),
                        message="The candidate does not match the per-table Analysis schema.",
                    ),
                ),
            )
        issues: list[AgentValidationIssue] = []
        relationships: list[JsonValue] = []
        positions: list[int] = []
        for index, link in enumerate(parsed.relationships):
            from_name = self._focus_columns.get(
                normalize_project_key_value(link.from_attribute_name)
            )
            if from_name is None:
                issues.append(
                    AgentValidationIssue(
                        code="candidate.from_outside_focus_table",
                        path=("relationships", index, "from_attribute_name"),
                        message=f"A link must start at a column of the focus table {self._focus}.",
                    )
                )
                continue
            table, _, column = link.to.partition(".")
            to_name = self._shown.get(table, {}).get(normalize_project_key_value(column))
            if to_name is None:
                issues.append(
                    AgentValidationIssue(
                        code="candidate.to_not_shown",
                        path=("relationships", index, "to"),
                        message="to must be tN.column for a column shown in key_directory "
                        "or in the focus table.",
                    )
                )
                continue
            relationships.append(
                {
                    **{f"from_{name}": value for name, value in self._keys[self._focus].items()},
                    "from_attribute_name": from_name,
                    **{f"to_{name}": value for name, value in self._keys[table].items()},
                    "to_attribute_name": to_name,
                    "relationship_kind": link.relationship_kind,
                    "inferred_cardinality": link.inferred_cardinality,
                }
            )
            positions.append(index)
        return {"relationships": relationships}, positions, tuple(issues)


def merge_table_findings(
    answers: Sequence[tuple[StageProjectChange, ...]],
    applied: tuple[AnalysisResultRecord, ...],
) -> tuple[tuple[StageProjectChange, ...], int]:
    """Join per-table answers in table order, keeping one finding per pair of columns.

    A finding is dropped when its two columns are already linked, in either direction and
    by any kind, by a saved finding or by an earlier finding of this run. A saved finding's
    own identity is an update, not a duplicate. Returns the joined change and the number
    of findings dropped.
    """
    saved = {_relationship_key(record) for record in applied}
    linked = {
        frozenset((_endpoint_key(record, "from"), _endpoint_key(record, "to")))
        for record in applied
    }
    records: list[dict[str, object]] = []
    dropped = 0
    for changes in answers:
        for change in changes:
            for record in change.records:
                ends = tuple(
                    tuple(
                        normalize_project_key_value(cast(str, record[f"{side}_{field}"]))
                        for field in _ATTRIBUTE_KEY_FIELDS
                    )
                    for side in ("from", "to")
                )
                identity = (
                    *ends[0],
                    *ends[1],
                    normalize_project_key_value(cast(str, record["relationship_kind"])),
                )
                pair = frozenset(ends)
                if identity not in saved and pair in linked:
                    dropped += 1
                    continue
                linked.add(pair)
                records.append(record)
    if not records:
        return (), dropped
    return (StageProjectChange(dataset="analysis_result", records=records),), dropped


def _table_issue(issue: AgentValidationIssue, positions: list[int]) -> AgentValidationIssue:
    """Point a full-answer issue back at the per-table answer's own fields."""
    path = issue.path
    if len(path) > 1 and path[0] == "relationships" and isinstance(path[1], int):
        rest = path[2:]
        if rest and isinstance(rest[0], str) and rest[0].startswith(("from_", "to_")):
            rest = ("to" if rest[0].startswith("to_") else "from_attribute_name", *rest[1:])
        path = ("relationships", positions[path[1]], *rest)
    return issue.model_copy(update={"path": path})


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
    except TypeError, ValueError, ValidationError:
        return None


def _merge_record(
    candidate: AnalysisInferenceRelationship,
    existing: AnalysisResultRecord | None,
) -> dict[str, object]:
    merged = cast(dict[str, object], candidate.model_dump(mode="json"))
    merged["relationship_kind"] = (
        normalize_project_key_value(candidate.relationship_kind)
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


_OBJECT_KEY_FIELDS = (
    "tenant_code",
    "system_code",
    "connection_code",
    "object_schema",
    "object_name",
)
_ATTRIBUTE_KEY_FIELDS = (*_OBJECT_KEY_FIELDS, "attribute_name")


def _relationship_key(
    record: AnalysisInferenceRelationship | AnalysisResultRecord,
) -> tuple[str, ...]:
    return (
        *_endpoint_key(record, "from"),
        *_endpoint_key(record, "to"),
        normalize_project_key_value(record.relationship_kind),
    )


def _endpoint_key(
    record: AnalysisInferenceRelationship | AnalysisResultRecord,
    endpoint: str,
) -> tuple[str, ...]:
    return tuple(
        normalize_project_key_value(getattr(record, f"{endpoint}_{field}"))
        for field in _ATTRIBUTE_KEY_FIELDS
    )


def _attribute_key(record: PhysicalAttributeKey) -> tuple[str, ...]:
    return tuple(
        normalize_project_key_value(getattr(record, field)) for field in _ATTRIBUTE_KEY_FIELDS
    )


__all__ = [
    "AnalysisInferenceCandidateValidator",
    "AnalysisInferenceRelationship",
    "AnalysisTableCandidateValidator",
    "AnalysisTableRelationship",
    "merge_table_findings",
]
