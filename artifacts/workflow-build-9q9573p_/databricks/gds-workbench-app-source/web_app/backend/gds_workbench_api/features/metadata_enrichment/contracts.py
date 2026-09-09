"""Typed, bounded metadata evidence and completion records. No physical samples."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

type EnrichmentField = Literal[
    "object_description", "attribute_description", "attribute_inferred_data_type"
]
type EnrichmentStatus = Literal[
    "applied", "existing", "locked", "inactive", "changed", "unavailable", "inconclusive"
]
type EvidenceMethod = Literal[
    "agent_description",
    "source_comment",
    "registered_type",
    "source_schema",
    "bronze_schema",
    "source_sample",
    "bronze_sample",
    "none",
]


class EnrichmentContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class EnrichmentDescriptionTarget(EnrichmentContract):
    object_id: int = Field(gt=0, le=999_999_999_999_999_999)
    attribute_id: int | None = Field(gt=0, le=999_999_999_999_999_999)
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")


class PhysicalRelation(EnrichmentContract):
    connection_id: int = Field(gt=0)
    catalog: str = Field(min_length=1, max_length=400)
    schema_name: str = Field(alias="schema", min_length=1, max_length=400)
    table: str = Field(min_length=1, max_length=400)


class SourceAttributeEvidence(EnrichmentContract):
    object_id: int = Field(gt=0)
    object_name: str
    object_schema: str
    object_description: str | None = Field(repr=False)
    source_tenant_id: int = Field(gt=0)
    system_code: str
    attribute_id: int = Field(gt=0)
    attribute_name: str
    attribute_data_type: str
    attribute_inferred_data_type: str | None
    attribute_description: str | None = Field(repr=False)
    is_active: bool
    is_masking_required: bool
    relation: PhysicalRelation | None
    relation_column: str | None


class EnrichmentAttribute(EnrichmentContract):
    attribute_id: int = Field(gt=0)
    attribute_name: str
    attribute_data_type: str
    attribute_inferred_data_type: str | None
    attribute_description: str | None = Field(repr=False)
    attribute_ordinal_position: int = Field(gt=0)
    is_active: bool
    is_locked: bool
    is_masking_required: bool
    relation_column: str | None
    source_candidate_count: int = Field(ge=0)
    source: SourceAttributeEvidence | None = Field(repr=False)


class EnrichmentObject(EnrichmentContract):
    object_id: int = Field(gt=0)
    object_name: str
    object_schema: str
    object_description: str | None = Field(repr=False)
    is_active: bool
    is_locked: bool
    zone_code: Literal["source", "bronze"]
    source_tenant_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    tenant_catalog: str | None
    system_code: str
    connection_id: int = Field(gt=0)
    relation: PhysicalRelation | None
    attributes: tuple[EnrichmentAttribute, ...] = Field(max_length=5_000, repr=False)
    prompt_inputs: dict[str, JsonValue] = Field(default_factory=dict, repr=False)


class MetadataEnrichmentContext(EnrichmentContract):
    workflow_run_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    baseline_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    description_targets: tuple[EnrichmentDescriptionTarget, ...] | None = Field(
        default=None, min_length=1, max_length=5_000
    )
    description_revision_matches: bool = True
    objects: tuple[EnrichmentObject, ...] = Field(min_length=1, max_length=200, repr=False)


class EnrichmentFieldResult(EnrichmentContract):
    object_id: int = Field(gt=0)
    attribute_id: int | None = Field(gt=0)
    field_name: EnrichmentField
    status: EnrichmentStatus
    evidence_method: EvidenceMethod
    applied_value: str | None = Field(default=None, max_length=2_000, repr=False)
    sample_count: int = Field(default=0, ge=0, le=50)

    @field_validator("applied_value")
    @classmethod
    def validate_value(cls, value: str | None) -> str | None:
        if value is not None and (
            not value.strip()
            or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value)
            or len(value.encode("utf-8")) > 2_000
        ):
            raise ValueError("Enrichment values must be bounded nonblank text")
        return value

    @model_validator(mode="after")
    def validate_field(self) -> EnrichmentFieldResult:
        if (self.field_name == "object_description") != (self.attribute_id is None):
            raise ValueError("Enrichment field identity is invalid")
        if self.status != "applied" and self.applied_value is not None:
            raise ValueError("Only applied fields may include a value")
        if (
            self.status == "applied"
            and self.field_name == "attribute_inferred_data_type"
            and self.applied_value is None
        ):
            raise ValueError("An applied inferred type must contain a value")
        if (
            self.field_name == "attribute_inferred_data_type"
            and self.applied_value is not None
            and (len(self.applied_value) > 100 or re.search(r"[\x00-\x1f\x7f]", self.applied_value))
        ):
            raise ValueError("The inferred type is invalid")
        return self


class MetadataEnrichmentCompletion(EnrichmentContract):
    workflow_run_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    workflow_run_state: Literal["completed", "completed_with_repair"]
    warning_count: int = Field(ge=0)
    result_count: int = Field(ge=0, le=10_200)
    counts: dict[EnrichmentStatus, int]
