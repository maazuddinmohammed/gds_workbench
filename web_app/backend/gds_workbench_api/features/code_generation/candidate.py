"""Exact-coverage SQL-only agent candidate validation."""

from __future__ import annotations

import re
from typing import Any, Literal, Self, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlglot import parse
from sqlglot.errors import ErrorLevel, ParseError
from sqlglot.expressions.ddl import DDL, Command, Set, Transaction, Use
from sqlglot.expressions.dml import DML
from sqlglot.expressions.query import Query

from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
    pydantic_validation_issues,
)

_UNSAFE_SQL_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class CodeGenerationTargetReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    object_id: int = Field(gt=0, repr=False)
    source_system_codes: tuple[str, ...] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_source_systems(self) -> Self:
        normalized = tuple(value.strip().casefold() for value in self.source_system_codes)
        if any(not value for value in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("Target source System Codes must be unique and nonblank")
        return self


class GeneratedSqlArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    object_id: int = Field(gt=0)
    artifact_name: str = Field(min_length=1, max_length=400)
    artifact_role: Literal["target_transformation", "support"]
    source_system_codes: tuple[str, ...] = Field(max_length=200)
    generated_sql: str = Field(min_length=1, repr=False)

    @field_validator("artifact_name")
    @classmethod
    def validate_artifact_name(cls, value: str) -> str:
        if value != value.strip() or value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("Artifact name must be a file name, not a path")
        return value

    @field_validator("generated_sql")
    @classmethod
    def validate_sql(cls, value: str) -> str:
        if not _is_valid_sql(value):
            raise ValueError("Generated SQL must be bounded SQL-only text")
        return value


class _AgentSqlArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(
        pattern=r"^[a-z][a-z0-9_]{0,99}$",
        description="Copy the exact opaque target reference from frozen authoring context.",
    )
    artifact_name: str = Field(
        min_length=1,
        max_length=400,
        description="File name only, without a directory path.",
    )
    artifact_role: Literal["target_transformation", "support"] = Field(
        description=(
            "target_transformation loads the target from assigned source Systems; "
            "support is target-bound DDL or helper SQL with no System assignment."
        )
    )
    source_system_codes: list[str] = Field(
        max_length=200,
        description=(
            "Exact frozen source System Codes covered by this transformation artifact. "
            "Use an empty list only for support artifacts."
        ),
    )
    generated_sql: str = Field(
        min_length=1,
        repr=False,
        description=(
            "Complete SQL-only artifact as plain text with no Markdown fences. Separate "
            "multiple statements with semicolons; an earlier temporary view may be used by "
            "later statements in the same orchestration session."
        ),
    )

    @field_validator("artifact_name")
    @classmethod
    def validate_artifact_name(cls, value: str) -> str:
        if value != value.strip() or value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError("Artifact name must be a file name, not a path")
        return value


class _AgentSqlBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifacts: list[_AgentSqlArtifact] = Field(
        min_length=1,
        max_length=50_000,
        description="Complete artifact ledger covering every frozen target exactly once.",
    )


class CodeGenerationCandidateValidator:
    """Validate the exact opaque target references selected by the backend."""

    def __init__(self, *, targets: tuple[CodeGenerationTargetReference, ...]) -> None:
        if not targets or len(targets) > 50_000:
            raise ValueError("Code Generation targets must be bounded and nonempty")
        refs = [target.target_ref for target in targets]
        identities = [target.object_id for target in targets]
        if len(refs) != len(set(refs)) or len(identities) != len(set(identities)):
            raise ValueError("Code Generation targets must be unique")
        self._targets = targets
        self._by_ref = {target.target_ref: target for target in targets}

    def output_schema(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], _AgentSqlBatch.model_json_schema())

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        batch, issues = _parse_batch(candidate)
        if issues:
            return AgentCandidateValidation(issues=issues)
        if batch is None:
            raise AssertionError("validated SQL batch is missing")

        issue = self._coverage_issue(batch)
        if issue is not None:
            return issue
        for index, artifact in enumerate(batch.artifacts):
            if not _is_valid_sql(artifact.generated_sql):
                return AgentCandidateValidation(
                    issues=(
                        AgentValidationIssue(
                            code="candidate.sql_invalid",
                            path=("artifacts", index, "generated_sql"),
                            message="Generated SQL must be bounded SQL-only text.",
                        ),
                    )
                )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> tuple[GeneratedSqlArtifact, ...]:
        batch, issues = _parse_batch(candidate)
        if issues or batch is None:
            raise InvalidRequestError("The Code Generation candidate is invalid.")
        if self._coverage_issue(batch) is not None:
            raise InvalidRequestError("The Code Generation candidate is invalid.")
        artifacts: list[GeneratedSqlArtifact] = []
        for candidate_artifact in batch.artifacts:
            target = self._by_ref[candidate_artifact.target_ref]
            try:
                artifacts.append(
                    GeneratedSqlArtifact(
                        target_ref=target.target_ref,
                        object_id=target.object_id,
                        artifact_name=candidate_artifact.artifact_name,
                        artifact_role=candidate_artifact.artifact_role,
                        source_system_codes=tuple(
                            _canonical_system_codes(
                                candidate_artifact.source_system_codes,
                                target.source_system_codes,
                            )
                        ),
                        generated_sql=candidate_artifact.generated_sql,
                    )
                )
            except ValidationError:
                raise InvalidRequestError("The Code Generation candidate is invalid.") from None
        return tuple(artifacts)

    def _coverage_issue(
        self,
        batch: _AgentSqlBatch,
    ) -> AgentCandidateValidation | None:
        artifacts_by_target: dict[str, list[_AgentSqlArtifact]] = {}
        for artifact in batch.artifacts:
            if artifact.target_ref not in self._by_ref:
                return _validation(
                    "candidate.target_coverage",
                    "Artifacts may reference only frozen targets.",
                )
            artifacts_by_target.setdefault(artifact.target_ref, []).append(artifact)
        if set(artifacts_by_target) != set(self._by_ref):
            return _validation(
                "candidate.target_coverage",
                "The candidate must cover every selected target.",
            )

        for target_ref, artifacts in artifacts_by_target.items():
            target = self._by_ref[target_ref]
            names = tuple(item.artifact_name.strip().casefold() for item in artifacts)
            if len(names) != len(set(names)):
                return _validation(
                    "candidate.artifact_name_duplicate",
                    "Artifact names must be unique within each target.",
                )
            assigned: list[str] = []
            transformation_count = 0
            for artifact in artifacts:
                codes = [value.strip().casefold() for value in artifact.source_system_codes]
                if any(not value for value in codes) or len(codes) != len(set(codes)):
                    return _validation(
                        "candidate.source_system_coverage",
                        "Artifact source System Codes must be unique and nonblank.",
                    )
                if artifact.artifact_role == "support":
                    if codes:
                        return _validation(
                            "candidate.support_system_assignment",
                            "Support artifacts cannot own source System assignments.",
                        )
                    continue
                transformation_count += 1
                if not codes:
                    return _validation(
                        "candidate.source_system_coverage",
                        "Transformation artifacts require source System assignments.",
                    )
                assigned.extend(codes)
            expected = {value.strip().casefold() for value in target.source_system_codes}
            if (
                transformation_count == 0
                or len(assigned) != len(set(assigned))
                or set(assigned) != expected
            ):
                return _validation(
                    "candidate.source_system_coverage",
                    "Transformation artifacts must assign every frozen source System exactly once.",
                )
        return None


def _parse_batch(
    candidate: JsonValue,
) -> tuple[_AgentSqlBatch | None, tuple[AgentValidationIssue, ...]]:
    try:
        return _AgentSqlBatch.model_validate(candidate, strict=True), ()
    except ValidationError as error:
        return None, pydantic_validation_issues(error)


def _validation(code: str, message: str) -> AgentCandidateValidation:
    return AgentCandidateValidation(
        issues=(AgentValidationIssue(code=code, path=("artifacts",), message=message),)
    )


def _canonical_system_codes(
    candidate_codes: list[str],
    frozen_codes: tuple[str, ...],
) -> tuple[str, ...]:
    canonical = {value.strip().casefold(): value for value in frozen_codes}
    try:
        return tuple(canonical[value.strip().casefold()] for value in candidate_codes)
    except KeyError:
        raise InvalidRequestError("The Code Generation candidate is invalid.") from None


def _is_valid_sql(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "```" in value
        or _UNSAFE_SQL_CONTROL.search(value) is not None
    ):
        return False
    try:
        statements = parse(
            value,
            read="databricks",
            error_level=ErrorLevel.RAISE,
        )
    except ParseError:
        return False
    executable_statement_types = (
        Query,
        DDL,
        DML,
        Command,
        Use,
        Set,
        Transaction,
    )
    return bool(statements) and all(
        isinstance(statement, executable_statement_types) for statement in statements
    )
