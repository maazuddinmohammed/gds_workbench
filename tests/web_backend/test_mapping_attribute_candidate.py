from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.mapping_contracts import MappingPackageDocumentV1
from pydantic import JsonValue
from test_mapping_header_candidate import (
    _candidate as _header_candidate,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_header_candidate import (
    _preparation as _header_preparation,  # pyright: ignore[reportPrivateUsage]
)

from gds_workbench_api.features.mapping.attribute_candidate import (
    MappingAttributeCandidateValidator,
    build_mapping_attribute_batch_plans,
)
from gds_workbench_api.features.mapping.candidate import (
    MappingHeaderCandidateValidator,
)
from gds_workbench_api.features.mapping import (
    ExistingMappingAttribute,
    MappingModeledAttribute,
    MappingOutputTemplate,
    MappingOutputTemplateField,
    MappingOutputTemplateInventory,
    MappingOutputTemplateSelection,
    MappingPreparation,
    assess_mapping_readiness,
)


def _preparation(
    *,
    operation: str = "build",
    existing: ExistingMappingAttribute | None = None,
) -> MappingPreparation:
    preparation = _header_preparation(operation=operation)
    modeled_attribute = MappingModeledAttribute(
        attribute_id=701,
        attribute_name="CustomerID",
        attribute_definition="Stable customer identifier.",
        attribute_data_type="BIGINT",
        is_nullable=False,
        ordinal_position=1,
        is_audit_column=False,
        status="active",
        is_locked=False,
    )
    header = preparation.context.headers[0]
    header = header.model_copy(
        update={
            "modeled_entity": header.modeled_entity.model_copy(
                update={"attributes": (modeled_attribute,)}
            ),
            "attribute_mappings": () if existing is None else (existing,),
        }
    )
    context = preparation.context.model_copy(update={"headers": (header,)})
    readiness = assess_mapping_readiness(
        plan=preparation.plan,
        context=context,
        registration=preparation.registration,
    )
    assert readiness.ready
    return preparation.model_copy(update={"context": context, "readiness": readiness})


def _package(preparation: MappingPreparation) -> MappingPackageDocumentV1:
    candidate = cast(JsonValue, _header_candidate())
    return (
        MappingHeaderCandidateValidator(preparation=preparation)
        .parse_validated(candidate)
        .package
    )


def _attribute_template(
    *fields: MappingOutputTemplateField,
) -> MappingOutputTemplate:
    return MappingOutputTemplate(
        output_template_id=881,
        code="mapping_attribute.review",
        name="Mapping Attribute review",
        description="Structured Attribute review fields.",
        target_type="mapping_attribute",
        schema_digest="7" * 64,
        schema_digest_is_valid=True,
        is_active=True,
        fields=fields,
    )


def _with_attribute_template(
    preparation: MappingPreparation,
    template: MappingOutputTemplate,
) -> MappingPreparation:
    selection = MappingOutputTemplateSelection(
        output_template_id=template.output_template_id,
        schema_digest=template.schema_digest,
    )
    selections = preparation.plan.output_template_selections.model_copy(
        update={"mapping_attribute": selection}
    )
    plan = preparation.plan.model_copy(
        update={"output_template_selections": selections}
    )
    context = preparation.context.model_copy(
        update={
            "output_template_selections": selections,
            "output_templates": MappingOutputTemplateInventory(
                ids=(template.output_template_id,),
                definitions=(template,),
            ),
        }
    )
    readiness = assess_mapping_readiness(
        plan=plan,
        context=context,
        registration=preparation.registration,
    )
    assert readiness.ready
    return preparation.model_copy(
        update={"plan": plan, "context": context, "readiness": readiness}
    )


def _candidate(
    preparation: MappingPreparation,
    package: MappingPackageDocumentV1,
) -> dict[str, Any]:
    batch = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    return {
        "schema_version": "1.0",
        "package_ref": package.package_ref,
        "target_object_id": batch.target_object_id,
        "source_system_id": batch.source_system_id,
        "chunk_index": batch.chunk_index,
        "chunk_count": batch.chunk_count,
        "package_digest": batch.package_digest,
        "coverage_manifest_digest": batch.coverage_manifest_digest,
        "attribute_mappings": [
            {
                "mapping_object_id": 102,
                "mapping_attribute_id": None,
                "local_ref": "customer_id_binding",
                "modeled_entity_type": "logical_entity",
                "logical_attribute_id": 701,
                "dimensional_attribute_id": None,
                "target_attribute_id": 901,
                "disposition": "create",
                "transformation": {
                    "schema_version": "1.0",
                    "transformation_kind": "direct",
                    "source_columns": [
                        {
                            "source_alias": "customer_source",
                            "source_attribute_id": 801,
                        }
                    ],
                    "step_output": None,
                    "expression": None,
                    "logic": "Use the source customer identifier.",
                },
            }
        ],
        "target_attribute_dispositions": [
            {
                "target_attribute_id": 901,
                "disposition": "mapped",
                "reason": None,
            }
        ],
        "coverage": {
            "expected_target_attribute_ids": list(batch.expected_target_attribute_ids),
            "returned_target_attribute_ids": [901],
            "expected_existing_mapping_attribute_ids": list(
                batch.expected_existing_mapping_attribute_ids
            ),
            "returned_existing_mapping_attribute_ids": [],
        },
    }


async def test_valid_attribute_batch_is_exact_normalized_and_non_persisting() -> None:
    preparation = _preparation()
    package = _package(preparation)
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=package,
        batch_plan=plan,
    )
    candidate = cast(JsonValue, _candidate(preparation, package))

    assert (await validator.validate(candidate)).issues == ()
    normalized = validator.parse_validated(candidate)

    assert normalized.package_ref == "customer_crm"
    assert normalized.attribute_mappings[0].local_ref == "customer_id_binding"
    assert normalized.attribute_mappings[0].transformation["source_columns"] == [
        {"source_alias": "customer_source", "source_attribute_id": 801}
    ]
    assert "AttributeMapperBatchOutputV1" in str(validator.output_schema())


async def test_batch_identity_and_exact_coverage_are_immutable() -> None:
    preparation = _preparation()
    package = _package(preparation)
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=package,
        batch_plan=plan,
    )

    for path, value, expected_code in (
        (("package_digest",), "f" * 64, "candidate.identity_mismatch"),
        (("coverage_manifest_digest",), "e" * 64, "candidate.identity_mismatch"),
        (
            ("coverage", "expected_target_attribute_ids"),
            [999],
            "candidate.coverage_mismatch",
        ),
        (
            ("coverage", "returned_target_attribute_ids"),
            [999],
            "candidate.coverage_mismatch",
        ),
    ):
        candidate = _candidate(preparation, package)
        target: dict[str, Any] = candidate
        for key in path[:-1]:
            target = cast(dict[str, Any], target[key])
        target[path[-1]] = value

        issues = (await validator.validate(cast(JsonValue, candidate))).issues

        assert expected_code in {issue.code for issue in issues}


async def test_existing_binding_is_actionable_but_cannot_be_repointed() -> None:
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
    package = _package(preparation)
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    assert plan.expected_existing_mapping_attribute_ids == (990,)
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=package,
        batch_plan=plan,
    )
    candidate = _candidate(preparation, package)
    mapping = cast(list[dict[str, Any]], candidate["attribute_mappings"])[0]
    mapping.update(
        {
            "mapping_attribute_id": 990,
            "local_ref": None,
            "disposition": "update",
            "logical_attribute_id": 702,
        }
    )
    coverage = cast(dict[str, Any], candidate["coverage"])
    coverage["returned_existing_mapping_attribute_ids"] = [990]

    issues = (await validator.validate(cast(JsonValue, candidate))).issues

    assert "candidate.binding_repointed" in {issue.code for issue in issues}


async def test_actionable_existing_binding_updates_without_changing_identity() -> None:
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
    package = _package(preparation)
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=package,
        batch_plan=plan,
    )
    candidate = _candidate(preparation, package)
    mapping = cast(list[dict[str, Any]], candidate["attribute_mappings"])[0]
    mapping.update(
        {
            "mapping_attribute_id": 990,
            "local_ref": None,
            "disposition": "update",
        }
    )
    coverage = cast(dict[str, Any], candidate["coverage"])
    coverage["returned_existing_mapping_attribute_ids"] = [990]

    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()
    normalized = validator.parse_validated(cast(JsonValue, candidate))
    assert normalized.attribute_mappings[0].mapping_attribute_id == 990
    assert normalized.attribute_mappings[0].disposition == "update"


async def test_build_and_extend_never_return_preserved_children() -> None:
    existing = ExistingMappingAttribute(
        mapping_attribute_id=990,
        modeled_attribute_id=701,
        target_attribute_id=901,
        transformation_document={
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "logic": "Preserved authoring.",
        },
        status="active",
        is_locked=True,
        agent_run_id=None,
        workflow_run_id=None,
        output_template_id=None,
    )
    for operation in ("build", "extend"):
        preparation = _preparation(operation=operation, existing=existing)
        package = _package(preparation)
        plan = build_mapping_attribute_batch_plans(
            preparation=preparation,
            package=package,
        )[0]
        assert plan.expected_existing_mapping_attribute_ids == ()
        validator = MappingAttributeCandidateValidator(
            preparation=preparation,
            package=package,
            batch_plan=plan,
        )
        candidate = _candidate(preparation, package)
        mapping = cast(list[dict[str, Any]], candidate["attribute_mappings"])[0]
        mapping.update(
            {
                "mapping_attribute_id": 990,
                "local_ref": None,
                "disposition": "update",
            }
        )
        coverage = cast(dict[str, Any], candidate["coverage"])
        coverage["returned_existing_mapping_attribute_ids"] = [990]

        issues = (await validator.validate(cast(JsonValue, candidate))).issues

        assert "candidate.attribute_not_actionable" in {issue.code for issue in issues}


async def test_preserved_complete_binding_is_covered_as_already_mapped() -> None:
    existing = ExistingMappingAttribute(
        mapping_attribute_id=990,
        modeled_attribute_id=701,
        target_attribute_id=901,
        transformation_document={
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "logic": "Preserved authoring.",
        },
        status="active",
        is_locked=True,
        agent_run_id=None,
        workflow_run_id=None,
        output_template_id=None,
    )
    preparation = _preparation(existing=existing)
    package = _package(preparation)
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=package,
        batch_plan=plan,
    )
    candidate = _candidate(preparation, package)
    candidate["attribute_mappings"] = []
    disposition = cast(
        list[dict[str, Any]], candidate["target_attribute_dispositions"]
    )[0]
    disposition["disposition"] = "already_mapped"

    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()
    assert (
        validator.parse_validated(cast(JsonValue, candidate))
        .target_attribute_dispositions[0]
        .disposition
        == "already_mapped"
    )


async def test_source_columns_and_step_outputs_must_resolve_in_frozen_context() -> None:
    template = _attribute_template(
        MappingOutputTemplateField(
            name="source_columns",
            description="Structured source references.",
            data_type="array",
            array_item_type="object",
            example=None,
            is_required=False,
            order=10,
        ),
        MappingOutputTemplateField(
            name="step_output",
            description="A package step output.",
            data_type="string",
            array_item_type=None,
            example=None,
            is_required=False,
            order=20,
        ),
    )
    preparation = _with_attribute_template(_preparation(), template)
    package = _package(preparation)
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=package,
        batch_plan=plan,
    )
    for field, value in (
        (
            "source_columns",
            [{"source_alias": "customer_source", "source_attribute_id": 999}],
        ),
        ("step_output", "unknown_output"),
    ):
        candidate = _candidate(preparation, package)
        mapping = cast(list[dict[str, Any]], candidate["attribute_mappings"])[0]
        mapping["transformation"] = {
            "schema_version": "1.0",
            "transformation_kind": "direct",
            field: value,
        }

        issues = (await validator.validate(cast(JsonValue, candidate))).issues

        assert "candidate.transformation_reference_invalid" in {
            issue.code for issue in issues
        }


async def test_dynamic_template_fields_remain_authoritative_when_not_reference_shaped() -> (
    None
):
    template = _attribute_template(
        MappingOutputTemplateField(
            name="source_columns",
            description="Reviewer labels, not physical source references.",
            data_type="array",
            array_item_type="string",
            example=None,
            is_required=True,
            order=10,
        ),
        MappingOutputTemplateField(
            name="step_output",
            description="Reviewer rank, not a package output name.",
            data_type="integer",
            array_item_type=None,
            example=None,
            is_required=True,
            order=20,
        ),
    )
    preparation = _with_attribute_template(_preparation(), template)
    package = _package(preparation)
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=package,
        batch_plan=plan,
    )
    candidate = _candidate(preparation, package)
    mapping = cast(list[dict[str, Any]], candidate["attribute_mappings"])[0]
    mapping["transformation"] = {
        "schema_version": "1.0",
        "transformation_kind": "direct",
        "source_columns": ["reviewed"],
        "step_output": 7,
    }

    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()


def test_attribute_planner_revalidates_exact_header_package_graph() -> None:
    preparation = _preparation()
    package_document = _package(preparation).model_dump(mode="python")
    package_document["source_system_dependencies"] = [
        {
            "predecessor_source_system_id": 999,
            "reason": "Not present in the frozen dependency graph.",
        }
    ]
    mutated = MappingPackageDocumentV1.model_validate(package_document, strict=True)

    with pytest.raises(ValueError, match="frozen Header|dependency"):
        build_mapping_attribute_batch_plans(
            preparation=preparation,
            package=mutated,
        )


async def test_attribute_sources_are_scoped_to_the_selected_header_entity() -> None:
    template = _attribute_template(
        MappingOutputTemplateField(
            name="source_columns",
            description="Structured source references.",
            data_type="array",
            array_item_type="object",
            example=None,
            is_required=True,
            order=10,
        )
    )
    preparation = _with_attribute_template(_preparation(), template)
    first_header = preparation.context.headers[0]
    second_header = first_header.model_copy(
        update={
            "mapping_object_id": 103,
            "modeled_entity": first_header.modeled_entity.model_copy(
                update={
                    "entity_id": 203,
                    "entity_name": "CustomerContact",
                    "attributes": (
                        first_header.modeled_entity.attributes[0].model_copy(
                            update={"attribute_id": 702}
                        ),
                    ),
                }
            ),
        }
    )
    first_source = preparation.context.sources[0]
    second_source = first_source.model_copy(
        update={
            "source_mapping_id": 302,
            "modeled_entity_id": 203,
            "object": first_source.object.model_copy(
                update={
                    "object_id": 402,
                    "object_name": "customer_contact",
                    "attributes": (
                        first_source.object.attributes[0].model_copy(
                            update={"attribute_id": 802}
                        ),
                    ),
                }
            ),
        }
    )
    context = preparation.context.model_copy(
        update={
            "headers": (first_header, second_header),
            "sources": (first_source, second_source),
        }
    )
    readiness = assess_mapping_readiness(
        plan=preparation.plan,
        context=context,
        registration=preparation.registration,
    )
    assert readiness.ready
    preparation = preparation.model_copy(
        update={"context": context, "readiness": readiness}
    )
    header_document = _header_candidate()
    header_package = cast(dict[str, Any], header_document["package"])
    header_package["executable_sources"].append(
        {
            "object_id": 402,
            "alias": "contact_source",
            "role": "customer contact source",
            "batch_rule": None,
        }
    )
    header_document["headers"].append(
        {
            "mapping_object_id": 103,
            "transformation": {
                "schema_version": "1.0",
                "transformation_kind": "direct",
                "source_aliases": ["contact_source"],
            },
        }
    )
    header_document["coverage"] = {
        "expected_mapping_object_ids": [102, 103],
        "returned_mapping_object_ids": [102, 103],
    }
    package = (
        MappingHeaderCandidateValidator(preparation=preparation)
        .parse_validated(cast(JsonValue, header_document))
        .package
    )
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=package,
        batch_plan=plan,
    )
    candidate = _candidate(preparation, package)
    cast(list[dict[str, Any]], candidate["attribute_mappings"])[0]["transformation"] = {
        "schema_version": "1.0",
        "transformation_kind": "direct",
        "source_columns": [
            {"source_alias": "contact_source", "source_attribute_id": 802}
        ],
    }

    issues = (await validator.validate(cast(JsonValue, candidate))).issues

    assert "candidate.transformation_reference_invalid" in {
        issue.code for issue in issues
    }


def test_batch_manifest_uses_canonical_numeric_coverage_order() -> None:
    existing_by_target = (
        ExistingMappingAttribute(
            mapping_attribute_id=20,
            modeled_attribute_id=701,
            target_attribute_id=902,
            transformation_document=None,
            status="active",
            is_locked=False,
            agent_run_id=None,
            workflow_run_id=None,
            output_template_id=None,
        ),
        ExistingMappingAttribute(
            mapping_attribute_id=10,
            modeled_attribute_id=701,
            target_attribute_id=901,
            transformation_document=None,
            status="active",
            is_locked=False,
            agent_run_id=None,
            workflow_run_id=None,
            output_template_id=None,
        ),
    )
    preparation = _preparation()
    header = preparation.context.headers[0].model_copy(
        update={"attribute_mappings": existing_by_target}
    )
    target_901 = preparation.context.target.attributes[0].model_copy(
        update={"attribute_ordinal_position": 2}
    )
    target_902 = target_901.model_copy(
        update={
            "attribute_id": 902,
            "attribute_name": "StatusID",
            "attribute_ordinal_position": 1,
        }
    )
    context = preparation.context.model_copy(
        update={
            "headers": (header,),
            "target": preparation.context.target.model_copy(
                update={"attributes": (target_902, target_901)}
            ),
        }
    )
    readiness = assess_mapping_readiness(
        plan=preparation.plan,
        context=context,
        registration=preparation.registration,
    )
    assert readiness.ready
    preparation = preparation.model_copy(
        update={"context": context, "readiness": readiness}
    )

    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=_package(preparation),
    )[0]

    assert plan.expected_target_attribute_ids == (901, 902)
    assert plan.expected_existing_mapping_attribute_ids == (10, 20)


async def test_agent_envelope_uses_shared_identifier_and_text_bounds() -> None:
    preparation = _preparation()
    package = _package(preparation)
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=package,
        batch_plan=plan,
    )

    for mutate in ("package_ref", "local_ref", "reason"):
        candidate = _candidate(preparation, package)
        if mutate == "package_ref":
            candidate["package_ref"] = "a" * 129
        elif mutate == "local_ref":
            cast(list[dict[str, Any]], candidate["attribute_mappings"])[0][
                "local_ref"
            ] = "a" * 129
        else:
            candidate["attribute_mappings"] = []
            disposition = cast(
                list[dict[str, Any]], candidate["target_attribute_dispositions"]
            )[0]
            disposition.update(
                {"disposition": "intentionally_unmapped", "reason": "   "}
            )

        issues = (await validator.validate(cast(JsonValue, candidate))).issues

        assert {issue.code for issue in issues} == {"candidate.schema_invalid"}


async def test_unchanged_disposition_is_absent_from_schema_and_envelope() -> None:
    preparation = _preparation()
    package = _package(preparation)
    plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )[0]
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=package,
        batch_plan=plan,
    )
    schema = cast(dict[str, Any], validator.output_schema())
    definitions = cast(dict[str, Any], schema["$defs"])
    mapping_item = cast(dict[str, Any], definitions["AttributeMappingItemV1"])
    properties = cast(dict[str, Any], mapping_item["properties"])
    disposition_schema = cast(dict[str, Any], properties["disposition"])
    candidate = _candidate(preparation, package)
    cast(list[dict[str, Any]], candidate["attribute_mappings"])[0]["disposition"] = (
        "unchanged"
    )

    assert disposition_schema["enum"] == ["create", "update"]
    assert {
        issue.code
        for issue in (await validator.validate(cast(JsonValue, candidate))).issues
    } == {"candidate.schema_invalid"}


def test_batch_planner_is_bounded_and_digest_is_deterministic() -> None:
    preparation = _preparation()
    package = _package(preparation)

    first = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )
    second = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=package,
    )

    assert first == second
    assert len(first) <= 100
    assert all(len(item.expected_target_attribute_ids) <= 100 for item in first)
    assert all(
        len(item.expected_existing_mapping_attribute_ids) <= 500 for item in first
    )
    assert len(first[0].coverage_manifest_digest) == 64


def test_attribute_candidate_requires_a_ready_matching_preparation() -> None:
    preparation = _preparation()
    package = _package(preparation)
    unavailable = preparation.model_copy(
        update={"readiness": preparation.readiness.model_copy(update={"ready": False})}
    )

    with pytest.raises(ValueError, match="ready"):
        build_mapping_attribute_batch_plans(
            preparation=unavailable,
            package=package,
        )

    mismatched = deepcopy(package.model_dump(mode="python"))
    mismatched["target_object_id"] = 999
    with pytest.raises(ValueError, match="frozen"):
        build_mapping_attribute_batch_plans(
            preparation=preparation,
            package=MappingPackageDocumentV1.model_validate(mismatched, strict=True),
        )
