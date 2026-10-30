"""Public Validation review contracts."""

from typing import Literal

from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import BaseModel, ConfigDict, Field, JsonValue


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ExportValidationRequest(_Contract):
    """Export active checks in active layer/shared groups, preserving currentness."""

    entity_type: Literal["logical_entity", "dimensional_entity"]
    expected_project_revision: int = Field(gt=0)


class ValidationBundleLimitExceededError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="validation_bundle_limit_exceeded",
            message="The requested Validation checks exceed the safe bundle limit.",
        )


class ValidationExportEmptyError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="validation_export_empty",
            message="No active Validation checks are available for this layer.",
        )


class ValidationEligibleSystem(_Contract):
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    # Entities the System feeds; those with a saved Mapping for it can be validated.
    scope_target_count: int = Field(gt=0)
    mapping_target_count: int = Field(ge=0)
    current_code_target_count: int = Field(ge=0)
    has_applied_validation: bool


class ValidationEligibleSystemCollection(_Contract):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    items: tuple[ValidationEligibleSystem, ...]
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
    is_locked: bool


class ValidationValidationGroup(_Contract):
    validation_group_id: int = Field(gt=0)
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"] | None = None
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    validation_group_name: str = Field(min_length=1, max_length=200)
    validation_group_description: str | None = Field(default=None, max_length=16_384)
    mapping_context_is_current: bool
    code_context_is_current: bool
    validation_group_is_current: bool
    is_active: bool
    is_locked: bool
    checks: tuple[ValidationValidationCheck, ...] = Field(max_length=50_000)


class ValidationLedger(_Contract):
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    groups: tuple[ValidationValidationGroup, ...] = Field(max_length=10_000)


__all__ = [
    "ValidationEligibleSystem",
    "ValidationEligibleSystemCollection",
    "ValidationLedger",
    "ValidationValidationCheck",
    "ValidationValidationGroup",
]
