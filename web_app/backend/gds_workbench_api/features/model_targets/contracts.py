"""Bounded requests for Logical/Silver and Dimensional/Gold handoff."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


class TargetContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


type TargetLayer = Literal["logical", "dimensional"]


class ExportModelTargetsRequest(TargetContract):
    layer: TargetLayer
    expected_model_revision: int = Field(gt=0)
    entity_ids: list[Annotated[int, Field(gt=0)]] | None = Field(
        default=None, min_length=1, max_length=200
    )
    object_schema: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)
    ]
    object_type_code: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None

    @field_validator("entity_ids")
    @classmethod
    def unique_entities(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("Select each Entity once.")
        return value

    @field_validator("object_schema", "object_type_code")
    @classmethod
    def no_controls(cls, value: str | None) -> str | None:
        if value is not None and any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError("Names cannot contain control characters.")
        return value


class TargetPlacement(TargetContract):
    tenant_code: str
    system_code: str
    connection_code: str
    source_tenant_code: str


class ObjectTypeOption(TargetContract):
    code: str
    name: str


class TargetSchema(TargetContract):
    layer: TargetLayer
    object_schema: str


class ModelTargetOptions(TargetContract):
    model_id: int
    model_revision: int
    placement: TargetPlacement | None
    object_types: tuple[ObjectTypeOption, ...]
    schemas: tuple[TargetSchema, ...] = ()


class RegisteredTarget(TargetContract):
    object_id: int
    object_schema: str
    object_name: str
    connection_code: str


class RegisteredTargetMatch(RegisteredTarget):
    matching_entity_ids: list[int] = Field(default_factory=list[int])
    bound_entity_ids: list[int] = Field(default_factory=list[int])


class RegisteredTargetPage(TargetContract):
    items: tuple[RegisteredTargetMatch, ...]
    next_after: int | None


class AttributeAssignment(TargetContract):
    modeled_attribute_id: int = Field(gt=0)
    attribute_id: int = Field(gt=0)


class BindingSelectionRequest(TargetContract):
    layer: TargetLayer
    expected_model_revision: int = Field(gt=0)
    entity_id: int = Field(gt=0)
    object_id: int = Field(gt=0)

    @field_validator("assignments", check_fields=False)
    @classmethod
    def unique_assignments(
        cls, value: list[AttributeAssignment] | None
    ) -> list[AttributeAssignment] | None:
        if value is not None and (
            len({item.modeled_attribute_id for item in value}) != len(value)
            or len({item.attribute_id for item in value}) != len(value)
        ):
            raise ValueError("Each modeled and target Attribute must be assigned once.")
        return value


class PreviewModelBindingRequest(BindingSelectionRequest):
    assignments: list[AttributeAssignment] | None = Field(default=None, max_length=5000)


class ApplyModelBindingRequest(BindingSelectionRequest):
    assignments: list[AttributeAssignment] = Field(max_length=5000)
    expected_plan_digest: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class BindingAttribute(TargetContract):
    attribute_id: int
    attribute_name: str
    data_type: str


class BindingAssignment(TargetContract):
    binding_id: int | None = None
    is_locked: bool = False
    modeled_attribute_id: int
    modeled_attribute_name: str
    modeled_data_type: str
    attribute_id: int | None


class ModelBindingPreview(TargetContract):
    binding_id: int | None = None
    is_locked: bool = False
    model_id: int
    model_revision: int
    entity_name: str
    target: RegisteredTarget
    assignments: tuple[BindingAssignment, ...]
    target_attributes: tuple[BindingAttribute, ...]
    can_apply: bool
    action_count: int
    issues: tuple[str, ...]
    plan_digest: str


class ModelTargetBinding(TargetContract):
    entity_id: int
    entity_name: str
    binding_id: int | None
    object_id: int | None
    object_schema: str | None
    object_name: str | None
    is_locked: bool


class ModelTargetBindingPage(TargetContract):
    model_id: int
    model_revision: int
    items: tuple[ModelTargetBinding, ...]
    next_after: int | None


class GenerateModelBindingsRequest(TargetContract):
    layer: TargetLayer
    expected_model_revision: int = Field(gt=0)
    object_schema: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)
    ]
    expected_plan_digest: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")] | None = None

    @field_validator("object_schema")
    @classmethod
    def valid_schema(cls, value: str) -> str:
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Schema cannot contain control characters")
        return value


class GeneratedBindingMatch(TargetContract):
    entity_id: int
    entity_name: str
    object_id: int | None = None
    object_name: str | None = None
    status: Literal["matched", "unmatched", "ambiguous", "locked", "existing", "incompatible"]
    issues: tuple[str, ...] = ()


class GeneratedBindingsPreview(TargetContract):
    model_id: int
    model_revision: int
    object_schema: str
    matches: tuple[GeneratedBindingMatch, ...]
    can_apply: bool
    action_count: int
    plan_digest: str
    issues: tuple[str, ...] = ()
