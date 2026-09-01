from __future__ import annotations

from hashlib import sha256
from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.qa.context import PostgresQAContextRepository
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
)
from gds_workbench_api.prompt_rendering import PromptComponentTemplates


def _plan() -> AgentRunPlan:
    return AgentRunPlan(
        workflow_run_id=1048,
        model_id=18,
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        model_revision=7,
        model_workflow="qa",
        workflow_execution_mode=None,
        modeled_entity_type=None,
        selected_scope_digest="a" * 64,
        selected_object_ids=(),
        selected_system_codes=("erp",),
        selection=AgentRunSelection(
            sdk_code="openai_agents_sdk",
            provider_code="microsoft_foundry",
            model_code="model-1",
            reasoning_effort_code="medium",
            max_turns=8,
            validation_retry_count=2,
        ),
        stages=(
            FrozenAgentStage(
                workflow_stage_id=31,
                stage_code="validation_generation",
                stage_order=1,
                prompt_template_version_id=81,
                prompt_template_digest="b" * 64,
                templates=PromptComponentTemplates(
                    system="system",
                    instruction="instruction",
                    tool_instruction=None,
                ),
                variables=(),
            ),
        ),
    )


def _target_row(
    *, generated: bool = True, source_system: str = "erp"
) -> dict[str, Any]:
    content = "SELECT * FROM catalog.silver.customer"
    row: dict[str, Any] = {
        "object_id": 501,
        "modeled_entity_type": "dimensional_entity",
        "mapping_context_digest": "c" * 64,
        "source_context_digest": "d" * 64,
        "source_context": {
            "target": {
                "tenant_code": "acme",
                "system_code": "gds",
                "connection_code": "lakehouse",
                "object_schema": "gold",
                "object_name": "dim_customer",
            },
            "source_systems": [
                {
                    "source_system_id": 91,
                    "system_code": source_system,
                    "system_name": "ERP",
                    "dependency_order": 1,
                }
            ],
            "object_mappings": [],
            "attribute_mappings": [],
        },
        "generated_artifact_type": None,
        "generated_code_content": None,
        "generated_mapping_context_digest": None,
        "generated_source_context_digest": None,
        "generated_code_digest": None,
        "generated_code_status": None,
        "generated_code_is_locked": None,
    }
    if generated:
        row.update(
            {
                "generated_artifact_type": "sql_file",
                "generated_code_content": content,
                "generated_mapping_context_digest": "c" * 64,
                "generated_source_context_digest": "d" * 64,
                "generated_code_digest": sha256(content.encode()).hexdigest(),
                "generated_code_status": "active",
                "generated_code_is_locked": False,
            }
        )
    return row


def _applied_row() -> dict[str, Any]:
    return {
        "tenant_code": "acme",
        "system_code": "erp",
        "validation_group_name": "reconciliation",
        "validation_group_description": "Counts reconcile.",
        "mapping_context_digest": "e" * 64,
        "code_context_digest": None,
        "validation_group_is_active": True,
        "validation_check_name": "row_count_nonnegative",
        "validation_check_description": "Count is valid.",
        "validation_category_code": "technical.count",
        "validation_severity": "blocking",
        "validation_query_sql": "SELECT count(*) FROM catalog.gold.dim_customer",
        "validation_comparison_query_sql": None,
        "validation_result_data_type": "integer",
        "validation_comparison_operator": "greater_than_or_equal",
        "validation_comparison_value_type": "literal",
        "validation_comparison_value": 0,
        "validation_check_is_active": True,
    }


class ContextTransaction:
    def __init__(
        self,
        *,
        target_rows: list[dict[str, Any]] | None = None,
        aggregate_context_bytes: int = 4096,
    ) -> None:
        self.target_rows = target_rows if target_rows is not None else [_target_row()]
        self.aggregate_context_bytes = aggregate_context_bytes
        self.full_context_fetched = False

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert parameters == (7, 18, 1048, 7)
        if "aggregate_context_bytes" in query:
            assert "octet_length(relevant_context.generated_code_content)" in query
            assert "matching_system.match_count" in query
            assert query.count("\n          NULL\n") == 2
            return [
                {
                    "selected_system_count": 1,
                    "target_context_count": len(self.target_rows),
                    "applied_group_count": 1,
                    "applied_check_count": 1,
                    "aggregate_context_bytes": self.aggregate_context_bytes,
                }
            ]
        if "target_context AS MATERIALIZED" in query:
            self.full_context_fetched = True
            assert "'logical_entity'" in query
            assert "'dimensional_entity'" in query
            assert query.count("\n          NULL\n") == 2
            assert "application.workflow_run_system_selection" in query
            assert "jsonb_array_elements" in query
            return self.target_rows
        if "workflow.validation_group" in query:
            self.full_context_fetched = True
            assert "selection.system_id = validation_group.system_id" in query
            assert "selection.system_code" in query
            assert "JOIN core.system" not in query
            assert "ORDER BY selection.selection_order" in query
            return [_applied_row()]
        assert "selection.system_code" in query
        assert "JOIN core.system" not in query
        return [
            {
                "tenant_code": "acme",
                "system_code": "erp",
                "selection_order": 1,
            }
        ]


@pytest.mark.asyncio
async def test_repository_builds_exact_system_mapping_code_and_applied_qa_context() -> (
    None
):
    context = await PostgresQAContextRepository().load(
        ContextTransaction(),
        tenant_id=7,
        plan=_plan(),
    )

    assert len(context.systems) == 1
    system = context.systems[0]
    assert system.system_ref == "system_1"
    assert system.system_code == "erp"
    assert system.mapping_context_digest != "c" * 64
    assert system.code_context_digest is not None
    assert [group.validation_group_name for group in system.applied_groups] == [
        "reconciliation"
    ]
    assert [check.validation_check_name for check in system.applied_checks] == [
        "row_count_nonnegative"
    ]
    assert isinstance(system.agent_context, dict)
    generated_code = system.agent_context["generated_code"]
    assert isinstance(generated_code, list)
    assert len(generated_code) == 1


@pytest.mark.asyncio
async def test_repository_requires_complete_mapping_for_every_frozen_system() -> None:
    with pytest.raises(InvalidRequestError, match="complete active applied Mapping"):
        await PostgresQAContextRepository().load(
            ContextTransaction(target_rows=[_target_row(source_system="crm")]),
            tenant_id=7,
            plan=_plan(),
        )


@pytest.mark.asyncio
async def test_repository_fails_closed_when_live_system_code_drifted_from_snapshot() -> (
    None
):
    with pytest.raises(InvalidRequestError, match="complete active applied Mapping"):
        await PostgresQAContextRepository().load(
            ContextTransaction(target_rows=[_target_row(source_system="erp_renamed")]),
            tenant_id=7,
            plan=_plan(),
        )


@pytest.mark.asyncio
async def test_repository_omits_stale_code_from_optional_context_digest() -> None:
    row = _target_row()
    row["generated_mapping_context_digest"] = "f" * 64
    context = await PostgresQAContextRepository().load(
        ContextTransaction(target_rows=[row]),
        tenant_id=7,
        plan=_plan(),
    )

    assert context.systems[0].code_context_digest is None
    assert isinstance(context.systems[0].agent_context, dict)
    assert context.systems[0].agent_context["generated_code"] == []


@pytest.mark.asyncio
async def test_repository_rejects_oversize_aggregate_before_full_context_fetch() -> (
    None
):
    transaction = ContextTransaction(aggregate_context_bytes=64 * 1024 * 1024 + 1)

    with pytest.raises(InvalidRequestError, match="bounded size"):
        await PostgresQAContextRepository().load(
            transaction,
            tenant_id=7,
            plan=_plan(),
        )

    assert transaction.full_context_fetched is False
