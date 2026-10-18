"""Requirements are evidence with automatic availability, scope and provenance."""

# pyright: reportPrivateUsage=false
from typing import Any, LiteralString, cast

import pytest
from gds_etl_workbench.domain.snapshots.project import ContextSection
from gds_workbench_api.features.context.context import select_context_records
from gds_workbench_api.features.mapping.execution_context import (
    build_mapping_execution_context,
)
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    DownstreamContextReaders,
    project_downstream_inputs,
)

from tests.mcp.project_test_fixtures import complete_project_graph
from tests.web_backend.mapping_fixtures import mapping_preparation


def section() -> dict[str, Any]:
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
            }
        ],
        "groups": [group],
        "records": [record],
    }


def test_requirements_are_filtered_by_activity_and_authorized_source_system_scope() -> (
    None
):
    data = section()
    scope = [
        {"tenant_code": "ACME", "system_code": "ERP"},
        {"tenant_code": "OTHER", "system_code": "CRM"},
    ]
    assert select_context_records(data, source_scope=scope)
    assert select_context_records(data, source_scope=scope)
    document = data["groups"][0]
    document.update(source_system_code="erp")
    assert select_context_records(data, source_scope=scope)
    document["source_system_code"] = "UNKNOWN"
    assert not select_context_records(data, source_scope=scope)
    document.update(source_system_code="ERP", is_active=False)
    assert not select_context_records(data, source_scope=scope)
    document["is_active"] = True
    data["records"][0]["status"] = "inactive"
    assert not select_context_records(data, source_scope=scope)


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_mapping_receives_unlinked_project_wide_requirements_in_both_modes(
    mode: Any,
) -> None:
    preparation = mapping_preparation()
    assert preparation.snapshot is not None
    preparation = preparation.model_copy(
        update={
            "snapshot": preparation.snapshot.model_copy(
                update={
                    "context": ContextSection.model_validate(section(), strict=False)
                }
            )
        }
    )
    execution = build_mapping_execution_context(
        preparation=preparation, execution_mode=mode
    )
    if mode == "one_shot":
        values = project_downstream_inputs(
            "mapping", cast(dict[str, Any], execution.embedded_context)
        )
    else:
        assert isinstance(execution.tool_catalog, DownstreamContextReaders)
        values = execution.tool_catalog.prompt_values
    requirements = values["mapping_support"]["context_records"]
    assert len(requirements) == 1
    assert (
        requirements[0]["context_text"] == "Report sales at month and customer grain."
    )
    assert "context_record_id" in requirements[0]


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_dimensional_requirements_follow_business_system_behind_silver(
    mode: Any,
) -> None:
    from gds_workbench_api.features.workflows.authoring.context import (
        AgentContextLimits,
        PostgresAgentContextRepository,
    )

    from tests.web_backend.test_agent_context import (
        DimensionalContextTransaction,
        _dimensional_snapshot,
        _load_physical_scope,
        _plan,
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

    result = await PostgresAgentContextRepository(
        snapshot_loader=load_snapshot,
        physical_scope_loader=_load_physical_scope,
        limits=AgentContextLimits(max_selected_attributes=1),
    ).load(
        DimensionalContextTransaction(),
        tenant_id=7,
        plan=_plan(
            project_workflow="dimensional", selected_object_ids=(701,)
        ).model_copy(update={"workflow_execution_mode": mode}),
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


@pytest.mark.parametrize("workflow", ["analysis", "conceptual", "logical"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_all_modeling_workflows_receive_context_without_layer_selection(
    workflow: Any, mode: Any
) -> None:
    from gds_workbench_api.features.workflows.authoring.context import (
        AgentContextLimits,
        PostgresAgentContextRepository,
    )

    from tests.web_backend.test_agent_context import (
        ContextTransaction,
        _load_physical_scope,
        _plan,
        _snapshot,
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
        async def fetch_all(
            self, query: LiteralString, parameters: tuple[Any, ...] = ()
        ):
            if len(parameters) >= 3 and parameters[2] == workflow:
                parameters = (*parameters[:2], "conceptual", *parameters[3:])
            return await super().fetch_all(query, parameters)

    result = await PostgresAgentContextRepository(
        snapshot_loader=load_snapshot,
        physical_scope_loader=_load_physical_scope,
        limits=AgentContextLimits(max_selected_attributes=100),
    ).load(
        ModelingTransaction(),
        tenant_id=7,
        plan=_plan(project_workflow=workflow).model_copy(
            update={"workflow_execution_mode": mode}
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
