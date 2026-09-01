from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue
from test_mapping_attribute_candidate import (
    _candidate as _attribute_candidate,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_attribute_candidate import (
    _preparation,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_header_candidate import (
    _candidate as _header_candidate,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_header_candidate import (
    _object_template,  # pyright: ignore[reportPrivateUsage]
)

from gds_workbench_api.features.mapping import (
    MappingOutputTemplate,
    MappingOutputTemplateField,
    MappingOutputTemplateInventory,
    MappingOutputTemplateSelection,
    MappingOutputTemplateSelections,
    MappingPreparation,
    assess_mapping_readiness,
)
from gds_workbench_api.features.mapping.attribute_candidate import (
    build_mapping_attribute_batch_plans,
)
from gds_workbench_api.features.mapping.candidate import (
    MappingHeaderCandidateValidator,
)
from gds_workbench_api.features.mapping.complete_candidate import (
    CompleteMappingCandidateValidator,
)


def _complete_candidate_for(
    preparation: MappingPreparation,
) -> tuple[CompleteMappingCandidateValidator, dict[str, Any]]:
    header_document = _header_candidate()
    header = MappingHeaderCandidateValidator(preparation=preparation).parse_validated(
        cast(JsonValue, header_document)
    )
    plans = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=header.package,
    )
    attribute_documents = [
        _attribute_candidate(preparation, header.package) for _ in plans
    ]
    return CompleteMappingCandidateValidator(preparation=preparation), {
        "schema_version": "1.0",
        "header": header_document,
        "attribute_batches": attribute_documents,
    }


def _complete_candidate() -> tuple[CompleteMappingCandidateValidator, dict[str, Any]]:
    return _complete_candidate_for(_preparation())


def _attribute_template() -> MappingOutputTemplate:
    return MappingOutputTemplate(
        output_template_id=881,
        code="mapping_attribute.review",
        name="Mapping Attribute review",
        description="Structured Attribute review fields.",
        target_type="mapping_attribute",
        schema_digest="9" * 64,
        schema_digest_is_valid=True,
        is_active=True,
        fields=(
            MappingOutputTemplateField(
                name="logic",
                description="Reviewable Attribute logic.",
                data_type="string",
                array_item_type=None,
                example="Use the source identifier.",
                is_required=True,
                order=10,
            ),
        ),
    )


def _preparation_with_templates() -> MappingPreparation:
    preparation = _preparation()
    object_template = _object_template()
    attribute_template = _attribute_template()
    selections = MappingOutputTemplateSelections(
        mapping_object=MappingOutputTemplateSelection(
            output_template_id=object_template.output_template_id,
            schema_digest=object_template.schema_digest,
        ),
        mapping_attribute=MappingOutputTemplateSelection(
            output_template_id=attribute_template.output_template_id,
            schema_digest=attribute_template.schema_digest,
        ),
    )
    plan = preparation.plan.model_copy(
        update={"output_template_selections": selections}
    )
    context = preparation.context.model_copy(
        update={
            "output_template_selections": selections,
            "output_templates": MappingOutputTemplateInventory(
                ids=(
                    object_template.output_template_id,
                    attribute_template.output_template_id,
                ),
                definitions=(object_template, attribute_template),
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


async def test_complete_candidate_returns_one_validated_atomic_result() -> None:
    validator, candidate = _complete_candidate()

    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()
    result = validator.parse_validated(cast(JsonValue, candidate))

    assert result.normalized.header.package.package_ref == "customer_crm"
    assert [change.dataset for change in result.changes] == [
        "mapping_object",
        "mapping_attribute",
    ]


async def test_complete_candidate_rejects_mapped_coverage_without_a_binding() -> None:
    validator, candidate = _complete_candidate()
    partial = deepcopy(candidate)
    batches = cast(list[dict[str, Any]], partial["attribute_batches"])
    batches[0]["attribute_mappings"] = []

    issues = (await validator.validate(cast(JsonValue, partial))).issues

    assert "candidate.disposition_invalid" in {issue.code for issue in issues}
    assert all(issue.path[:2] == ("attribute_batches", 0) for issue in issues)
    with pytest.raises(InvalidRequestError, match="Attribute"):
        validator.parse_validated(cast(JsonValue, partial))


async def test_complete_candidate_revalidates_the_raw_header_boundary() -> None:
    validator, candidate = _complete_candidate()
    forged = deepcopy(candidate)
    header = cast(dict[str, Any], forged["header"])
    headers = cast(list[dict[str, Any]], header["headers"])
    transformation = cast(dict[str, Any], headers[0]["transformation"])
    transformation["source_aliases"] = ["unfrozen_source"]

    issues = (await validator.validate(cast(JsonValue, forged))).issues

    assert {issue.code for issue in issues} == {
        "candidate.source_alias_outside_context"
    }
    assert issues[0].path[0] == "header"
    with pytest.raises(InvalidRequestError, match="Header"):
        validator.parse_validated(cast(JsonValue, forged))


async def test_complete_candidate_requires_every_attribute_batch_once() -> None:
    validator, candidate = _complete_candidate()
    duplicate = deepcopy(candidate)
    batches = cast(list[dict[str, Any]], duplicate["attribute_batches"])
    batches.append(deepcopy(batches[0]))

    issues = (await validator.validate(cast(JsonValue, duplicate))).issues

    assert {issue.code for issue in issues} == {
        "candidate.attribute_batch_coverage_mismatch"
    }
    with pytest.raises(InvalidRequestError, match="every Attribute batch once"):
        validator.parse_validated(cast(JsonValue, duplicate))


def test_complete_output_schema_is_strict_and_uses_both_frozen_templates() -> None:
    schema = CompleteMappingCandidateValidator(
        preparation=_preparation_with_templates()
    ).output_schema()
    definitions = cast(dict[str, Any], schema["$defs"])
    object_leaf = cast(
        dict[str, Any], definitions["ObjectMappingTransformationDocumentV1"]
    )
    attribute_leaf = cast(
        dict[str, Any], definitions["AttributeMappingTransformationDocumentV1"]
    )

    assert schema["additionalProperties"] is False
    assert object_leaf["additionalProperties"] is False
    assert set(cast(dict[str, Any], object_leaf["properties"])) == {
        "schema_version",
        "transformation_kind",
        "source_aliases",
        "logic",
    }
    assert attribute_leaf["additionalProperties"] is False
    assert set(cast(dict[str, Any], attribute_leaf["properties"])) == {
        "schema_version",
        "transformation_kind",
        "logic",
    }


async def test_complete_candidate_enforces_both_frozen_dynamic_templates() -> None:
    validator, candidate = _complete_candidate_for(_preparation_with_templates())
    batches = cast(list[dict[str, Any]], candidate["attribute_batches"])
    mappings = cast(list[dict[str, Any]], batches[0]["attribute_mappings"])
    transformation = cast(dict[str, Any], mappings[0]["transformation"])
    transformation.pop("source_columns")
    transformation.pop("step_output")
    transformation.pop("expression")

    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()

    transformation["undeclared"] = "not allowed"
    issues = (await validator.validate(cast(JsonValue, candidate))).issues
    assert "candidate.transformation_invalid" in {issue.code for issue in issues}


async def test_pathological_batch_returns_one_bounded_error() -> None:
    validator, candidate = _complete_candidate()
    batches = cast(list[dict[str, Any]], candidate["attribute_batches"])
    mappings = cast(list[dict[str, Any]], batches[0]["attribute_mappings"])
    original = mappings[0]
    mappings[:] = []
    for index in range(202):
        duplicate = deepcopy(original)
        duplicate["local_ref"] = f"customer_id_binding_{index}"
        mappings.append(duplicate)

    issues = (await validator.validate(cast(JsonValue, candidate))).issues

    assert len(issues) == 1
    assert issues[0].code == "candidate.attribute_batch_invalid"
    assert issues[0].path == ("attribute_batches", 0)


async def test_complete_envelope_failure_reports_the_missing_field() -> None:
    validator, candidate = _complete_candidate()
    candidate.pop("header")

    issues = (await validator.validate(cast(JsonValue, candidate))).issues

    assert len(issues) == 1
    assert issues[0].code == "candidate.schema_required"
    assert issues[0].path == ("header",)
