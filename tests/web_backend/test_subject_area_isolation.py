"""Subject Areas only choose tables; they never become another workflow's input."""

# Reuse synthetic fixtures at the actual frozen-context and prompt boundaries.
# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import Any, Literal, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    SubjectAreaRecord,
    SubjectAreaTableRecord,
)
from gds_etl_workbench.domain.snapshots.project import ProjectSnapshot, SubjectAreaSection
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

# Inputs and readers that exist only for Subject Area runs.
SUBJECT_AREA_INPUTS = (
    "scope_tables",
    "table_links",
    "existing_subject_areas",
    "max_subject_area_columns",
)
SUBJECT_AREA_TOOLS = ("get_scope_tables", "get_table_links", "get_subject_areas")


def _active_section(definition: str = "Saved Subject Area detail.") -> SubjectAreaSection:
    return SubjectAreaSection(
        areas=(
            SubjectAreaRecord(
                subject_area_name="Customer Sales",
                subject_area_definition=definition,
                subject_area_status="active",
                subject_area_is_locked=False,
            ),
        ),
        tables=(
            SubjectAreaTableRecord(
                subject_area_name="Customer Sales",
                tenant_code="SOURCE",
                system_code="ERP",
                connection_code="GDS",
                object_schema="bronze_sales",
                object_name="customers",
                subject_area_table_status="active",
                subject_area_table_is_locked=False,
            ),
        ),
    )


@pytest.mark.parametrize(
    ("workflow", "stage"),
    [
        ("analysis", "relationship_inference"),
        ("logical", "candidate_authoring"),
        ("dimensional", "candidate_authoring"),
        ("mapping", "mapping_authoring"),
        ("code_generation", "sql_generation"),
        ("validation", "validation_generation"),
    ],
)
def test_other_workflows_offer_no_subject_area_inputs_or_tools(workflow: str, stage: str) -> None:
    tool_names = {tool.name for tool in registered_tool_definitions(workflow)}
    assert not any("subject_area" in name for name in tool_names)
    assert not tool_names & set(SUBJECT_AREA_TOOLS)
    for mode in ("one_shot", "tool_assisted"):
        contracts = list_prompt_input_contracts(
            project_workflow=workflow, workflow_execution_mode=mode, stage_code=stage
        )
        assert not {contract.name for contract in contracts} & set(SUBJECT_AREA_INPUTS)
        assert not any("subject_area" in contract.resolver_key for contract in contracts)
        plan = _plan().model_copy(
            update={"project_workflow": workflow, "workflow_execution_mode": mode}
        )
        for name in SUBJECT_AREA_INPUTS:
            for resolver in (
                f"workflow.{workflow}.common.{stage}.inputs.{name}",
                f"workflow.subject_area.common.candidate_authoring.inputs.{name}",
            ):
                assert (
                    get_prompt_input_contract(
                        project_workflow=workflow,
                        workflow_execution_mode=mode,
                        stage_code=stage,
                        resolver_key=resolver,
                    )
                    is None
                )
                frozen = plan.stages[0].model_copy(
                    update={
                        "stage_code": stage,
                        "variables": (
                            PromptVariableDefinition(
                                name=name,
                                resolver_key=resolver,
                                data_type="json",
                                is_required=False,
                            ),
                        ),
                    }
                )
                # A custom registration of a Subject Area input resolves to nothing.
                assert (
                    project_prompt_input_values(
                        plan=plan, stage=frozen, context={}, resolver_values={}
                    )
                    == {}
                )
    assert set(SUBJECT_AREA_TOOLS) <= {
        tool.name for tool in registered_tool_definitions("subject_area")
    }


@pytest.mark.parametrize("workflow", ["logical", "dimensional"])
def test_stale_subject_areas_cannot_escape_provider_or_readers(
    workflow: Literal["logical", "dimensional"],
) -> None:
    context = (logical_context() if workflow == "logical" else dimensional_context()).context
    stale = context.model_copy(
        update={"applied": context.applied.model_copy(update={"subject_area": _active_section()})}
    )
    provider = cast(dict[str, Any], _provider_context(stale))

    assert provider["applied"]["subject_area"] is None
    assert provider == _provider_context(context)
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
        for name in SUBJECT_AREA_TOOLS:
            with pytest.raises(AgentContextToolRequestError):
                catalog.invoke(name, {})
        for dataset in ("subject_area", "subject_area_table"):
            with pytest.raises(AgentContextToolRequestError):
                catalog.invoke(
                    "get_agent_context_dataset", {"dataset": dataset, "offset": 0, "limit": 200}
                )
        with pytest.raises(InvalidRequestError):
            configure_tools(
                catalog,
                ("get_subject_areas",),
                workflow=workflow,
                execution_mode="tool_assisted",
            )


@pytest.mark.parametrize("workflow", ["logical", "dimensional"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_subject_area_changes_do_not_change_downstream_frozen_inputs(
    workflow: Literal["logical", "dimensional"],
    mode: Literal["one_shot", "tool_assisted"],
) -> None:
    original = _dimensional_snapshot()
    snapshots = [
        original.model_copy(update={"subject_area": section})
        for section in (
            SubjectAreaSection(areas=(), tables=()),
            original.subject_area,
            _active_section("Independent Subject Area detail. " * 1000),
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
        assert bundle.snapshot is snapshot  # Private graph-validation state keeps every area.
        assert bundle.context.applied.subject_area is None
        inputs.append(
            _bounded_attempt_context(
                original_context=bundle.embedded_context, repair=None, maximum_bytes=None
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
            assert not set(SUBJECT_AREA_TOOLS) & set(bundle.tool_catalog.allowed_tool_names)
    assert inputs[0] == inputs[1] == inputs[2]
    assert projected[0] == projected[1] == projected[2]
    assert "Subject Area detail" not in str(cast(object, inputs))
