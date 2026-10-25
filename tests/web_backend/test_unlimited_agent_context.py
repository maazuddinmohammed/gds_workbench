"""Unlimited provider evidence keeps complete records and existing safety boundaries."""

# Reuse synthetic context fixtures; no database or provider connections.
# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Literal, LiteralString, cast

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import ContextRecord
from gds_etl_workbench.domain.safe_json import validate_safe_json
from gds_etl_workbench.domain.snapshots.project import ProjectSnapshot
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextToolRequestError,
    PostgresAgentContextRepository,
    reject_forbidden_provider_json,
)
from gds_workbench_api.features.workflows.authoring.context_contracts import (
    INPUT_EXAMPLES,
)
from gds_workbench_api.features.workflows.authoring.context_readers import (
    FrozenContextReaders,
)
from gds_workbench_api.integrations.agents.adapters import OpenAIAgentsSdkAdapter
from pydantic import JsonValue, ValidationError

from tests.web_backend.test_agent_context import (
    ContextTransaction,
    _load_physical_scope,
    _load_snapshot,
    _plan,
    _snapshot,
    _snapshot_with_policy_json,
)

LARGE_DESCRIPTION = "Documented business meaning. " * 50_000


class UnlimitedContextTransaction(ContextTransaction):
    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        if "attribute_ordinal_position" in query:
            assert parameters[-1] is None, (
                "Default SQL retrieval must not impose a row limit."
            )
            parameters = (
                *parameters[:-1],
                101,
            )  # Existing fixture's explicit-limit assertion.
        if len(parameters) >= 3 and parameters[2] == "logical":
            # The shared fixture rows are keyed to the default Subject Area workflow.
            parameters = (*parameters[:2], "subject_area", *parameters[3:])
        rows = await super().fetch_all(query, parameters)
        for row in rows:
            if "object_description" in row:
                row["object_description"] = LARGE_DESCRIPTION
            if "attribute_description" in row:
                row["attribute_description"] = LARGE_DESCRIPTION
        return rows


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
async def test_default_repository_preserves_large_descriptions_in_both_modes(
    mode: Literal["one_shot", "tool_assisted"],
) -> None:
    assert len(LARGE_DESCRIPTION.encode()) > 1024 * 1024
    # Logical reads whole physical Objects and Attributes through its readers.
    bundle = await PostgresAgentContextRepository(
        physical_scope_loader=_load_physical_scope,
        snapshot_loader=_load_snapshot,
    ).load(
        UnlimitedContextTransaction(),
        tenant_id=7,
        plan=_plan(execution_mode=mode, project_workflow="logical"),
    )
    if mode == "one_shot":
        assert bundle.tool_catalog is None
        embedded = cast(dict[str, Any], bundle.embedded_context)
        selected = embedded["selected_objects"][0]
        assert selected["object"]["object_description"] == LARGE_DESCRIPTION
        assert selected["attributes"][0]["attribute_description"] == LARGE_DESCRIPTION
    else:
        assert bundle.tool_catalog is not None
        assert bundle.tool_catalog.max_result_bytes is None
        assert bundle.tool_catalog.max_cumulative_result_bytes is None
        objects = cast(dict[str, Any], bundle.tool_catalog.invoke("get_objects", {}))
        details = cast(
            dict[str, Any], bundle.tool_catalog.invoke("get_object_details", {})
        )
        assert objects["items"][0]["object_description"] == LARGE_DESCRIPTION
        assert (
            details["items"][0]["attributes"][0]["attribute_description"]
            == LARGE_DESCRIPTION
        )
        assert objects["is_complete"] and details["is_complete"]
        assert details["incomplete_object_key"] is None


def test_unlimited_readers_keep_whole_records_paging_and_cursor_boundaries() -> None:
    values = deepcopy(INPUT_EXAMPLES["analysis"])
    for group in values["object_attribute_context"]:
        group["attributes"][0]["attribute_description"] = LARGE_DESCRIPTION
    catalog = FrozenContextReaders(
        workflow="analysis",
        values=values,
        max_result_bytes=None,
        max_page_records=1,
        max_cumulative_result_bytes=None,
    )
    request = AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="analysis_inference",
        stage="relationship_inference",
        execution_mode="tool_assisted",
        selection=_plan().selection,
        system_prompt="Infer supported relationships.",
        instruction_prompt="Use saved evidence.",
        tool_instruction=None,
        context={},
        output_schema={"type": "object"},
        allowed_tool_names=tuple(tool.name for tool in catalog.definitions),
        local_tool_catalog=catalog,
    )
    provider_catalog = OpenAIAgentsSdkAdapter._tool_catalog(request)
    assert provider_catalog is not None
    assert provider_catalog is catalog, (
        "No cumulative byte limiter may wrap unlimited readers."
    )
    first = catalog.invoke("get_object_details", {})
    cursor = first["next_cursor"]
    assert isinstance(cursor, str) and not first["is_complete"]
    assert first["incomplete_object_key"] is None
    assert first["items"] == values["object_attribute_context"][:1]
    second = catalog.invoke("get_object_details", {"cursor": cursor})
    assert second["next_cursor"] is None and second["is_complete"]
    assert second["incomplete_object_key"] is None
    assert first["items"] + second["items"] == values["object_attribute_context"]
    # Repeated reads exceed the former 10 MiB cumulative ceiling without changing data.
    for _ in range(10):
        assert provider_catalog.invoke("get_object_details", {}) == first
    with pytest.raises(AgentContextToolRequestError):
        catalog.invoke("get_objects", {"cursor": cursor})
    with pytest.raises(AgentContextToolRequestError):
        catalog.invoke("get_object_details", {"cursor": "unknown-cursor"})
    other_run = FrozenContextReaders(
        workflow="analysis",
        values=values,
        max_result_bytes=None,
        max_page_records=1,
        max_cumulative_result_bytes=None,
    )
    with pytest.raises(AgentContextToolRequestError):
        other_run.invoke("get_object_details", {"cursor": cursor})


@pytest.mark.asyncio
async def test_default_repository_accepts_large_deep_nonsecret_policy_evidence() -> (
    None
):
    # Stay inside the separate 256 KiB persisted policy contract while exceeding
    # the old provider JSON string, depth, and node limits.
    nested: dict[str, object] = {"explanation": "Documented rule. " * 2500}
    for _ in range(16):
        nested = {"detail": nested}
    policy: dict[str, object] = {
        "meaning": nested,
        "labels": [f"label-{index}" for index in range(5000)],
    }

    async def load_snapshot(*_: object) -> ProjectSnapshot:
        return _snapshot_with_policy_json(policy)

    bundle = await PostgresAgentContextRepository(
        physical_scope_loader=_load_physical_scope,
        snapshot_loader=load_snapshot,
    ).load(UnlimitedContextTransaction(), tenant_id=7, plan=_plan())
    embedded = cast(dict[str, Any], bundle.embedded_context)
    assert embedded["project_details"]["silver_model_audit_columns_template"] == policy


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prohibited_key", ("object_id", "api_key", "connection_string", "raw_tool_output")
)
async def test_unlimited_repository_still_rejects_prohibited_nested_fields(
    prohibited_key: str,
) -> None:
    async def load_snapshot(*_: object) -> ProjectSnapshot:
        return _snapshot_with_policy_json(
            {"detail": {prohibited_key: "synthetic-private-marker"}}
        )

    with pytest.raises(WorkbenchError) as caught:
        await PostgresAgentContextRepository(
            physical_scope_loader=_load_physical_scope,
            snapshot_loader=load_snapshot,
        ).load(UnlimitedContextTransaction(), tenant_id=7, plan=_plan())
    assert caught.value.code == "agent_context_unavailable"
    assert "synthetic-private-marker" not in str(caught.value)


@pytest.mark.parametrize(
    "prohibited_value",
    ("Bearer synthetic-private-marker", "password=synthetic-private-marker"),
)
def test_unlimited_value_safety_check_still_rejects_sensitive_text(
    prohibited_value: str,
) -> None:
    value: JsonValue = {"explanation": LARGE_DESCRIPTION, "detail": [prohibited_value]}
    with pytest.raises(WorkbenchError) as caught:
        reject_forbidden_provider_json(value, reject_sensitive_values=True)
    assert caught.value.code == "agent_context_unavailable"
    assert "synthetic-private-marker" not in str(caught.value)


@pytest.mark.parametrize("shape", ("bytes", "string", "depth", "nodes"))
def test_explicit_json_and_mcp_record_bounds_are_unchanged(shape: str) -> None:
    value: dict[str, object]
    if shape == "bytes":
        value = {"explanation": LARGE_DESCRIPTION}
    elif shape == "string":
        value = {"explanation": "x" * 32_769}
    elif shape == "depth":
        value = {"label": "leaf"}
        for _ in range(13):
            value = {"detail": value}
    else:
        value = {"labels": list(range(4097))}
    validate_safe_json(value, maximum_bytes=None, label="Provider evidence")
    with pytest.raises(ValueError):
        validate_safe_json(
            value,
            maximum_bytes=65536,
            label="Bounded JSON",
        )
    record = _snapshot().context.records[0].model_dump(mode="json")
    # The removed structured-details field remains rejected by the lean Context contract.
    record["modeling_assertion_details"] = value
    with pytest.raises(ValidationError):
        ContextRecord.model_validate_json(json.dumps(record), strict=True)


def test_provider_context_preserves_only_canonical_context_uuid_identity() -> None:
    reject_forbidden_provider_json(
        {"context_record_id": "00000000-0000-4000-8000-000000000001"}
    )
    for value in (1, "customer.key", "00000000-0000-4000-8000-00000000000A"):
        with pytest.raises(WorkbenchError):
            reject_forbidden_provider_json({"context_record_id": value})
    with pytest.raises(WorkbenchError):
        reject_forbidden_provider_json({"context_group_id": 1})
