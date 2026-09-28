"""Code execution preserves complete Entity/System coverage in both Model layers."""

# Existing fake execution fixtures are deliberately shared.
# pyright: reportPrivateUsage=false

from typing import Literal, cast

import pytest
from gds_etl_workbench.domain.modeling_records import GeneratedCodeSourceSystemRecord
from pydantic import JsonValue

from tests.web_backend.test_code_generation_executor import (
    _CLAIM_TOKEN,
    _AgentExecutor,
    _execution_context_for_target_count,
    _plan,
    _PlanRepository,
    _principal,
    _service,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("layer", ["logical_entity", "dimensional_entity"])
async def test_each_entity_generates_all_of_its_system_files_before_handoff(
    layer: Literal["logical_entity", "dimensional_entity"],
) -> None:
    context = _execution_context_for_target_count(3)
    systems = (("CRM",), ("ERP", "WEB"), ("DEFAULT",))
    targets = tuple(
        target.model_copy(
            update={
                "modeled_entity_type": layer,
                "modeled_entity_schema_name": "silver" if layer == "logical_entity" else "gold",
                "source_system_codes": codes,
            }
        )
        for target, codes in zip(context.targets, systems, strict=True)
    )
    context = context.model_copy(update={"targets": targets})
    plan = _plan().model_copy(
        update={
            "modeled_entity_type": layer,
            "selected_entity_ids": tuple(target.modeled_entity_id for target in targets),
            "code_generation_file_layout": "per_system",
        }
    )
    agent = _AgentExecutor(
        responses=[
            cast(
                JsonValue,
                {
                    "artifacts": [
                        {
                            "target_ref": target.target_ref,
                            "artifact_name": f"{target.target_ref}_{code.lower()}.sql",
                            "source_system_codes": [code],
                            "generated_sql": "SELECT 1 AS reference_id",
                        }
                        for code in target.source_system_codes
                    ]
                },
            )
            for target in targets
        ]
    )
    service, _, _, handoff, no_op, lifecycle = _service(
        executor=agent,
        plan_repository=_PlanRepository(plan=plan),
        context=context,
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert len(agent.requests) == 3
    assert len(handoff.calls) == 1
    assert no_op.requests == [] and lifecycle.failed is None
    assignments = [
        GeneratedCodeSourceSystemRecord.model_validate(record)
        for change in handoff.calls[0]
        if change.dataset == "generated_code_source_system"
        for record in change.records
    ]
    assert {(item.modeled_entity_name, item.source_system_code) for item in assignments} == {
        ("Target1", "CRM"),
        ("Target2", "ERP"),
        ("Target2", "WEB"),
        ("Target3", "DEFAULT"),
    }
    assert all(item.modeled_entity_type == layer for item in assignments)
    assert len(assignments) == 4
