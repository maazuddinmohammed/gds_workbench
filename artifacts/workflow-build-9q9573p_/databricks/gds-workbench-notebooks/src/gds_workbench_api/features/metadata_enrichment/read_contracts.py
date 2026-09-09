"""Bounded results from a physical metadata enrichment Run."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from gds_workbench_api.features.workflows.runs.contracts import RunState

from .contracts import EnrichmentContract, EnrichmentField, EnrichmentFieldResult, EnrichmentStatus


class MetadataEnrichmentResult(EnrichmentFieldResult):
    result_id: int = Field(gt=0)
    object_schema: str | None = Field(max_length=400)
    object_name: str | None = Field(max_length=400)
    attribute_name: str | None = Field(max_length=400)
    storage_type: str | None = Field(max_length=100)

    @model_validator(mode="after")
    def validate_record(self) -> MetadataEnrichmentResult:
        if (self.field_name == "object_description") != (self.attribute_id is None):
            raise ValueError("The field must match its physical metadata identity")
        if (self.status == "applied") != (self.applied_value is not None):
            raise ValueError("Only applied results contain a generated value")
        if (
            self.field_name == "attribute_inferred_data_type"
            and self.applied_value is not None
            and len(self.applied_value) > 100
        ):
            raise ValueError("The inferred type exceeds the metadata type limit")
        return self


class MetadataEnrichmentResultPage(EnrichmentContract):
    tenant_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    workflow_run_id: int = Field(gt=0)
    workflow_run_state: RunState
    total_count: int = Field(ge=0, le=10_200)
    result_count: int = Field(ge=0, le=10_200)
    warning_count: int = Field(ge=0, le=10_200)
    counts: dict[EnrichmentStatus, Annotated[int, Field(ge=0, le=10_200)]]
    applied_field_counts: dict[EnrichmentField, Annotated[int, Field(ge=0, le=10_200)]]
    results: tuple[MetadataEnrichmentResult, ...] = Field(max_length=200, repr=False)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0, le=10_200)
    next_offset: int | None = Field(ge=1, le=10_200)

    @model_validator(mode="after")
    def validate_page(self) -> MetadataEnrichmentResultPage:
        if set(self.applied_field_counts) != {
            "object_description",
            "attribute_description",
            "attribute_inferred_data_type",
        } or sum(self.applied_field_counts.values()) != self.counts.get("applied", 0):
            raise ValueError("The applied field summary must reconcile")
        if self.total_count != self.result_count or sum(self.counts.values()) != self.total_count:
            raise ValueError("The result summary must reconcile")
        if self.warning_count != sum(
            self.counts.get(status, 0) for status in ("changed", "unavailable", "inconclusive")
        ):
            raise ValueError("The warning summary must reconcile")
        if len(self.results) != min(self.limit, max(0, self.total_count - self.offset)):
            raise ValueError("The result page must match its bounds")
        expected_next = self.offset + len(self.results)
        if self.next_offset != (expected_next if expected_next < self.total_count else None):
            raise ValueError("The next page must match the returned results")
        return self
