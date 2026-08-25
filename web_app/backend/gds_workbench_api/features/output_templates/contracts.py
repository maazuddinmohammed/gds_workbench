"""Public read-only Output Template catalog contracts."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

type OutputTemplateTargetType = Literal["mapping_object", "mapping_attribute"]
type OutputTemplateFieldDataType = Literal[
    "string", "integer", "number", "boolean", "object", "array"
]
type OutputTemplateArrayItemType = Literal["string", "integer", "number", "boolean", "object"]


class OutputTemplateContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class OutputTemplateSummary(OutputTemplateContract):
    output_template_id: int = Field(gt=0)
    output_template_code: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]{0,99}$",
    )
    output_template_name: str = Field(min_length=1, max_length=200)
    output_template_description: str | None = Field(default=None, max_length=2000)
    output_template_target_type: OutputTemplateTargetType
    output_template_schema_digest: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    output_template_schema_digest_is_valid: bool
    is_active: bool
    field_count: int = Field(ge=1, le=500)


class OutputTemplatePage(OutputTemplateContract):
    tenant_id: int = Field(gt=0)
    items: tuple[OutputTemplateSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class OutputTemplateField(OutputTemplateContract):
    output_template_field_name: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_]{0,99}$",
    )
    output_template_field_description: str = Field(min_length=1, max_length=2000)
    output_template_field_data_type: OutputTemplateFieldDataType
    output_template_field_array_item_type: OutputTemplateArrayItemType | None
    output_template_field_is_required: bool
    output_template_field_order: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_array_item_type(self) -> Self:
        is_array = self.output_template_field_data_type == "array"
        if is_array != (self.output_template_field_array_item_type is not None):
            raise ValueError("Only array Output Template fields declare an item type")
        return self


class OutputTemplateDetail(OutputTemplateContract):
    tenant_id: int = Field(gt=0)
    template: OutputTemplateSummary
    fields: tuple[OutputTemplateField, ...] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_ordered_fields(self) -> Self:
        names = [field.output_template_field_name for field in self.fields]
        orders = [field.output_template_field_order for field in self.fields]
        if (
            len(self.fields) != self.template.field_count
            or len(names) != len(set(names))
            or len(orders) != len(set(orders))
            or orders != sorted(orders)
        ):
            raise ValueError("Output Template fields must match their unique ordered summary")
        return self
