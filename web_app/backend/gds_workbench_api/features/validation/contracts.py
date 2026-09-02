"""Public Validation review contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ValidationEligibleSystem(_Contract):
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    mapping_target_count: int = Field(gt=0, le=50_000)
    current_code_target_count: int = Field(ge=0, le=50_000)
    has_applied_validation: bool


class ValidationEligibleSystemCollection(_Contract):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    items: tuple[ValidationEligibleSystem, ...] = Field(max_length=1_000)
    is_truncated: bool


class ValidationValidationCheck(_Contract):
    validation_check_id: int = Field(gt=0)
    validation_check_name: str = Field(min_length=1, max_length=200)
    validation_check_description: str | None = Field(default=None, max_length=16_384)
    validation_category_code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    validation_severity: Literal["blocking", "warning", "informational"]
    validation_query_sql: str = Field(min_length=1, max_length=100_000, repr=False)
    validation_comparison_query_sql: str | None = Field(
        default=None,
        max_length=100_000,
        repr=False,
    )
    validation_result_data_type: (
        Literal["boolean", "integer", "decimal", "text", "date", "timestamp"] | None
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
    ]
    validation_comparison_value_type: Literal[
        "none",
        "literal",
        "literal_list",
        "query",
    ]
    validation_comparison_value: JsonValue | None = Field(default=None, repr=False)
    is_active: bool


class ValidationValidationGroup(_Contract):
    validation_group_id: int = Field(gt=0)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    validation_group_name: str = Field(min_length=1, max_length=200)
    validation_group_description: str | None = Field(default=None, max_length=16_384)
    mapping_context_is_current: bool
    code_context_is_current: bool
    validation_group_is_current: bool
    is_active: bool
    checks: tuple[ValidationValidationCheck, ...] = Field(max_length=50_000)


class ValidationLedger(_Contract):
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    groups: tuple[ValidationValidationGroup, ...] = Field(max_length=10_000)


__all__ = [
    "ValidationEligibleSystem",
    "ValidationEligibleSystemCollection",
    "ValidationLedger",
    "ValidationValidationCheck",
    "ValidationValidationGroup",
]
