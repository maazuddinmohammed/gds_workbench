from __future__ import annotations

import json
from typing import cast

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue
from test_mapping_attribute_candidate import (
    _candidate as _attribute_candidate,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_attribute_candidate import (
    _preparation as _attribute_preparation,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_execution_context import (
    _five_thousand_attribute_preparation,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_executor import (
    _preparation as _executor_preparation,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_header_candidate import (
    _candidate as _header_candidate,  # pyright: ignore[reportPrivateUsage]
)

from gds_workbench_api.features.mapping.attribute_candidate import (
    MappingAttributeCandidateValidator,
    build_mapping_attribute_batch_plans,
)
from gds_workbench_api.features.mapping.candidate import (
    MappingHeaderCandidateValidator,
)
from gds_workbench_api.features.mapping.detailed import (
    MappingDetailedTargetReviewValidator,
    build_mapping_attribute_stage_context,
    build_mapping_detailed_review_manifest,
    build_mapping_header_stage_context,
    build_mapping_target_review_context,
    merge_mapping_detailed_candidate,
)
from gds_workbench_api.features.mapping.preparation_contracts import (
    ExistingMappingAttribute,
)
from gds_workbench_api.integrations.agents.fake_mapping import (
    fake_mapping_attribute_batch,
)

_MAXIMUM_STAGE_BYTES = 256 * 1024


def _serialized_size(value: JsonValue) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _repair_envelope_size(value: JsonValue) -> int:
    return _serialized_size(
        cast(JsonValue, {"original_context": value, "repair": None})
    )


def test_maximum_mapping_input_is_partitioned_into_exact_bounded_stage_contexts() -> (
    None
):
    preparation = _five_thousand_attribute_preparation()
    detailed_plan = _executor_preparation("detailed_coverage").plan.agent_plan
    preparation = preparation.model_copy(
        update={
            "plan": preparation.plan.model_copy(update={"agent_plan": detailed_plan})
        }
    )
    raw_header = cast(JsonValue, _header_candidate())
    header = MappingHeaderCandidateValidator(preparation=preparation).parse_validated(
        raw_header
    )

    header_context = build_mapping_header_stage_context(
        preparation=preparation,
        maximum_bytes=_MAXIMUM_STAGE_BYTES,
    )
    assert _repair_envelope_size(header_context) <= _MAXIMUM_STAGE_BYTES

    batch_plans = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=header.package,
    )
    assert len(batch_plans) == 50
    returned_target_ids: list[int] = []
    for batch_plan in batch_plans:
        context = build_mapping_attribute_stage_context(
            preparation=preparation,
            header=header,
            batch_plan=batch_plan,
            maximum_bytes=_MAXIMUM_STAGE_BYTES,
        )
        assert _repair_envelope_size(context) <= _MAXIMUM_STAGE_BYTES
        document = cast(dict[str, JsonValue], context)
        mapping_context = cast(dict[str, JsonValue], document["mapping_context"])
        target = cast(dict[str, JsonValue], mapping_context["target"])
        target_attributes = cast(list[dict[str, JsonValue]], target["attributes"])
        batch_target_ids = [
            cast(int, item["attribute_id"]) for item in target_attributes
        ]
        assert batch_target_ids == list(batch_plan.expected_target_attribute_ids)
        returned_target_ids.extend(batch_target_ids)

    expected_target_ids = [
        item.attribute_id
        for item in preparation.context.target.attributes
        if item.is_active
    ]
    assert returned_target_ids == expected_target_ids
    assert len(returned_target_ids) == len(set(returned_target_ids)) == 5_000

    raw_batches = tuple(
        cast(
            JsonValue,
            {
                "chunk_index": plan.chunk_index,
                "chunk_count": plan.chunk_count,
                "package_digest": plan.package_digest,
                "coverage_manifest_digest": plan.coverage_manifest_digest,
            },
        )
        for plan in batch_plans
    )
    manifest = build_mapping_detailed_review_manifest(
        header_candidate=raw_header,
        header=header,
        batch_plans=batch_plans,
        raw_batches=raw_batches,
    )
    target_context = build_mapping_target_review_context(
        manifest=manifest,
        maximum_bytes=_MAXIMUM_STAGE_BYTES,
    )
    assert _repair_envelope_size(target_context) <= _MAXIMUM_STAGE_BYTES
    reviewed_target_ids = [
        identifier
        for batch in manifest.batches
        for identifier in batch.expected_target_attribute_ids
    ]
    assert reviewed_target_ids == expected_target_ids


@pytest.mark.asyncio
async def test_mapping_review_receipt_and_server_merge_fail_closed_on_batch_loss() -> (
    None
):
    preparation = _executor_preparation("detailed_coverage")
    raw_header = cast(JsonValue, _header_candidate())
    header = MappingHeaderCandidateValidator(preparation=preparation).parse_validated(
        raw_header
    )
    batch_plans = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=header.package,
    )
    raw_batch = cast(JsonValue, _attribute_candidate(preparation, header.package))
    manifest = build_mapping_detailed_review_manifest(
        header_candidate=raw_header,
        header=header,
        batch_plans=batch_plans,
        raw_batches=(raw_batch,),
    )
    review_context = build_mapping_target_review_context(
        manifest=manifest,
        maximum_bytes=_MAXIMUM_STAGE_BYTES,
    )
    assert _repair_envelope_size(review_context) <= _MAXIMUM_STAGE_BYTES

    validator = MappingDetailedTargetReviewValidator(manifest=manifest)
    receipt = cast(JsonValue, manifest.model_dump(mode="json"))
    assert not (await validator.validate(receipt)).issues
    changed = cast(dict[str, JsonValue], manifest.model_dump(mode="json"))
    changed["draft_candidate_digest"] = "0" * 64
    assert (await validator.validate(cast(JsonValue, changed))).issues

    merged = cast(
        dict[str, JsonValue],
        merge_mapping_detailed_candidate(
            header_candidate=raw_header,
            batch_plans=batch_plans,
            raw_batches=(raw_batch,),
        ),
    )
    assert merged["header"] == raw_header
    assert merged["attribute_batches"] == [raw_batch]

    with pytest.raises(InvalidRequestError):
        merge_mapping_detailed_candidate(
            header_candidate=raw_header,
            batch_plans=batch_plans,
            raw_batches=(),
        )
    with pytest.raises(InvalidRequestError):
        merge_mapping_detailed_candidate(
            header_candidate=raw_header,
            batch_plans=batch_plans,
            raw_batches=(raw_batch, raw_batch),
        )


@pytest.mark.asyncio
async def test_detailed_attribute_slice_preserves_authoritative_existing_binding() -> (
    None
):
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
    preparation = _attribute_preparation(existing=existing)
    raw_header = cast(JsonValue, _header_candidate())
    header = MappingHeaderCandidateValidator(preparation=preparation).parse_validated(
        raw_header
    )
    batch_plan = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=header.package,
    )[0]
    context = cast(
        dict[str, JsonValue],
        build_mapping_attribute_stage_context(
            preparation=preparation,
            header=header,
            batch_plan=batch_plan,
            maximum_bytes=_MAXIMUM_STAGE_BYTES,
        ),
    )
    mapping_context = cast(dict[str, JsonValue], context["mapping_context"])
    validator = MappingAttributeCandidateValidator(
        preparation=preparation,
        package=header.package,
        batch_plan=batch_plan,
    )
    candidate = fake_mapping_attribute_batch(
        context=mapping_context,
        package=cast(dict[str, JsonValue], header.package.model_dump(mode="json")),
        batch_plan=cast(dict[str, JsonValue], batch_plan.model_dump(mode="json")),
        output_schema=validator.output_schema(),
    )

    assert not (await validator.validate(candidate)).issues
    document = cast(dict[str, JsonValue], candidate)
    assert document["attribute_mappings"] == []
    dispositions = cast(
        list[dict[str, JsonValue]],
        document["target_attribute_dispositions"],
    )
    assert dispositions == [
        {
            "target_attribute_id": 901,
            "disposition": "already_mapped",
            "reason": None,
        }
    ]
