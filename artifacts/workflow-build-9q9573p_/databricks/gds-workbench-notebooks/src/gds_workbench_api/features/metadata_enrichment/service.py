"""Infer missing types and author one Object unit at a time, then apply guarded metadata."""

from __future__ import annotations

import json
import re
from contextlib import suppress
from copy import deepcopy
from typing import cast
from uuid import UUID

from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.infrastructure.databricks_sql import DatabricksSqlExecutor
from pydantic import JsonValue

from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowRunStart,
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.authoring.progress import AgentWorkflowProgress
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentContextPolicy,
    AgentExecutor,
    AgentValidationIssue,
    load_default_agent_context_policy,
)
from gds_workbench_api.features.workflows.authoring.stage_runner import AgentStageRunner

from .contracts import EnrichmentFieldResult, MetadataEnrichmentCompletion
from .evidence import MetadataEvidenceReader
from .repository import MetadataEnrichmentRepository


class DescriptionValidator:
    def __init__(self, targets: dict[str, str]) -> None:
        self.targets = targets

    def output_schema(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["descriptions"],
                "properties": {
                    "descriptions": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": list(self.targets),
                        "properties": {
                            ref: {
                                "anyOf": [
                                    {"type": "string", "minLength": 1, "maxLength": 2_000},
                                    {"type": "null"},
                                ]
                            }
                            for ref in self.targets
                        },
                    }
                },
            },
        )

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        descriptions = candidate.get("descriptions") if isinstance(candidate, dict) else None
        if (
            not isinstance(candidate, dict)
            or not isinstance(descriptions, dict)
            or set(descriptions) != set(self.targets)
            or set(candidate) != {"descriptions"}
        ):
            return AgentCandidateValidation(
                issues=(
                    AgentValidationIssue(
                        code="candidate.description_coverage",
                        path=("descriptions",),
                        message=(
                            "Return exactly the requested description references; "
                            "use null for insufficient evidence."
                        ),
                    ),
                )
            )
        issues: list[AgentValidationIssue] = []
        for ref, value in descriptions.items():
            if value is None:
                continue
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value.encode("utf-8")) > 2_000
                or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value)
                or value.strip().casefold() in {"todo", "tbd", "unknown", "n/a", "not available"}
                or value.strip().casefold() == self.targets[ref].replace("_", " ").casefold()
            ):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.description_invalid",
                        path=("descriptions", ref),
                        message=(
                            "Provide a meaningful description within 2000 UTF-8 bytes; "
                            "use null when unknown."
                        ),
                    )
                )
        return AgentCandidateValidation(issues=tuple(issues))


class DatabaseMetadataEnrichmentExecutor:
    def __init__(
        self,
        *,
        repository: MetadataEnrichmentRepository,
        agent_executor: AgentExecutor,
        lifecycle: DatabaseAgentWorkflowLifecycle,
        sql_executor: DatabricksSqlExecutor | None = None,
        context_policy: AgentContextPolicy | None = None,
    ) -> None:
        self._repository = repository
        self._lifecycle = lifecycle
        self._sql_executor = sql_executor
        self._policy = context_policy or load_default_agent_context_policy()
        self._stage = AgentStageRunner(executor=agent_executor, policy=self._policy)

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        return await self._lifecycle.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_workflow="metadata_enrichment",
            expected_execution_mode="one_shot",
            expected_model_revision=expected_model_revision,
        )

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> MetadataEnrichmentCompletion:
        finalization_attempted = False
        try:
            plan, context = await self._repository.load(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            progress = AgentWorkflowProgress(
                lifecycle=self._lifecycle,
                principal=principal,
                workflow_run_id=workflow_run_id,
                expected_model_revision=expected_model_revision,
                workflow_run_claim_token=workflow_run_claim_token,
            )
            await progress.append(
                attempt=1,
                stage="metadata_evidence",
                status="running",
                message="Reading source schema and bounded type evidence for missing metadata.",
                current=None,
                total=None,
                finding_count=0,
            )

            async def connection_loader(connection_id: int):
                return await self._repository.connection(
                    principal,
                    workflow_run_id=workflow_run_id,
                    expected_model_revision=expected_model_revision,
                    connection_id=connection_id,
                )

            evidence = MetadataEvidenceReader(
                executor=self._sql_executor, connection_loader=connection_loader
            )
            regeneration = context.description_targets
            targets = {(target.object_id, target.attribute_id) for target in regeneration or ()}
            if regeneration is None:
                await evidence.collect(context.objects)
            elif context.description_revision_matches and regeneration[0].attribute_id is not None:
                await evidence.collect(
                    tuple(
                        item.model_copy(
                            update={
                                "attributes": tuple(
                                    attribute
                                    for attribute in item.attributes
                                    if (item.object_id, attribute.attribute_id) in targets
                                )
                            }
                        )
                        for item in context.objects
                    )
                )
            results: list[EnrichmentFieldResult] = []
            units: list[tuple[str, dict[str, JsonValue], dict[str, str], dict[str, int]]] = []
            key_fields = (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
            for item in context.objects:
                inputs = deepcopy(item.prompt_inputs)
                object_rows = inputs.get("object_context")
                if (
                    not isinstance(object_rows, list)
                    or len(object_rows) != 1
                    or not isinstance(object_rows[0], dict)
                ):
                    raise InvalidRequestError("The frozen Object prompt context is unavailable.")
                object_key = [object_rows[0][name] for name in key_fields]
                object_ref = json.dumps(object_key, ensure_ascii=False, separators=(",", ":"))
                if regeneration is None or (item.object_id, None) in targets:
                    object_status = (
                        "inactive"
                        if not item.is_active
                        else "locked"
                        if item.is_locked
                        else "changed"
                        if not context.description_revision_matches
                        else "inconclusive"
                    )
                    position = len(results)
                    results.append(
                        EnrichmentFieldResult(
                            object_id=item.object_id,
                            attribute_id=None,
                            field_name="object_description",
                            status=object_status,
                            evidence_method="none",
                        )
                    )
                    if object_status == "inconclusive":
                        units.append(
                            (
                                "metadata_enrichment_object",
                                deepcopy(inputs),
                                {object_ref: item.object_name},
                                {object_ref: position},
                            )
                        )
                attribute_targets: dict[str, str] = {}
                attribute_positions: dict[str, int] = {}
                selected_names: list[JsonValue] = []
                for attribute in item.attributes:
                    if (
                        regeneration is not None
                        and (item.object_id, attribute.attribute_id) not in targets
                    ):
                        continue
                    inactive = not item.is_active or not attribute.is_active
                    locked = item.is_locked or attribute.is_locked
                    typed = evidence.infer_type(item, attribute)
                    type_status = (
                        "inactive"
                        if inactive
                        else "locked"
                        if locked
                        else "existing"
                        if attribute.attribute_inferred_data_type
                        else "applied"
                        if typed.data_type
                        else "inconclusive"
                    )
                    results.append(
                        EnrichmentFieldResult(
                            object_id=item.object_id,
                            attribute_id=attribute.attribute_id,
                            field_name="attribute_inferred_data_type",
                            status=type_status,
                            evidence_method=typed.method if type_status == "applied" else "none",
                            applied_value=typed.data_type if type_status == "applied" else None,
                            sample_count=typed.sample_count if type_status == "applied" else 0,
                        )
                    )
                    description_status = (
                        "inactive"
                        if inactive
                        else "locked"
                        if locked
                        else "changed"
                        if not context.description_revision_matches
                        else "inconclusive"
                    )
                    position = len(results)
                    results.append(
                        EnrichmentFieldResult(
                            object_id=item.object_id,
                            attribute_id=attribute.attribute_id,
                            field_name="attribute_description",
                            status=description_status,
                            evidence_method="none",
                        )
                    )
                    if description_status == "inconclusive":
                        ref = json.dumps(
                            [*object_key, attribute.attribute_name],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        attribute_targets[ref] = attribute.attribute_name
                        attribute_positions[ref] = position
                        selected_names.append(attribute.attribute_name)
                if attribute_targets:
                    groups = inputs.get("object_attribute_context")
                    if (
                        not isinstance(groups, list)
                        or len(groups) != 1
                        or not isinstance(groups[0], dict)
                    ):
                        raise InvalidRequestError(
                            "The frozen Attribute prompt context is unavailable."
                        )
                    # Keep every active sibling as evidence; only this selected set is writable.
                    groups[0]["selected_attribute_names"] = selected_names
                    units.append(
                        (
                            "metadata_enrichment_attribute",
                            inputs,
                            attribute_targets,
                            attribute_positions,
                        )
                    )

            maximum_attempt = 1
            for unit_number, (prompt_workflow, inputs, assigned, positions) in enumerate(units, 1):
                validator = DescriptionValidator(assigned)
                stage_context = cast(JsonValue, {"prompt_inputs": inputs})
                try:
                    outcome = await self._stage.run(
                        plan=plan,
                        stage_code="candidate_authoring",
                        prompt_workflow=prompt_workflow,
                        resolver_values={"workflow.validation_failures": []},
                        context=stage_context,
                        output_schema=validator.output_schema(),
                        allowed_tool_names=(),
                        validator=validator,
                    )
                    descriptions = cast(
                        dict[str, JsonValue],
                        cast(dict[str, JsonValue], outcome.candidate)["descriptions"],
                    )
                    maximum_attempt = max(maximum_attempt, outcome.attempt_count)
                    for ref, value in descriptions.items():
                        position = positions[ref]
                        results[position] = results[position].model_copy(
                            update={
                                "status": "applied",
                                "applied_value": value.strip() if isinstance(value, str) else None,
                                "evidence_method": "agent_description",
                            }
                        )
                except WorkbenchError:
                    # Retry belongs to the shared runner. Never split an Object unit or
                    # substitute tools; preserve type completion and continue the next unit.
                    for position in positions.values():
                        results[position] = results[position].model_copy(
                            update={"status": "unavailable"}
                        )
                await progress.append(
                    attempt=maximum_attempt,
                    stage="candidate_authoring",
                    status="running",
                    message="Completed an Object description unit.",
                    current=unit_number,
                    total=len(units),
                    finding_count=0,
                )
            warning_count = sum(
                result.status in {"inconclusive", "unavailable"} for result in results
            )
            await progress.append(
                attempt=maximum_attempt,
                stage="metadata_enrichment",
                status="warning" if warning_count else "running",
                message="Metadata evidence is ready; unresolved fields remain unchanged."
                if warning_count
                else "Metadata evidence is ready for guarded completion.",
                current=None,
                total=None,
                finding_count=warning_count,
            )
            finalization_attempted = True
            return await self._repository.complete(
                principal,
                context=context,
                workflow_run_claim_token=workflow_run_claim_token,
                results=tuple(results),
            )
        except Exception as error:
            safe_error = (
                error
                if isinstance(error, WorkbenchError)
                else WorkbenchError(
                    code="metadata_enrichment_failed",
                    message="Metadata enrichment could not complete.",
                )
            )
            if not finalization_attempted:
                with suppress(Exception):
                    await self._lifecycle.fail(
                        principal,
                        workflow_run_id=workflow_run_id,
                        expected_model_revision=expected_model_revision,
                        workflow_run_claim_token=workflow_run_claim_token,
                        failure_code=safe_error.code,
                        safe_failure_message=safe_error.message,
                    )
            raise safe_error from None
