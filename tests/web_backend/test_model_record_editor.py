"""Manual definition edits validate complete records and preserve their graph identity."""

from typing import get_args

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.snapshots.model import DATASETS_BY_NAME
from gds_workbench_api.features.model_change_sets.contracts import (
    PreviewModelRecordsRequest,
    ReviewModelRecordsRequest,
)
from gds_workbench_api.features.model_change_sets.editor import (
    EditableDataset,
    ModelRecordEditorRequest,
    SaveModelRecordRequest,
    model_record_editor,
    prepare_model_record_edit,
)
from pydantic import ValidationError

from tests.mcp.model_test_fixtures import complete_model_graph, complete_physical_scope
from tests.web_backend.test_modeled_record_review import review_graph


@pytest.mark.parametrize("dataset", [value for value in get_args(EditableDataset.__value__) if value != "mapping_object"])
def test_edit_definition_preserves_all_other_fields(dataset: EditableDataset) -> None:
    review = review_graph(complete_model_graph())
    editor = model_record_editor(
        review,
        ModelRecordEditorRequest(
            dataset=dataset,
            record_id=1,
            expected_model_revision=1,
        ),
    )
    name = f"{dataset}_definition"
    assert name in {field.name for field in editor.fields}
    assert not any(
        field.name in DATASETS_BY_NAME[dataset].canonical_key
        or field.name.endswith(("_status", "_is_locked"))
        for field in editor.fields
    )
    validation = prepare_model_record_edit(
        review,
        SaveModelRecordRequest(
            dataset=dataset,
            record_id=1,
            expected_model_revision=1,
            changes={name: "Manually clarified definition."},
        ),
        complete_physical_scope(),
    )
    assert validation.valid
    original = review.records_by_id[dataset][1].model_dump()
    updated = validation.records[dataset][0].model_dump()
    assert {field for field in original if original[field] != updated[field]} == {name}


def test_logical_attribute_editor_exposes_key_origins_and_audit_classification() -> None:
    review = review_graph(complete_model_graph())
    editor = model_record_editor(
        review,
        ModelRecordEditorRequest(
            dataset="logical_attribute", record_id=1, expected_model_revision=1
        ),
    )
    field_names = {field.name for field in editor.fields}
    assert "logical_attribute_is_primary_key" not in field_names
    assert {
        "logical_attribute_is_surrogate_key",
        "logical_attribute_is_natural_key",
        "logical_attribute_is_audit_column",
    } <= field_names
    with pytest.raises(WorkbenchError):
        prepare_model_record_edit(
            review,
            SaveModelRecordRequest(
                dataset="logical_attribute",
                record_id=1,
                expected_model_revision=1,
                changes={"logical_attribute_is_primary_key": True},
            ),
            complete_physical_scope(),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"logical_entity_schema_name": "silver", "logical_entity_name": "Renamed"},
        {"logical_entity_is_locked": False},
        {"logical_entity_status": "inactive"},
        {"sources": []},
        {"logical_entity_type": "invalid"},
        {"logical_entity_type": "other"},
        {"logical_entity_definition": "   "},
    ],
)
def test_editor_rejects_identity_lifecycle_evidence_and_invalid_definition(
    changes: dict[str, object],
) -> None:
    with pytest.raises(WorkbenchError):
        prepare_model_record_edit(
            review_graph(complete_model_graph()),
            SaveModelRecordRequest(
                dataset="logical_entity",
                record_id=1,
                expected_model_revision=1,
                changes=changes,
            ),
            complete_physical_scope(),
        )


def test_editor_protects_locked_records_and_shows_model_choices() -> None:
    graph = complete_model_graph()
    graph["logical_entity"][0]["logical_entity_is_locked"] = True
    review = review_graph(graph)
    command = SaveModelRecordRequest(
        dataset="logical_entity",
        record_id=1,
        expected_model_revision=1,
        changes={"logical_entity_definition": "Revised definition."},
    )
    editor = model_record_editor(review, command)
    assert editor.is_locked
    type_field = next(field for field in editor.fields if field.name == "logical_entity_type")
    assert type_field.kind == "choice" and "transaction" in type_field.options
    with pytest.raises(WorkbenchError) as error:
        prepare_model_record_edit(review, command, complete_physical_scope())
    assert error.value.code == "record_locked"


@pytest.mark.parametrize("request_type", [PreviewModelRecordsRequest, ReviewModelRecordsRequest])
@pytest.mark.parametrize(
    "invalid",
    [
        {"record_ids": []},
        {"layer": "logical", "record_ids": [1]},
        {"layer": "logical", "record_ids": [], "action": "unlock"},
        {"layer": "conceptual", "record_ids": []},
    ],
)
def test_clear_contract_cannot_bypass_explicit_selection(
    request_type: type[PreviewModelRecordsRequest] | type[ReviewModelRecordsRequest],
    invalid: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        request_type.model_validate(
            {
                "dataset": "logical_entity",
                "record_ids": [1],
                "action": "deactivate",
                "expected_model_revision": 1,
                **invalid,
            }
        )
