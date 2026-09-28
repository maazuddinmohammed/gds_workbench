from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.application.change_sets.model_validation import ModelValidationIssue
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    TenantLockRequiredError,
    WorkbenchError,
)
from gds_workbench_api.features.mapping.preparation_contracts import (
    MappingPreparation,
    MappingRunContext,
    MappingRunContextUnavailableError,
    ModeledEntityType,
)
from gds_workbench_api.features.mapping.readiness import assess_mapping_readiness
from gds_workbench_api.features.mapping.service import (
    MappingChangeSetHandoff,
    MappingNoOpCompleter,
    MappingPreparationService,
    MappingWorkflow,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionFailedError,
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizationResult,
    WorkflowChangeSetHandoffResult,
    WorkflowChangeSetValidationError,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowRunStart,
    AgentWorkflowTerminalResult,
)
from gds_workbench_api.features.workflows.authoring.no_op import AuthoringNoOpReceipt
from gds_workbench_api.features.workflows.authoring.plan import WorkflowExecutionMode
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
    AgentContextTooLargeError,
)
from gds_workbench_api.integrations.agents.composition import LocalFakeAgentAdapter
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)
from mapping_fixtures import mapping_preparation, mapping_validation_preparation
from pydantic import JsonValue


class _RecordingFake:
    def __init__(self) -> None:
        self.requests: list[AgentExecutionRequest] = []
        self.fake = LocalFakeAgentAdapter(sdk_code="openai_agents_sdk")

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        return await self.fake.execute(request)


class _Lifecycle:
    def __init__(self) -> None:
        self.starts: list[tuple[RequestPrincipal, int, int, int, str, str | None, int]] = []
        self.append_event = AsyncMock()
        self.fail = AsyncMock()

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_workflow: str,
        expected_execution_mode: str | None,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        self.starts.append(
            (
                principal,
                tenant_id,
                model_id,
                workflow_run_id,
                expected_workflow,
                expected_execution_mode,
                expected_model_revision,
            )
        )
        return AgentWorkflowRunStart(
            changed=True,
            workflow_run_id=workflow_run_id,
            workflow_run_state="running",
            started_at=datetime(2026, 8, 24, 10, tzinfo=UTC),
            model_revision=expected_model_revision,
        )


def _executor(
    preparation: MappingPreparation,
    agent: _RecordingFake,
    policy: AgentContextPolicy | None = None,
    *,
    lifecycle: _Lifecycle | None = None,
    additional_preparations: tuple[MappingPreparation, ...] = (),
    retention: AsyncMock | None = None,
) -> tuple[MappingWorkflow, AsyncMock, AsyncMock, AsyncMock]:
    async def finalize(
        _: RequestPrincipal,
        *,
        changes: tuple[StageModelChange, ...],
        **__: object,
    ) -> WorkflowChangeSetFinalizationResult:
        return WorkflowChangeSetFinalizationResult(
            handoff=WorkflowChangeSetHandoffResult(
                model_id=18,
                workflow_run_id=1048,
                model_change_set_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                replayed=False,
                draft_revision=1,
                candidate_digest="c" * 64,
                staged_record_count=sum(len(change.records) for change in changes),
                validated_at=datetime.now(UTC),
            ),
            completion=AgentWorkflowTerminalResult(
                changed=True,
                workflow_run_id=1048,
                workflow_run_state="completed",
                completed_at=datetime.now(UTC),
            ),
        )

    handoff = AsyncMock(side_effect=finalize)
    no_op = AsyncMock(
        return_value=AuthoringNoOpReceipt(
            model_id=18,
            model_revision=7,
            workflow_run_id=1048,
            workflow_run_state="completed",
            model_workflow="mapping",
            workflow_execution_mode=preparation.plan.agent_plan.workflow_execution_mode,
            correlation_id=preparation.plan.correlation_id,
            candidate_digest="d" * 64,
            replayed=False,
            completed_at=datetime.now(UTC),
            final_event=AgentWorkflowEvent(
                sequence=3,
                attempt=1,
                stage="mapping.backend_validation",
                status="running",
                message="No effective change.",
                current=1,
                total=1,
                finding_count=0,
            ),
        )
    )
    selected_lifecycle = lifecycle or _Lifecycle()
    fail = selected_lifecycle.fail
    service = MappingWorkflow(
        preparation_service=cast(
            MappingPreparationService,
            SimpleNamespace(
                prepare=AsyncMock(return_value=(preparation, *additional_preparations)),
            ),
        ),
        agent_executor=agent,
        handoff=cast(
            MappingChangeSetHandoff,
            SimpleNamespace(finalize=handoff, retain_failed_candidate=retention or AsyncMock()),
        ),
        no_op=cast(MappingNoOpCompleter, SimpleNamespace(complete=no_op)),
        lifecycle=selected_lifecycle,
        context_policy=policy,
    )
    return service, handoff, no_op, fail


async def _execute(
    service: MappingWorkflow,
) -> WorkflowChangeSetHandoffResult | AuthoringNoOpReceipt:
    return await service.execute_started(
        RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=UUID("44444444-4444-4444-4444-444444444444"),
        expected_model_revision=7,
    )


def _two_system_preparations(
    mode: WorkflowExecutionMode,
) -> tuple[MappingPreparation, MappingPreparation]:
    first = mapping_preparation(execution_mode=mode)
    pair = first.plan.pair.model_copy(update={"source_system_id": 41})
    plan = first.plan.model_copy(update={"pair": pair, "selection_ordinal": 2})
    context = first.context.model_copy(
        update={
            "pair": pair,
            "source_system": first.context.source_system.model_copy(
                update={"system_id": 41, "system_code": "GDS", "system_name": "GDS"}
            ),
        }
    )
    return first, first.model_copy(
        update={
            "plan": plan,
            "context": context,
            "readiness": assess_mapping_readiness(plan=plan, context=context),
        }
    )


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
async def test_start_binds_mapping_without_executing(
    mode: WorkflowExecutionMode,
) -> None:
    lifecycle = _Lifecycle()
    agent = _RecordingFake()
    service, handoff, no_op, fail = _executor(
        mapping_preparation(execution_mode=mode),
        agent,
        lifecycle=lifecycle,
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    result = await service.start(
        principal,
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_execution_mode=mode,
        expected_model_revision=7,
    )

    assert lifecycle.starts == [(principal, 7, 18, 1048, "mapping", mode, 7)]
    assert result.workflow_run_id == 1048
    assert result.model_revision == 7
    assert agent.requests == []
    handoff.assert_not_awaited()
    no_op.assert_not_awaited()
    fail.assert_not_awaited()
    lifecycle.append_event.assert_not_awaited()


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
@pytest.mark.parametrize("layer", ("logical_entity", "dimensional_entity"))
async def test_mapping_local_fake_completes_each_mode(
    mode: WorkflowExecutionMode,
    layer: ModeledEntityType,
) -> None:
    agent = _RecordingFake()
    preparation = mapping_preparation(
        execution_mode=mode,
        attribute_count=4,
        modeled_entity_type=layer,
    )
    assert preparation.snapshot is not None
    service, handoff, no_op, fail = _executor(preparation, agent)

    from gds_etl_workbench.application.change_sets.model_validation import (
        validate_future_graph,
    )

    with patch(
        "gds_workbench_api.features.mapping.service.validate_future_graph",
        wraps=validate_future_graph,
    ) as validate:
        result = await _execute(service)
    validate.assert_called_once()
    assert validate.call_args.kwargs["snapshot"].model_id == 18
    assert set(validate.call_args.kwargs["staged_documents"]) == {
        "mapping_object",
        "mapping_attribute",
    }

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 5
    handoff.assert_awaited_once()
    no_op.assert_not_awaited()
    fail.assert_not_awaited()
    assert [request.stage for request in agent.requests] == ["mapping_authoring"]


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
@pytest.mark.parametrize("failed_pair_first", (False, True))
@pytest.mark.parametrize(
    "failure_kind",
    (
        "incomplete_attributes",
        "missing_transformation_rule",
        "missing_join_evidence",
        "provider_timeout",
        "context_too_large",
    ),
)
async def test_mapping_retains_complete_pairs_when_another_selected_system_fails(
    mode: WorkflowExecutionMode,
    failed_pair_first: bool,
    failure_kind: str,
) -> None:
    class IncompleteSystemAgent(_RecordingFake):
        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            result = await super().execute(request)
            context = cast(dict[str, JsonValue], request.context)
            original = cast(dict[str, JsonValue], context["original_context"])
            values = cast(dict[str, JsonValue], original["values"])
            system = cast(dict[str, JsonValue], values["source_system"])
            if system["system_code"] == "GDS":
                if failure_kind == "provider_timeout":
                    raise AgentExecutionFailedError("timeout")
                if failure_kind == "context_too_large":
                    raise AgentContextTooLargeError()
                candidate = cast(dict[str, JsonValue], result.candidate)
                return result.model_copy(
                    update={
                        "candidate": (
                            {**candidate, "attribute_mappings": []}
                            if failure_kind == "incomplete_attributes"
                            else {
                                "schema_version": "1.0",
                                "object_mapping": None,
                                "attribute_mappings": [],
                                "issues": [{"code": failure_kind}],
                            }
                        ),
                    }
                )
            return result

    first, second = _two_system_preparations(mode)
    preparations = (second, first) if failed_pair_first else (first, second)
    agent, lifecycle = IncompleteSystemAgent(), _Lifecycle()
    service, handoff, no_op, fail = _executor(
        preparations[0], agent, additional_preparations=preparations[1:], lifecycle=lifecycle
    )

    result = await _execute(service)

    # The successful pair is complete; the failed pair contributes no partial
    # Object/Attribute rows to the authoritative finalizer.
    assert len(agent.requests) == (
        2 if failure_kind in {"provider_timeout", "context_too_large"} else 3
    )
    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 2
    handoff.assert_awaited_once()
    assert {
        record["source_system_code"]
        for change in handoff.call_args.kwargs["changes"]
        for record in change.records
    } == {"CRM"}
    no_op.assert_not_awaited()
    fail.assert_not_awaited()
    outcomes = [
        call.kwargs["event"]
        for call in lifecycle.append_event.call_args_list
        if call.kwargs["event"].stage.startswith("mapping.pair_")
    ]
    assert [(event.stage, event.current) for event in outcomes] == [
        (
            "mapping.pair_failed" if failed_pair_first else "mapping.pair_completed",
            2 if failed_pair_first else 1,
        ),
        (
            "mapping.pair_completed" if failed_pair_first else "mapping.pair_failed",
            1 if failed_pair_first else 2,
        ),
    ]


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
@pytest.mark.parametrize("first_outcome", ("failed", "no_source", "unchanged", "locked"))
async def test_mapping_without_successful_changes_cannot_hide_a_failed_pair(
    mode: WorkflowExecutionMode,
    first_outcome: str,
) -> None:
    first, second = _two_system_preparations(mode)
    if first_outcome in {"unchanged", "locked"}:
        first = mapping_preparation(
            execution_mode=mode, existing=True, locked=first_outcome == "locked"
        )
    elif first_outcome == "no_source":
        context = first.context.model_copy(update={"sources": ()})
        first = first.model_copy(
            update={
                "context": context,
                "readiness": assess_mapping_readiness(plan=first.plan, context=context),
            }
        )

    class NoSuccessfulChangesAgent(_RecordingFake):
        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            self.requests.append(request)
            outer = cast(dict[str, JsonValue], request.context)
            original = cast(dict[str, JsonValue], outer["original_context"])
            values = cast(dict[str, JsonValue], original["values"])
            system = cast(dict[str, JsonValue], values["source_system"])
            if system["system_code"] == "CRM" and first_outcome == "no_source":
                return AgentExecutionResult(
                    candidate={
                        "schema_version": "1.0",
                        "outcome": "no_applicable_source",
                        "object_mapping": None,
                        "attribute_mappings": [],
                    },
                    turn_count=1,
                    tool_call_count=0,
                )
            if system["system_code"] == "CRM" and first_outcome == "unchanged":
                header = first.context.headers[0]
                names = {
                    attribute.attribute_id: attribute.attribute_name
                    for attribute in header.modeled_entity.attributes
                }
                return AgentExecutionResult(
                    candidate=cast(
                        JsonValue,
                        {
                            "schema_version": "1.0",
                            "object_mapping": {
                                "object_dependency_order": header.object_dependency_order,
                                "mapping_transformation_document": header.transformation_document,
                            },
                            "attribute_mappings": [
                                {
                                    "modeled_attribute_name": names[child.modeled_attribute_id],
                                    "attribute_mapping_transformation_document": (
                                        child.transformation_document
                                    ),
                                }
                                for child in header.attribute_mappings
                            ],
                        },
                    ),
                    turn_count=1,
                    tool_call_count=0,
                )
            return AgentExecutionResult(
                candidate={
                    "schema_version": "1.0",
                    "object_mapping": None,
                    "attribute_mappings": [],
                    "issues": [{"code": "missing_join_evidence"}],
                },
                turn_count=1,
                tool_call_count=0,
            )

    service, handoff, no_op, fail = _executor(
        first, NoSuccessfulChangesAgent(), additional_preparations=(second,)
    )
    with pytest.raises(WorkbenchError) as error:
        await _execute(service)
    assert error.value.code == "mapping_evidence_unresolved"
    handoff.assert_not_awaited()
    no_op.assert_not_awaited()
    fail.assert_awaited_once()


@pytest.mark.parametrize("failed_pair_first", (False, True))
@pytest.mark.parametrize(
    "failure_code",
    (
        "authorization",
        "tenant_lock",
        "claim",
        "revision",
    ),
)
async def test_mapping_safety_fence_failure_never_becomes_partial_success(
    failed_pair_first: bool,
    failure_code: str,
) -> None:
    first, second = _two_system_preparations("one_shot")
    fatal = {
        "authorization": AuthorizationDeniedError(),
        "tenant_lock": TenantLockRequiredError(),
        "claim": DependencyUnavailableError(),
        "revision": WorkbenchError("model_revision_conflict", "Model revision changed."),
    }[failure_code]

    class FatalSystemAgent(_RecordingFake):
        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            outer = cast(dict[str, JsonValue], request.context)
            original = cast(dict[str, JsonValue], outer["original_context"])
            values = cast(dict[str, JsonValue], original["values"])
            system = cast(dict[str, JsonValue], values["source_system"])
            if system["system_code"] == "GDS":
                self.requests.append(request)
                raise fatal
            return await super().execute(request)

    preparations = (second, first) if failed_pair_first else (first, second)
    agent = FatalSystemAgent()
    service, handoff, no_op, fail = _executor(
        preparations[0], agent, additional_preparations=preparations[1:]
    )
    with pytest.raises(WorkbenchError) as error:
        await _execute(service)
    assert error.value.code == fatal.code
    assert len(agent.requests) == (1 if failed_pair_first else 2)
    handoff.assert_not_awaited()
    no_op.assert_not_awaited()
    fail.assert_awaited_once()


@pytest.mark.parametrize("failed_pair_first", (False, True))
async def test_mapping_context_identity_drift_aborts_even_with_a_valid_sibling(
    failed_pair_first: bool,
) -> None:
    first, second = _two_system_preparations("one_shot")
    context = second.context.model_copy(update={"model_revision": 8})
    second = second.model_copy(
        update={
            "context": context,
            "readiness": assess_mapping_readiness(plan=second.plan, context=context),
        }
    )
    assert any(issue.code == "context.identity_drift" for issue in second.readiness.issues)
    preparations = (second, first) if failed_pair_first else (first, second)
    agent = _RecordingFake()
    service, handoff, no_op, fail = _executor(
        preparations[0], agent, additional_preparations=preparations[1:]
    )
    with pytest.raises(MappingRunContextUnavailableError):
        await _execute(service)
    assert len(agent.requests) == (0 if failed_pair_first else 1)
    handoff.assert_not_awaited()
    no_op.assert_not_awaited()
    fail.assert_awaited_once()


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
async def test_partial_mapping_still_requires_authoritative_finalizer_validation(
    mode: WorkflowExecutionMode,
) -> None:
    class OneFailedPair(_RecordingFake):
        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            if self.requests:
                self.requests.append(request)
                raise AgentExecutionFailedError("timeout")
            return await super().execute(request)

    first, second = _two_system_preparations(mode)
    retention = AsyncMock()
    service, handoff, no_op, fail = _executor(
        first, OneFailedPair(), additional_preparations=(second,), retention=retention
    )
    issue = ModelValidationIssue(
        code="mapping.full_graph_conflict",
        dataset="mapping_object",
        record_number=1,
        fields=(),
        message="Synthetic authoritative graph conflict.",
    )
    handoff.side_effect = WorkflowChangeSetValidationError((issue,))

    with pytest.raises(WorkflowChangeSetValidationError) as error:
        await _execute(service)

    assert error.value.issues == (issue,)
    handoff.assert_awaited_once()
    retention.assert_awaited_once()
    assert retention.call_args.kwargs["changes"] == handoff.call_args.kwargs["changes"]
    assert {
        record["source_system_code"]
        for change in retention.call_args.kwargs["changes"]
        for record in change.records
    } == {"CRM"}
    no_op.assert_not_awaited()
    # Retaining the rejected draft owns the terminal failure transaction.
    fail.assert_not_awaited()


@pytest.mark.parametrize("first_failure", ("evidence", "graph"))
async def test_failed_candidate_retention_belongs_to_the_reported_pair(
    first_failure: str,
) -> None:
    first, second = _two_system_preparations("one_shot")
    if first_failure == "graph":
        context = second.context.model_copy(update={"sources": ()})
        second = second.model_copy(
            update={
                "context": context,
                "readiness": assess_mapping_readiness(plan=second.plan, context=context),
            }
        )

    class MixedFailures(_RecordingFake):
        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            result = await super().execute(request)
            outer = cast(dict[str, JsonValue], request.context)
            original = cast(dict[str, JsonValue], outer["original_context"])
            values = cast(dict[str, JsonValue], original["values"])
            system = cast(dict[str, JsonValue], values["source_system"])
            evidence_failure = system["system_code"] == "CRM" and first_failure == "evidence"
            no_source = system["system_code"] == "GDS" and first_failure == "graph"
            if evidence_failure or no_source:
                return result.model_copy(
                    update={
                        "candidate": {
                            "schema_version": "1.0",
                            "object_mapping": None,
                            "attribute_mappings": [],
                            **(
                                {"outcome": "no_applicable_source"}
                                if no_source
                                else {
                                    "issues": [{"code": "missing_transformation_rule"}],
                                }
                            ),
                        }
                    }
                )
            return result

    issue = ModelValidationIssue(
        code="mapping.full_graph_conflict",
        dataset="mapping_object",
        record_number=1,
        fields=(),
        message="Synthetic authoritative graph conflict.",
    )
    retention = AsyncMock()
    service, handoff, no_op, fail = _executor(
        first, MixedFailures(), additional_preparations=(second,), retention=retention
    )

    def validate_graph(*, staged_documents: object, **_: object) -> SimpleNamespace:
        return SimpleNamespace(issues=(issue,) if staged_documents else ())

    with (
        patch(
            "gds_workbench_api.features.mapping.service.validate_future_graph",
            side_effect=validate_graph,
        ),
        pytest.raises(WorkbenchError),
    ):
        await _execute(service)
    handoff.assert_not_awaited()
    no_op.assert_not_awaited()
    if first_failure == "evidence":
        # A later rejected candidate must not be attached to the earlier missing-rule error.
        retention.assert_not_awaited()
        fail.assert_awaited_once()
    else:
        # A subsequent no-source candidate must not erase the first rejected candidate.
        retention.assert_awaited_once()
        assert retention.call_args.kwargs["issues"] == (issue,)
        assert {
            record["source_system_code"]
            for change in retention.call_args.kwargs["changes"]
            for record in change.records
        } == {"CRM"}
        fail.assert_not_awaited()


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
@pytest.mark.parametrize("layer", ("logical_entity", "dimensional_entity"))
async def test_mapping_authors_every_selected_entity_individually(
    mode: WorkflowExecutionMode,
    layer: ModeledEntityType,
) -> None:
    first = mapping_preparation(execution_mode=mode, attribute_count=3, modeled_entity_type=layer)
    pair = first.plan.pair.model_copy(update={"modeled_entity_id": 202})
    plan = first.plan.model_copy(
        update={
            "pair": pair,
            "selection_ordinal": 2,
            "agent_plan": first.plan.agent_plan.model_copy(update={"selected_entity_ids": (202,)}),
        }
    )
    entity = first.context.target.model_copy(
        update={
            "entity_id": 202,
            "entity_name": "CustomerArchive",
        }
    )
    context = first.context.model_copy(
        update={
            "pair": pair,
            "target": entity,
            "headers": (
                first.context.headers[0].model_copy(
                    update={
                        "modeled_entity_id": 202,
                        "modeled_entity": entity,
                    }
                ),
            ),
            "sources": tuple(
                source.model_copy(update={"modeled_entity_id": 202})
                for source in first.context.sources
            ),
        }
    )
    second = mapping_validation_preparation(plan, context)
    assert first.snapshot is not None and second.snapshot is not None
    section_name = layer.removesuffix("_entity")
    first_section = getattr(first.snapshot, section_name)
    second_section = getattr(second.snapshot, section_name)
    snapshot = first.snapshot.model_copy(
        update={
            section_name: first_section.model_copy(
                update={
                    "entities": (
                        *first_section.entities,
                        *second_section.entities,
                    ),
                    "attributes": (
                        *first_section.attributes,
                        *second_section.attributes,
                    ),
                }
            ),
        }
    )
    agent = _RecordingFake()
    service, handoff, no_op, fail = _executor(
        first.model_copy(update={"snapshot": snapshot}),
        agent,
        additional_preparations=(second.model_copy(update={"snapshot": snapshot}),),
    )
    result = await _execute(service)

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 8
    assert len(agent.requests) == 2
    changes = handoff.call_args.kwargs["changes"]
    objects = next(change.records for change in changes if change.dataset == "mapping_object")
    assert {record["modeled_entity_name"] for record in objects} == {
        "Customer",
        "CustomerArchive",
    }
    handoff.assert_awaited_once()
    no_op.assert_not_awaited()
    fail.assert_not_awaited()


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
@pytest.mark.parametrize("layer", ("logical_entity", "dimensional_entity"))
@pytest.mark.parametrize("mapped_sibling", (False, True))
async def test_mapping_records_no_applicable_source_without_fabricating_a_mapping(
    mode: WorkflowExecutionMode,
    layer: ModeledEntityType,
    mapped_sibling: bool,
) -> None:
    class NoSourceAgent(_RecordingFake):
        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            context = cast(dict[str, JsonValue], request.context)
            original = cast(dict[str, JsonValue], context["original_context"])
            values = cast(dict[str, JsonValue], original["values"])
            system = cast(dict[str, JsonValue], values["source_system"])
            if mapped_sibling and system["system_code"] == "CRM":
                return await super().execute(request)
            self.requests.append(request)
            return AgentExecutionResult(
                candidate={
                    "schema_version": "1.0",
                    "outcome": "no_applicable_source",
                    "object_mapping": None,
                    "attribute_mappings": [],
                },
                turn_count=1,
                tool_call_count=0,
            )

    applicable = mapping_preparation(execution_mode=mode, modeled_entity_type=layer)
    pair = applicable.plan.pair.model_copy(update={"source_system_id": 41})
    plan = applicable.plan.model_copy(
        update={"pair": pair, "selection_ordinal": 2 if mapped_sibling else 1}
    )
    context = applicable.context.model_copy(
        update={
            "pair": pair,
            "dependency": None,
            "sources": (),
            "source_system": applicable.context.source_system.model_copy(
                update={"system_id": 41, "system_code": "GDS", "system_name": "GDS"}
            ),
        }
    )
    preparation = applicable.model_copy(
        update={
            "plan": plan,
            "context": context,
            "readiness": assess_mapping_readiness(plan=plan, context=context),
        }
    )
    agent, lifecycle = NoSourceAgent(), _Lifecycle()
    service, handoff, no_op, fail = _executor(
        preparation,
        agent,
        lifecycle=lifecycle,
        additional_preparations=(applicable,) if mapped_sibling else (),
    )
    result = await _execute(service)
    assert len(agent.requests) == (2 if mapped_sibling else 1)
    if mapped_sibling:
        assert isinstance(result, WorkflowChangeSetHandoffResult)
        handoff.assert_awaited_once()
        no_op.assert_not_awaited()
        changes = handoff.call_args.kwargs["changes"]
        assert {
            record["source_system_code"] for change in changes for record in change.records
        } == {"CRM"}
        assert result.staged_record_count == 2
    else:
        assert isinstance(result, AuthoringNoOpReceipt)
        handoff.assert_not_awaited()
        no_op.assert_awaited_once()
    fail.assert_not_awaited()
    assert any(
        "No applicable source found" in call.kwargs["event"].message
        for call in lifecycle.append_event.call_args_list
    )


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
async def test_mapping_large_descriptions_reach_the_agent_unchanged(
    mode: WorkflowExecutionMode,
) -> None:
    preparation = mapping_preparation(execution_mode=mode)
    raw = preparation.context.model_dump(mode="json")
    long_description = "Synthetic descriptive metadata. " * 100
    raw["source_system"]["system_description"] = long_description
    raw["target"]["entity_definition"] = long_description
    raw["target"]["attributes"][0]["attribute_definition"] = long_description
    raw["sources"][0]["object"]["object_description"] = long_description
    attribute_description = "x" * 1_100_000
    raw["sources"][0]["object"]["attributes"][0]["attribute_description"] = attribute_description
    entity = raw["headers"][0]["modeled_entity"]
    entity["entity_definition"] = long_description
    entity["grain"] = long_description
    entity["attributes"][0]["attribute_definition"] = long_description
    context = MappingRunContext.model_validate(raw, strict=False)
    assert context.model_dump(mode="json") == raw
    plan = preparation.plan.agent_plan
    stage = plan.stages[0].model_copy(
        update={
            "templates": PromptComponentTemplates(
                system="Mapping system.", instruction="{{ source_evidence }}"
            ),
            "variables": (
                PromptVariableDefinition(
                    name="source_evidence",
                    resolver_key="workflow.mapping.common.mapping_authoring.inputs.source_evidence",
                    data_type="json",
                    is_required=True,
                ),
            ),
        }
    )
    preparation = preparation.model_copy(
        update={
            "context": context,
            "plan": preparation.plan.model_copy(
                update={"agent_plan": plan.model_copy(update={"stages": (stage,)})}
            ),
        }
    )
    agent = _RecordingFake()
    service, handoff, _, fail = _executor(preparation, agent)

    await _execute(service)
    original = cast(
        dict[str, JsonValue],
        cast(dict[str, JsonValue], agent.requests[0].context)["original_context"],
    )
    values = cast(dict[str, JsonValue], original["values"])
    source = cast(list[dict[str, JsonValue]], values["source_evidence"])[0]
    source_object = cast(dict[str, JsonValue], source["object"])
    attribute = cast(list[dict[str, JsonValue]], source_object["attributes"])[0]
    assert attribute["attribute_description"] == attribute_description
    assert attribute_description in agent.requests[0].instruction_prompt
    handoff.assert_awaited_once()
    fail.assert_not_awaited()


async def test_mapping_requires_private_validation_context_before_provider() -> None:
    preparation = mapping_preparation()
    assert "snapshot" not in preparation.model_dump()
    assert "physical_scope" not in preparation.model_dump()
    agent = _RecordingFake()
    service, handoff, _, fail = _executor(preparation.model_copy(update={"snapshot": None}), agent)
    with pytest.raises(MappingRunContextUnavailableError):
        await _execute(service)
    assert not agent.requests
    handoff.assert_not_awaited()
    fail.assert_awaited_once()


@pytest.mark.parametrize("selected_tools", [(), ("get_existing_mapping",)])
async def test_mapping_saved_reader_selection_is_enforced(
    selected_tools: tuple[str, ...],
) -> None:
    preparation = mapping_preparation(execution_mode="tool_assisted")
    plan = preparation.plan.agent_plan
    plan = plan.model_copy(
        update={
            "stages": (
                plan.stages[0].model_copy(
                    update={
                        "agent_tool_names": selected_tools,
                    }
                ),
            )
        }
    )
    preparation = preparation.model_copy(
        update={"plan": preparation.plan.model_copy(update={"agent_plan": plan})}
    )
    agent = _RecordingFake()
    service, handoff, _, fail = _executor(preparation, agent)
    await _execute(service)
    assert agent.requests[0].allowed_tool_names == selected_tools
    assert agent.requests[0].local_tool_catalog is not None
    from gds_etl_workbench.domain.errors import InvalidRequestError

    with pytest.raises(InvalidRequestError):
        agent.requests[0].local_tool_catalog.invoke("get_mapping_sources", {})
    handoff.assert_awaited_once()
    fail.assert_not_awaited()
