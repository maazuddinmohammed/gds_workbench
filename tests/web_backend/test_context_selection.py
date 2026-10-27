"""Requirements are evidence with automatic availability, scope and provenance."""

# pyright: reportPrivateUsage=false
from typing import Any, LiteralString, cast

import pytest
from gds_etl_workbench.domain.snapshots.project import ContextSection
from tests.mcp.project_test_fixtures import complete_project_graph
from tests.web_backend.mapping_fixtures import mapping_preparation

from gds_workbench_api.features.context.context import (
    select_context_records,
    with_cited_context_records,
)
from gds_workbench_api.features.mapping.execution_context import (
    build_mapping_execution_context,
)
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    DownstreamContextReaders,
    project_downstream_inputs,
)


ALL_WORKFLOWS = (
    "analysis",
    "subject_area",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
    "validation",
)


def section(workflows: tuple[str, ...] = ALL_WORKFLOWS) -> dict[str, Any]:
    graph = complete_project_graph()
    group = {**graph["context_group"][0], "source_system_code": None}
    record = {
        **graph["context_record"][0],
        "context_text": "Report sales at month and customer grain.",
    }
    return {
        "types": [
            {
                "context_type_name": "Business Requirement",
                "context_type_description": None,
                "context_type_workflows": list(workflows),
            }
        ],
        "groups": [group],
        "records": [record],
    }


def test_requirements_are_filtered_by_activity_and_authorized_source_system_scope() -> None:
    data = section()
    scope = [
        {"tenant_code": "ACME", "system_code": "ERP"},
        {"tenant_code": "OTHER", "system_code": "CRM"},
    ]
    assert select_context_records(data, source_scope=scope, workflow="mapping")
    assert select_context_records(data, source_scope=scope, workflow="mapping")
    document = data["groups"][0]
    document.update(source_system_code="erp")
    assert select_context_records(data, source_scope=scope, workflow="mapping")
    document["source_system_code"] = "UNKNOWN"
    assert not select_context_records(data, source_scope=scope, workflow="mapping")
    document.update(source_system_code="ERP", is_active=False)
    assert not select_context_records(data, source_scope=scope, workflow="mapping")
    document["is_active"] = True
    data["records"][0]["status"] = "inactive"
    assert not select_context_records(data, source_scope=scope, workflow="mapping")


def test_records_reach_only_the_workflows_their_type_is_routed_to() -> None:
    data = section(("mapping", "validation"))
    scope = [{"tenant_code": "ACME", "system_code": "ERP"}]
    assert select_context_records(data, source_scope=scope, workflow="mapping")
    assert not select_context_records(data, source_scope=scope, workflow="logical")
    data["types"][0]["context_type_workflows"] = []
    assert not select_context_records(data, source_scope=scope, workflow="mapping")


def test_cited_records_pass_whatever_their_type_or_system() -> None:
    data = section(("code_generation",))
    data["groups"][0]["source_system_code"] = "CRM"
    record_id = data["records"][0]["context_record_id"]
    scope = [{"tenant_code": "ACME", "system_code": "ERP"}]
    routed = select_context_records(data, source_scope=scope, workflow="logical")
    assert routed == []
    cited = with_cited_context_records(data, routed, {record_id.upper()})
    assert [record["context_record_id"] for record in cited] == [record_id]
    assert with_cited_context_records(data, cited, {record_id}) == cited
    data["records"][0]["status"] = "inactive"
    assert with_cited_context_records(data, [], {record_id}) == []


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_mapping_receives_unlinked_project_wide_requirements_in_both_modes(
    mode: Any,
) -> None:
    preparation = mapping_preparation()
    assert preparation.snapshot is not None
    preparation = preparation.model_copy(
        update={
            "snapshot": preparation.snapshot.model_copy(
                update={"context": ContextSection.model_validate(section(), strict=False)}
            )
        }
    )
    execution = build_mapping_execution_context(preparation=preparation, execution_mode=mode)
    if mode == "one_shot":
        values = project_downstream_inputs(
            "mapping", cast(dict[str, Any], execution.embedded_context)
        )
    else:
        assert isinstance(execution.tool_catalog, DownstreamContextReaders)
        values = execution.tool_catalog.prompt_values
    requirements = values["mapping_support"]["context_records"]
    assert len(requirements) == 1
    assert requirements[0]["context_text"] == "Report sales at month and customer grain."
    assert "context_record_id" in requirements[0]


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_dimensional_requirements_follow_business_system_behind_silver(
    mode: Any,
) -> None:
    from tests.web_backend.test_agent_context import (
        DimensionalContextTransaction,
        _dimensional_snapshot,
        _load_physical_scope,
        _plan,
    )

    from gds_workbench_api.features.workflows.authoring.context import (
        AgentContextLimits,
        PostgresAgentContextRepository,
    )

    requirement = section()
    requirement["groups"][0].update(source_system_code="ERP")
    snapshot = _dimensional_snapshot().model_copy(
        update={
            "project_tenant_code": "PROJECT_OWNER",
            "context": ContextSection.model_validate(requirement, strict=False),
        }
    )

    async def load_snapshot(*_: object):
        return snapshot

    # Optimize packages the whole run when it loads; the Mapping behind silver names ERP.
    result = await PostgresAgentContextRepository(
        snapshot_loader=load_snapshot,
        physical_scope_loader=_load_physical_scope,
        limits=AgentContextLimits(max_selected_attributes=1),
    ).load(
        DimensionalContextTransaction(),
        tenant_id=7,
        plan=_plan(
            project_workflow="dimensional",
            selected_object_ids=(701,),
            execution_mode=mode,
            operation="optimize",
        ),
    )
    if mode == "one_shot":
        assert isinstance(result.embedded_context, dict)
        assert "context_source_scope" not in result.embedded_context
        values = cast(dict[str, Any], result.embedded_context["prompt_inputs"])
    else:
        assert result.tool_catalog is not None
        values = result.tool_catalog.prompt_values
    assert len(values["context_records"]) == 1
    assert values["context_records"][0]["context_type_name"] == "Business Requirement"
    assert "context_source_scope" not in values


@pytest.mark.parametrize("workflow", ["analysis", "subject_area", "logical"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_all_modeling_workflows_receive_context_without_layer_selection(
    workflow: Any, mode: Any
) -> None:
    from tests.web_backend.test_agent_context import (
        _CUSTOMERS,
        ContextTransaction,
        _load_physical_scope,
        _plan,
        _snapshot,
    )

    from gds_workbench_api.features.workflows.authoring.context import (
        AgentContextLimits,
        PostgresAgentContextRepository,
        focus_subject_area,
    )

    data = section()
    data["groups"][0].update(source_system_code="ERP")
    snapshot = _snapshot().model_copy(
        update={
            "project_tenant_code": "PROJECT_OWNER",
            "context": ContextSection.model_validate(data, strict=False),
        }
    )

    async def load_snapshot(*_: object):
        return snapshot

    class ModelingTransaction(ContextTransaction):
        async def fetch_all(self, query: LiteralString, parameters: tuple[Any, ...] = ()):
            if len(parameters) >= 3 and parameters[2] == workflow:
                parameters = (*parameters[:2], "subject_area", *parameters[3:])
            return await super().fetch_all(query, parameters)

    plan = _plan(project_workflow=workflow, execution_mode=mode)
    result = await PostgresAgentContextRepository(
        snapshot_loader=load_snapshot,
        physical_scope_loader=_load_physical_scope,
        limits=AgentContextLimits(max_selected_attributes=100),
    ).load(ModelingTransaction(), tenant_id=7, plan=plan)
    if workflow == "logical":
        # A Logical Build packages each Subject Area call; the area holds the Object.
        focused = focus_subject_area(
            result, plan=plan, subject_area=_CUSTOMERS, logical=snapshot.logical
        )
        assert focused is not None
        result = focused
    if mode == "one_shot":
        assert isinstance(result.embedded_context, dict)
        assert "context_source_scope" not in result.embedded_context
        values = cast(dict[str, Any], result.embedded_context["prompt_inputs"])
    else:
        assert result.tool_catalog is not None
        values = result.tool_catalog.prompt_values
    assert len(values["context_records"]) == 1
