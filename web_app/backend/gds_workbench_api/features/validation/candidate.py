"""Validate and reconcile complete per-System Validation candidates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Literal, cast

from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.domain.databricks_sql import validate_databricks_sql
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    ValidationCheckRecord,
    ValidationGroupRecord,
    normalize_model_key_value,
)
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
    pydantic_validation_issues,
)

from .context import ValidationExecutionContext, ValidationSystemAuthoringContext

_MAX_GROUPS_PER_SYSTEM = 500
_MAX_CHECKS_PER_GROUP = 1_000
_MAX_CHECKS_PER_SYSTEM = 10_000
_MAX_CANDIDATE_BYTES = 16 * 1024 * 1024

type ValidationLiteral = bool | int | float | str
type ValidationLiteralList = Annotated[
    list[ValidationLiteral],
    Field(min_length=1, max_length=10_000),
]


class _AgentValidationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    validation_check_name: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"\S",
        description="Stable name unique within the owning Validation Group.",
    )
    validation_check_description: str | None = Field(
        default=None,
        min_length=1,
        description="Optional intent and failure meaning; use null when unnecessary.",
    )
    validation_category_code: str = Field(
        pattern=r"^[a-z][a-z0-9_.-]{0,99}$",
        description=(
            "Stable lower-case category such as technical.execution or business.reconciliation."
        ),
    )
    validation_severity: Literal["blocking", "warning", "informational"] = Field(
        description="Operational importance when this assertion fails."
    )
    validation_query_sql: str = Field(
        min_length=1,
        description=(
            "Query A using governed Databricks SQL. Every physical relation must be fully "
            "qualified as catalog.schema.table; only an unqualified temporary view or table "
            "declared earlier in this same SQL batch may be referenced unqualified. Except "
            "for executes_successfully, its final result must be exactly one row and one "
            "column at runtime; any other cardinality is a query-contract execution error, "
            "not an assertion failure."
        ),
    )
    validation_comparison_query_sql: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Query B, populated only when comparison_value_type is query. Every physical "
            "relation must be fully qualified as catalog.schema.table; only an unqualified "
            "temporary object declared earlier in this same SQL batch may be referenced "
            "unqualified. Its final result must be exactly one row and one column at runtime."
        ),
    )
    validation_result_data_type: (
        Literal["boolean", "integer", "decimal", "text", "date", "timestamp"] | None
    ) = Field(
        description=(
            "Type of the single Query A cell and query-valued Query B cell; null only for "
            "executes_successfully, whose result shape is ignored."
        )
    )
    validation_comparison_operator: Literal[
        "executes_successfully",
        "is_null",
        "is_not_null",
        "is_true",
        "is_false",
        "equal",
        "not_equal",
        "greater_than",
        "greater_than_or_equal",
        "less_than",
        "less_than_or_equal",
        "in",
        "not_in",
    ] = Field(
        description=(
            "Assertion over Query A. executes_successfully uses result type null/value type "
            "none; is_null/is_not_null use a declared result type and none; is_true/is_false "
            "use boolean and none; equal/not_equal use literal or query; ordered comparisons "
            "use integer, decimal, date, or timestamp with literal or query; in/not_in use "
            "literal_list."
        )
    )
    validation_comparison_value_type: Literal[
        "none",
        "literal",
        "literal_list",
        "query",
    ] = Field(
        description=(
            "Comparison operand source. query requires Query B and a null comparison value; "
            "literal/literal_list require a value and no Query B; none requires both absent."
        )
    )
    validation_comparison_value: ValidationLiteral | ValidationLiteralList | None = Field(
        description=(
            "Typed literal operand, or a non-empty homogeneous list for in/not_in. Values "
            "must match validation_result_data_type; otherwise use null."
        )
    )


class _AgentValidationGroup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    validation_group_name: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"\S",
        description="Stable name unique within this System and shared by its Checks.",
    )
    validation_group_description: str | None = Field(
        default=None,
        min_length=1,
        description="Optional purpose and Validation coverage; use null when unnecessary.",
    )
    validation_checks: list[_AgentValidationCheck] = Field(
        min_length=1,
        max_length=_MAX_CHECKS_PER_GROUP,
        description="Complete desired active Check list for this Group.",
    )


class _AgentValidationSystemCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    system_ref: str = Field(
        pattern=r"^system_[1-9][0-9]{0,3}$",
        description="Copy the exact opaque System reference supplied in frozen context.",
    )
    validation_groups: list[_AgentValidationGroup] = Field(
        min_length=1,
        max_length=_MAX_GROUPS_PER_SYSTEM,
        description=(
            "Complete desired active Validation Group ledger for this System; omission retires "
            "a previously applied Group or Check."
        ),
    )


@dataclass(frozen=True, slots=True)
class ValidatedValidationSystemCandidate:
    system_ref: str
    groups: tuple[ValidationGroupRecord, ...]
    checks: tuple[ValidationCheckRecord, ...]


class ValidationSystemCandidateValidator:
    def __init__(self, *, context: ValidationSystemAuthoringContext) -> None:
        self._context = context

    def output_schema(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], _AgentValidationSystemCandidate.model_json_schema())

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        try:
            self.parse_validated(candidate)
        except _CandidateIssueError as error:
            return AgentCandidateValidation(issues=(error.issue,))
        except ValidationError as error:
            return AgentCandidateValidation(issues=pydantic_validation_issues(error))
        except (InvalidRequestError, TypeError, ValueError):
            return AgentCandidateValidation(
                issues=(
                    AgentValidationIssue(
                        code="candidate.schema_invalid",
                        path=(),
                        message="The candidate does not match the required Validation schema.",
                    ),
                )
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> ValidatedValidationSystemCandidate:
        try:
            encoded = json.dumps(
                candidate,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise InvalidRequestError("The Validation candidate is invalid.") from None
        if len(encoded) > _MAX_CANDIDATE_BYTES:
            raise _CandidateIssueError(
                AgentValidationIssue(
                    code="candidate.too_large",
                    path=(),
                    message="The Validation candidate exceeds its bounded size.",
                )
            )
        parsed = _AgentValidationSystemCandidate.model_validate(candidate, strict=True)
        if parsed.system_ref != self._context.system_ref:
            raise _CandidateIssueError(
                AgentValidationIssue(
                    code="candidate.system_coverage",
                    path=("system_ref",),
                    message="The candidate must use the exact frozen System reference.",
                )
            )
        group_names = [
            normalize_model_key_value(group.validation_group_name)
            for group in parsed.validation_groups
        ]
        if len(group_names) != len(set(group_names)):
            raise _CandidateIssueError(
                AgentValidationIssue(
                    code="candidate.validation_group_duplicate",
                    path=("validation_groups",),
                    message="Validation Group names must be unique for the System.",
                )
            )
        check_count = sum(len(group.validation_checks) for group in parsed.validation_groups)
        if check_count > _MAX_CHECKS_PER_SYSTEM:
            raise _CandidateIssueError(
                AgentValidationIssue(
                    code="candidate.validation_check_limit",
                    path=("validation_groups",),
                    message="The Validation candidate contains too many Validation Checks.",
                )
            )

        groups: list[ValidationGroupRecord] = []
        checks: list[ValidationCheckRecord] = []
        for group_index, group in enumerate(parsed.validation_groups):
            check_names = [
                normalize_model_key_value(check.validation_check_name)
                for check in group.validation_checks
            ]
            if len(check_names) != len(set(check_names)):
                raise _CandidateIssueError(
                    AgentValidationIssue(
                        code="candidate.validation_check_duplicate",
                        path=("validation_groups", group_index, "validation_checks"),
                        message="Validation Check names must be unique within their Group.",
                    )
                )
            contract_path: tuple[str | int, ...] = ("validation_groups", group_index)
            try:
                groups.append(
                    ValidationGroupRecord(
                        tenant_code=self._context.tenant_code,
                        system_code=self._context.system_code,
                        validation_group_name=group.validation_group_name,
                        validation_group_description=group.validation_group_description,
                        is_active=True,
                    )
                )
                for check_index, check in enumerate(group.validation_checks):
                    contract_path = (
                        "validation_groups",
                        group_index,
                        "validation_checks",
                        check_index,
                    )
                    _validate_query(
                        check.validation_query_sql,
                        must_return_rows=(
                            check.validation_comparison_operator != "executes_successfully"
                        ),
                        path=(
                            "validation_groups",
                            group_index,
                            "validation_checks",
                            check_index,
                            "validation_query_sql",
                        ),
                    )
                    if check.validation_comparison_query_sql is not None:
                        _validate_query(
                            check.validation_comparison_query_sql,
                            must_return_rows=True,
                            path=(
                                "validation_groups",
                                group_index,
                                "validation_checks",
                                check_index,
                                "validation_comparison_query_sql",
                            ),
                        )
                    comparison_value = check.validation_comparison_value
                    checks.append(
                        ValidationCheckRecord(
                            tenant_code=self._context.tenant_code,
                            system_code=self._context.system_code,
                            validation_group_name=group.validation_group_name,
                            validation_check_name=check.validation_check_name,
                            validation_check_description=(check.validation_check_description),
                            validation_category_code=check.validation_category_code,
                            validation_severity=check.validation_severity,
                            validation_query_sql=check.validation_query_sql,
                            validation_comparison_query_sql=(check.validation_comparison_query_sql),
                            validation_result_data_type=(check.validation_result_data_type),
                            validation_comparison_operator=(check.validation_comparison_operator),
                            validation_comparison_value_type=(
                                check.validation_comparison_value_type
                            ),
                            validation_comparison_value=(
                                tuple(comparison_value)
                                if isinstance(comparison_value, list)
                                else comparison_value
                            ),
                            is_active=True,
                        )
                    )
            except _CandidateIssueError:
                raise
            except ValidationError as error:
                diagnostic = pydantic_validation_issues(
                    error,
                    path_prefix=contract_path,
                    maximum_issues=1,
                )[0]
                raise _CandidateIssueError(
                    AgentValidationIssue(
                        code="candidate.validation_contract_invalid",
                        path=diagnostic.path,
                        message=diagnostic.message,
                    )
                ) from None
            except (TypeError, ValueError):
                raise _CandidateIssueError(
                    AgentValidationIssue(
                        code="candidate.validation_contract_invalid",
                        path=("validation_groups", group_index),
                        message=(
                            "The Validation Group or one of its Checks has an invalid "
                            "assertion contract."
                        ),
                    )
                ) from None
        return ValidatedValidationSystemCandidate(
            system_ref=parsed.system_ref,
            groups=tuple(groups),
            checks=tuple(checks),
        )


def reconcile_validation_candidates(
    *,
    context: ValidationExecutionContext,
    candidates: tuple[ValidatedValidationSystemCandidate, ...],
) -> tuple[StageModelChange, ...]:
    systems_by_ref = {system.system_ref: system for system in context.systems}
    candidates_by_ref = {candidate.system_ref: candidate for candidate in candidates}
    if (
        len(systems_by_ref) != len(context.systems)
        or len(candidates_by_ref) != len(candidates)
        or set(candidates_by_ref) != set(systems_by_ref)
    ):
        raise InvalidRequestError("The Validation candidate and frozen System coverage differ.")

    changed_groups: list[ValidationGroupRecord] = []
    changed_checks: list[ValidationCheckRecord] = []
    for system_ref, system in systems_by_ref.items():
        candidate = candidates_by_ref[system_ref]
        applied_groups = {_group_key(group): group for group in system.applied_groups}
        applied_checks = {_check_key(check): check for check in system.applied_checks}
        desired_groups = {_group_key(group): group for group in candidate.groups}
        desired_checks = {_check_key(check): check for check in candidate.checks}
        if (
            len(applied_groups) != len(system.applied_groups)
            or len(applied_checks) != len(system.applied_checks)
            or len(desired_groups) != len(candidate.groups)
            or len(desired_checks) != len(candidate.checks)
        ):
            raise InvalidRequestError("The Validation candidate context is ambiguous.")

        for key, desired in desired_groups.items():
            if desired != applied_groups.get(key) or key not in {
                (
                    normalize_model_key_value(system.tenant_code),
                    normalize_model_key_value(system.system_code),
                    normalize_model_key_value(name),
                )
                for name in system.current_group_names
            }:
                changed_groups.append(desired)
        for key, applied in applied_groups.items():
            if key not in desired_groups and applied.is_active:
                changed_groups.append(applied.model_copy(update={"is_active": False}))

        for key, desired in desired_checks.items():
            if desired != applied_checks.get(key):
                changed_checks.append(desired)
        for key, applied in applied_checks.items():
            if key not in desired_checks and applied.is_active:
                changed_checks.append(applied.model_copy(update={"is_active": False}))

    changes: list[StageModelChange] = []
    if changed_groups:
        changed_groups.sort(key=_group_key)
        changes.append(
            StageModelChange(
                dataset="validation_group",
                records=[record.model_dump(mode="json") for record in changed_groups],
            )
        )
    if changed_checks:
        changed_checks.sort(key=_check_key)
        changes.append(
            StageModelChange(
                dataset="validation_check",
                records=[record.model_dump(mode="json") for record in changed_checks],
            )
        )
    return tuple(changes)


class _CandidateIssueError(Exception):
    def __init__(self, issue: AgentValidationIssue) -> None:
        super().__init__(issue.code)
        self.issue = issue


def _validate_query(
    sql: str,
    *,
    must_return_rows: bool,
    path: tuple[str | int, ...],
) -> None:
    """Validate static SQL safety; deterministic orchestration enforces runtime cardinality."""
    try:
        validated = validate_databricks_sql(sql)
    except InvalidRequestError:
        raise _CandidateIssueError(
            AgentValidationIssue(
                code="candidate.validation_query_invalid",
                path=path,
                message=(
                    "Validation SQL must use governed read-only Databricks SQL, qualify every "
                    "physical relation as catalog.schema.table, and use only an unqualified "
                    "temporary object declared earlier in the same SQL batch."
                ),
            )
        ) from None
    if must_return_rows and not validated.final_returns_rows:
        raise _CandidateIssueError(
            AgentValidationIssue(
                code="candidate.validation_query_result_invalid",
                path=path,
                message="This Validation SQL must end with a row-returning statement.",
            )
        )


def _group_key(record: ValidationGroupRecord) -> tuple[str, str, str]:
    return (
        normalize_model_key_value(record.tenant_code),
        normalize_model_key_value(record.system_code),
        normalize_model_key_value(record.validation_group_name),
    )


def _check_key(record: ValidationCheckRecord) -> tuple[str, str, str, str]:
    return (
        normalize_model_key_value(record.tenant_code),
        normalize_model_key_value(record.system_code),
        normalize_model_key_value(record.validation_group_name),
        normalize_model_key_value(record.validation_check_name),
    )
