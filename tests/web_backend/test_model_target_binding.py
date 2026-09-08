"""Both modeled layers require complete, compatible, explicit physical Bindings."""

from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset
from gds_workbench_api.features.model_targets.binding import prepare_model_binding
from gds_workbench_api.features.model_targets.contracts import (
    ApplyModelBindingRequest,
    AttributeAssignment,
    PreviewModelBindingRequest,
    TargetLayer,
)
from pydantic import ValidationError

from tests.mcp.model_test_fixtures import complete_model_graph, complete_physical_scope
from tests.web_backend.test_modeled_record_review import review_graph


def binding_fixture(layer: TargetLayer) -> dict[str, Any]:
    graph = complete_model_graph()
    entity_type = f"{layer}_entity"
    original = next(
        row
        for row in graph["model_object_binding"]
        if row["modeled_entity_type"] == entity_type
    )
    entity_name = original["modeled_entity_name"]
    target = {
        field: original[field]
        for field in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        )
    }
    target["object_id"] = 100
    attributes: list[dict[str, object]] = []
    for index, modeled in enumerate(
        graph[cast(ModelChangeSetDataset, f"{layer}_attribute")], start=1
    ):
        if modeled[f"{layer}_entity_name"] != entity_name:
            continue
        binding = next(
            row
            for row in graph["model_attribute_binding"]
            if row["modeled_entity_type"] == entity_type
            and row["modeled_entity_name"] == entity_name
            and row["modeled_attribute_name"] == modeled[f"{layer}_attribute_name"]
        )
        attributes.append(
            {
                "attribute_id": index + 100,
                "attribute_name": binding["attribute_name"],
                "attribute_data_type": modeled[f"{layer}_attribute_data_type"],
                "attribute_nullability": modeled[f"{layer}_attribute_is_nullable"],
                "is_natural_key": modeled["logical_attribute_is_natural_key"]
                if layer == "logical"
                else modeled["dimensional_attribute_key_role"] == "business",
                "is_surrogate_key": modeled["logical_attribute_is_surrogate_key"]
                if layer == "logical"
                else modeled["dimensional_attribute_key_role"] == "surrogate",
                "is_meta_data": modeled[f"{layer}_attribute_is_audit_column"],
                "is_masking_required": False,
            }
        )
    for dataset in ("model_object_binding", "model_attribute_binding"):
        graph[dataset] = [
            row
            for row in graph[dataset]
            if not (
                row["modeled_entity_type"] == entity_type
                and row["modeled_entity_name"] == entity_name
            )
        ]
    return {
        "model": ModelReadContext(
            model_id=1, tenant_id=1, model_name="test", model_revision=2
        ),
        "review": review_graph(graph),
        "physical_scope": complete_physical_scope(),
        "command": PreviewModelBindingRequest(
            layer=layer, entity_id=1, object_id=100, expected_model_revision=2
        ),
        "target": target,
        "target_attributes": attributes,
        "masked_attribute_ids": set(),
    }


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
def test_complete_binding_previews_the_same_exact_apply(layer: TargetLayer) -> None:
    fixture = binding_fixture(layer)
    preview = prepare_model_binding(**fixture).preview
    assert preview.can_apply, preview.issues
    assert preview.action_count == 3
    assignments = [
        AttributeAssignment(
            modeled_attribute_id=row.modeled_attribute_id, attribute_id=row.attribute_id
        )
        for row in preview.assignments
        if row.attribute_id is not None
    ]
    fixture["command"] = ApplyModelBindingRequest(
        layer=layer,
        entity_id=1,
        object_id=100,
        expected_model_revision=2,
        assignments=assignments,
        expected_plan_digest=preview.plan_digest,
    )
    assert prepare_model_binding(**fixture).preview == preview
    changed = deepcopy(fixture)
    changed["target_attributes"][0]["attribute_nullability"] = True
    changed_preview = prepare_model_binding(**changed).preview
    assert not changed_preview.can_apply
    assert changed_preview.plan_digest != preview.plan_digest


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
@pytest.mark.parametrize(
    "mismatch", ["missing", "extra", "type", "key", "audit", "masking"]
)
def test_incomplete_or_incompatible_targets_cannot_bind(
    layer: TargetLayer, mismatch: str
) -> None:
    fixture = binding_fixture(layer)
    attributes = fixture["target_attributes"]
    if mismatch == "missing":
        attributes.pop()
    elif mismatch == "extra":
        attributes.append(
            {**attributes[0], "attribute_id": 999, "attribute_name": "extra"}
        )
    elif mismatch == "type":
        attributes[0]["attribute_data_type"] = "VARCHAR(1)"
    elif mismatch == "key":
        attributes[0]["is_natural_key"] = not attributes[0]["is_natural_key"]
    elif mismatch == "audit":
        attributes[0]["is_meta_data"] = not attributes[0]["is_meta_data"]
    else:
        fixture["masked_attribute_ids"] = {1}
    preview = prepare_model_binding(**fixture).preview
    assert not preview.can_apply
    assert preview.issues


def test_duplicate_assignments_and_implicit_apply_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ApplyModelBindingRequest(
            layer="logical",
            entity_id=1,
            object_id=100,
            expected_model_revision=2,
            expected_plan_digest="0" * 64,
        )  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        PreviewModelBindingRequest(
            layer="logical",
            entity_id=1,
            object_id=100,
            expected_model_revision=2,
            assignments=[
                AttributeAssignment(modeled_attribute_id=1, attribute_id=101),
                AttributeAssignment(modeled_attribute_id=2, attribute_id=101),
            ],
        )


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
def test_existing_locked_bindings_are_preserved_and_cannot_be_reassigned(
    layer: TargetLayer,
) -> None:
    fixture = binding_fixture(layer)
    graph = complete_model_graph()
    for dataset in ("model_object_binding", "model_attribute_binding"):
        for row in graph[dataset]:
            row[f"{dataset}_is_locked"] = True
    fixture["review"] = review_graph(graph)
    original = fixture["review"].snapshot.model_dump(mode="json")
    unchanged = prepare_model_binding(**fixture).preview
    assert unchanged.can_apply, unchanged.issues
    assert unchanged.action_count == 0
    fixture["command"] = PreviewModelBindingRequest(
        layer=layer,
        entity_id=1,
        object_id=100,
        expected_model_revision=2,
        assignments=[
            AttributeAssignment(modeled_attribute_id=1, attribute_id=102),
            AttributeAssignment(modeled_attribute_id=2, attribute_id=101),
        ],
    )
    rejected = prepare_model_binding(**fixture).preview
    assert not rejected.can_apply
    assert fixture["review"].snapshot.model_dump(mode="json") == original
