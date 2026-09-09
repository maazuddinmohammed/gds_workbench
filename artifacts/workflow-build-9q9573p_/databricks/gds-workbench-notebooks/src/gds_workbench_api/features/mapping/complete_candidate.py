"""Validate one complete, transformation-only Mapping candidate."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue, ValidationError

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


class CompleteMappingCandidateValidator:
    def __init__(self, *, preparation: MappingPreparation) -> None:
        self._preparation = preparation

    def output_schema(self) -> dict[str, JsonValue]:
        return deepcopy(compile_mapping_output_schema(preparation=self._preparation))

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        try:
            parsed = CompleteMappingCandidateV1.model_validate(candidate, strict=True)
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
            parsed = CompleteMappingCandidateV1.model_validate(candidate, strict=True)
        except ValidationError:
            raise InvalidRequestError("The Mapping candidate is invalid.") from None
        changes = MappingCandidateReconciler(preparation=self._preparation).reconcile(
            candidate=parsed
        )
        return CompleteMappingCandidateResult(normalized=parsed, changes=changes)
