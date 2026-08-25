from __future__ import annotations

from typing import cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.mapping_profiles import mapping_package_digest
from pydantic import JsonValue
from test_mapping_attribute_candidate import (
    _attribute_template,  # pyright: ignore[reportPrivateUsage]
    _preparation,  # pyright: ignore[reportPrivateUsage]
    _with_attribute_template,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_attribute_candidate import (
    _candidate as _attribute_candidate,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_header_candidate import (
    _candidate as _header_candidate,  # pyright: ignore[reportPrivateUsage]
)

from gds_workbench_api.features.mapping.attribute_candidate import (
    MappingAttributeCandidateValidator,
    NormalizedMappingAttributeBatch,
    build_mapping_attribute_batch_plans,
)
from gds_workbench_api.features.mapping.candidate import (
    MappingHeaderCandidateValidator,
    NormalizedMappingHeaderCandidate,
)
from gds_workbench_api.features.mapping import (
    ExistingMappingAttribute,
    MappingOutputTemplateField,
    MappingPreparation,
    assess_mapping_readiness,
)
from gds_workbench_api.features.mapping.reconciliation import (
    MappingCandidateReconciler,
)


def _validated_candidates() -> tuple[
    MappingCandidateReconciler,
    NormalizedMappingHeaderCandidate,
    tuple[NormalizedMappingAttributeBatch, ...],
]:
    preparation = _preparation()
    header_validator = MappingHeaderCandidateValidator(preparation=preparation)
    header = header_validator.parse_validated(cast(JsonValue, _header_candidate()))
    plans = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=header.package,
    )
    batches = tuple(
        MappingAttributeCandidateValidator(
            preparation=preparation,
            package=header.package,
            batch_plan=plan,
        ).parse_validated(
            cast(JsonValue, _attribute_candidate(preparation, header.package))
        )
        for plan in plans
    )
    return MappingCandidateReconciler(preparation=preparation), header, batches


def _preservation_only_preparation() -> MappingPreparation:
    existing = ExistingMappingAttribute(
        mapping_attribute_id=990,
        modeled_attribute_id=701,
        target_attribute_id=901,
        transformation_document={
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "logic": "Use the customer identifier.",
        },
        status="active",
        is_locked=True,
        agent_run_id=None,
        workflow_run_id=None,
        output_template_id=None,
    )
    preparation = _preparation(existing=existing)
    package = _header_candidate()["package"]
    header = preparation.context.headers[0].model_copy(
        update={
            "artifact_type": "sql_file",
            "artifact_generation_instructions": "Generate idempotent SQL.",
            "profile": preparation.plan.profile,
            "mapping_package_document": package,
            "mapping_package_digest": mapping_package_digest(package),
            "transformation_document": _header_candidate()["headers"][0][
                "transformation"
            ],
            "is_locked": True,
        }
    )
    context = preparation.context.model_copy(
        update={
            "headers": (header,),
            "target_dependency_graph": (
                preparation.context.target_dependency_graph.model_copy(
                    update={
                        "nodes": (
                            preparation.context.target_dependency_graph.nodes[
                                0
                            ].model_copy(
                                update={
                                    "has_locked_headers": True,
                                    "has_unlocked_headers": False,
                                }
                            ),
                        )
                    }
                )
            ),
        }
    )
    readiness = assess_mapping_readiness(
        plan=preparation.plan,
        context=context,
        registration=preparation.registration,
    )
    assert readiness.ready
    assert readiness.package_action == "preserve"
    return preparation.model_copy(update={"context": context, "readiness": readiness})


def _unchanged_extend_candidates(
    *,
    select_attribute_template: bool = False,
) -> tuple[
    MappingCandidateReconciler,
    NormalizedMappingHeaderCandidate,
    tuple[NormalizedMappingAttributeBatch, ...],
]:
    attribute_transformation: dict[str, JsonValue] = (
        {
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "logic": "Use the source customer identifier.",
        }
        if select_attribute_template
        else {
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "source_columns": [
                {"source_alias": "customer_source", "source_attribute_id": 801}
            ],
            "step_output": None,
            "expression": None,
            "logic": "Use the source customer identifier.",
        }
    )
    existing = ExistingMappingAttribute(
        mapping_attribute_id=990,
        modeled_attribute_id=701,
        target_attribute_id=901,
        transformation_document=attribute_transformation,
        status="active",
        is_locked=False,
        agent_run_id=None,
        workflow_run_id=None,
        output_template_id=None,
    )
    preparation = _preparation(operation="extend", existing=existing)
    if select_attribute_template:
        preparation = _with_attribute_template(
            preparation,
            _attribute_template(
                MappingOutputTemplateField(
                    name="logic",
                    description="Reviewable Attribute logic.",
                    data_type="string",
                    array_item_type=None,
                    example="Use the source customer identifier.",
                    is_required=True,
                    order=10,
                )
            ),
        )
    raw_header = _header_candidate()
    package = raw_header["package"]
    header = preparation.context.headers[0].model_copy(
        update={
            "artifact_type": "sql_file",
            "artifact_generation_instructions": "Generate idempotent SQL.",
            "profile": preparation.plan.profile,
            "mapping_package_document": package,
            "mapping_package_digest": mapping_package_digest(package),
            "transformation_document": raw_header["headers"][0]["transformation"],
        }
    )
    context = preparation.context.model_copy(update={"headers": (header,)})
    readiness = assess_mapping_readiness(
        plan=preparation.plan,
        context=context,
        registration=preparation.registration,
    )
    assert readiness.ready
    preparation = preparation.model_copy(
        update={"context": context, "readiness": readiness}
    )
    normalized_header = MappingHeaderCandidateValidator(
        preparation=preparation
    ).parse_validated(cast(JsonValue, raw_header))
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=normalized_header.package,
    )[0]
    raw_attribute = _attribute_candidate(preparation, normalized_header.package)
    raw_mapping = raw_attribute["attribute_mappings"][0]
    raw_mapping.update(
        {
            "mapping_attribute_id": 990,
            "local_ref": None,
            "disposition": "update",
            "transformation": attribute_transformation,
        }
    )
    raw_attribute["coverage"]["returned_existing_mapping_attribute_ids"] = [990]
    batch = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=normalized_header.package,
        batch_plan=plan,
    ).parse_validated(cast(JsonValue, raw_attribute))
    return (
        MappingCandidateReconciler(preparation=preparation),
        normalized_header,
        (batch,),
    )


def test_complete_mapping_candidates_compile_exact_atomic_deltas() -> None:
    reconciler, header, batches = _validated_candidates()

    changes = reconciler.reconcile(header=header, attribute_batches=batches)

    assert [change.dataset for change in changes] == [
        "mapping_object",
        "mapping_attribute",
    ]
    object_record = changes[0].records[0]
    assert object_record["tenant_code"] == "NWA"
    assert object_record["system_code"] == "GDS"
    assert object_record["connection_code"] == "lakehouse"
    assert object_record["object_schema"] == "silver_crm"
    assert object_record["object_name"] == "customer"
    assert object_record["source_system_code"] == "CRM"
    assert object_record["modeled_entity_type"] == "logical_entity"
    assert object_record["modeled_entity_name"] == "CustomerStatus"
    assert object_record["mapping_package_document"] == header.package.model_dump(
        mode="json"
    )
    attribute_record = changes[1].records[0]
    assert attribute_record["modeled_attribute_name"] == "CustomerID"
    assert attribute_record["attribute_name"] == "CustomerID"
    assert attribute_record["attribute_mapping_status"] == "active"
    assert attribute_record["attribute_mapping_is_locked"] is False


def test_reconciliation_rejects_missing_duplicate_or_foreign_batches() -> None:
    reconciler, header, batches = _validated_candidates()

    with pytest.raises(InvalidRequestError, match="complete"):
        reconciler.reconcile(header=header, attribute_batches=())
    with pytest.raises(InvalidRequestError, match="complete"):
        reconciler.reconcile(
            header=header,
            attribute_batches=(*batches, batches[0]),
        )

    foreign = batches[0].model_copy(update={"package_digest": "f" * 64})
    with pytest.raises(InvalidRequestError, match="package"):
        reconciler.reconcile(header=header, attribute_batches=(foreign,))


def test_reconciliation_rejects_cross_batch_local_reference_reuse() -> None:
    reconciler, header, batches = _validated_candidates()
    duplicate = batches[0].model_copy(
        update={
            "chunk_index": 2,
            "chunk_count": 2,
            "attribute_mappings": batches[0].attribute_mappings,
        }
    )

    with pytest.raises(InvalidRequestError, match="complete"):
        reconciler.reconcile(
            header=header,
            attribute_batches=(batches[0], duplicate),
        )


def test_reconciliation_rejects_invalid_shared_record_contract() -> None:
    reconciler, header, batches = _validated_candidates()
    invalid_mapping = (
        batches[0]
        .attribute_mappings[0]
        .model_copy(
            update={
                "transformation": {
                    "schema_version": "1.0",
                    "transformation_kind": "unknown",
                }
            }
        )
    )
    invalid = batches[0].model_copy(update={"attribute_mappings": (invalid_mapping,)})

    with pytest.raises(InvalidRequestError, match="validation"):
        reconciler.reconcile(header=header, attribute_batches=(invalid,))


def test_reconciliation_rejects_package_or_preparation_identity_drift() -> None:
    reconciler, header, batches = _validated_candidates()
    drifted = header.model_copy(update={"package_digest": "f" * 64})

    with pytest.raises(InvalidRequestError, match="package"):
        reconciler.reconcile(header=drifted, attribute_batches=batches)


def test_reconciliation_rejects_forged_mapped_disposition_without_mapping() -> None:
    reconciler, header, batches = _validated_candidates()
    forged = batches[0].model_copy(update={"attribute_mappings": ()})

    with pytest.raises(InvalidRequestError, match="semantic"):
        reconciler.reconcile(header=header, attribute_batches=(forged,))


def test_reconciliation_rejects_forged_missing_actionable_existing_binding() -> None:
    existing = ExistingMappingAttribute(
        mapping_attribute_id=990,
        modeled_attribute_id=701,
        target_attribute_id=901,
        transformation_document=None,
        status="active",
        is_locked=False,
        agent_run_id=None,
        workflow_run_id=None,
        output_template_id=None,
    )
    preparation = _preparation(existing=existing)
    header = MappingHeaderCandidateValidator(preparation=preparation).parse_validated(
        cast(JsonValue, _header_candidate())
    )
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=header.package,
    )[0]
    candidate = _attribute_candidate(preparation, header.package)
    candidate_mapping = candidate["attribute_mappings"][0]
    candidate_mapping.update(
        {
            "mapping_attribute_id": 990,
            "local_ref": None,
            "disposition": "update",
        }
    )
    candidate["coverage"]["returned_existing_mapping_attribute_ids"] = [990]
    batch = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=header.package,
        batch_plan=plan,
    ).parse_validated(cast(JsonValue, candidate))
    intentionally_unmapped = batch.target_attribute_dispositions[0].model_copy(
        update={"disposition": "intentionally_unmapped", "reason": "No valid source."}
    )
    forged = batch.model_copy(
        update={
            "attribute_mappings": (),
            "target_attribute_dispositions": (intentionally_unmapped,),
        }
    )

    with pytest.raises(InvalidRequestError, match="semantic"):
        MappingCandidateReconciler(preparation=preparation).reconcile(
            header=header,
            attribute_batches=(forged,),
        )


def test_reconciliation_rejects_forged_header_source_alias() -> None:
    reconciler, header, batches = _validated_candidates()
    forged_header = header.headers[0].model_copy(
        update={
            "transformation": {
                **header.headers[0].transformation,
                "source_aliases": ["outside_frozen_context"],
            }
        }
    )
    forged = header.model_copy(update={"headers": (forged_header,)})

    with pytest.raises(InvalidRequestError, match="semantic"):
        reconciler.reconcile(header=forged, attribute_batches=batches)


def test_preservation_only_ready_run_is_an_explicit_no_change() -> None:
    reconciler = MappingCandidateReconciler(
        preparation=_preservation_only_preparation()
    )

    assert reconciler.reconcile_preserved() == ()


def test_actionable_run_cannot_claim_a_preserved_no_change() -> None:
    reconciler = MappingCandidateReconciler(preparation=_preparation())

    with pytest.raises(InvalidRequestError, match="requires agent output"):
        reconciler.reconcile_preserved()


def test_valid_unchanged_extend_candidate_has_no_effective_change() -> None:
    reconciler, header, batches = _unchanged_extend_candidates()

    assert reconciler.reconcile(header=header, attribute_batches=batches) == ()


def test_template_selection_change_is_persisted_without_business_change() -> None:
    reconciler, header, batches = _unchanged_extend_candidates(
        select_attribute_template=True
    )

    changes = reconciler.reconcile(header=header, attribute_batches=batches)

    assert [change.dataset for change in changes] == ["mapping_attribute"]
    assert len(changes[0].records) == 1


def test_reconciliation_rejects_forged_dynamic_template_document() -> None:
    reconciler, header, batches = _unchanged_extend_candidates(
        select_attribute_template=True
    )
    mapping = (
        batches[0]
        .attribute_mappings[0]
        .model_copy(
            update={
                "transformation": {
                    **batches[0].attribute_mappings[0].transformation,
                    "undeclared": "forged",
                }
            }
        )
    )
    forged = batches[0].model_copy(update={"attribute_mappings": (mapping,)})

    with pytest.raises(InvalidRequestError, match="semantic"):
        reconciler.reconcile(header=header, attribute_batches=(forged,))
