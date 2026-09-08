"""Canonical applied echoes preserve history without authorizing new evidence."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.modeling_records import PhysicalObjectKey
from gds_etl_workbench.domain.snapshots.model import (
    ConceptualSection,
    DimensionalSection,
    LogicalSection,
)
from gds_workbench_api.features.analysis.candidate import (
    AnalysisInferenceCandidateValidator,
)
from gds_workbench_api.features.conceptual.candidate import ConceptualCandidateValidator
from gds_workbench_api.features.dimensional.candidate import (
    DimensionalCandidateValidator,
)
from gds_workbench_api.features.logical.candidate import LogicalCandidateValidator

from tests.web_backend import test_analysis_candidate as analysis
from tests.web_backend import test_conceptual_candidate as conceptual
from tests.web_backend import test_dimensional_candidate as dimensional
from tests.web_backend import test_logical_candidate as logical

FAMILIES = ("analysis", "conceptual", "logical", "dimensional")
CODES = {
    "analysis": "candidate.endpoint_outside_selection",
    "conceptual": "candidate.support_outside_selection",
    "logical": "candidate.source_outside_selection",
    "dimensional": "candidate.source_outside_selection",
}
type CandidateValidator = (
    AnalysisInferenceCandidateValidator
    | ConceptualCandidateValidator
    | LogicalCandidateValidator
    | DimensionalCandidateValidator
)


def _lock_history(value: Any) -> None:
    if isinstance(value, list):
        for item in cast(list[Any], value):
            _lock_history(item)
    elif isinstance(value, dict):
        for key, item in cast(dict[str, Any], value).items():
            if key.endswith("is_locked"):
                value[key] = True
            else:
                _lock_history(item)


def _case(
    family: str, *, selected: bool = False, locked: bool = False, applied: bool = True
) -> tuple[CandidateValidator, dict[str, Any]]:
    if family == "analysis":
        history = analysis._applied(locked=locked)
        candidate = {"relationships": [analysis._candidate(basis=history.relationship_basis)]}
        keys = (
            (
                analysis._attribute(object_name="order_raw", attribute_name="customer_id"),
                analysis._attribute(object_name="customer_raw", attribute_name="customer_id"),
            )
            if selected
            else (analysis._attribute(object_name="new_selected_raw", attribute_name="id"),)
        )
        return AnalysisInferenceCandidateValidator(
            selected_attribute_keys=keys, applied=(history,) if applied else ()
        ), candidate
    if family == "conceptual":
        candidate = {
            "objects": [conceptual._object(supports=[conceptual._support()])],
            "relationships": [],
        }
        history_doc = deepcopy(candidate)
        if locked:
            _lock_history(history_doc)
        history = ConceptualSection.model_validate_json(json.dumps(history_doc), strict=True)
        key = PhysicalObjectKey.model_validate(
            conceptual._physical_object(name="customer_raw" if selected else "new_selected_raw"),
            strict=True,
        )
        return ConceptualCandidateValidator(
            selected_object_keys=(key,),
            assertion_record_keys=(),
            applied=history if applied else None,
        ), candidate
    fixtures = logical if family == "logical" else dimensional
    candidate = fixtures._candidate()
    history_doc = deepcopy(candidate)
    if locked:
        _lock_history(history_doc)
    obj = fixtures._object()
    attr = fixtures._attribute()
    if not selected:
        obj = obj.model_copy(update={"object_name": "new_selected_raw"})
        attr = attr.model_copy(update={"object_name": "new_selected_raw"})
    if family == "logical":
        return LogicalCandidateValidator(
            selected_object_keys=(obj,),
            selected_attribute_keys=(attr,),
            assertion_record_keys=(),
            applied=LogicalSection.model_validate_json(json.dumps(history_doc), strict=True)
            if applied
            else None,
        ), candidate
    return DimensionalCandidateValidator(
        selected_object_keys=(obj,),
        selected_attribute_keys=(attr,),
        assertion_record_keys=(),
        applied=DimensionalSection.model_validate_json(json.dumps(history_doc), strict=True)
        if applied
        else None,
    ), candidate


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("locked", (False, True))
async def test_exact_history_echo_in_current_selection_is_valid_and_no_change(
    family: str, locked: bool
) -> None:
    validator, candidate = _case(family, selected=True, locked=locked)
    assert (await validator.validate(candidate)).issues == ()
    assert validator.parse_validated(candidate) == ()


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("locked", (False, True))
async def test_exact_history_echo_outside_current_selection_is_valid_and_no_change(
    family: str, locked: bool
) -> None:
    validator, candidate = _case(family, locked=locked)
    original = deepcopy(candidate)
    assert (await validator.validate(candidate)).issues == ()
    assert validator.parse_validated(candidate) == ()
    assert candidate == original


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("locked", (False, True))
async def test_omitting_history_outside_current_selection_preserves_it(
    family: str, locked: bool
) -> None:
    validator, candidate = _case(family, locked=locked)
    empty: dict[str, Any] = {key: [] for key in candidate}
    if family == "dimensional":
        # Dimensional requires a nonempty candidate. Echo the unchanged submodel
        # (which has no physical evidence) while omitting historical sources.
        empty["submodels"] = candidate["submodels"]
    assert (await validator.validate(empty)).issues == ()
    assert validator.parse_validated(empty) == ()


@pytest.mark.parametrize("family", FAMILIES)
async def test_genuine_new_outside_selection_evidence_remains_rejected(family: str) -> None:
    validator, candidate = _case(family, applied=False)
    assert {issue.code for issue in (await validator.validate(candidate)).issues} == {CODES[family]}


@pytest.mark.parametrize("family", FAMILIES)
async def test_historical_evidence_copied_to_a_new_owner_still_rejected(family: str) -> None:
    validator, candidate = _case(family)
    if family == "analysis":
        candidate["relationships"][0]["relationship_kind"] = "association"
    elif family == "conceptual":
        candidate["objects"][0]["conceptual_object_name"] = "New concept"
    else:
        candidate["entities"][0][f"{family}_entity_name"] = "New entity"
        candidate["attributes"][0][f"{family}_entity_name"] = "New entity"
    assert CODES[family] in {issue.code for issue in (await validator.validate(candidate)).issues}


@pytest.mark.parametrize("family", FAMILIES)
async def test_editing_history_content_still_requires_selected_evidence(family: str) -> None:
    validator, candidate = _case(family)
    if family == "analysis":
        candidate["relationships"][0]["relationship_basis"] = "Changed evidence."
    elif family == "conceptual":
        candidate["objects"][0]["conceptual_object_definition"] = "Changed definition."
    else:
        candidate["entities"][0][f"{family}_entity_definition"] = "Changed definition."
        candidate["attributes"][0][f"{family}_attribute_definition"] = "Changed definition."
    assert CODES[family] in {issue.code for issue in (await validator.validate(candidate)).issues}


@pytest.mark.parametrize("family", FAMILIES[1:])
@pytest.mark.parametrize("edit", ("rationale", "status", "source"))
async def test_changed_nested_history_is_not_an_echo(family: str, edit: str) -> None:
    validator, candidate = _case(family)
    if family == "conceptual":
        source = candidate["objects"][0]["supports"][0]
        field = "support_reason" if edit == "rationale" else "support_status"
    else:
        source = candidate["entities"][0]["sources"][0]
        field = "rationale" if edit == "rationale" else "status"
    if edit == "source":
        source["source_object"]["object_name"] = "another_outside_object"
    else:
        source[field] = "Changed evidence." if edit == "rationale" else "inactive"
    assert CODES[family] in {issue.code for issue in (await validator.validate(candidate)).issues}


@pytest.mark.parametrize("family", FAMILIES[1:])
@pytest.mark.parametrize("locked", (False, True))
async def test_omitted_nested_history_is_restored_before_echo_comparison(
    family: str, locked: bool
) -> None:
    validator, candidate = _case(family, locked=locked)
    if family == "conceptual":
        candidate["objects"][0]["supports"] = []
    else:
        candidate["entities"][0]["sources"] = []
        candidate["attributes"][0]["sources"] = []
    assert (await validator.validate(candidate)).issues == ()
    assert validator.parse_validated(candidate) == ()


@pytest.mark.parametrize("family", FAMILIES[1:])
async def test_duplicate_historical_owner_is_still_rejected(family: str) -> None:
    validator, candidate = _case(family)
    section = (
        "relationships"
        if family == "analysis"
        else "objects"
        if family == "conceptual"
        else "entities"
    )
    candidate[section].append(deepcopy(candidate[section][0]))
    issues = (await validator.validate(candidate)).issues
    assert any("duplicate" in issue.code for issue in issues)


@pytest.mark.parametrize("family", FAMILIES)
async def test_historical_echo_does_not_grant_agent_lock_authority(family: str) -> None:
    validator, candidate = _case(family)
    section = (
        "relationships"
        if family == "analysis"
        else "objects"
        if family == "conceptual"
        else "entities"
    )
    field = (
        "analysis_result_is_locked"
        if family == "analysis"
        else "conceptual_object_is_locked"
        if family == "conceptual"
        else f"{family}_entity_is_locked"
    )
    candidate[section][0][field] = True
    assert (await validator.validate(candidate)).issues


@pytest.mark.parametrize("family", FAMILIES)
async def test_historical_echo_can_accompany_new_selected_output(family: str) -> None:
    validator, candidate = _case(family)
    if family == "analysis":
        validator = AnalysisInferenceCandidateValidator(
            selected_attribute_keys=(
                analysis._attribute(object_name="new_orders", attribute_name="customer_id"),
                analysis._attribute(object_name="new_customers", attribute_name="id"),
            ),
            applied=(analysis._applied(),),
        )
        new = deepcopy(candidate["relationships"][0])
        new["from_object_name"] = "new_orders"
        new["to_object_name"] = "new_customers"
        new["to_attribute_name"] = "id"
        candidate["relationships"].append(new)
    elif family == "conceptual":
        new = deepcopy(candidate["objects"][0])
        new["conceptual_object_name"] = "New concept"
        new["supports"][0]["source_object"]["object_name"] = "new_selected_raw"
        candidate["objects"].append(new)
    else:
        new_entity = deepcopy(candidate["entities"][0])
        new_entity[f"{family}_entity_name"] = "New customer"
        new_entity["sources"][0]["source_object"]["object_name"] = "new_selected_raw"
        new_attribute = deepcopy(candidate["attributes"][0])
        new_attribute[f"{family}_entity_name"] = "New customer"
        new_attribute["sources"][0]["source_attribute"]["object_name"] = "new_selected_raw"
        candidate["entities"].append(new_entity)
        candidate["attributes"].append(new_attribute)
    original = deepcopy(candidate)
    assert (await validator.validate(candidate)).issues == ()
    changes = validator.parse_validated(candidate)
    assert sum(len(change.records) for change in changes) == (
        2 if family in ("logical", "dimensional") else 1
    )
    assert candidate == original


async def test_exact_duplicate_analysis_history_collapses_to_one_unchanged_record() -> None:
    validator, candidate = _case("analysis")
    candidate["relationships"].append(deepcopy(candidate["relationships"][0]))
    assert (await validator.validate(candidate)).issues == ()
    assert validator.parse_validated(candidate) == ()
