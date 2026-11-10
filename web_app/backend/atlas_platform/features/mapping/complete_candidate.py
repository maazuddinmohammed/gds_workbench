"""Validate one complete, transformation-only Mapping candidate."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, cast

from atlas_mcp.application.change_sets.project import StageProjectChange
from atlas_mcp.domain.errors import InvalidRequestError
from pydantic import JsonValue, ValidationError
from sqlglot import TokenType, exp, parse, tokenize
from sqlglot.errors import ErrorLevel, SqlglotError
from sqlglot.expressions.ddl import DDL
from sqlglot.expressions.dml import DML

from atlas_platform.features.workflows.authoring.gold_policy import effective_gold_templates
from atlas_platform.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
    pydantic_validation_issues,
)

from .contracts import MAX_MAPPING_OBJECT_BYTES, CompleteMappingCandidateV1, MappingObjectCandidate
from .output_schema import compile_mapping_output_schema, uses_standard_mapping_templates
from .preparation_contracts import MappingPreparation
from .reconciliation import MappingCandidateReconciler
from .semantics import defer_circular_sources


@dataclass(frozen=True, slots=True)
class CompleteMappingCandidateResult:
    normalized: CompleteMappingCandidateV1
    changes: tuple[StageProjectChange, ...]
    warnings: tuple[AgentValidationIssue, ...]
    has_transformations: bool
    has_object_transformation: bool
    is_partial: bool
    mapped_attribute_count: int
    attribute_count: int


def _materialize_sample_query(
    preparation: MappingPreparation,
    candidate: CompleteMappingCandidateV1,
    framework_names: set[str],
) -> CompleteMappingCandidateV1:
    """Support older frozen prompts that requested a SELECT projection marker."""
    obj = candidate.object_mapping
    if obj is None or obj.mapping_transformation_document is None:
        return candidate
    document = obj.mapping_transformation_document
    query = document.get("sample_query")
    marker = "<mapped_columns>"
    if (
        not isinstance(query, str)
        or marker not in query.lower()
        or document == preparation.context.headers[0].transformation_document
        or not uses_standard_mapping_templates(preparation, include_v2=False)
    ):
        return candidate

    # A quoted marker is ordinary SQL data. Reserve only the bare projection slot.
    try:
        tokens = tokenize(query, read="databricks")
    except SqlglotError:
        raise InvalidRequestError("The Mapping projection shorthand has invalid SQL.") from None
    slots = [
        i
        for i, token in enumerate(tokens)
        if token.token_type == TokenType.LT
        and query[token.start : token.start + len(marker)].lower() == marker
    ]
    if not slots:
        return candidate
    slot = slots[0]
    # CTE bodies and scalar subqueries are parenthesized. Their SELECT may have
    # the same output aliases as the outer query, so check the marker's own scope.
    depth = 0
    for token in tokens[:slot]:
        if token.token_type == TokenType.L_PAREN:
            depth += 1
        elif token.token_type == TokenType.R_PAREN:
            depth -= 1
    if (
        len(slots) != 1
        or depth != 0
        or slot == 0
        or tokens[slot - 1].token_type != TokenType.SELECT
        or len(tokens) <= slot + 3
        or tokens[slot + 3].token_type != TokenType.FROM
    ):
        raise InvalidRequestError("Use SELECT <mapped_columns> FROM once, in the outer query.")

    returned = {
        item.modeled_attribute_name.casefold(): item.attribute_mapping_transformation_document
        for item in candidate.attribute_mappings
    }
    names: list[str] = []
    projections: list[str] = []
    projection_chars = 0
    for target in sorted(
        preparation.context.target.attributes,
        key=lambda item: (
            item.attribute_name.casefold() == "sourcesystemid",
            item.ordinal_position,
        ),
    ):
        name = target.attribute_name
        rule = returned.get(name.casefold())
        if target.status != "active" or name.casefold() in framework_names or rule is None:
            continue
        expression = rule.get("transformation_logic")
        if (
            not isinstance(expression, str)
            or not expression.strip()
            or rule.get("default_record") is not None
        ):
            raise InvalidRequestError(
                "Projection shorthand requires a SQL expression and null default_record for "
                "each projected Attribute. Use the full sample query for separate default rules."
            )
        names.append(name)
        projections.append(expression.strip() + " AS `" + name.replace("`", "``") + "`")
        projection_chars += len(projections[-1])
        if projection_chars > MAX_MAPPING_OBJECT_BYTES:
            raise InvalidRequestError(
                "Expanded Mapping transformation document exceeds 524,288 bytes."
            )
    if not projections:
        raise InvalidRequestError(
            "Projection shorthand needs at least one mapped value expression."
        )
    start = tokens[slot].start
    expanded = query[:start] + ",\n    ".join(projections) + query[start + len(marker) :]
    # Validate the expanded JSON against the same UTF-8 document limit as a full query.
    materialized = MappingObjectCandidate(
        object_dependency_order=obj.object_dependency_order,
        mapping_transformation_document={**document, "sample_query": expanded},
    )
    try:
        # Code binds registered System values later, including a parent's different
        # namespace. Substitute only in this syntax check, never in saved Mapping.
        statements = parse(
            re.sub(r"<[^<>\r\n]{1,100} System ID>", "0", expanded),
            read="databricks",
            error_level=ErrorLevel.RAISE,
        )
    except SqlglotError, RecursionError:
        raise InvalidRequestError(
            "Projection shorthand needs one SELECT with SQL value expressions."
        ) from None
    query_ast = statements[0] if len(statements) == 1 else None
    if (
        not isinstance(query_ast, exp.Select)
        or query_ast.find(DML, DDL, exp.Into, exp.Command) is not None
        or any(not isinstance(cte.this, exp.Query) for cte in query_ast.find_all(exp.CTE))
        or [column.alias for column in query_ast.selects] != names
        or any(
            not isinstance(column, exp.Alias)
            or isinstance(column.this, exp.Alias)
            or column.this.is_star
            for column in query_ast.selects
        )
    ):
        raise InvalidRequestError(
            "Projection shorthand needs one SELECT and one unaliased value expression per "
            "mapped Attribute. Write a full sample query for different branch projections."
        )
    return candidate.model_copy(update={"object_mapping": materialized})


class CompleteMappingCandidateValidator:
    def __init__(self, *, preparation: MappingPreparation) -> None:
        self._preparation = preparation

    def output_schema(self) -> dict[str, JsonValue]:
        return deepcopy(compile_mapping_output_schema(preparation=self._preparation))

    def _reconcile(
        self, candidate: JsonValue
    ) -> tuple[CompleteMappingCandidateV1, tuple[StageProjectChange, ...]]:
        parsed = CompleteMappingCandidateV1.model_validate(candidate, strict=True)
        parsed, retain_object, retain_fields = defer_circular_sources(self._preparation, parsed)
        reconciler = MappingCandidateReconciler(
            preparation=self._preparation,
            retain_saved_object=retain_object,
            retain_saved_attributes=frozenset(retain_fields),
        )
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
        parsed = _materialize_sample_query(self._preparation, parsed, framework_names)
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
            # Validate even the supplied records that the no-source normalization omits.
            reconciler.reconcile(candidate=parsed)
            parsed = parsed.model_copy(
                update={
                    "outcome": "no_applicable_source",
                    "object_mapping": None,
                    "attribute_mappings": (),
                }
            )
        return parsed, reconciler.reconcile(candidate=parsed)

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        try:
            self._reconcile(candidate)
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
            parsed, changes = self._reconcile(candidate)
        except ValidationError:
            raise InvalidRequestError("The Mapping candidate is invalid.") from None
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
                        "Add or correct source relationships or business context records."
                    ),
                    "missing_transformation_rule": (
                        "A required transformation rule is missing. "
                        "Add the relevant attribute lineage or business context record."
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
