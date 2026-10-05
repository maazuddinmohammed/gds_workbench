"""Validate one complete, transformation-only Mapping candidate."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue, ValidationError

from gds_workbench_api.features.workflows.authoring.gold_policy import effective_gold_templates
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
    pydantic_validation_issues,
)

from .contracts import CompleteMappingCandidateV1
from .output_schema import compile_mapping_output_schema
from .preparation_contracts import MappingPreparation
from .reconciliation import MappingCandidateReconciler


@dataclass(frozen=True, slots=True)
class CompleteMappingCandidateResult:
    normalized: CompleteMappingCandidateV1
    changes: tuple[StageModelChange, ...]
    warnings: tuple[AgentValidationIssue, ...]
    has_transformations: bool
    has_object_transformation: bool
    is_partial: bool
    mapped_attribute_count: int
    attribute_count: int


class CompleteMappingCandidateValidator:
    def __init__(self, *, preparation: MappingPreparation) -> None:
        self._preparation = preparation

    def output_schema(self) -> dict[str, JsonValue]:
        return deepcopy(compile_mapping_output_schema(preparation=self._preparation))

    def _parse(self, candidate: JsonValue) -> CompleteMappingCandidateV1:
        parsed = CompleteMappingCandidateV1.model_validate(candidate, strict=True)
        MappingCandidateReconciler(preparation=self._preparation).reconcile(candidate=parsed)
        context = self._preparation.context
        technical, _ = effective_gold_templates(context.authoring.technical_columns_template, None)
        history = cast(dict[str, Any] | None, technical.get("type_2"))
        history_names: set[str] = (
            {
                str(cast(dict[str, Any], column).get("semantic_name", "")).casefold()
                for column in history.values()
                if isinstance(column, dict)
            }
            if isinstance(history, dict) and context.modeled_entity_type == "dimensional_entity"
            else set()
        )
        framework_names = {
            item.attribute_name.casefold()
            for item in context.target.attributes
            if item.is_surrogate_key
            or (item.is_audit_column and item.attribute_name.casefold() != "sourcesystemid")
            or item.attribute_name.casefold() in history_names
        }
        documents = [
            item
            for item in parsed.attribute_mappings
            if item.attribute_mapping_transformation_document is not None
        ]
        object_document = (
            parsed.object_mapping.mapping_transformation_document if parsed.object_mapping else None
        )
        # Generated/framework population does not establish a source-System contribution.
        # Keep opaque custom Object logic and valid partial business transformations.
        only_framework = documents and all(
            item.modeled_attribute_name.casefold() in framework_names for item in documents
        )
        no_source_rowset = object_document is None or (
            object_document.get("source_tables") == []
            and not context.source_system.is_default
            and not any(
                object_document.get(key)
                for key in (
                    "source_objects",
                    "source_logical_entities",
                    "source_dimensional_entities",
                )
            )
        )
        if only_framework and no_source_rowset:
            return parsed.model_copy(
                update={
                    "outcome": "no_applicable_source",
                    "object_mapping": None,
                    "attribute_mappings": (),
                }
            )
        return parsed

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        try:
            parsed = self._parse(candidate)
            MappingCandidateReconciler(preparation=self._preparation).reconcile(candidate=parsed)
        except ValidationError as error:
            return AgentCandidateValidation(issues=pydantic_validation_issues(error))
        except (InvalidRequestError, ValueError) as error:
            return AgentCandidateValidation(
                issues=(
                    AgentValidationIssue(
                        code="candidate.mapping_integrity_invalid",
                        path=(),
                        message=str(error),
                    ),
                )
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> CompleteMappingCandidateResult:
        try:
            parsed = self._parse(candidate)
        except ValidationError:
            raise InvalidRequestError("The Mapping candidate is invalid.") from None
        changes = MappingCandidateReconciler(preparation=self._preparation).reconcile(
            candidate=parsed
        )
        header = self._preparation.context.headers[0]
        object_document = header.transformation_document
        attributes: dict[int, object] = {
            item.modeled_attribute_id: item.transformation_document
            if item.status == "active"
            else None
            for item in header.attribute_mappings
        }
        names = {
            item.attribute_name.casefold(): item.attribute_id
            for item in header.modeled_entity.attributes
            if item.status == "active"
        }
        for change in changes:
            for record in change.records:
                if change.dataset == "mapping_object":
                    object_document = record["mapping_transformation_document"]
                else:
                    name = str(record["modeled_attribute_name"]).casefold()
                    attributes[names[name]] = record["attribute_mapping_transformation_document"]
        mapped_count = sum(
            attributes.get(attribute_id) is not None for attribute_id in names.values()
        )
        has_transformations = object_document is not None or mapped_count > 0
        known_names = {item.attribute_name for item in self._preparation.context.target.attributes}
        warnings = tuple(
            AgentValidationIssue(
                code=f"mapping.{issue.code}",
                path=("issues", index),
                message=(
                    f"Attribute {issue.modeled_attribute_name}: "
                    if issue.modeled_attribute_name in known_names
                    and issue.modeled_attribute_name.isprintable()
                    else ""
                )
                + {
                    "missing_join_evidence": (
                        "Required join evidence is missing. "
                        "Add or correct source relationships or business assertions."
                    ),
                    "missing_transformation_rule": (
                        "A required transformation rule is missing. "
                        "Add the relevant attribute lineage or business assertion."
                    ),
                    "preserved_mapping_conflict": (
                        "The requested mapping conflicts with preserved Object or Attribute logic. "
                        "Review selection and locks."
                    ),
                }[issue.code],
            )
            for index, issue in enumerate(parsed.issues)
        )
        return CompleteMappingCandidateResult(
            normalized=parsed,
            changes=changes,
            warnings=warnings,
            has_transformations=has_transformations,
            has_object_transformation=object_document is not None,
            is_partial=has_transformations
            and (object_document is None or mapped_count < len(names)),
            mapped_attribute_count=mapped_count,
            attribute_count=len(names),
        )
