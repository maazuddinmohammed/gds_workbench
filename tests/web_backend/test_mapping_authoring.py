from __future__ import annotations

# pyright: reportPrivateUsage=false

import json
from typing import cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError

from mapping_fixtures import mapping_candidate, mapping_preparation

from gds_workbench_api.features.mapping.complete_candidate import (
    CompleteMappingCandidateValidator,
)
from gds_workbench_api.features.mapping.execution_context import (
    build_mapping_execution_context,
)
from gds_workbench_api.features.mapping.reconciliation import MappingCandidateReconciler
from gds_workbench_api.features.mapping.read_service import _MAPPING_TARGETS_SQL
from gds_workbench_api.features.workflows.authoring.plan import WorkflowExecutionMode


def _serialized(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def test_mapping_targets_are_bound_silver_or_gold_not_model_inputs() -> None:
    assert "workflow.list_model_object_eligibility" in _MAPPING_TARGETS_SQL
    assert "is_logical_mapping_target_eligible" in _MAPPING_TARGETS_SQL
    assert "is_dimensional_mapping_target_eligible" in _MAPPING_TARGETS_SQL
    assert "model_input_scope" not in _MAPPING_TARGETS_SQL


@pytest.mark.asyncio
async def test_mapping_candidate_contains_only_flexible_transformation_content() -> None:
    preparation = mapping_preparation()
    validator = CompleteMappingCandidateValidator(preparation=preparation)

    schema = validator.output_schema()
    result = await validator.validate(mapping_candidate())
    parsed = validator.parse_validated(mapping_candidate())

    assert result.issues == ()
    assert [change.dataset for change in parsed.changes] == [
        "mapping_object",
        "mapping_attribute",
    ]
    object_record = parsed.changes[0].records[0]
    attribute_record = parsed.changes[1].records[0]
    assert object_record["modeled_entity_name"] == "Customer"
    assert object_record["source_system_code"] == "CRM"
    assert cast(
        dict[str, object], object_record["mapping_transformation_document"]
    )["kind"] == "direct"
    assert attribute_record["modeled_attribute_name"] == "CustomerID"
    assert cast(
        dict[str, object], attribute_record["attribute_mapping_transformation_document"]
    )["kind"] == "direct"
    for removed in (
        "mapping_profile",
        "package_digest",
        "mapping_context_digest",
        "source_context_digest",
        "mapping_artifact_type",
    ):
        assert removed not in _serialized(schema)
        assert removed not in _serialized(mapping_candidate())


@pytest.mark.asyncio
async def test_mapping_candidate_requires_exact_bound_attribute_coverage() -> None:
    validator = CompleteMappingCandidateValidator(preparation=mapping_preparation())
    incomplete = mapping_candidate()
    incomplete["attribute_mappings"] = []

    validation = await validator.validate(incomplete)

    assert [issue.code for issue in validation.issues] == [
        "candidate.mapping_integrity_invalid"
    ]
    with pytest.raises(InvalidRequestError, match="every actionable bound Attribute"):
        validator.parse_validated(incomplete)


def test_locked_complete_mapping_is_preserved_without_agent_output() -> None:
    preparation = mapping_preparation(existing=True, locked=True)

    assert preparation.readiness.ready is True
    assert preparation.readiness.headers[0].action == "preserve"
    assert [item.action for item in preparation.readiness.headers[0].attribute_actions] == [
        "preserve"
    ]
    assert MappingCandidateReconciler(preparation=preparation).reconcile_preserved() == ()


@pytest.mark.parametrize("execution_mode", ("one_shot", "tool_assisted", "detailed_coverage"))
def test_all_mapping_modes_share_one_authoring_contract(
    execution_mode: WorkflowExecutionMode,
) -> None:
    preparation = mapping_preparation(execution_mode=execution_mode)
    context = build_mapping_execution_context(
        preparation=preparation,
        execution_mode=execution_mode,
    )

    if execution_mode == "tool_assisted":
        assert context.tool_catalog is not None
        header_page = context.tool_catalog.invoke(
            "get_mapping_context_dataset",
            {"dataset": "modeled_attribute", "offset": 0, "limit": 10},
        )
        assert "model_object_binding_id" in _serialized(header_page)
    else:
        assert context.tool_catalog is None
    assert "mapping_profile" not in _serialized(context.embedded_context)
    assert "package_digest" not in _serialized(context.embedded_context)
