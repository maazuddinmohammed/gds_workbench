"""Governed complete-Model command contracts."""

import json
from datetime import datetime
from typing import Literal, Self

from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    ModelSchemaDefinition,
    normalize_model_key_value,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationInfo,
    field_validator,
    model_validator,
)

from gds_workbench_api.capabilities import (
    MAX_AGENT_TURNS,
    MAX_VALIDATION_RETRIES,
    AgentRunSelection,
)

_MAX_TEMPLATE_BYTES = 32 * 1024
_MAX_NAMING_INSTRUCTION_BYTES = 32 * 1024
_AGENT_CODE_PATTERN = r"^[a-z][a-z0-9_.-]{0,99}$"
_AGENT_MODEL_CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$"

type JsonObject = dict[str, JsonValue]


class CompleteModelRequest(BaseModel):
    """One complete create/update document; omitted fields are explicit nulls."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_name: str = Field(min_length=1, max_length=255)
    model_description: str | None = Field(default=None, min_length=1, max_length=2000)
    logical_schemas: list[ModelSchemaDefinition] = Field(
        default_factory=list[ModelSchemaDefinition], max_length=100
    )
    dimensional_schemas: list[ModelSchemaDefinition] = Field(
        default_factory=list[ModelSchemaDefinition], max_length=100
    )
    default_mapping_source_system_id: int | None = Field(default=None, gt=0)
    logical_entity_scd_type: Literal["type_1", "type_2"] | None = None
    dimensional_entity_scd_type: Literal["type_1", "type_2"] | None = None
    silver_model_naming_instructions: str | None = Field(
        default=None,
        min_length=1,
        max_length=_MAX_NAMING_INSTRUCTION_BYTES,
    )
    silver_model_audit_columns_template: JsonObject | None = None
    gold_model_naming_instructions: str | None = Field(
        default=None,
        min_length=1,
        max_length=_MAX_NAMING_INSTRUCTION_BYTES,
    )
    gold_model_technical_columns_template: JsonObject | None = None
    gold_model_audit_columns_template: JsonObject | None = None
    default_agent_sdk_code: str | None = Field(
        default=None,
        pattern=_AGENT_CODE_PATTERN,
        max_length=100,
    )
    default_agent_provider_code: str | None = Field(
        default=None,
        pattern=_AGENT_CODE_PATTERN,
        max_length=100,
    )
    default_agent_model_code: str | None = Field(
        default=None,
        pattern=_AGENT_MODEL_CODE_PATTERN,
        max_length=200,
    )
    default_reasoning_effort_code: str | None = Field(
        default=None,
        pattern=_AGENT_CODE_PATTERN,
        max_length=50,
    )
    default_max_turns: int | None = Field(default=None, ge=1, le=MAX_AGENT_TURNS)
    default_validation_retry_count: int | None = Field(
        default=None, ge=0, le=MAX_VALIDATION_RETRIES
    )

    @field_validator(
        "model_name",
        "model_description",
        "silver_model_naming_instructions",
        "gold_model_naming_instructions",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object, info: ValidationInfo) -> object:
        if value is None or not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{info.field_name} must be nonblank")
        if (
            info.field_name is not None
            and info.field_name.endswith("naming_instructions")
            and len(normalized.encode()) > _MAX_NAMING_INSTRUCTION_BYTES
        ):
            raise ValueError(f"{info.field_name} is too large")
        return normalized

    @field_validator(
        "silver_model_audit_columns_template",
        "gold_model_technical_columns_template",
        "gold_model_audit_columns_template",
    )
    @classmethod
    def bound_template(cls, value: JsonObject | None) -> JsonObject | None:
        if (
            value is not None
            and len(
                json.dumps(
                    value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
            )
            > _MAX_TEMPLATE_BYTES
        ):
            raise ValueError("Model template is too large")
        return value

    @field_validator("logical_schemas", "dimensional_schemas")
    @classmethod
    def validate_schemas(cls, value: list[ModelSchemaDefinition]) -> list[ModelSchemaDefinition]:
        names = [normalize_model_key_value(item.schema_name) for item in value]
        if len(set(names)) != len(names):
            raise ValueError("Schema names must be unique within the layer")
        if (
            len(json.dumps([item.model_dump() for item in value], ensure_ascii=False).encode())
            > 262144
        ):
            raise ValueError("Schema definitions must fit within 256 KB")
        return value

    @model_validator(mode="after")
    def validate_agent_defaults(self) -> Self:
        values = (
            self.default_agent_sdk_code,
            self.default_agent_provider_code,
            self.default_agent_model_code,
            self.default_reasoning_effort_code,
            self.default_max_turns,
            self.default_validation_retry_count,
        )
        if any(value is not None for value in values) and not all(
            value is not None for value in values
        ):
            raise ValueError("Model agent defaults must be complete or absent")
        return self

    def agent_selection(self) -> AgentRunSelection | None:
        if self.default_agent_sdk_code is None:
            return None
        if (
            self.default_agent_provider_code is None
            or self.default_agent_model_code is None
            or self.default_reasoning_effort_code is None
            or self.default_max_turns is None
            or self.default_validation_retry_count is None
        ):
            raise ValueError("Model agent defaults must be complete or absent")
        return AgentRunSelection(
            sdk_code=self.default_agent_sdk_code,
            provider_code=self.default_agent_provider_code,
            model_code=self.default_agent_model_code,
            reasoning_effort_code=self.default_reasoning_effort_code,
            max_turns=self.default_max_turns,
            validation_retry_count=self.default_validation_retry_count,
        )


class UpdateModelRequest(CompleteModelRequest):
    expected_model_revision: int = Field(gt=0)


class ArchiveModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    expected_model_revision: int = Field(gt=0)


class SetModelLockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    expected_model_revision: int = Field(gt=0)
    is_locked: bool


class ModelCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    is_active: bool
    updated_at: datetime


class ModelRevisionConflictError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="model_revision_conflict",
            message="The Model changed; refresh it before retrying this command.",
        )


class ModelNameConflictError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="model_name_conflict",
            message=(
                "A Model with this name already exists in this Tenant, including archived Models."
            ),
        )


class ModelSchemaConflictError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="model_schema_conflict",
            message=(
                "An existing Entity still uses a removed or renamed schema. "
                "Restore its schema name before saving, including schemas "
                "used by inactive Entities."
            ),
        )
