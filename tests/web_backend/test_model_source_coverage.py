"""Coverage measures distinct selected support, not output Entity counts."""

# pyright: reportPrivateUsage=false
import json
from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.snapshots.model import DimensionalSection, LogicalSection
from gds_workbench_api.features.dimensional.candidate import (
    DimensionalCandidateValidator,
)
from gds_workbench_api.features.logical.candidate import LogicalCandidateValidator
from pydantic import JsonValue

from tests.web_backend import test_dimensional_candidate as dimensional
from tests.web_backend import test_logical_candidate as logical


@pytest.mark.parametrize(
    ("layer", "total", "covered", "accepted"),
    [
        ("logical", 30, 20, False),
        ("logical", 30, 21, True),
        ("logical", 30, 25, True),
        ("logical", 31, 21, False),
        ("logical", 31, 22, True),
        ("logical", 3, 2, False),
        ("logical", 1, 1, True),
        ("dimensional", 30, 17, False),
        ("dimensional", 30, 18, True),
        ("dimensional", 30, 25, True),
        ("dimensional", 31, 18, False),
        ("dimensional", 31, 19, True),
        ("dimensional", 3, 2, True),
        ("dimensional", 1, 1, True),
    ],
)
async def test_distinct_support_threshold_rounds_up(
    layer: str, total: int, covered: int, accepted: bool
) -> None:
    if layer == "logical":
        inputs = (
            logical._object(),
            *(logical._object(f"source_{i}") for i in range(1, total)),
        )
        validator = LogicalCandidateValidator(
            selected_object_keys=inputs,
            selected_attribute_keys=(logical._attribute(),),
            assertion_record_keys=(),
            applied=None,
        )
        candidate = cast(dict[str, Any], logical._candidate())
        refs = [item.model_dump(mode="json") for item in inputs]
        source_field = "source_object"
    else:
        entities = (
            dimensional._object(),
            *(dimensional._object(f"source_{i}") for i in range(1, total)),
        )
        validator = DimensionalCandidateValidator(
            selected_entity_keys=entities,
            selected_attribute_keys=(dimensional._attribute(),),
            assertion_record_keys=(),
            applied=None,
        )
        candidate = cast(dict[str, Any], dimensional._candidate())
        refs = [item.model_dump(mode="json") for item in entities]
        source_field = "source_logical_entity"

    source = candidate["entities"][0]["sources"][0]
    candidate["entities"][0]["sources"] = [
        {**deepcopy(source), source_field: ref, "source_order": index + 1}
        for index, ref in enumerate(refs[:covered])
    ]
    # One output Entity may consolidate many input sources.
    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()
    issues = validator.validate_coverage(cast(JsonValue, candidate))
    assert (not issues) is accepted
    if issues:
        assert f"{covered}/{total}" in issues[0].message
        assert f"{70 if layer == 'logical' else 60}%" in issues[0].message
        feedback = issues[0].model_dump(mode="json")
        assert sorted(feedback["source_refs"], key=str) == sorted(
            refs[covered:], key=str
        )


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
async def test_retained_and_new_support_counts_once_and_excludes_inactive_or_unselected(
    layer: str,
) -> None:
    factory = logical if layer == "logical" else dimensional
    candidate = cast(dict[str, Any], factory._candidate())
    required = 7 if layer == "logical" else 6
    inputs = (
        factory._object(),
        *(factory._object(f"source_{i}") for i in range(1, 10)),
    )
    refs = [item.model_dump(mode="json") for item in inputs]
    source_field = "source_object" if layer == "logical" else "source_logical_entity"
    entity = candidate["entities"][0]
    source = deepcopy(entity["sources"][0])
    retained = deepcopy(candidate)
    retained["attributes"] = []
    retained_entity = retained["entities"][0]
    retained_entity[f"{layer}_entity_name"] = "Retained"
    retained_entity["sources"] = [
        {**deepcopy(source), source_field: ref, "source_order": i + 1}
        for i, ref in enumerate(
            [
                *refs[: required - 1],
                factory._object("outside_this_run").model_dump(mode="json"),
            ]
        )
    ]
    entity["sources"].append(
        {
            **deepcopy(source),
            source_field: refs[required - 1],
            "source_order": 2,
        }
    )
    duplicate = deepcopy(entity)
    duplicate[f"{layer}_entity_name"] = "SameSupport"
    candidate["entities"].append(duplicate)
    if layer == "logical":
        validator = LogicalCandidateValidator(
            selected_object_keys=cast(Any, inputs),
            selected_attribute_keys=(logical._attribute(),),
            assertion_record_keys=(),
            applied=LogicalSection.model_validate_json(json.dumps(retained)),
        )
    else:
        validator = DimensionalCandidateValidator(
            selected_entity_keys=cast(Any, inputs),
            selected_attribute_keys=(dimensional._attribute(),),
            assertion_record_keys=(),
            applied=DimensionalSection.model_validate_json(json.dumps(retained)),
        )
    assert (await validator.validate(cast(JsonValue, candidate))).issues == ()
    assert validator.validate_coverage(cast(JsonValue, candidate)) == ()
    # Both output Entities name the same input; it counts once. Inactive support
    # and a mapping on an inactive Entity must stop contributing entirely.
    entity["sources"][1]["status"] = "inactive"
    duplicate[f"{layer}_entity_status"] = "inactive"
    issues = validator.validate_coverage(cast(JsonValue, candidate))
    assert len(issues) == 1
    assert f"{required - 1}/10" in issues[0].message


def test_missing_source_feedback_is_bounded_and_preserves_complete_identity() -> None:
    objects = tuple(logical._object(f"source_{i}") for i in range(70))
    validator = LogicalCandidateValidator(
        selected_object_keys=objects,
        selected_attribute_keys=(),
        assertion_record_keys=(),
        applied=None,
    )
    issues = validator.validate_coverage(
        {"submodels": [], "entities": [], "attributes": [], "relationships": []}
    )
    assert "0/70" in issues[0].message
    assert len(issues[0].source_refs) == 50
    assert all(
        set(ref) == set(objects[0].model_dump()) for ref in issues[0].source_refs
    )
    assert "source_" not in repr(issues[0])


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
@pytest.mark.parametrize(
    ("threshold", "covered", "accepted"),
    [
        (1, 1, True),
        (69, 69, True),
        (70, 69, False),
        (99, 99, True),
        (100, 99, False),
        (100, 100, True),
    ],
)
def test_custom_model_threshold_controls_validation_and_prompt(
    layer: str, threshold: int, covered: int, accepted: bool
) -> None:
    factory = logical if layer == "logical" else dimensional
    inputs = tuple(factory._object("source_" + str(index)) for index in range(100))
    candidate = cast(dict[str, Any], factory._candidate())
    candidate["attributes"] = []
    source = candidate["entities"][0]["sources"][0]
    source_field = "source_object" if layer == "logical" else "source_logical_entity"
    candidate["entities"][0]["sources"] = [
        {
            **deepcopy(source),
            source_field: item.model_dump(mode="json"),
            "source_order": index + 1,
        }
        for index, item in enumerate(inputs[:covered])
    ]
    if layer == "logical":
        validator = LogicalCandidateValidator(
            selected_object_keys=cast(Any, inputs),
            selected_attribute_keys=(),
            assertion_record_keys=(),
            applied=None,
            coverage_threshold_percent=threshold,
        )
    else:
        validator = DimensionalCandidateValidator(
            selected_entity_keys=cast(Any, inputs),
            selected_attribute_keys=(),
            assertion_record_keys=(),
            applied=None,
            coverage_threshold_percent=threshold,
        )
    assert (not validator.validate_coverage(cast(JsonValue, candidate))) is accepted
    assert f"target is {threshold}%" in str(validator.output_schema()["description"])
