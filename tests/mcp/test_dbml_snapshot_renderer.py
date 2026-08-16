from __future__ import annotations

from copy import deepcopy
from typing import cast

import pytest
from test_model_change_set_validation import _complete_graph

from gds_etl_workbench.tools.snapshots.archive import SnapshotContractError
from gds_etl_workbench.tools.snapshots.dbml.renderer import render_dbml_documents
from gds_etl_workbench.tools.snapshots.model.contracts import ModelSnapshot


def test_full_dbml_renders_complete_and_submodel_files() -> None:
    documents = render_dbml_documents(
        _snapshot(),
        model_type="full",
        include_submodels=True,
    )

    assert [document.path for document in documents] == [
        "conceptual.dbml",
        "dimensional_complete.dbml",
        "dimensional_sales_mart.dbml",
        "logical_complete.dbml",
        "logical_sales.dbml",
    ]
    contents = {document.path: document.content.decode() for document in documents}
    assert 'Table "Customer"' in contents["conceptual.dbml"]
    assert "Ref conceptual_relationship_1:" in contents["conceptual.dbml"]
    assert '"customer_id" bigint [pk, not null' in contents["logical_complete.dbml"]
    assert "Ref logical_relationship_1:" in contents["logical_complete.dbml"]
    assert "Ref dimensional_relationship_1:" in contents["dimensional_complete.dbml"]


def test_dbml_can_render_one_layer_without_submodels() -> None:
    documents = render_dbml_documents(
        _snapshot(),
        model_type="logical",
        include_submodels=False,
    )

    assert [document.path for document in documents] == ["logical_complete.dbml"]


def test_full_dbml_without_submodels_contains_only_complete_files() -> None:
    documents = render_dbml_documents(
        _snapshot(),
        model_type="full",
        include_submodels=False,
    )

    assert [document.path for document in documents] == [
        "conceptual.dbml",
        "dimensional_complete.dbml",
        "logical_complete.dbml",
    ]


def test_dbml_adds_default_file_only_for_unassigned_entities() -> None:
    graph = _complete_graph()
    entities = cast(list[dict[str, object]], graph["logical_entity"])
    entities[0]["submodels"] = []

    documents = render_dbml_documents(
        _snapshot(graph),
        model_type="logical",
        include_submodels=True,
    )

    assert [document.path for document in documents] == [
        "logical_complete.dbml",
        "logical_default.dbml",
        "logical_sales.dbml",
    ]
    default = next(document for document in documents if document.path == "logical_default.dbml")
    assert default.table_count == 1
    assert default.relationship_count == 0
    assert 'Table "Order"' in default.content.decode()


def test_dbml_rejects_effective_relationship_with_inactive_endpoint() -> None:
    graph = _complete_graph()
    objects = cast(list[dict[str, object]], graph["conceptual_object"])
    objects[0]["conceptual_object_status"] = "inactive"

    with pytest.raises(SnapshotContractError, match="inactive or missing endpoint"):
        render_dbml_documents(
            _snapshot(graph),
            model_type="conceptual",
            include_submodels=False,
        )


def test_dbml_quotes_unsafe_data_types_and_is_deterministic() -> None:
    graph = _complete_graph()
    attributes = cast(list[dict[str, object]], graph["logical_attribute"])
    attributes[0]["logical_attribute_data_type"] = "decimal(18, 2) injected"
    snapshot = _snapshot(graph)

    first = render_dbml_documents(
        snapshot,
        model_type="logical",
        include_submodels=True,
    )
    second = render_dbml_documents(
        snapshot,
        model_type="logical",
        include_submodels=True,
    )

    assert first == second
    assert '"decimal(18, 2) injected"' in first[0].content.decode()


def _snapshot(
    graph: dict[str, list[dict[str, object]]] | None = None,
) -> ModelSnapshot:
    records = deepcopy(graph or _complete_graph())
    return ModelSnapshot.model_validate(
        {
            "model_id": 1,
            "model_name": "Sales Model",
            "model_revision": 2,
            "model_scope": {
                "details": records["model_details"][0],
                "objects": records["model_scope"],
            },
            "profiling": {"profiles": records["profiling_profile"]},
            "analysis": {"relationships": records["analysis_result"]},
            "assertion": {
                "documents": records["modeling_assertion_document"],
                "records": records["modeling_assertion_record"],
            },
            "conceptual": {
                "objects": records["conceptual_object"],
                "relationships": records["conceptual_relationship"],
            },
            "logical": {
                "submodels": records["logical_submodel"],
                "entities": records["logical_entity"],
                "attributes": records["logical_attribute"],
                "relationships": records["logical_relationship"],
            },
            "dimensional": {
                "submodels": records["dimensional_submodel"],
                "entities": records["dimensional_entity"],
                "attributes": records["dimensional_attribute"],
                "relationships": records["dimensional_relationship"],
            },
            "mapping": {
                "dependencies": records["mapping_dependency"],
                "objects": records["mapping_object"],
                "attributes": records["mapping_attribute"],
            },
        },
        strict=False,
    )
