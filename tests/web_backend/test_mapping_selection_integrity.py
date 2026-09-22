"""Selected Mapping writes retain protected records and use registered evidence."""

from typing import Any, cast

import pytest
from gds_workbench_api.features.mapping.complete_candidate import CompleteMappingCandidateValidator
from gds_workbench_api.features.mapping.execution_context import build_mapping_execution_context
from gds_workbench_api.features.mapping.readiness import assess_mapping_readiness
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    DownstreamContextReaders,
    project_downstream_inputs,
)
from pydantic import JsonValue

from tests.web_backend.mapping_fixtures import mapping_candidate, mapping_preparation


def test_parent_lock_preserves_children_even_when_their_own_locks_are_open() -> None:
    preparation = mapping_preparation(existing=True, locked=True)
    header = preparation.context.headers[0]
    header = header.model_copy(
        update={
            "attribute_mappings": tuple(
                child.model_copy(update={"is_locked": False}) for child in header.attribute_mappings
            )
        }
    )
    context = preparation.context.model_copy(update={"headers": (header,)})
    readiness = assess_mapping_readiness(plan=preparation.plan, context=context)
    assert readiness.ready
    assert readiness.headers[0].action == "preserve"
    assert all(item.action == "preserve" for item in readiness.headers[0].attribute_actions)


@pytest.mark.parametrize("existing", [True, False])
def test_unselected_attributes_are_preserved_only_when_already_authored(existing: bool) -> None:
    preparation = mapping_preparation(existing=existing, attribute_count=2)
    plan = preparation.plan.model_copy(
        update={"operation": "generate", "selected_attribute_ids": (901,)}
    )
    readiness = assess_mapping_readiness(plan=plan, context=preparation.context)
    assert readiness.ready == existing
    assert [row.action for row in readiness.headers[0].attribute_actions] == [
        "extend" if existing else "author",
        "preserve" if existing else "blocked",
    ]


async def test_preserved_attributes_prevent_silent_object_join_changes() -> None:
    preparation = mapping_preparation(existing=True)
    plan = preparation.plan.model_copy(
        update={"operation": "generate", "selected_attribute_ids": ()}
    )
    preparation = preparation.model_copy(
        update={
            "plan": plan,
            "readiness": assess_mapping_readiness(plan=plan, context=preparation.context),
        }
    )
    candidate = mapping_candidate()
    candidate["attribute_mappings"] = []
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    assert (await validator.validate(candidate)).issues
    candidate["object_mapping"] = {
        "object_dependency_order": 0,
        "mapping_transformation_document": {"kind": "direct", "logic": "existing"},
    }
    assert not (await validator.validate(candidate)).issues
    assert not validator.parse_validated(candidate).changes


@pytest.mark.parametrize("mistake", ["object", "attribute", "alias", "undeclared"])
async def test_declared_physical_references_are_checked_against_frozen_sources(
    mistake: str,
) -> None:
    preparation = mapping_preparation()
    key = {
        name: getattr(preparation.context.sources[0].object, name)
        for name in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        )
    }
    sources: list[Any] = [{**key, "alias": "c"}]
    attributes: list[Any] = [{**key, "attribute_name": "customer_id"}]
    candidate: dict[str, Any] = {
        "schema_version": "1.0",
        "object_mapping": {
            "object_dependency_order": 0,
            "mapping_transformation_document": {"source_objects": sources},
        },
        "attribute_mappings": [
            {
                "modeled_attribute_name": "CustomerID",
                "attribute_mapping_transformation_document": {"source_attributes": attributes},
            }
        ],
    }
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    assert not (await validator.validate(candidate)).issues
    if mistake == "object":
        sources[0]["object_name"] = "invented"
    elif mistake == "attribute":
        attributes[0]["attribute_name"] = "invented"
    elif mistake == "alias":
        sources.append(sources[0].copy())
    else:
        sources.clear()
    assert (await validator.validate(candidate)).issues


async def test_missing_evidence_returns_a_fixed_actionable_diagnostic() -> None:
    validator = CompleteMappingCandidateValidator(preparation=mapping_preparation())
    value = await validator.validate(
        {
            "schema_version": "1.0",
            "object_mapping": None,
            "attribute_mappings": [],
            "issues": [{"code": "missing_join_evidence", "modeled_attribute_name": None}],
        }
    )
    assert value.issues[0].code == "mapping.missing_join_evidence"
    assert "Add or correct source relationships" in value.issues[0].message


def test_mapping_support_uses_actual_lineage_in_both_execution_modes() -> None:
    preparation = mapping_preparation()
    one_shot = build_mapping_execution_context(preparation=preparation, execution_mode="one_shot")
    values = project_downstream_inputs("mapping", cast(dict[str, Any], one_shot.embedded_context))
    support = values["mapping_support"]
    assert support["attribute_lineage"][0]["modeled_attribute_name"] == "CustomerID"
    source = support["attribute_lineage"][0]["sources"][0]["source_attribute"]
    assert source["object_name"] == "customer"
    assert source["attribute_name"] == "customer_id"
    assisted = build_mapping_execution_context(
        preparation=preparation, execution_mode="tool_assisted"
    )
    assert isinstance(assisted.tool_catalog, DownstreamContextReaders)
    assert assisted.tool_catalog.prompt_values["mapping_support"] == support


async def test_unchanged_legacy_object_document_does_not_block_attribute_regeneration() -> None:
    preparation = mapping_preparation(existing=True)
    document: dict[str, JsonValue] = {
        "source_objects": ["bronze_crm.customer"],
        "steps": ["Keep current rows."],
    }
    context = preparation.context.model_copy(
        update={
            "headers": (
                preparation.context.headers[0].model_copy(
                    update={"transformation_document": document}
                ),
            )
        }
    )
    preparation = preparation.model_copy(update={"context": context})
    candidate = mapping_candidate()
    candidate["object_mapping"] = {
        "object_dependency_order": 0,
        "mapping_transformation_document": document,
    }
    result = await CompleteMappingCandidateValidator(preparation=preparation).validate(candidate)
    assert not result.issues
