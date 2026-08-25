from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from gds_etl_workbench.domain.mapping_profiles import (
    MAPPING_STANDARD_SCHEMA_DIGEST,
    mapping_package_digest,
)
from pydantic import JsonValue
from test_mapping_preparation import (
    _context,  # pyright: ignore[reportPrivateUsage]
    _plan,  # pyright: ignore[reportPrivateUsage]
)

from gds_workbench_api.features.mapping.candidate import (
    MappingHeaderCandidateValidator,
)
from gds_workbench_api.features.mapping import (
    MappingOutputTemplate,
    MappingOutputTemplateField,
    MappingPreparation,
    MappingProfileIdentity,
    MappingRunContext,
)
from gds_workbench_api.features.mapping.profile_registry import (
    load_mapping_profile_registry,
)


def _preparation(
    *,
    operation: str = "build",
    object_template: MappingOutputTemplate | None = None,
) -> MappingPreparation:
    object_selection = (
        None
        if object_template is None
        else (object_template.output_template_id, object_template.schema_digest)
    )
    plan = _plan(operation=operation, object_template=object_selection).model_copy(
        update={
            "profile": MappingProfileIdentity(
                key="mapping.standard",
                version="1.0.0",
                schema_digest=MAPPING_STANDARD_SCHEMA_DIGEST,
            )
        }
    )
    original = _context()
    header = original.headers[1].model_copy(update={"output_template_id": None})
    source = original.sources[0].model_copy(
        update={"modeled_entity_id": header.modeled_entity.entity_id}
    )
    context = MappingRunContext.model_validate(
        {
            **original.model_dump(mode="python"),
            "output_template_selections": plan.output_template_selections.model_dump(
                mode="python"
            ),
            "output_templates": {
                "ids": (
                    []
                    if object_template is None
                    else [object_template.output_template_id]
                ),
                "definitions": (
                    []
                    if object_template is None
                    else [object_template.model_dump(mode="python")]
                ),
            },
            "sources": [source.model_dump(mode="python")],
            "headers": [header.model_dump(mode="python")],
            "target_dependency_graph": {
                "nodes": [
                    {
                        "target_object_id": plan.pair.target_object_id,
                        "dependency_order": 0,
                        "status": "active",
                        "has_locked_headers": False,
                        "has_unlocked_headers": True,
                    }
                ],
                "edges": [],
                "malformed_reference_count": 0,
                "mixed_order_target_count": 0,
            },
        },
        strict=False,
    )
    from gds_workbench_api.features.mapping import assess_mapping_readiness

    registration = load_mapping_profile_registry()
    readiness = assess_mapping_readiness(
        plan=plan,
        context=context,
        registration=registration,
    )
    assert readiness.ready
    return MappingPreparation(
        plan=plan,
        context=context,
        registration=registration,
        readiness=readiness,
    )


def _candidate() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "package": {
            "schema_version": "1.0",
            "package_ref": "customer_crm",
            "route": "logical_to_silver",
            "target_object_id": 501,
            "source_system_id": 31,
            "artifact_type": "sql_file",
            "artifact_generation_instructions": "Generate idempotent SQL.",
            "pydantic_profile": {
                "key": "mapping.standard",
                "version": "1.0.0",
                "schema_digest": MAPPING_STANDARD_SCHEMA_DIGEST,
            },
            "executable_sources": [
                {
                    "object_id": 401,
                    "alias": "customer_source",
                    "role": "customer source",
                    "batch_rule": None,
                }
            ],
            "non_executable_provenance": [],
            "runtime_parameters": [],
            "source_system_dependencies": [],
            "target_dependencies": [],
            "steps": [
                {
                    "name": "project_customer",
                    "depends_on": [],
                    "inputs": ["customer_source"],
                    "output": "customer_projected",
                    "logic": "Project the customer source.",
                }
            ],
            "grain_and_deduplication": "One row per customer.",
            "load": {
                "write_mode": "append",
                "merge_keys": [],
                "partition_basis": None,
                "concurrent_system_write_mode": "serialized",
                "concurrent_write_basis": "One selected source System at a time.",
            },
        },
        "headers": [
            {
                "mapping_object_id": 102,
                "transformation": {
                    "schema_version": "1.0",
                    "transformation_kind": "direct",
                    "source_aliases": ["customer_source"],
                    "logic": "Use the customer source directly.",
                },
            }
        ],
        "coverage": {
            "expected_mapping_object_ids": [102],
            "returned_mapping_object_ids": [102],
        },
    }


def _object_template() -> MappingOutputTemplate:
    return MappingOutputTemplate(
        output_template_id=880,
        code="mapping_object.review",
        name="Mapping Object review",
        description="Structured header review fields.",
        target_type="mapping_object",
        schema_digest="8" * 64,
        schema_digest_is_valid=True,
        is_active=True,
        fields=(
            MappingOutputTemplateField(
                name="source_aliases",
                description="Executable source aliases.",
                data_type="array",
                array_item_type="string",
                example=["customer_source"],
                is_required=True,
                order=10,
            ),
            MappingOutputTemplateField(
                name="logic",
                description="Reviewable Mapping logic.",
                data_type="string",
                array_item_type=None,
                example="Use the customer source directly.",
                is_required=True,
                order=20,
            ),
        ),
    )


def _with_preserved_header(preparation: MappingPreparation) -> MappingPreparation:
    candidate = _candidate()
    package = cast(dict[str, Any], candidate["package"])
    original = _context().headers[0]
    preserved = original.model_copy(
        update={
            "artifact_type": "sql_file",
            "artifact_generation_instructions": "Generate idempotent SQL.",
            "profile": preparation.plan.profile,
            "mapping_package_document": package,
            "mapping_package_digest": mapping_package_digest(package),
            "transformation_document": {
                "schema_version": "1.0",
                "transformation_kind": "direct",
                "source_aliases": ["customer_source"],
            },
            "output_template_id": None,
            "attribute_mappings": tuple(
                child.model_copy(update={"output_template_id": None})
                for child in original.attribute_mappings
            ),
        }
    )
    author = preparation.context.headers[0]
    source_for_preserved = preparation.context.sources[0].model_copy(
        update={
            "source_mapping_id": 302,
            "modeled_entity_id": preserved.modeled_entity.entity_id,
        }
    )
    context = preparation.context.model_copy(
        update={
            "headers": (preserved, author),
            "sources": (*preparation.context.sources, source_for_preserved),
            "target_dependency_graph": (
                preparation.context.target_dependency_graph.model_copy(
                    update={
                        "nodes": (
                            preparation.context.target_dependency_graph.nodes[
                                0
                            ].model_copy(
                                update={
                                    "has_locked_headers": True,
                                    "has_unlocked_headers": True,
                                }
                            ),
                        )
                    }
                )
            ),
        }
    )
    from gds_workbench_api.features.mapping import assess_mapping_readiness

    readiness = assess_mapping_readiness(
        plan=preparation.plan,
        context=context,
        registration=preparation.registration,
    )
    assert readiness.ready
    assert [(item.mapping_object_id, item.action) for item in readiness.headers] == [
        (101, "preserve"),
        (102, "author" if preparation.plan.operation == "build" else "extend"),
    ]
    return preparation.model_copy(update={"context": context, "readiness": readiness})


async def test_valid_build_header_candidate_normalizes_without_persistence() -> None:
    validator = MappingHeaderCandidateValidator(preparation=_preparation())
    candidate = cast(JsonValue, _candidate())

    assert (await validator.validate(candidate)).issues == ()
    normalized = validator.parse_validated(candidate)

    assert normalized.package.target_object_id == 501
    assert normalized.headers[0].mapping_object_id == 102
    assert normalized.headers[0].transformation["source_aliases"] == ["customer_source"]
    assert len(normalized.package_digest) == 64
    assert "MappingPackageDocumentV1" in str(validator.output_schema())


async def test_candidate_must_match_the_exact_frozen_pair_route_and_artifact() -> None:
    for field, value in (
        ("target_object_id", 999),
        ("source_system_id", 999),
        ("route", "dimensional_to_gold"),
        ("artifact_type", "python_file"),
    ):
        candidate = _candidate()
        package = cast(dict[str, Any], candidate["package"])
        package[field] = value

        issues = (
            await MappingHeaderCandidateValidator(preparation=_preparation()).validate(
                cast(JsonValue, candidate)
            )
        ).issues

        assert {issue.code for issue in issues} == {"candidate.identity_mismatch"}


async def test_build_candidate_cannot_return_a_preserved_locked_header() -> None:
    preparation = _with_preserved_header(_preparation())
    candidate = _candidate()
    headers = cast(list[dict[str, Any]], candidate["headers"])
    preserved = deepcopy(headers[0])
    preserved["mapping_object_id"] = 101
    headers.insert(0, preserved)
    coverage = cast(dict[str, Any], candidate["coverage"])
    coverage["expected_mapping_object_ids"] = [101, 102]
    coverage["returned_mapping_object_ids"] = [101, 102]

    issues = (
        await MappingHeaderCandidateValidator(preparation=preparation).validate(
            cast(JsonValue, candidate)
        )
    ).issues

    assert "candidate.header_not_actionable" in {issue.code for issue in issues}


async def test_candidate_rejects_a_preparation_that_is_not_ready() -> None:
    preparation = _preparation()
    preparation = preparation.model_copy(
        update={"readiness": preparation.readiness.model_copy(update={"ready": False})}
    )

    issues = (
        await MappingHeaderCandidateValidator(preparation=preparation).validate(
            cast(JsonValue, _candidate())
        )
    ).issues

    assert "candidate.preparation_not_ready" in {issue.code for issue in issues}


async def test_build_candidate_must_keep_the_package_of_preserved_headers() -> None:
    preparation = _with_preserved_header(_preparation())
    candidate = _candidate()
    coverage = cast(dict[str, Any], candidate["coverage"])
    coverage["expected_mapping_object_ids"] = [101, 102]
    package = cast(dict[str, Any], candidate["package"])
    package["artifact_generation_instructions"] = "Generate different SQL."

    issues = (
        await MappingHeaderCandidateValidator(preparation=preparation).validate(
            cast(JsonValue, candidate)
        )
    ).issues

    assert "candidate.package_preservation_required" in {issue.code for issue in issues}


async def test_package_executable_sources_must_resolve_in_frozen_context() -> None:
    candidate = _candidate()
    package = cast(dict[str, Any], candidate["package"])
    sources = cast(list[dict[str, Any]], package["executable_sources"])
    sources[0]["object_id"] = 999

    issues = (
        await MappingHeaderCandidateValidator(preparation=_preparation()).validate(
            cast(JsonValue, candidate)
        )
    ).issues

    assert "candidate.source_outside_context" in {issue.code for issue in issues}


async def test_batch_rule_must_name_the_frozen_object_batch_attribute() -> None:
    candidate = _candidate()
    package = cast(dict[str, Any], candidate["package"])
    sources = cast(list[dict[str, Any]], package["executable_sources"])
    sources[0]["batch_rule"] = {"attribute_id": 801, "values": [1048]}

    issues = (
        await MappingHeaderCandidateValidator(preparation=_preparation()).validate(
            cast(JsonValue, candidate)
        )
    ).issues

    assert "candidate.batch_attribute_mismatch" in {issue.code for issue in issues}


async def test_header_source_aliases_must_resolve_for_that_frozen_entity() -> None:
    candidate = _candidate()
    headers = cast(list[dict[str, Any]], candidate["headers"])
    transformation = cast(dict[str, Any], headers[0]["transformation"])
    transformation["source_aliases"] = ["unknown_source"]

    issues = (
        await MappingHeaderCandidateValidator(preparation=_preparation()).validate(
            cast(JsonValue, candidate)
        )
    ).issues

    assert "candidate.source_alias_outside_context" in {issue.code for issue in issues}


async def test_package_source_dependencies_must_equal_the_complete_frozen_graph() -> (
    None
):
    candidate = _candidate()
    package = cast(dict[str, Any], candidate["package"])
    package["source_system_dependencies"] = [
        {"predecessor_source_system_id": 20, "reason": "Unfrozen dependency."}
    ]

    issues = (
        await MappingHeaderCandidateValidator(preparation=_preparation()).validate(
            cast(JsonValue, candidate)
        )
    ).issues

    assert "candidate.source_dependency_mismatch" in {issue.code for issue in issues}


async def test_load_merge_keys_must_resolve_to_active_target_attributes() -> None:
    candidate = _candidate()
    package = cast(dict[str, Any], candidate["package"])
    load = cast(dict[str, Any], package["load"])
    load["write_mode"] = "merge"
    load["merge_keys"] = [999]

    issues = (
        await MappingHeaderCandidateValidator(preparation=_preparation()).validate(
            cast(JsonValue, candidate)
        )
    ).issues

    assert "candidate.target_attribute_outside_context" in {
        issue.code for issue in issues
    }


async def test_selected_template_drives_schema_and_dynamic_leaf_validation() -> None:
    validator = MappingHeaderCandidateValidator(
        preparation=_preparation(object_template=_object_template())
    )
    schema = validator.output_schema()
    assert "source_aliases" in str(schema)
    assert "Reviewable Mapping logic." in str(schema)

    candidate = _candidate()
    headers = cast(list[dict[str, Any]], candidate["headers"])
    transformation = cast(dict[str, Any], headers[0]["transformation"])
    transformation.pop("logic")

    issues = (await validator.validate(cast(JsonValue, candidate))).issues

    assert {issue.code for issue in issues} == {"candidate.transformation_invalid"}


async def test_agent_cannot_create_or_repoint_header_bindings_or_lock_state() -> None:
    for field, value in (
        ("modeled_entity_id", 999),
        ("is_locked", True),
        ("status", "inactive"),
    ):
        candidate = _candidate()
        headers = cast(list[dict[str, Any]], candidate["headers"])
        headers[0][field] = value

        issues = (
            await MappingHeaderCandidateValidator(preparation=_preparation()).validate(
                cast(JsonValue, candidate)
            )
        ).issues

        assert {issue.code for issue in issues} == {"candidate.schema_invalid"}


async def test_header_mapper_rejects_partial_or_false_coverage() -> None:
    preparation = _with_preserved_header(_preparation())
    candidate = _candidate()
    coverage = cast(dict[str, Any], candidate["coverage"])
    coverage["expected_mapping_object_ids"] = [101]
    coverage["returned_mapping_object_ids"] = [101]
    headers = cast(list[dict[str, Any]], candidate["headers"])
    headers[0]["mapping_object_id"] = 101

    issues = (
        await MappingHeaderCandidateValidator(preparation=preparation).validate(
            cast(JsonValue, candidate)
        )
    ).issues
    codes = {issue.code for issue in issues}

    assert "candidate.coverage_mismatch" in codes
    assert "candidate.coverage_incomplete" in codes
    assert "candidate.header_not_actionable" in codes


async def test_package_target_dependencies_must_equal_the_complete_frozen_graph() -> (
    None
):
    candidate = _candidate()
    package = cast(dict[str, Any], candidate["package"])
    package["target_dependencies"] = [
        {"predecessor_target_object_id": 400, "reason": "Unfrozen target."}
    ]

    issues = (
        await MappingHeaderCandidateValidator(preparation=_preparation()).validate(
            cast(JsonValue, candidate)
        )
    ).issues

    assert "candidate.target_dependency_mismatch" in {issue.code for issue in issues}


async def test_extend_revises_only_readiness_marked_unlocked_headers() -> None:
    preparation = _with_preserved_header(_preparation(operation="extend"))
    candidate = _candidate()
    coverage = cast(dict[str, Any], candidate["coverage"])
    coverage["expected_mapping_object_ids"] = [101, 102]

    validator = MappingHeaderCandidateValidator(preparation=preparation)

    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()
    assert [
        header.mapping_object_id
        for header in validator.parse_validated(cast(JsonValue, candidate)).headers
    ] == [102]


async def test_template_identity_drift_is_a_bounded_validation_issue() -> None:
    preparation = _preparation(object_template=_object_template())
    template = preparation.context.output_templates.definitions[0].model_copy(
        update={"is_active": False}
    )
    context = preparation.context.model_copy(
        update={
            "output_templates": preparation.context.output_templates.model_copy(
                update={"definitions": (template,)}
            )
        }
    )
    preparation = preparation.model_copy(
        update={
            "context": context,
            "readiness": preparation.readiness.model_copy(update={"ready": False}),
        }
    )

    issues = (
        await MappingHeaderCandidateValidator(preparation=preparation).validate(
            cast(JsonValue, _candidate())
        )
    ).issues

    assert "candidate.template_identity_mismatch" in {issue.code for issue in issues}
