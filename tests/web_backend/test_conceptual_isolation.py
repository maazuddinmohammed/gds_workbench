"""Conceptual authoring cannot supply downstream inputs, tools or prerequisites."""

# Reuse synthetic fixtures at the actual frozen-context and prompt boundaries.
# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import Literal, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.snapshots.project import ProjectSnapshot
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextLimits,
    AgentContextToolRequestError,
    InMemoryAgentContextToolCatalog,
    PostgresAgentContextRepository,
    _provider_context,
)
from gds_workbench_api.features.workflows.authoring.context_inputs import project_context_inputs
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
    list_prompt_input_contracts,
    project_prompt_input_values,
)
from gds_workbench_api.features.workflows.authoring.repair import _bounded_attempt_context
from gds_workbench_api.features.workflows.authoring.tool_configuration import (
    configure_tools,
    registered_tool_definitions,
)
from gds_workbench_api.prompt_rendering import PromptVariableDefinition
from pydantic import JsonValue

from tests.web_backend.test_agent_context import (
    DimensionalContextTransaction,
    LogicalContextTransaction,
    _dimensional_snapshot,
    _load_physical_scope,
    _plan,
)
from tests.web_backend.test_dimensional_executor import _context_bundle as dimensional_context
from tests.web_backend.test_logical_executor import _context_bundle as logical_context


@pytest.mark.parametrize(
    ("workflow", "stage"),
    [
        ("logical", "candidate_authoring"),
        ("dimensional", "candidate_authoring"),
        ("mapping", "mapping_authoring"),
        ("code_generation", "sql_generation"),
        ("validation", "validation_generation"),
    ],
)
def test_downstream_contracts_and_custom_variables_exclude_conceptual(
    workflow: str, stage: str
) -> None:
    for mode in ("one_shot", "tool_assisted"):
        contracts = list_prompt_input_contracts(
            project_workflow=workflow, workflow_execution_mode=mode, stage_code=stage
        )
        assert not any("conceptual" in item.name for item in contracts)
        assert not any("conceptual" in item.name for item in registered_tool_definitions(workflow))
        for namespace, name in (
            ("common", "conceptual_objects"),
            ("common", "conceptual_object_list"),
            ("common", "conceptual_relationships"),
            ("common", "conceptual_relationship_list"),
            (mode, "applied_conceptual"),
        ):
            resolver = f"workflow.{workflow}.{namespace}.{stage}.inputs.{name}"
            assert (
                get_prompt_input_contract(
                    project_workflow=workflow,
                    workflow_execution_mode=mode,
                    stage_code=stage,
                    resolver_key=resolver,
                )
                is None
            )
            plan = _plan().model_copy(update={"project_workflow": workflow})
            frozen = plan.stages[0].model_copy(
                update={
                    "stage_code": stage,
                    "variables": (
                        PromptVariableDefinition(
                            name=name, resolver_key=resolver, data_type="json", is_required=False
                        ),
                    ),
                }
            )
            # Existing custom registrations cannot reintroduce a removed input,
            # even when a legacy caller supplies its old resolver value.
            with pytest.raises(InvalidRequestError, match="only to Conceptual"):
                project_prompt_input_values(
                    plan=plan,
                    stage=frozen,
                    context={},
                    resolver_values={resolver: {"objects": ["stale Conceptual input"]}},
                )
    assert "get_conceptual_objects" in {
        tool.name for tool in registered_tool_definitions("conceptual")
    }


@pytest.mark.parametrize("workflow", ["logical", "dimensional"])
def test_stale_conceptual_sections_cannot_escape_provider_or_generic_reader(
    workflow: Literal["logical", "dimensional"],
) -> None:
    context = (logical_context() if workflow == "logical" else dimensional_context()).context
    stale = context.model_copy(
        update={
            "applied": context.applied.model_copy(
                update={
                    "conceptual": _dimensional_snapshot().conceptual,
                }
            ),
        }
    )
    baseline = _provider_context(context)
    assert _provider_context(stale) == baseline
    assert project_context_inputs(stale.model_dump(mode="json")) == project_context_inputs(
        context.model_dump(mode="json")
    )
    catalogs = [
        InMemoryAgentContextToolCatalog(
            context=item, max_result_bytes=None, max_catalog_bytes=None, max_page_records=200
        )
        for item in (context, stale)
    ]
    assert catalogs[0].manifest == catalogs[1].manifest
    assert catalogs[0].prompt_values == catalogs[1].prompt_values
    for catalog in catalogs:
        for name in (
            "get_conceptual_objects",
            "list_conceptual_objects",
            "get_conceptual_relationships",
            "list_conceptual_relationships",
        ):
            with pytest.raises(AgentContextToolRequestError):
                catalog.invoke(name, {})
        for dataset in ("conceptual_object", "conceptual_relationship"):
            with pytest.raises(AgentContextToolRequestError):
                catalog.invoke(
                    "get_agent_context_dataset",
                    {
                        "dataset": dataset,
                        "offset": 0,
                        "limit": 200,
                    },
                )
        with pytest.raises(InvalidRequestError):
            configure_tools(
                catalog,
                ("get_conceptual_objects",),
                workflow=workflow,
                execution_mode="tool_assisted",
            )


@pytest.mark.parametrize("workflow", ["logical", "dimensional"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_conceptual_changes_do_not_change_downstream_frozen_authoring_inputs(
    workflow: Literal["logical", "dimensional"],
    mode: Literal["one_shot", "tool_assisted"],
) -> None:
    original = _dimensional_snapshot()
    changed = original.conceptual.objects[0].model_copy(
        update={
            "conceptual_object_name": "Changed Conceptual business concept",
            "conceptual_object_definition": "Independent Conceptual detail. " * 1000,
            "conceptual_object_status": "active",
        }
    )
    snapshots = [
        original.model_copy(update={"conceptual": section})
        for section in (
            original.conceptual.model_copy(update={"objects": (), "relationships": ()}),
            original.conceptual,
            original.conceptual.model_copy(update={"objects": (changed,)}),
        )
    ]
    plan = _plan(
        project_workflow=workflow,
        execution_mode=mode,
        selected_object_ids=(701,) if workflow == "dimensional" else (501,),
    )
    inputs: list[JsonValue] = []
    projected: list[dict[str, object]] = []
    for snapshot in snapshots:

        async def load_snapshot(
            *_: object, selected: ProjectSnapshot = snapshot
        ) -> ProjectSnapshot:
            return selected

        bundle = await PostgresAgentContextRepository(
            snapshot_loader=load_snapshot,
            physical_scope_loader=_load_physical_scope,
            limits=AgentContextLimits(max_selected_attributes=100),
        ).load(
            DimensionalContextTransaction()
            if workflow == "dimensional"
            else LogicalContextTransaction(),
            tenant_id=7,
            plan=plan,
        )
        assert bundle.snapshot is snapshot  # Private graph-preservation state is retained.
        assert bundle.context.applied.conceptual is None
        assert bundle.context.applied.logical == original.logical
        if workflow == "dimensional":
            assert (
                bundle.context.selected_logical_entities[0].entity == original.logical.entities[0]
            )
        inputs.append(
            _bounded_attempt_context(
                original_context=bundle.embedded_context,
                repair=None,
                maximum_bytes=None,
            )
        )
        contracts = list_prompt_input_contracts(
            project_workflow=workflow,
            workflow_execution_mode=mode,
            stage_code="candidate_authoring",
        )
        stage = plan.stages[0].model_copy(
            update={
                "variables": tuple(
                    PromptVariableDefinition(
                        name=contract.name,
                        resolver_key=contract.resolver_key,
                        data_type=contract.data_type,
                        is_required=False,
                    )
                    for contract in contracts
                )
            }
        )
        projected.append(
            project_prompt_input_values(
                plan=plan,
                stage=stage,
                context=bundle.embedded_context,
                resolver_values={},
                precomputed_values=bundle.tool_catalog.prompt_values
                if bundle.tool_catalog
                else None,
            )
        )
        if bundle.tool_catalog:
            assert not any("conceptual" in name for name in bundle.tool_catalog.allowed_tool_names)
    assert inputs[0] == inputs[1] == inputs[2]
    assert projected[0] == projected[1] == projected[2]
    assert "Changed Conceptual business concept" not in str(cast(object, inputs))
