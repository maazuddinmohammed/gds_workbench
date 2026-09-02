"""Small, flexible Mapping authoring contract."""

from __future__ import annotations

import json
from typing import Literal, Self, cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

type JsonObject = dict[str, JsonValue]


class MappingContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class MappingObjectCandidate(MappingContractModel):
    object_dependency_order: int = Field(ge=0)
    mapping_transformation_document: JsonObject

    @model_validator(mode="after")
    def validate_size(self) -> Self:
        if _json_size(self.mapping_transformation_document) > 524_288:
            raise ValueError("Mapping transformation document exceeds 524,288 bytes")
        return self


class MappingAttributeCandidate(MappingContractModel):
    modeled_attribute_name: str = Field(min_length=1, max_length=255, pattern=r"\S")
    attribute_mapping_transformation_document: JsonObject

    @model_validator(mode="after")
    def validate_size(self) -> Self:
        if _json_size(self.attribute_mapping_transformation_document) > 65_536:
            raise ValueError("Attribute Mapping document exceeds 65,536 bytes")
        return self


class CompleteMappingCandidateV1(MappingContractModel):
    """Agent output: transformation content only; identity comes from the frozen run."""

    schema_version: Literal["1.0"]
    object_mapping: MappingObjectCandidate | None
    attribute_mappings: tuple[MappingAttributeCandidate, ...] = Field(max_length=5_000)

    @field_validator("attribute_mappings", mode="before")
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


def _json_size(value: JsonValue) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
