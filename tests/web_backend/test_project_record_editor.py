"""Manual definition edits validate complete records and preserve their graph identity."""

from dataclasses import replace
from typing import get_args

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.snapshots.project import DATASETS_BY_NAME
from gds_workbench_api.features.project_change_sets.contracts import (
    PreviewProjectRecordsRequest,
    ReviewProjectRecordsRequest,
)
from gds_workbench_api.features.project_change_sets.editor import (
    EditableDataset,
    ProjectRecordEditorRequest,
    SaveProjectRecordRequest,
    prepare_project_record_edit,
    project_record_editor,
)
from pydantic import ValidationError

from tests.mcp.project_test_fixtures import (
    complete_physical_scope,
    complete_project_graph,
)
from tests.web_backend.test_modeled_record_review import review_graph


@pytest.mark.parametrize(
    "dataset",
    [
        value
        for value in get_args(EditableDataset.__value__)
        if value != "mapping_object"
    ],
)
def test_edit_definition_preserves_all_other_fields(dataset: EditableDataset) -> None:
    review = review_graph(complete_project_graph())
    editor = project_record_editor(
        review,
        ProjectRecordEditorRequest(
            dataset=dataset,
            record_id=1,
            expected_project_revision=1,
        ),
    )
    # Relationships have no definition; their basis explains the link.
    name = f"{dataset}_basis" if dataset.endswith("_relationship") else f"{dataset}_definition"
    assert name in {field.name for field in editor.fields}
    assert not any(
        field.name in DATASETS_BY_NAME[dataset].canonical_key
        or field.name.endswith(("_status", "_is_active", "_is_locked"))
        for field in editor.fields
    )
    validation = prepare_project_record_edit(
        review,
        SaveProjectRecordRequest(
            dataset=dataset,
            record_id=1,
            expected_project_revision=1,
            changes={name: "Manually clarified definition."},
        ),
        complete_physical_scope(),
    )
    assert validation.valid
    original = review.records_by_id[dataset][1].model_dump()
    updated = validation.records[dataset][0].model_dump()
    assert {field for field in original if original[field] != updated[field]} == {name}


def test_logical_attribute_editor_exposes_key_origins_and_audit_classification() -> (
    None
):
    review = review_graph(complete_project_graph())
    editor = project_record_editor(
        review,
        ProjectRecordEditorRequest(
            dataset="logical_attribute", record_id=1, expected_project_revision=1
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
        prepare_project_record_edit(
            review,
            SaveProjectRecordRequest(
                dataset="logical_attribute",
                record_id=1,
                expected_project_revision=1,
                changes={"logical_attribute_is_primary_key": True},
            ),
            complete_physical_scope(),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"logical_entity_schema_name": "silver", "logical_entity_name": "Renamed"},
        {"logical_entity_is_locked": False},
        {"logical_entity_is_active": False},
        {"sources": []},
        {"logical_entity_type": "invalid"},
        {"logical_entity_type": "lookup"},
        {"logical_entity_definition": "   "},
    ],
)
def test_editor_rejects_identity_lifecycle_evidence_and_invalid_definition(
    changes: dict[str, object],
) -> None:
    with pytest.raises(WorkbenchError):
        prepare_project_record_edit(
            review_graph(complete_project_graph()),
            SaveProjectRecordRequest(
                dataset="logical_entity",
                record_id=1,
                expected_project_revision=1,
                changes=changes,
            ),
            complete_physical_scope(),
        )


def test_editor_protects_locked_records_and_shows_project_choices() -> None:
    graph = complete_project_graph()
    graph["logical_entity"][0]["logical_entity_is_locked"] = True
    review = review_graph(graph)
    command = SaveProjectRecordRequest(
        dataset="logical_entity",
        record_id=1,
        expected_project_revision=1,
        changes={"logical_entity_definition": "Revised definition."},
    )
    editor = project_record_editor(review, command)
    assert editor.is_locked
    type_field = next(
        field for field in editor.fields if field.name == "logical_entity_type"
    )
    assert type_field.kind == "choice" and "transaction" in type_field.options
    with pytest.raises(WorkbenchError) as error:
        prepare_project_record_edit(review, command, complete_physical_scope())
    assert error.value.code == "record_locked"


def test_editor_offers_only_active_reference_codes() -> None:
    review = review_graph(complete_project_graph())
    logical = review.snapshot.logical
    review = replace(
        review,
        snapshot=review.snapshot.model_copy(
            update={
                "logical": logical.model_copy(
                    update={
                        "entity_types": tuple(
                            row.model_copy(
                                update={
                                    "logical_entity_type_is_active": (
                                        row.logical_entity_type_code != "history"
                                    )
                                }
                            )
                            for row in logical.entity_types
                        )
                    }
                )
            }
        ),
    )
    entity_editor = project_record_editor(
        review,
        ProjectRecordEditorRequest(
            dataset="logical_entity", record_id=1, expected_project_revision=1
        ),
    )
    entity_type = next(
        field for field in entity_editor.fields if field.name == "logical_entity_type"
    )
    assert "core" in entity_type.options and "history" not in entity_type.options
    assert "logical_entity_type_detail" not in {field.name for field in entity_editor.fields}
    fact_editor = project_record_editor(
        review,
        ProjectRecordEditorRequest(
            dataset="dimensional_entity", record_id=1, expected_project_revision=1
        ),
    )
    fact_type = next(
        field for field in fact_editor.fields if field.name == "dimensional_fact_type"
    )
    assert fact_type.kind == "choice" and not fact_type.required
    assert {"transaction", "periodic_snapshot"} <= set(fact_type.options)


@pytest.mark.parametrize(
    "request_type", [PreviewProjectRecordsRequest, ReviewProjectRecordsRequest]
)
@pytest.mark.parametrize(
    "invalid",
    [
        {"record_ids": []},
        {"layer": "logical", "record_ids": [1]},
        {"layer": "logical", "record_ids": [], "action": "unlock"},
        {"layer": "subject_area", "record_ids": []},
    ],
)
def test_clear_contract_cannot_bypass_explicit_selection(
    request_type: type[PreviewProjectRecordsRequest]
    | type[ReviewProjectRecordsRequest],
    invalid: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        request_type.model_validate(
            {
                "dataset": "logical_entity",
                "record_ids": [1],
                "action": "deactivate",
                "expected_project_revision": 1,
                **invalid,
            }
        )
