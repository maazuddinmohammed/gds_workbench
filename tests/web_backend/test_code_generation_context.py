from __future__ import annotations

from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.code_generation.context import (
    PostgresCodeGenerationContextRepository,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
)
from gds_workbench_api.prompt_rendering import PromptComponentTemplates


def _plan(*, selected_object_ids: tuple[int, ...] = (501, 502)) -> AgentRunPlan:
    return AgentRunPlan(
        workflow_run_id=1048,
        model_id=18,
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        model_revision=7,
        model_workflow="code_generation",
        workflow_execution_mode=None,
        modeled_entity_type="logical_entity",
        code_generation_coverage_mode="selected_targets",
        sql_generation_guide_id=90,
        sql_generation_guide_version_id=91,
        sql_generation_guide_digest="9" * 64,
        selected_scope_digest="a" * 64,
        selected_object_ids=selected_object_ids,
        selection=AgentRunSelection(
            sdk_code="langchain_create_agent",
            provider_code="databricks",
            model_code="databricks-primary",
            reasoning_effort_code="medium",
            max_turns=8,
            validation_retry_count=1,
        ),
        stages=(
            FrozenAgentStage(
                workflow_stage_id=31,
                stage_code="sql_generation",
                stage_order=10,
                prompt_template_version_id=81,
                prompt_template_digest="b" * 64,
                templates=PromptComponentTemplates(
                    system="Generate SQL.",
                    instruction="Use context.",
                ),
                variables=(),
            ),
        ),
    )


def _row(object_id: int) -> dict[str, Any]:
    return {
        "object_id": object_id,
        "source_system_count": 2,
        "mapping_context_digest": "c" * 64,
        "source_context_digest": "d" * 64,
        "sql_generation_guide_version_id": 91,
        "mapping_count": 1,
        "attribute_mapping_count": 1,
        "source_context": {
            "target": {
                "tenant_code": "NWA",
                "system_code": "GDS",
                "object_schema": "silver_crm",
                "object_name": f"target_{object_id}",
            },
            "source_systems": [
                {"system_code": "CRM", "dependency_order": 10},
                {"system_code": "ERP", "dependency_order": 20},
            ],
            "object_mappings": [
                {
                    "source_system": {"system_code": "CRM"},
                    "transformation": {"kind": "direct"},
                }
            ],
            "attribute_mappings": [
                {
                    "source_system": {"system_code": "CRM"},
                    "target": "customer_id",
                }
            ],
        },
        "guide_document": {
            "guide_code": "default_sql",
            "guide_name": "Default SQL",
            "version_number": 1,
            "content": "Use MERGE when appropriate.",
        },
    }


class ContextTransaction:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "list_code_generation_target_context" in query
        assert "workflow_run_object_selection" in query
        assert "run.sql_generation_guide_version_id" in query
        assert parameters == (7, 18, 1048, 7, "logical_entity")
        return self.rows


@pytest.mark.asyncio
async def test_context_uses_opaque_refs_and_exact_selected_target_coverage() -> None:
    context = await PostgresCodeGenerationContextRepository().load(
        ContextTransaction([_row(501), _row(502)]),
        tenant_id=7,
        plan=_plan(),
    )

    assert [target.target_ref for target in context.targets] == ["target_1", "target_2"]
    assert context.targets[0].source_context_digest == "d" * 64
    assert isinstance(context.agent_context, dict)
    targets = context.agent_context["targets"]
    assert isinstance(targets, list)
    assert isinstance(targets[0], dict)
    assert targets[0]["target_ref"] == "target_1"
    target_context = targets[0].get("context")
    assert isinstance(target_context, dict)
    source_systems = target_context.get("source_systems")
    assert isinstance(source_systems, list)
    assert len(source_systems) == 2
    assert "object_id" not in str(context.agent_context)
    assert "Use MERGE" not in repr(context)


@pytest.mark.asyncio
async def test_context_rejects_missing_selected_object_without_truncation() -> None:
    with pytest.raises(InvalidRequestError, match="incomplete"):
        await PostgresCodeGenerationContextRepository().load(
            ContextTransaction([_row(501)]),
            tenant_id=7,
            plan=_plan(),
        )


@pytest.mark.asyncio
async def test_context_rejects_oversized_mapping_collections() -> None:
    row = _row(501)
    row["mapping_count"] = 201

    with pytest.raises(InvalidRequestError, match="bounded"):
        await PostgresCodeGenerationContextRepository().load(
            ContextTransaction([row, _row(502)]),
            tenant_id=7,
            plan=_plan(),
        )


@pytest.mark.asyncio
async def test_context_allows_complete_object_mapping_without_attribute_mappings() -> (
    None
):
    first = _row(501)
    second = _row(502)
    first["attribute_mapping_count"] = 0
    second["attribute_mapping_count"] = 0
    first["source_context"]["attribute_mappings"] = []
    second["source_context"]["attribute_mappings"] = []

    context = await PostgresCodeGenerationContextRepository().load(
        ContextTransaction([first, second]),
        tenant_id=7,
        plan=_plan(),
    )

    assert len(context.targets) == 2
