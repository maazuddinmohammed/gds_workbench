from __future__ import annotations

# pyright: reportPrivateUsage=false
import json
from typing import cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.mapping.complete_candidate import (
    CompleteMappingCandidateValidator,
)
from gds_workbench_api.features.mapping.execution_context import (
    build_mapping_execution_context,
)
from gds_workbench_api.features.mapping.preparation_contracts import (
    MappingPhysicalObject,
    ModeledEntityType,
)
from gds_workbench_api.features.mapping.read_service import _MAPPING_TARGETS_SQL
from gds_workbench_api.features.mapping.readiness import assess_mapping_readiness
from gds_workbench_api.features.mapping.reconciliation import MappingCandidateReconciler
from gds_workbench_api.features.workflows.authoring.plan import WorkflowExecutionMode
from mapping_fixtures import mapping_candidate, mapping_preparation
from pydantic import JsonValue, ValidationError


def _serialized(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def test_mapping_targets_are_bound_silver_or_gold_not_model_inputs() -> None:
    assert "workflow.list_model_object_eligibility" in _MAPPING_TARGETS_SQL
    assert "is_logical_mapping_target_eligible" in _MAPPING_TARGETS_SQL
    assert "is_dimensional_mapping_target_eligible" in _MAPPING_TARGETS_SQL
    assert "model_input_scope" not in _MAPPING_TARGETS_SQL


@pytest.mark.parametrize("owner", [None, 0, "missing"])
def test_mapping_physical_object_requires_source_tenant(owner: object) -> None:
    value = mapping_preparation().context.target.model_dump(mode="json")
    if owner == "missing":
        value.pop("source_tenant_id")
    else:
        value["source_tenant_id"] = owner
    with pytest.raises(ValidationError):
        MappingPhysicalObject.model_validate_json(json.dumps(value))


def test_mapping_physical_placement_and_source_tenant_are_independent() -> None:
    value = mapping_preparation().context.target.model_dump(mode="json")
    value.update(tenant_id=9, source_tenant_id=7)
    physical = MappingPhysicalObject.model_validate_json(json.dumps(value))
    assert physical.tenant_id == 9
    assert physical.source_tenant_id == 7


@pytest.mark.parametrize(
    "modeled_entity_type", ["logical_entity", "dimensional_entity"]
)
@pytest.mark.parametrize("source_zone", ["source", "bronze", "silver", "gold"])
def test_mapping_readiness_enforces_each_route_source_zone(
    modeled_entity_type: ModeledEntityType, source_zone: str
) -> None:
    preparation = mapping_preparation(modeled_entity_type=modeled_entity_type)
    assert preparation.readiness.ready
    source = preparation.context.sources[0]
    context = preparation.context.model_copy(
        update={
            "sources": (
                source.model_copy(
                    update={
                        "object": source.object.model_copy(
                            update={"zone_code": source_zone}
                        )
                    }
                ),
            ),
        }
    )
    result = assess_mapping_readiness(plan=preparation.plan, context=context)
    expected = source_zone in (
        {"source", "bronze"} if modeled_entity_type == "logical_entity" else {"silver"}
    )
    assert result.ready is expected
    assert (
        "source.zone_invalid" in {issue.code for issue in result.issues}
    ) is not expected


@pytest.mark.asyncio
async def test_mapping_candidate_contains_only_flexible_transformation_content() -> (
    None
):
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
    assert (
        cast(dict[str, object], object_record["mapping_transformation_document"])[
            "kind"
        ]
        == "direct"
    )
    assert attribute_record["modeled_attribute_name"] == "CustomerID"
    assert (
        cast(
            dict[str, object],
            attribute_record["attribute_mapping_transformation_document"],
        )["kind"]
        == "direct"
    )
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


@pytest.mark.parametrize("target", ("object", "attribute"))
async def test_new_mapping_documents_must_contain_transformation_content(
    target: str,
) -> None:
    candidate = mapping_candidate()
    if target == "object":
        cast(dict[str, JsonValue], candidate["object_mapping"])[
            "mapping_transformation_document"
        ] = {}
    else:
        cast(list[dict[str, JsonValue]], candidate["attribute_mappings"])[0][
            "attribute_mapping_transformation_document"
        ] = {}
    validation = await CompleteMappingCandidateValidator(
        preparation=mapping_preparation(),
    ).validate(candidate)
    assert validation.issues


def test_locked_complete_mapping_is_preserved_without_agent_output() -> None:
    preparation = mapping_preparation(existing=True, locked=True)

    assert preparation.readiness.ready is True
    assert preparation.readiness.headers[0].action == "preserve"
    assert [
        item.action for item in preparation.readiness.headers[0].attribute_actions
    ] == ["preserve"]
    assert (
        MappingCandidateReconciler(preparation=preparation).reconcile_preserved() == ()
    )


@pytest.mark.parametrize("execution_mode", ("one_shot", "tool_assisted"))
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
            "get_existing_mapping",
            {},
        )
        assert "model_object_binding_id" not in _serialized(header_page)
        assert "CustomerID" in _serialized(header_page)
    else:
        assert context.tool_catalog is None
    assert "mapping_profile" not in _serialized(context.embedded_context)
    assert "package_digest" not in _serialized(context.embedded_context)


@pytest.mark.parametrize("execution_mode", ("one_shot", "tool_assisted"))
def test_mapping_context_preserves_storage_and_inferred_type_evidence(
    execution_mode: WorkflowExecutionMode,
) -> None:
    preparation = mapping_preparation(execution_mode=execution_mode)
    source = preparation.context.sources[0]
    attribute = source.object.attributes[0].model_copy(
        update={
            "attribute_data_type": "STRING",
            "attribute_inferred_data_type": "DECIMAL(12,2)",
            "attribute_description": "Order amount in the transaction currency.",
        }
    )
    preparation = preparation.model_copy(
        update={
            "context": preparation.context.model_copy(
                update={
                    "sources": (
                        source.model_copy(
                            update={
                                "object": source.object.model_copy(
                                    update={"attributes": (attribute,)}
                                )
                            }
                        ),
                    )
                }
            )
        }
    )
    execution = build_mapping_execution_context(
        preparation=preparation, execution_mode=execution_mode
    )
    if execution_mode == "tool_assisted":
        assert execution.tool_catalog is not None
        page = cast(
            dict[str, JsonValue],
            execution.tool_catalog.invoke(
                "get_mapping_sources",
                {},
            ),
        )
        sources = cast(list[dict[str, JsonValue]], page["items"])
        source_object = cast(dict[str, JsonValue], sources[0]["object"])
        attributes = cast(list[dict[str, JsonValue]], source_object["attributes"])
    else:
        document = cast(
            dict[str, JsonValue],
            (execution.embedded_context),
        )
        values = cast(dict[str, JsonValue], document["values"])
        sources = cast(list[dict[str, JsonValue]], values["source_evidence"])
        source_object = cast(dict[str, JsonValue], sources[0]["object"])
        attributes = cast(list[dict[str, JsonValue]], source_object["attributes"])
    assert attributes[0]["attribute_data_type"] == "STRING"
    assert attributes[0]["attribute_inferred_data_type"] == "DECIMAL(12,2)"
    assert (
        attributes[0]["attribute_description"]
        == "Order amount in the transaction currency."
    )
    assert preparation.context.target.attributes[0].attribute_inferred_data_type is None
