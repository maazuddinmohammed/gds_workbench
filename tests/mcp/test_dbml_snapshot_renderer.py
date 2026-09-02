from __future__ import annotations

from copy import deepcopy

import pytest
from tests.mcp.model_test_fixtures import (
    complete_model_graph,
    snapshot_from_graph,
)

from gds_etl_workbench.tools.snapshots.archive import SnapshotContractError
from gds_etl_workbench.tools.snapshots.dbml.renderer import render_dbml_documents
from gds_etl_workbench.tools.snapshots.model.contracts import (
    ModelChangeSetDataset,
    ModelSnapshot,
)


def test_full_dbml_renders_complete_and_submodel_files() -> None:
    documents = render_dbml_documents(
        snapshot_fixture(),
        model_type="full",
        include_submodels=True,
    )

    assert [document.path for document in documents] == [
        "conceptual.dbml",
        "dimensional_complete.dbml",
        "dimensional_salesmart.dbml",
        "logical_complete.dbml",
        "logical_sales.dbml",
    ]
    contents = {document.path: document.content.decode() for document in documents}
    assert 'Table "Customer"' in contents["conceptual.dbml"]
    assert "Ref conceptual_relationship_1:" in contents["conceptual.dbml"]
    assert '"CustomerID" bigint [pk, not null' in contents["logical_complete.dbml"]
    assert "Ref logical_relationship_1:" in contents["logical_complete.dbml"]
    assert "Ref dimensional_relationship_1:" in contents["dimensional_complete.dbml"]
    assert "Optional: no" in contents["dimensional_complete.dbml"]


def test_dbml_can_render_one_layer_without_submodels() -> None:
    documents = render_dbml_documents(
        snapshot_fixture(),
        model_type="logical",
        include_submodels=False,
    )

    assert [document.path for document in documents] == ["logical_complete.dbml"]


def test_full_dbml_without_submodels_contains_only_complete_files() -> None:
    documents = render_dbml_documents(
        snapshot_fixture(),
        model_type="full",
        include_submodels=False,
    )

    assert [document.path for document in documents] == [
        "conceptual.dbml",
        "dimensional_complete.dbml",
        "logical_complete.dbml",
    ]


def test_dbml_adds_default_file_only_for_unassigned_entities() -> None:
    graph = complete_model_graph()
    entities = graph["logical_entity"]
    entities[0]["submodels"] = []

    documents = render_dbml_documents(
        snapshot_fixture(graph),
        model_type="logical",
        include_submodels=True,
    )

    assert [document.path for document in documents] == [
        "logical_complete.dbml",
        "logical_default.dbml",
        "logical_sales.dbml",
    ]
    default = next(
        document for document in documents if document.path == "logical_default.dbml"
    )
    assert default.table_count == 1
    assert default.relationship_count == 0
    assert 'Table "Order"' in default.content.decode()


def test_dbml_rejects_effective_relationship_with_inactive_endpoint() -> None:
    graph = complete_model_graph()
    objects = graph["conceptual_object"]
    objects[0]["conceptual_object_status"] = "inactive"

    with pytest.raises(SnapshotContractError, match="inactive or missing endpoint"):
        render_dbml_documents(
            snapshot_fixture(graph),
            model_type="conceptual",
            include_submodels=False,
        )


def test_dbml_quotes_unsafe_data_types_and_is_deterministic() -> None:
    graph = complete_model_graph()
    attributes = graph["logical_attribute"]
    attributes[0]["logical_attribute_data_type"] = "decimal(18, 2) injected"
    snapshot = snapshot_fixture(graph)

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


def snapshot_fixture(
    graph: dict[ModelChangeSetDataset, list[dict[str, object]]] | None = None,
) -> ModelSnapshot:
    return snapshot_from_graph(deepcopy(graph or complete_model_graph()))
