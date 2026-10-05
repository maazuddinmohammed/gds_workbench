"""Manual Mapping edits keep source selection, locks and graph validation authoritative."""

from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.application.model_snapshot import ModelReviewSnapshot
from gds_workbench_api.features.mapping.editor import (
    mapping_record_editor,
    prepare_mapping_edit,
)
from gds_workbench_api.features.model_change_sets.editor import (
    ModelRecordEditor,
    ModelRecordEditorRequest,
    SaveModelRecordRequest,
)

from tests.mcp.model_test_fixtures import (
    complete_model_graph,
    complete_physical_scope,
    SOURCE_ORDERS,
)
from tests.web_backend.test_modeled_record_review import review_graph

REFERENCE = dict(
    zip(
        (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        ),
        SOURCE_ORDERS,
        strict=True,
    )
)
SOURCES: list[dict[str, Any]] = [
    {
        "source": {
            "object": {
                **REFERENCE,
                "attributes": [
                    {
                        "attribute_name": name,
                        "attribute_data_type": "BIGINT",
                        "is_active": True,
                    }
                    for name in ("order_id", "customer_id")
                ],
            }
        }
    }
]


def edit_context(
    *, locked: str | None = None
) -> tuple[ModelReviewSnapshot, ModelRecordEditor]:
    graph = complete_model_graph()
    graph["mapping_object"][0]["mapping_transformation_document"] = {
        "source_tables": [REFERENCE],
        "transformation_logic": "Read orders.",
        "custom": {"nested": [1, False, None]},
    }
    for row in graph["mapping_attribute"]:
        name = (
            "order_id" if row["modeled_attribute_name"] == "OrderID" else "customer_id"
        )
        row["attribute_mapping_transformation_document"] = {
            "source_columns": [{**REFERENCE, "attribute_name": name}],
            "transformation_logic": name,
        }
    if locked:
        field = (
            "object_mapping_is_locked"
            if locked == "mapping_object"
            else "attribute_mapping_is_locked"
        )
        graph[cast(Any, locked)][0][field] = True
    review = review_graph(graph)
    command = ModelRecordEditorRequest(
        dataset="mapping_object", record_id=1, expected_model_revision=1
    )
    editor = mapping_record_editor(review, command, SOURCES)
    return review, editor


def save_command(editor: ModelRecordEditor, **overrides: Any) -> SaveModelRecordRequest:
    assert editor.mapping is not None
    changes: dict[str, Any] = {
        "object_mapping": {
            "object_dependency_order": editor.mapping["dependency_order"],
            "mapping_transformation_document": deepcopy(
                editor.mapping["object_document"]
            ),
        },
        "attribute_mappings": [],
    }
    if "attribute_mappings" in overrides:
        changes.pop("object_mapping")
    changes.update(overrides)
    return SaveModelRecordRequest(
        dataset="mapping_object",
        record_id=1,
        expected_model_revision=1,
        changes=changes,
    )


def test_manual_mapping_edit_preserves_custom_fields_and_unedited_attributes() -> None:
    review, editor = edit_context()
    command = save_command(editor)
    command.changes["object_mapping"]["mapping_transformation_document"][
        "filter_criteria"
    ] = "Only active orders."
    result = prepare_mapping_edit(review, command, editor, complete_physical_scope())
    assert result.valid
    records = result.records["mapping_object"]
    document = records[0].model_dump()["mapping_transformation_document"]
    assert document["custom"] == {"nested": [1, False, None]}
    assert document["filter_criteria"] == "Only active orders."
    assert not result.records.get("mapping_attribute")


@pytest.mark.parametrize(
    "violation", ["unselected_table", "outside_scope", "unknown_column"]
)
def test_source_columns_require_selected_eligible_tables(violation: str) -> None:
    review, editor = edit_context()
    command = save_command(editor)
    reference = {**REFERENCE, "attribute_name": "order_id"}
    if violation == "unselected_table":
        command.changes["object_mapping"]["mapping_transformation_document"][
            "source_tables"
        ] = []
    elif violation == "outside_scope":
        reference["object_name"] = "unregistered"
        command.changes["object_mapping"]["mapping_transformation_document"][
            "source_tables"
        ] = [reference]
    else:
        reference["attribute_name"] = "missing"
    if violation == "unknown_column":
        command.changes.pop("object_mapping")
        command.changes["attribute_mappings"] = [
            {
                "modeled_attribute_name": "OrderID",
                "attribute_mapping_transformation_document": {
                    "source_columns": [reference],
                    "transformation_logic": "Read the key.",
                },
            }
        ]
    with pytest.raises(WorkbenchError):
        prepare_mapping_edit(review, command, editor, complete_physical_scope())


@pytest.mark.parametrize("locked", ["mapping_object", "mapping_attribute"])
def test_locked_mapping_or_child_protects_object_logic(locked: str) -> None:
    review, editor = edit_context(locked=locked)
    command = save_command(editor)
    command.changes["object_mapping"]["mapping_transformation_document"][
        "filter_criteria"
    ] = "Changed rows."
    with pytest.raises(WorkbenchError) as error:
        prepare_mapping_edit(review, command, editor, complete_physical_scope())
    assert error.value.code == "record_locked"


def test_attribute_edit_preserves_object_document() -> None:
    review, editor = edit_context()
    command = save_command(
        editor,
        attribute_mappings=[
            {
                "modeled_attribute_name": "OrderID",
                "attribute_mapping_transformation_document": {
                    "source_columns": [{**REFERENCE, "attribute_name": "order_id"}],
                    "transformation_logic": "Cast order_id to BIGINT.",
                    "default_record": "Leave null.",
                },
            }
        ],
    )
    result = prepare_mapping_edit(review, command, editor, complete_physical_scope())
    assert result.valid
    assert not result.records.get("mapping_object")
    assert len(result.records["mapping_attribute"]) == 1


def test_object_and_attribute_edits_cannot_be_combined() -> None:
    review, editor = edit_context()
    command = save_command(editor)
    command.changes["attribute_mappings"] = [
        {
            "modeled_attribute_name": "OrderID",
            "attribute_mapping_transformation_document": {
                "transformation_logic": "Changed"
            },
        }
    ]
    with pytest.raises(WorkbenchError) as error:
        prepare_mapping_edit(review, command, editor, complete_physical_scope())
    assert error.value.code == "invalid_request"
