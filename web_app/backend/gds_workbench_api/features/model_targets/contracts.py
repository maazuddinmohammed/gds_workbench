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

    @field_validator("object_type_code")
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


class ExportModelDdlRequest(TargetContract):
    layer: Literal["conceptual", "logical", "dimensional"]
    expected_model_revision: int = Field(gt=0)
    entity_ids: list[Annotated[int, Field(gt=0)]] | None = Field(
        default=None, min_length=1, max_length=200
    )

    @field_validator("entity_ids")
    @classmethod
    def unique_entities(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Select each Entity once.")
        return value


class ModelTargetOptions(TargetContract):
    model_id: int
    model_revision: int
    placement: TargetPlacement | None
