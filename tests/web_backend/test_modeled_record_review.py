"""Every result lifecycle plan remains a valid graph and preserves authored values."""

from dataclasses import replace
from typing import cast

import pytest
from gds_etl_workbench.application.project_snapshot import ProjectReviewSnapshot
from gds_etl_workbench.domain.modeling_records import ContextRecord
from gds_etl_workbench.domain.snapshots.project import (
    ProjectChangeSetDataset,
    project_snapshot_records,
)
from gds_workbench_api.features.project_change_sets.review import (
    REVIEW_FIELDS,
    ProjectLayer,
    ProjectReviewDataset,
    prepare_project_record_review,
    review_lifecycle,
)

from tests.mcp.project_test_fixtures import (
    complete_physical_scope,
    complete_project_graph,
    snapshot_from_graph,
)


def review_graph(
    graph: dict[ProjectChangeSetDataset, list[dict[str, object]]],
) -> ProjectReviewSnapshot:
    snapshot = snapshot_from_graph(graph)
    return ProjectReviewSnapshot(
        snapshot=snapshot,
        records_by_id={
            dataset: {
                row.context_record_id if isinstance(row, ContextRecord) else i + 1: row
                for i, row in enumerate(rows)
            }
            for dataset, rows in project_snapshot_records(snapshot).items()
            if dataset in REVIEW_FIELDS
        },
    )


@pytest.mark.parametrize("dataset", list(REVIEW_FIELDS))
def test_all_result_lifecycle_transitions_preserve_graph_and_content(
    dataset: ProjectReviewDataset,
) -> None:
    graph = complete_project_graph()
    for action in ("lock", "unlock", "deactivate", "reactivate"):
        review = review_graph(graph)
        prepared = prepare_project_record_review(
            review,
            physical_scope=complete_physical_scope(),
            dataset=dataset,
            record_ids=[next(iter(review.records_by_id[dataset]))],
            action=action,
        )
        assert prepared.validation.valid, [
            (i.code, i.dataset) for i in prepared.validation.issues
        ]
        for decision in prepared.decisions:
            original, changed = (
                decision.original.model_dump(mode="json"),
                decision.reviewed.model_dump(mode="json"),
            )
            assert {
                field for field in original if original[field] != changed[field]
            } <= set(REVIEW_FIELDS[decision.dataset][:2])
            if decision.dataset == "context_record":
                position = next(
                    index
                    for index, row in enumerate(graph[decision.dataset])
                    if row["context_record_id"] == decision.record_id
                )
            else:
                assert isinstance(decision.record_id, int)
                position = decision.record_id - 1
            graph[decision.dataset][position] = changed
        selected = prepared.decisions[0]
        assert selected.selected and selected.dataset == dataset
        locked, status = review_lifecycle(selected.reviewed, dataset)
        assert locked is (action == "lock")
        assert status == ("inactive" if action == "deactivate" else "active")


@pytest.mark.parametrize("dependent_locked", [False, True])
def test_context_retirement_includes_supported_records_and_respects_locks(
    dependent_locked: bool,
) -> None:
    graph = complete_project_graph()
    graph["dimensional_entity"][0]["dimensional_entity_is_locked"] = dependent_locked
    context_id = cast(str, graph["context_record"][0]["context_record_id"])
    prepared = prepare_project_record_review(
        review_graph(graph),
        physical_scope=complete_physical_scope(),
        dataset="context_record",
        record_ids=[context_id],
        action="deactivate",
    )
    assert prepared.decisions[0].record_id == context_id
    assert prepared.decisions[0].selected
    assert {item.dataset for item in prepared.decisions} >= {
        "context_record",
        "dimensional_entity",
        "dimensional_attribute",
    }
    assert prepared.validation.valid is (not dependent_locked)
    if dependent_locked:
        assert any(
            issue.code == "record_locked" for issue in prepared.validation.issues
        )
    for item in prepared.decisions:
        assert (
            review_lifecycle(item.original, item.dataset)[0]
            == review_lifecycle(item.reviewed, item.dataset)[0]
        )


def test_attribute_retirement_includes_mapping_code_and_validation() -> None:
    review = review_graph(complete_project_graph())
    prepared = prepare_project_record_review(
        review,
        physical_scope=complete_physical_scope(),
        dataset="logical_attribute",
        record_ids=[2],
        action="deactivate",
    )
    assert prepared.validation.valid
    assert {d.dataset for d in prepared.decisions} >= {
        "logical_attribute",
        "logical_relationship",
        "mapping_object",
        "mapping_attribute",
        "generated_code",
        "generated_code_source_system",
        "validation_group",
        "validation_check",
    }
    assert all(
        d.selected or "Required" in d.reason or "last active Mapping" in d.reason
        for d in prepared.decisions
    )
    graph = complete_project_graph()
    graph["mapping_attribute"][0]["attribute_mapping_is_locked"] = True
    blocked = prepare_project_record_review(
        review_graph(graph),
        physical_scope=complete_physical_scope(),
        dataset="logical_attribute",
        record_ids=[2],
        action="deactivate",
    )
    assert not blocked.validation.valid and any(
        i.code == "record_locked" for i in blocked.validation.issues
    )


def test_stale_code_review_preserves_assignments_and_authoring_still_rejects() -> None:
    from gds_etl_workbench.application.change_sets.project_validation import (
        validate_future_graph,
    )

    graph = complete_project_graph()
    for dataset in ("mapping_object", "mapping_attribute"):
        graph[cast(ProjectChangeSetDataset, dataset)] += [
            {**row, "source_system_code": "CRM"}
            for row in graph[cast(ProjectChangeSetDataset, dataset)]
        ]
    physical = replace(
        complete_physical_scope(), active_system_codes=frozenset({"erp", "crm", "gds"})
    )
    for action in ("lock", "unlock"):
        review = review_graph(graph)
        prepared = prepare_project_record_review(
            review,
            physical_scope=physical,
            dataset="generated_code",
            record_ids=[next(iter(review.records_by_id[dataset]))],
            action=action,
        )
        assert prepared.validation.valid
        graph["generated_code"][0] = prepared.decisions[0].reviewed.model_dump(
            mode="json"
        )
    assert not validate_future_graph(
        snapshot=review_graph(graph).snapshot,
        physical_scope=physical,
        staged_documents={"generated_code": graph["generated_code"]},
    ).valid


def test_partial_code_retirement_previews_the_bundle_and_reactivation_requires_coverage() -> (
    None
):
    graph = complete_project_graph()
    for dataset in ("mapping_object", "mapping_attribute"):
        name = cast(ProjectChangeSetDataset, dataset)
        graph[name] += [{**row, "source_system_code": "CRM"} for row in graph[name]]
    graph["generated_code"].append(
        {**graph["generated_code"][0], "artifact_name": "crm.sql"}
    )
    graph["generated_code_source_system"].append(
        {
            **graph["generated_code_source_system"][0],
            "artifact_name": "crm.sql",
            "source_system_code": "CRM",
        }
    )
    physical = replace(
        complete_physical_scope(), active_system_codes=frozenset({"erp", "crm", "gds"})
    )
    retired = prepare_project_record_review(
        review_graph(graph),
        physical_scope=physical,
        dataset="generated_code",
        record_ids=[1],
        action="deactivate",
    )
    assert retired.validation.valid
    assert {(d.dataset, d.record_id) for d in retired.decisions} == {
        ("generated_code", 1),
        ("generated_code", 2),
        ("generated_code_source_system", 1),
        ("generated_code_source_system", 2),
    }
    for decision in retired.decisions:
        assert isinstance(decision.record_id, int)
        graph[decision.dataset][decision.record_id - 1] = decision.reviewed.model_dump(
            mode="json"
        )
    partial = prepare_project_record_review(
        review_graph(graph),
        physical_scope=physical,
        dataset="generated_code",
        record_ids=[1],
        action="reactivate",
    )
    assert not partial.validation.valid
    complete = prepare_project_record_review(
        review_graph(graph),
        physical_scope=physical,
        dataset="generated_code",
        record_ids=[1, 2],
        action="reactivate",
    )
    assert complete.validation.valid


@pytest.mark.parametrize("layer", ["subject_area", "logical", "dimensional"])
def test_clear_layer_selects_every_active_record_and_required_dependents(
    layer: ProjectLayer,
) -> None:
    review = review_graph(complete_project_graph())
    prepared = prepare_project_record_review(
        review,
        physical_scope=complete_physical_scope(),
        dataset=cast(
            ProjectReviewDataset,
            "subject_area" if layer == "subject_area" else f"{layer}_entity",
        ),
        record_ids=[],
        action="deactivate",
        layer=layer,
    )
    assert prepared.validation.valid
    selected = {
        (item.dataset, item.record_id) for item in prepared.decisions if item.selected
    }
    assert selected == {
        (dataset, record_id)
        for dataset, records in review.records_by_id.items()
        if dataset == layer or dataset.startswith(layer + "_")
        for record_id, row in records.items()
        if review_lifecycle(row, cast(ProjectReviewDataset, dataset))[1] == "active"
    }
    assert {
        item.reason for item in prepared.decisions if item.selected
    } == {f"Clear the {'Subject Area' if layer == 'subject_area' else layer.title()} layer."}
    if layer == "subject_area":
        # Subject Areas are not modeling evidence; clearing them retires no model.
        assert {item.dataset for item in prepared.decisions} == {
            "subject_area",
            "subject_area_table",
        }
    for record_id, row in review.records_by_id["mapping_object"].items():
        if row.model_dump()["modeled_entity_type"] == f"{layer}_entity":
            assert any(
                item.dataset == "mapping_object" and item.record_id == record_id
                for item in prepared.decisions
            )


def test_clear_layer_includes_records_beyond_the_ledger_page_and_blocks_locked_children() -> (
    None
):
    graph = complete_project_graph()
    template = graph["subject_area"][0]
    graph["subject_area"].extend(
        {**template, "subject_area_name": f"Extra {number}"} for number in range(230)
    )
    graph["subject_area_table"][0]["subject_area_table_is_locked"] = True
    prepared = prepare_project_record_review(
        review_graph(graph),
        physical_scope=complete_physical_scope(),
        dataset="subject_area",
        record_ids=[],
        action="deactivate",
        layer="subject_area",
    )
    assert len(prepared.decisions) > 230
    assert not prepared.validation.valid
    assert any(issue.code == "record_locked" for issue in prepared.validation.issues)


def test_removing_logical_output_traces_persisted_dimensional_entity_lineage() -> None:
    graph = complete_project_graph()
    logical = graph["logical_entity"][0]
    graph["dimensional_entity"][0]["sources"] = [
        {
            "support_source_type": "logical_entity",
            "source_logical_entity": {
                "logical_entity_schema_name": logical["logical_entity_schema_name"],
                "logical_entity_name": logical["logical_entity_name"],
            },
            "rationale": "Applied Logical Entity input.",
            "is_active": True,
            "is_locked": False,
        }
    ]
    dimensional_key = {
        "modeled_entity_type": "dimensional_entity",
        "modeled_entity_schema_name": "gold",
        "modeled_entity_name": "SalesFact",
    }
    graph["mapping_object"].append({**graph["mapping_object"][0], **dimensional_key})
    graph["mapping_attribute"].extend(
        {
            **graph["mapping_attribute"][0],
            **dimensional_key,
            "modeled_attribute_name": name,
        }
        for name in ("SalesKey", "CustomerKey")
    )
    prepared = prepare_project_record_review(
        review_graph(graph),
        physical_scope=complete_physical_scope(),
        dataset="logical_entity",
        record_ids=[1],
        action="deactivate",
    )
    assert prepared.validation.valid
    assert any(
        item.dataset == "dimensional_entity" and item.record_id == 1
        for item in prepared.decisions
    )
    assert any(
        item.dataset == "mapping_object"
        and item.original.model_dump()["modeled_entity_name"] == "SalesFact"
        for item in prepared.decisions
    )
