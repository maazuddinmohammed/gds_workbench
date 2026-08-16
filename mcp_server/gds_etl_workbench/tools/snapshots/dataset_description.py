"""Typed column guidance shared by Snapshot schemas and MCP descriptions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

type JsonScalar = str | int | float | bool | None
type AcceptedValueKind = Literal[
    "fixed",
    "literal",
    "reference",
    "constrained",
    "freeform",
]


class DescriptionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DatasetColumnReference(DescriptionModel):
    record_type: str
    datasets: tuple[str, ...]
    column: str
    composite_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    nullable: bool


class DatasetColumnAcceptedValues(DescriptionModel):
    kind: AcceptedValueKind
    values: tuple[JsonScalar, ...]
    references: tuple[DatasetColumnReference, ...]
    constraints: dict[str, object]


class DatasetColumnDescription(DescriptionModel):
    name: str
    data_types: tuple[str, ...]
    required: bool
    nullable: bool
    description: str
    population_guidance: str
    accepted_values: DatasetColumnAcceptedValues
    examples: tuple[JsonScalar, ...]


class DatasetDescription(DescriptionModel):
    population_rules: tuple[str, ...]
    columns: tuple[DatasetColumnDescription, ...]
