"""Requirements are evidence with automatic availability, scope and provenance."""

# pyright: reportPrivateUsage=false
from typing import Any, LiteralString, cast

import pytest
from gds_workbench_api.features.assertions.context import project_assertions
from gds_workbench_api.features.mapping.execution_context import (
    build_mapping_execution_context,
)
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    project_downstream_inputs,
    DownstreamContextReaders,
)
from gds_etl_workbench.domain.snapshots.model import AssertionSection

from tests.mcp.model_test_fixtures import complete_model_graph
from tests.web_backend.mapping_fixtures import mapping_preparation


def section() -> dict[str, Any]:
    graph = complete_model_graph()
    document = dict(graph["modeling_assertion_document"][0])
    document.update(tenant_code=None, system_code=None)
    record = dict(graph["modeling_assertion_record"][0])
    record.update(
        modeling_assertion_record_type="reporting_requirement",
        modeling_assertion_applicable_layers=["conceptual"],
        modeling_assertion_details={
            "grain": "Month and customer",
            "history": "At sale time",
        },
    )
    return {"documents": [document], "records": [record]}


def test_requirements_are_filtered_by_activity_and_joint_tenant_system_scope() -> None:
    data = section()
    scope = [
        {"tenant_code": "ACME", "system_code": "ERP"},
        {"tenant_code": "OTHER", "system_code": "CRM"},
    ]
    assert project_assertions(data, source_scope=scope)
    assert project_assertions(data, source_scope=scope)
    document = data["documents"][0]
    document.update(tenant_code="acme", system_code="erp")
    assert project_assertions(data, source_scope=scope)
    document["system_code"] = "CRM"
    assert not project_assertions(data, source_scope=scope)
    document.update(system_code="ERP", is_active=False)
    assert not project_assertions(data, source_scope=scope)
    document["is_active"] = True
    data["records"][0]["modeling_assertion_record_status"] = "inactive"
    assert not project_assertions(data, source_scope=scope)


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_mapping_receives_unlinked_model_wide_requirements_in_both_modes(
    mode: Any,
) -> None:
    preparation = mapping_preparation()
    assert preparation.snapshot is not None
    preparation = preparation.model_copy(
        update={
            "snapshot": preparation.snapshot.model_copy(
                update={
                    "assertion": AssertionSection.model_validate(
                        section(), strict=False
                    )
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
    requirements = values["mapping_support"]["assertions"]
    assert len(requirements) == 1
    assert (
        requirements[0]["modeling_assertion_details"]["grain"] == "Month and customer"
    )
    assert "modeling_assertion_record_id" not in requirements[0]


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
    requirement["documents"][0].update(tenant_code="MODEL_OWNER", system_code="ERP")
    snapshot = _dimensional_snapshot().model_copy(
        update={
            "model_tenant_code": "MODEL_OWNER",
            "assertion": AssertionSection.model_validate(requirement, strict=False),
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
        plan=_plan(model_workflow="dimensional", selected_object_ids=(701,)).model_copy(
            update={"workflow_execution_mode": mode}
        ),
    )
    if mode == "one_shot":
        assert isinstance(result.embedded_context, dict)
        assert "assertion_source_scope" not in result.embedded_context
        values = cast(dict[str, Any], result.embedded_context["prompt_inputs"])
    else:
        assert result.tool_catalog is not None
        values = result.tool_catalog.prompt_values
    assert len(values["modeling_assertions"]) == 1
    assert (
        values["modeling_assertions"][0]["modeling_assertion_record_type"]
        == "reporting_requirement"
    )
    assert "assertion_source_scope" not in values


@pytest.mark.parametrize("workflow", ["analysis", "conceptual", "logical"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_all_modeling_workflows_receive_assertions_without_layer_selection(
    workflow: Any, mode: Any
) -> None:
    from gds_workbench_api.features.workflows.authoring.context import (
        AgentContextLimits,
        PostgresAgentContextRepository,
    )
    from tests.web_backend.test_agent_context import (
        ContextTransaction,
        _snapshot,
        _load_physical_scope,
        _plan,
    )

    data = section()
    data["documents"][0].update(tenant_code="MODEL_OWNER", system_code="ERP")
    data["records"][0]["modeling_assertion_applicable_layers"] = []
    snapshot = _snapshot().model_copy(
        update={
            "model_tenant_code": "MODEL_OWNER",
            "assertion": AssertionSection.model_validate(data, strict=False),
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
        plan=_plan(model_workflow=workflow).model_copy(
            update={"workflow_execution_mode": mode}
        ),
    )
    if mode == "one_shot":
        assert isinstance(result.embedded_context, dict)
        assert "assertion_source_scope" not in result.embedded_context
        values = cast(dict[str, Any], result.embedded_context["prompt_inputs"])
    else:
        assert result.tool_catalog is not None
        values = result.tool_catalog.prompt_values
    assert len(values["modeling_assertions"]) == 1
