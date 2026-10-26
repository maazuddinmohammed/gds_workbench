"""A Build call sees only its own Subject Area; Optimize and the readers see none."""

# Reuse synthetic fixtures at the actual frozen-context and prompt boundaries.
# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Literal, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.snapshots.project import LogicalSection, SubjectAreaSection
from tests.mcp.project_test_fixtures import snapshot_from_graph
from tests.web_backend.test_agent_context import _plan
from tests.web_backend.test_dimensional_executor import (
    _SALES,
    _selected_logical_entity,
    _subject_areas,
)
from tests.web_backend.test_dimensional_executor import _context_bundle as dimensional_context
from tests.web_backend.test_dimensional_executor import _plan as dimensional_plan
from tests.web_backend.test_logical_executor import _context_bundle as logical_context
from tests.web_backend.test_logical_executor import _plan as logical_plan
from tests.web_backend.test_logical_executor import _selected_object

from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextBundle,
    AgentContextToolRequestError,
    focus_subject_area,
)
from gds_workbench_api.features.workflows.authoring.context import (
    _context_bundle as package_context,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    PlannedSubjectArea,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import (
    get_prompt_input_contract,
    list_prompt_input_contracts,
    project_prompt_input_values,
)
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
)
SUBJECT_AREA_TOOLS = ("get_scope_tables", "get_table_links", "get_subject_areas")
# A second selected area that a Build call of the first area must never see.
_OTHER = "Zebra Ledger"

type Workflow = Literal["logical", "dimensional"]
type Mode = Literal["one_shot", "tool_assisted"]


@pytest.mark.parametrize(
    ("workflow", "stage"),
    [
        ("analysis", "relationship_inference"),
        ("logical", "build_authoring"),
        ("logical", "optimize_authoring"),
        ("dimensional", "build_authoring"),
        ("dimensional", "optimize_authoring"),
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
        names = {contract.name for contract in contracts}
        assert not names & set(SUBJECT_AREA_INPUTS)
        # Only a Build call is told which one area it works on.
        assert ("subject_area_context" in names) == (stage == "build_authoring")
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


def _two_area_run(
    workflow: Workflow,
    mode: Mode,
    *,
    operation: Literal["build", "optimize"] = "build",
    other_definition: str | None = f"{_OTHER} business area.",
) -> tuple[AgentContextBundle, AgentRunPlan]:
    """A loaded run with two selected Subject Areas, each holding one table.

    The first area's Logical Entity (Dimensional) or table (Logical) is what a Build call
    of it works on. other_definition None leaves the second area out of the saved areas.
    """
    if workflow == "logical":
        bundle = logical_context(
            mode=mode,
            operation=operation,
            selected_objects=(
                _selected_object(),
                _selected_object(selection_order=2, object_name="ledger_raw", key_name="id"),
            ),
            subject_areas={"Customers": ("customer_raw",), _OTHER: ("ledger_raw",)},
        )
        plan = logical_plan(mode=mode, operation=operation, subject_areas=("Customers", _OTHER))
    else:
        other = PlannedSubjectArea(
            subject_area_id=69,
            subject_area_name=_OTHER,
            subject_area_definition=f"{_OTHER} business area.",
        )
        bundle = dimensional_context(mode=mode, operation=operation)
        raw = bundle.context.model_dump(mode="json")
        raw["selected_logical_entities"].append(
            _selected_logical_entity("ledger_entry", table="ledger_raw", order=2)
        )
        raw["applied"]["subject_area"] = _subject_areas(
            (_SALES, ("sales_customer",)), (other, ("ledger_raw",))
        )
        bundle = replace(bundle, context=bundle.context.model_validate(raw, strict=False))
        plan = dimensional_plan(mode=mode, operation=operation, subject_areas=(_SALES, other))
    areas = bundle.context.applied.subject_area
    assert areas is not None
    if other_definition is None:
        areas = SubjectAreaSection(
            areas=tuple(row for row in areas.areas if row.subject_area_name != _OTHER),
            tables=tuple(row for row in areas.tables if row.subject_area_name != _OTHER),
        )
    else:
        areas = areas.model_copy(
            update={
                "areas": tuple(
                    row.model_copy(update={"subject_area_definition": other_definition})
                    if row.subject_area_name == _OTHER
                    else row
                    for row in areas.areas
                )
            }
        )
    context = bundle.context.model_copy(
        update={"applied": bundle.context.applied.model_copy(update={"subject_area": areas})}
    )
    return replace(bundle, context=context, snapshot=snapshot_from_graph({})), plan


def _call(bundle: AgentContextBundle, plan: AgentRunPlan) -> AgentContextBundle:
    """Package what one model call receives, as the executors do."""
    assert bundle.snapshot is not None and bundle.limits is not None
    if plan.workflow_operation == "optimize":
        return package_context(
            bundle.context,
            plan=plan,
            limits=bundle.limits,
            snapshot=bundle.snapshot,
            physical_scope=bundle.physical_scope,
        )
    focused = focus_subject_area(
        bundle,
        plan=plan,
        subject_area=plan.subject_areas[0],
        logical=LogicalSection(entities=(), attributes=(), relationships=()),
        dimensional=None if plan.project_workflow == "logical" else bundle.snapshot.dimensional,
    )
    assert focused is not None
    return focused


def _model_view(call: AgentContextBundle) -> dict[str, Any]:
    """Everything a model can see in one call: inline context, or manifest and datasets."""
    catalog = call.tool_catalog
    if catalog is None:
        return cast(dict[str, Any], call.embedded_context)
    manifest = cast(dict[str, Any], catalog.manifest)
    return {
        "manifest": manifest,
        "prompt_values": catalog.prompt_values,
        "datasets": {
            dataset: catalog.invoke(
                "get_agent_context_dataset", {"dataset": dataset, "offset": 0, "limit": 20}
            )
            for dataset in manifest["dataset_counts"]
        },
    }


@pytest.mark.parametrize("workflow", ["logical", "dimensional"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_build_call_sees_only_its_own_subject_area(workflow: Workflow, mode: Mode) -> None:
    bundle, plan = _two_area_run(workflow, mode)
    area = plan.subject_areas[0]

    call = _call(bundle, plan)
    view = _model_view(call)

    inputs = view["prompt_values"] if call.tool_catalog else view["prompt_inputs"]
    assert inputs["subject_area_context"] == {
        "name": area.subject_area_name,
        "definition": area.subject_area_definition,
        "input_count": 1,
    }
    # The saved Subject Area records, and the other selected area, never reach the model.
    assert _OTHER not in json.dumps(view)
    if call.tool_catalog is None:
        assert view["applied"]["subject_area"] is None
        assert view["build_subject_area"] == {
            "name": area.subject_area_name,
            "definition": area.subject_area_definition,
        }
        return
    catalog = call.tool_catalog
    assert not any("subject_area" in name for name in catalog.allowed_tool_names)
    for name in catalog.allowed_tool_names:
        assert _OTHER not in json.dumps(catalog.invoke(name, {}))
    for name in SUBJECT_AREA_TOOLS:
        with pytest.raises(AgentContextToolRequestError):
            catalog.invoke(name, {})
    for dataset in ("subject_area", "subject_area_table"):
        with pytest.raises(AgentContextToolRequestError):
            catalog.invoke(
                "get_agent_context_dataset", {"dataset": dataset, "offset": 0, "limit": 20}
            )
    with pytest.raises(InvalidRequestError):
        configure_tools(
            catalog, ("get_subject_areas",), workflow=workflow, execution_mode="tool_assisted"
        )


@pytest.mark.parametrize("workflow", ["logical", "dimensional"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_optimize_call_sees_no_subject_area(workflow: Workflow, mode: Mode) -> None:
    bundle, plan = _two_area_run(workflow, mode, operation="optimize")

    call = _call(bundle, plan)
    view = _model_view(call)

    inputs = view["prompt_values"] if call.tool_catalog else view["prompt_inputs"]
    assert "subject_area_context" not in inputs
    text = json.dumps(view)
    assert "business area." not in text and "Customer sales activity." not in text
    if call.tool_catalog is None:
        assert view["build_subject_area"] is None
        assert view["applied"]["subject_area"] is None
    else:
        assert not any("subject_area" in name for name in call.tool_catalog.allowed_tool_names)


@pytest.mark.parametrize("workflow", ["logical", "dimensional"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("operation", ["build", "optimize"])
def test_other_subject_areas_do_not_change_a_call(
    workflow: Workflow, mode: Mode, operation: Literal["build", "optimize"]
) -> None:
    views = [
        _model_view(
            _call(
                *_two_area_run(
                    workflow, mode, operation=operation, other_definition=other_definition
                )
            )
        )
        for other_definition in (
            f"{_OTHER} business area.",
            "Independent Subject Area detail. " * 1000,
            None,
        )
    ]

    assert views[0] == views[1] == views[2]
    assert "Subject Area detail" not in json.dumps(views)
