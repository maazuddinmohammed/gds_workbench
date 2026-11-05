from __future__ import annotations

# Reuse the existing model fixture builders.
# pyright: reportPrivateUsage=false
# Synthetic model/load graphs only; no database or execution connection.
from typing import cast

import pytest
from atlas_mcp.application.change_sets.project import StageProjectChange
from atlas_mcp.domain.errors import InvalidRequestError
from atlas_mcp.domain.snapshots.project import LogicalSection
from atlas_platform.features.dimensional.policy import (
    DimensionalProjectionConflictError,
    project_dimensional_foreign_key_policy,
)
from atlas_platform.features.logical.policy import project_logical_audit_policy
from atlas_platform.features.mapping import assess_mapping_readiness
from atlas_platform.features.mapping.complete_candidate import CompleteMappingCandidateValidator
from atlas_platform.features.mapping.preparation_contracts import MappingTargetDependencyGraph
from atlas_platform.features.workflows.authoring.dependency_order import resolve_dependency_orders
from pydantic import JsonValue

from tests.web_backend.mapping_fixtures import mapping_candidate, mapping_preparation
from tests.web_backend.test_dimensional_policy import _projected_baseline, _technical_template
from tests.web_backend.test_logical_candidate import _answer, _relationship, _validator


def test_dependency_order_preserves_gaps_and_propagates_to_saved_dependents() -> None:
    orders, blocked = resolve_dependency_orders(
        {"parent": 4, "child": 1, "grandchild": 2, "independent": 0},
        [("child", "parent"), ("grandchild", "child")],
        targets={"parent"},
        include_dependents=True,
    )
    assert orders == {"parent": 4, "child": 5, "grandchild": 6}
    assert not blocked
    assert resolve_dependency_orders(
        orders,
        [("child", "parent"), ("grandchild", "child")],
        targets={"child"},
        include_dependents=True,
    ) == (orders, set())


def test_dependency_cycle_blocks_only_its_dependents() -> None:
    graph = [("a", "b"), ("b", "a"), ("child", "a"), ("self", "self")]
    orders = {key: 0 for key in ("a", "b", "child", "self", "independent")}
    assert resolve_dependency_orders(orders, graph, targets={"independent"}) == (
        {"independent": 0},
        set(),
    )
    assert resolve_dependency_orders(orders, graph, targets={"child"}) == (
        {},
        {"a", "b", "child"},
    )
    assert resolve_dependency_orders(orders, graph, targets={"self"}) == ({}, {"self"})


@pytest.mark.parametrize("locked", [False, True])
def test_logical_relationship_only_change_orders_saved_child(locked: bool) -> None:
    initial = project_logical_audit_policy(
        changes=_validator().parse_validated(cast(JsonValue, _answer(relationships=False))),
        applied=None,
        raw_template={"schema_version": "1.0", "columns": []},
    )
    by_dataset = {change.dataset: change.records for change in initial}
    applied = LogicalSection.model_validate(
        {
            "entities": by_dataset["logical_entity"],
            "attributes": by_dataset["logical_attribute"],
            "relationships": [],
        },
        strict=False,
    )
    applied = applied.model_copy(
        update={
            "entities": tuple(
                row.model_copy(update={"logical_entity_is_locked": locked})
                if row.logical_entity_name == "SalesOrder"
                else row
                for row in applied.entities
            )
        }
    )
    # The affected saved child may lie outside this area's selected tables.
    # Only its execution order changes; its existing source evidence remains valid.
    validator = _validator(applied=applied, tables=("customer_raw",))
    answer = cast(JsonValue, {"entities": [], "relationships": [_relationship()], "retire": []})
    if locked:
        with pytest.raises(InvalidRequestError):
            validator.parse_validated(answer)
        return
    changes = validator.parse_validated(answer)
    entity = next(
        row for change in changes if change.dataset == "logical_entity" for row in change.records
    )
    assert entity["logical_entity_name"] == "SalesOrder"
    assert entity["logical_entity_dependency_order"] == 1
    assert entity["sources"] == by_dataset["logical_entity"][1]["sources"]


@pytest.mark.parametrize("locked", [False, True])
def test_dimensional_relationship_only_change_orders_saved_fact(locked: bool) -> None:
    baseline = _projected_baseline()
    baseline = baseline.model_copy(
        update={
            "entities": tuple(
                row.model_copy(
                    update={
                        "dimensional_entity_dependency_order": 0,
                        "dimensional_entity_is_locked": locked,
                    }
                )
                if row.dimensional_entity_type == "fact"
                else row
                for row in baseline.entities
            )
        }
    )
    changes = (
        StageProjectChange(
            dataset="dimensional_relationship",
            records=[baseline.relationships[0].model_dump(mode="json")],
        ),
    )
    if locked:
        with pytest.raises(DimensionalProjectionConflictError, match="locked Dimensional Entity"):
            project_dimensional_foreign_key_policy(
                changes=changes, applied=baseline, raw_technical_template=_technical_template()
            )
        return
    result = project_dimensional_foreign_key_policy(
        changes=changes, applied=baseline, raw_technical_template=_technical_template()
    )
    entity = next(
        row for change in result if change.dataset == "dimensional_entity" for row in change.records
    )
    assert entity["dimensional_entity_name"] == "Sales Fact"
    assert entity["dimensional_entity_dependency_order"] == 1


@pytest.mark.parametrize("locked", [False, True])
async def test_mapping_uses_resolved_order_over_stale_saved_header(locked: bool) -> None:
    preparation = mapping_preparation(existing=True, locked=locked)
    graph = MappingTargetDependencyGraph.model_validate(
        {
            "nodes": [
                {
                    "modeled_entity_id": entity,
                    "dependency_order": order,
                    "status": "active",
                    "has_locked_headers": locked,
                    "has_unlocked_headers": not locked,
                }
                for entity, order in ((200, 4), (201, 0))
            ],
            "edges": [{"predecessor_modeled_entity_id": 200, "successor_modeled_entity_id": 201}],
            "malformed_reference_count": 0,
            "mixed_order_target_count": 0,
        },
        strict=False,
    )
    context = preparation.context.model_copy(update={"target_dependency_graph": graph})
    readiness = assess_mapping_readiness(plan=preparation.plan, context=context)
    assert readiness.headers[0].required_dependency_order == 5
    if locked:
        assert not readiness.ready
        assert "dependency.locked_order" in {issue.code for issue in readiness.issues}
        return
    assert readiness.ready
    preparation = preparation.model_copy(update={"context": context, "readiness": readiness})
    result = CompleteMappingCandidateValidator(preparation=preparation).parse_validated(
        cast(
            JsonValue,
            {
                "schema_version": "1.0",
                "object_mapping": None,
                "attribute_mappings": [],
            },
        )
    )
    entity = next(
        row
        for change in result.changes
        if change.dataset == "mapping_object"
        for row in change.records
    )
    assert entity["object_dependency_order"] == 5


@pytest.mark.parametrize("saved_parent_order", (0, 4))
async def test_mapping_cannot_raise_parent_order_past_frozen_child(saved_parent_order: int) -> None:
    preparation = mapping_preparation(existing=True)
    graph = preparation.context.target_dependency_graph.model_dump(mode="json")
    graph["nodes"] = [
        {
            **graph["nodes"][0],
            "modeled_entity_id": entity_id,
            "dependency_order": order,
        }
        for entity_id, order in ((201, saved_parent_order), (202, saved_parent_order + 1))
    ]
    graph["edges"] = [
        {"predecessor_modeled_entity_id": 201, "successor_modeled_entity_id": 202}
    ]
    context = preparation.context.model_copy(
        update={
            "target_dependency_graph": MappingTargetDependencyGraph.model_validate(
                graph, strict=False
            ),
            "headers": (
                preparation.context.headers[0].model_copy(
                    update={"object_dependency_order": saved_parent_order}
                ),
            ),
        }
    )
    preparation = preparation.model_copy(
        update={
            "context": context,
            "readiness": assess_mapping_readiness(plan=preparation.plan, context=context),
        }
    )
    candidate = mapping_candidate()
    obj = cast(dict[str, JsonValue], candidate["object_mapping"])
    obj["object_dependency_order"] = 99

    result = CompleteMappingCandidateValidator(preparation=preparation).parse_validated(
        cast(JsonValue, candidate)
    )

    orders = [
        row["object_dependency_order"]
        for change in result.changes
        if change.dataset == "mapping_object"
        for row in change.records
    ]
    assert orders == [saved_parent_order]
    parent_order = orders[0]
    assert isinstance(parent_order, int)
    assert parent_order < graph["nodes"][1]["dependency_order"]


@pytest.mark.parametrize("cycle", [False, True])
def test_mapping_reports_affected_self_or_cycle_dependency(cycle: bool) -> None:
    preparation = mapping_preparation()
    graph = preparation.context.target_dependency_graph.model_dump(mode="json")
    if cycle:
        graph["nodes"].append({**graph["nodes"][0], "modeled_entity_id": 202})
        graph["edges"] = [
            {"predecessor_modeled_entity_id": 201, "successor_modeled_entity_id": 202},
            {"predecessor_modeled_entity_id": 202, "successor_modeled_entity_id": 201},
        ]
    else:
        graph["edges"] = [
            {"predecessor_modeled_entity_id": 201, "successor_modeled_entity_id": 201}
        ]
    context = preparation.context.model_copy(
        update={
            "target_dependency_graph": MappingTargetDependencyGraph.model_validate(
                graph, strict=False
            )
        }
    )
    readiness = assess_mapping_readiness(plan=preparation.plan, context=context)
    assert not readiness.ready
    assert "dependency.unschedulable" in {issue.code for issue in readiness.issues}
