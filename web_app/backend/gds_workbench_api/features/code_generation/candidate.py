"""Exact-coverage SQL-only agent candidate validation."""

from __future__ import annotations

import re
from typing import Any, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator
from sqlglot import parse
from sqlglot.errors import ErrorLevel, ParseError
from sqlglot.expressions.ddl import DDL, Command, Set, Transaction, Use
from sqlglot.expressions.dml import DML
from sqlglot.expressions.query import Query

from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
)

_MAX_SQL_BYTES = 4 * 1024 * 1024
_UNSAFE_SQL_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class CodeGenerationTargetReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    object_id: int = Field(gt=0, repr=False)


class GeneratedSqlArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    object_id: int = Field(gt=0)
    generated_sql: str = Field(min_length=1, repr=False)

    @field_validator("generated_sql")
    @classmethod
    def validate_sql(cls, value: str) -> str:
        if not _is_valid_sql(value):
            raise ValueError("Generated SQL must be bounded SQL-only text")
        return value


class _AgentSqlArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    target_ref: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    generated_sql: str = Field(min_length=1, repr=False)


class _AgentSqlBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    artifacts: list[_AgentSqlArtifact] = Field(min_length=1, max_length=50_000)


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
        batch, issue = _parse_batch(candidate)
        if issue is not None:
            return AgentCandidateValidation(issues=(issue,))
        if batch is None:
            raise AssertionError("validated SQL batch is missing")

        refs = [artifact.target_ref for artifact in batch.artifacts]
        if len(refs) != len(set(refs)):
            return _validation("candidate.target_ref_duplicate", "Target references repeat.")
        if set(refs) != set(self._by_ref):
            return _validation(
                "candidate.target_coverage",
                "The candidate must cover every selected target exactly once.",
            )
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
        batch, issue = _parse_batch(candidate)
        if issue is not None or batch is None:
            raise InvalidRequestError("The Code Generation candidate is invalid.")
        refs = [artifact.target_ref for artifact in batch.artifacts]
        if len(refs) != len(set(refs)) or set(refs) != set(self._by_ref):
            raise InvalidRequestError("The Code Generation candidate is invalid.")
        artifacts: list[GeneratedSqlArtifact] = []
        for candidate_artifact in batch.artifacts:
            target = self._by_ref[candidate_artifact.target_ref]
            try:
                artifacts.append(
                    GeneratedSqlArtifact(
                        target_ref=target.target_ref,
                        object_id=target.object_id,
                        generated_sql=candidate_artifact.generated_sql,
                    )
                )
            except ValidationError:
                raise InvalidRequestError("The Code Generation candidate is invalid.") from None
        return tuple(artifacts)


def _parse_batch(
    candidate: JsonValue,
) -> tuple[_AgentSqlBatch | None, AgentValidationIssue | None]:
    try:
        return _AgentSqlBatch.model_validate(candidate, strict=True), None
    except ValidationError:
        return None, AgentValidationIssue(
            code="candidate.schema_invalid",
            path=(),
            message="The candidate does not match the required SQL artifact schema.",
        )


def _validation(code: str, message: str) -> AgentCandidateValidation:
    return AgentCandidateValidation(
        issues=(AgentValidationIssue(code=code, path=("artifacts",), message=message),)
    )


def _is_valid_sql(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value.strip()
        or "```" in value
        or _UNSAFE_SQL_CONTROL.search(value) is not None
        or len(value.encode("utf-8")) > _MAX_SQL_BYTES
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
