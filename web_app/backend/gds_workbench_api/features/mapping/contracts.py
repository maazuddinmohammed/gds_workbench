"""Small, flexible Mapping authoring contract."""

from __future__ import annotations

import json
from typing import Annotated, Literal, Self, cast

from gds_etl_workbench.domain.modeling_records import has_mapping_transformation_content
from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

type JsonObject = dict[str, JsonValue]


class MappingContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MappingTargetSelection(MappingContractModel):
    modeled_entity_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    selected_attribute_ids: list[Annotated[int, Field(gt=0)]]

    @field_validator("selected_attribute_ids")
    @classmethod
    def unique_attributes(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("Select each Attribute once")
        return sorted(value)


class MappingObjectCandidate(MappingContractModel):
    object_dependency_order: int = Field(ge=0)
    mapping_transformation_document: JsonObject | None

    @field_validator("mapping_transformation_document")
    @classmethod
    def normalize_blank(cls, value: JsonObject | None) -> JsonObject | None:
        if mapping_json_size(value) > 524_288:
            raise ValueError("Mapping transformation document exceeds 524,288 bytes")
        return value if has_mapping_transformation_content(value) else None


class MappingAttributeCandidate(MappingContractModel):
    modeled_attribute_name: str = Field(min_length=1, max_length=255, pattern=r"\S")
    attribute_mapping_transformation_document: JsonObject | None

    @field_validator("attribute_mapping_transformation_document")
    @classmethod
    def normalize_blank(cls, value: JsonObject | None) -> JsonObject | None:
        if mapping_json_size(value) > 65_536:
            raise ValueError("Attribute Mapping document exceeds 65,536 bytes")
        return value if has_mapping_transformation_content(value) else None


class MappingUnresolvedIssue(MappingContractModel):
    code: Literal[
        "missing_join_evidence", "missing_transformation_rule", "preserved_mapping_conflict"
    ]
    modeled_attribute_name: str | None = Field(default=None, max_length=255)


class CompleteMappingCandidateV1(MappingContractModel):
    """Agent output: transformation content only; identity comes from the frozen run."""

    schema_version: Literal["1.0"]
    outcome: Literal["mapped", "no_applicable_source"] = Field(
        default="mapped",
        description=(
            "Use no_applicable_source with no transformations when this System has no "
            "evidenced contribution. Generated keys and framework audit/history population "
            "alone never establish a Mapping. Preserve supported partial business output."
        ),
    )
    issues: tuple[MappingUnresolvedIssue, ...] = Field(default=(), max_length=200)
    object_mapping: MappingObjectCandidate | None
    attribute_mappings: tuple[MappingAttributeCandidate, ...] = Field(max_length=5_000)

    @field_validator("attribute_mappings", "issues", mode="before")
    @classmethod
    def normalize_json_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(cast(list[object], value))
        return value

    @model_validator(mode="after")
    def validate_unique_attributes(self) -> Self:
        names = [item.modeled_attribute_name.casefold() for item in self.attribute_mappings]
        if len(names) != len(set(names)):
            raise ValueError("Mapping Attribute names must be unique")
        return self


def mapping_json_size(value: JsonValue) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
