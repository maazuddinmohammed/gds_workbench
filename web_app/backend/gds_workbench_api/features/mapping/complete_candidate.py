"""Validate one complete Mapping candidate without persistence."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Literal, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.mapping_contracts import MappingContractModel
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from pydantic import Field, JsonValue, ValidationError

from gds_workbench_api.features.mapping.attribute_candidate import (
    MappingAttributeCandidateValidator,
    NormalizedMappingAttributeBatch,
    build_mapping_attribute_batch_plans,
)
from gds_workbench_api.features.mapping.candidate import (
    MappingHeaderCandidateValidator,
    NormalizedMappingHeaderCandidate,
)
from gds_workbench_api.features.mapping.contracts import (
    AttributeMapperBatchOutputV1,
    HeaderMapperOutputV1,
)
from gds_workbench_api.features.mapping.output_schema import (
    compile_attribute_mapper_output_schema,
    enrich_mapping_agent_output_schema,
)
from gds_workbench_api.features.mapping.preparation_contracts import (
    MappingOutputTemplate,
    MappingPreparation,
)
from gds_workbench_api.features.mapping.reconciliation import (
    MappingCandidateReconciler,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
    pydantic_validation_issues,
)

_MAX_ATTRIBUTE_BATCHES = 100


class _CompleteMappingCandidateSchemaV1(MappingContractModel):
    """Static scaffold whose two dynamic leaves are replaced before exposure."""

    schema_version: Literal["1.0"]
    header: HeaderMapperOutputV1
    attribute_batches: list[AttributeMapperBatchOutputV1] = Field(
        min_length=1,
        max_length=_MAX_ATTRIBUTE_BATCHES,
    )


class _AgentCompleteEnvelope(MappingContractModel):
    schema_version: Literal["1.0"]
    header: JsonValue
    attribute_batches: list[JsonValue] = Field(
        min_length=1,
        max_length=_MAX_ATTRIBUTE_BATCHES,
    )


class NormalizedCompleteMappingCandidate(MappingContractModel):
    schema_version: Literal["1.0"] = "1.0"
    header: NormalizedMappingHeaderCandidate
    attribute_batches: tuple[NormalizedMappingAttributeBatch, ...] = Field(
        min_length=1,
        max_length=_MAX_ATTRIBUTE_BATCHES,
    )


@dataclass(frozen=True, slots=True)
class CompleteMappingCandidateResult:
    """Validated normalized authoring plus its identical atomic staged contract."""

    normalized: NormalizedCompleteMappingCandidate
    changes: tuple[StageModelChange, ...]


class CompleteMappingCandidateValidator:
    """Converge one-shot, tool-assisted, and detailed Mapping output."""

    def __init__(self, *, preparation: MappingPreparation) -> None:
        self._preparation = preparation
        self._header_validator = MappingHeaderCandidateValidator(preparation=preparation)

    def output_schema(self) -> dict[str, JsonValue]:
        schema = cast(
            dict[str, JsonValue],
            deepcopy(_CompleteMappingCandidateSchemaV1.model_json_schema()),
        )
        definitions = schema.get("$defs")
        if not isinstance(definitions, dict):
            raise RuntimeError("The complete Mapping schema is incomplete.")
        header_schema = self._header_validator.output_schema()
        attribute_schema = compile_attribute_mapper_output_schema(
            template=_selected_attribute_template(self._preparation)
        )
        _replace_definition(
            target=definitions,
            source=header_schema,
            name="ObjectMappingTransformationDocumentV1",
        )
        _replace_definition(
            target=definitions,
            source=attribute_schema,
            name="AttributeMappingTransformationDocumentV1",
        )
        enrich_mapping_agent_output_schema(schema)
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        envelope, envelope_issues = _parse_envelope(candidate)
        if envelope is None:
            return AgentCandidateValidation(issues=envelope_issues)

        header_validation = await self._header_validator.validate(envelope.header)
        if header_validation.issues:
            return AgentCandidateValidation(
                issues=tuple(_prefix_issue(issue, "header") for issue in header_validation.issues)
            )
        try:
            header = self._header_validator.parse_validated(envelope.header)
            plans = build_mapping_attribute_batch_plans(
                preparation=self._preparation,
                package=header.package,
            )
        except (InvalidRequestError, ValueError):
            return AgentCandidateValidation(
                issues=(
                    _issue(
                        "candidate.header_invalid",
                        ("header",),
                        "The validated Header cannot produce immutable Attribute batches.",
                    ),
                )
            )

        indexed = _index_batches(envelope.attribute_batches)
        if indexed is None or set(indexed) != {plan.chunk_index for plan in plans}:
            return AgentCandidateValidation(
                issues=(
                    _issue(
                        "candidate.attribute_batch_coverage_mismatch",
                        ("attribute_batches",),
                        "Every immutable Attribute batch must be returned exactly once.",
                    ),
                )
            )

        issues: list[AgentValidationIssue] = []
        for plan in plans:
            raw_index, document = indexed[plan.chunk_index]
            try:
                validator = MappingAttributeCandidateValidator(
                    preparation=self._preparation,
                    package=header.package,
                    batch_plan=plan,
                )
                validation = await validator.validate(document)
            except (InvalidRequestError, ValidationError, ValueError):
                issues.append(
                    _issue(
                        "candidate.attribute_batch_invalid",
                        ("attribute_batches", raw_index),
                        "The Attribute batch failed bounded backend validation.",
                    )
                )
                continue
            remaining = 200 - len(issues)
            issues.extend(
                tuple(
                    _prefix_issue(issue, "attribute_batches", raw_index)
                    for issue in validation.issues
                )[:remaining]
            )
            if len(issues) == 200:
                break
        if issues:
            return AgentCandidateValidation(issues=tuple(issues))
        try:
            self.parse_validated(candidate)
        except (InvalidRequestError, ValueError):
            return AgentCandidateValidation(
                issues=(
                    _issue(
                        "candidate.reconciliation_failed",
                        (),
                        "The complete Mapping candidate failed atomic reconciliation.",
                    ),
                )
            )
        return AgentCandidateValidation(issues=())

    def parse_validated(self, candidate: JsonValue) -> CompleteMappingCandidateResult:
        envelope, envelope_issues = _parse_envelope(candidate)
        if envelope is None:
            del envelope_issues
            raise InvalidRequestError("The complete Mapping candidate is invalid.")
        header = self._header_validator.parse_validated(envelope.header)
        plans = build_mapping_attribute_batch_plans(
            preparation=self._preparation,
            package=header.package,
        )
        indexed = _index_batches(envelope.attribute_batches)
        if indexed is None or set(indexed) != {plan.chunk_index for plan in plans}:
            raise InvalidRequestError(
                "The complete Mapping candidate requires every Attribute batch once."
            )
        batches = tuple(
            MappingAttributeCandidateValidator(
                preparation=self._preparation,
                package=header.package,
                batch_plan=plan,
            ).parse_validated(indexed[plan.chunk_index][1])
            for plan in plans
        )
        normalized = NormalizedCompleteMappingCandidate(
            header=header,
            attribute_batches=batches,
        )
        changes = MappingCandidateReconciler(preparation=self._preparation).reconcile(
            header=normalized.header,
            attribute_batches=normalized.attribute_batches,
        )
        return CompleteMappingCandidateResult(
            normalized=normalized,
            changes=changes,
        )


def _parse_envelope(
    candidate: JsonValue,
) -> tuple[_AgentCompleteEnvelope | None, tuple[AgentValidationIssue, ...]]:
    try:
        return _AgentCompleteEnvelope.model_validate(candidate, strict=True), ()
    except ValidationError as error:
        return None, pydantic_validation_issues(error)


def _index_batches(
    documents: Sequence[JsonValue],
) -> dict[int, tuple[int, JsonValue]] | None:
    indexed: dict[int, tuple[int, JsonValue]] = {}
    for raw_index, document in enumerate(documents):
        if not isinstance(document, dict):
            return None
        chunk_index = document.get("chunk_index")
        if (
            isinstance(chunk_index, bool)
            or not isinstance(chunk_index, int)
            or chunk_index in indexed
        ):
            return None
        indexed[chunk_index] = (raw_index, document)
    return indexed


def _selected_attribute_template(
    preparation: MappingPreparation,
) -> MappingOutputTemplate | None:
    selection = preparation.plan.output_template_selections.mapping_attribute
    if selection is None:
        return None
    template = next(
        (
            item
            for item in preparation.context.output_templates.definitions
            if item.output_template_id == selection.output_template_id
        ),
        None,
    )
    if (
        template is None
        or template.target_type != "mapping_attribute"
        or template.schema_digest != selection.schema_digest
        or not template.schema_digest_is_valid
        or not template.is_active
    ):
        raise InvalidRequestError("The frozen Mapping Attribute output template is unavailable.")
    return template


def _replace_definition(
    *,
    target: dict[str, JsonValue],
    source: dict[str, JsonValue],
    name: str,
) -> None:
    source_definitions = source.get("$defs")
    if (
        name not in target
        or not isinstance(source_definitions, dict)
        or name not in source_definitions
    ):
        raise RuntimeError("The dynamic Mapping stage schema is incomplete.")
    target[name] = deepcopy(source_definitions[name])


def _prefix_issue(
    issue: AgentValidationIssue,
    *prefix: str | int,
) -> AgentValidationIssue:
    return AgentValidationIssue(
        code=issue.code,
        path=(*prefix, *issue.path),
        message=issue.message,
    )


def _issue(
    code: str,
    path: tuple[str | int, ...],
    message: str,
) -> AgentValidationIssue:
    return AgentValidationIssue(code=code, path=path, message=message)
