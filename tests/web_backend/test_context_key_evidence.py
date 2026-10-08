"""Registered key evidence survives unknown or contradictory Model enrichment."""

# Synthetic context only; no provider or database calls.
# pyright: reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest
from gds_workbench_api.features.workflows.authoring.context_contracts import (
    INPUT_EXAMPLES,
    WORKFLOW_INPUTS,
    workflow_input_contracts,
)
from gds_workbench_api.features.workflows.authoring.context_inputs import project_context_inputs
from gds_workbench_api.features.workflows.authoring.context_readers import FrozenContextReaders
from jsonschema import Draft202012Validator

from tests.web_backend.test_logical_executor import _context_bundle


@pytest.mark.parametrize(
    "workflow",
    [name for name, inputs in WORKFLOW_INPUTS.items() if "object_attribute_context" in inputs],
)
@pytest.mark.parametrize("registered", [True, False])
@pytest.mark.parametrize("enriched", ["absent", None, False, True])
@pytest.mark.parametrize("mode", ["inline", "reader"])
def test_registered_and_enriched_natural_keys_remain_distinct(
    workflow: str, registered: bool, enriched: str | bool | None, mode: str
) -> None:
    context = deepcopy(_context_bundle().context.model_dump(mode="json"))
    context["model_workflow"] = workflow
    attribute = context["selected_objects"][0]["attributes"][0]
    attribute["is_natural_key"] = registered
    attribute["enrichment"] = {} if enriched == "absent" else {"is_natural_key": enriched}
    if workflow == "dimensional":
        context["supporting_objects"] = context["selected_objects"]
        context["selected_objects"] = []
    original = deepcopy(context)
    values = project_context_inputs(context)
    if mode == "reader":
        reader = FrozenContextReaders(
            workflow=workflow,
            values=values,
            max_result_bytes=None,
            max_page_records=20,
            max_cumulative_result_bytes=None,
        )
        groups = reader.invoke("get_object_details", {})["items"]
    else:
        groups = values["object_attribute_context"]
    projected = groups[0]["attributes"][0]
    assert projected["registered_is_natural_key"] is registered
    assert projected["is_natural_key"] is (None if enriched == "absent" else enriched)
    schema = workflow_input_contracts(workflow)["object_attribute_context"]["schema"]
    assert cast(Any, Draft202012Validator(schema)).is_valid(groups)
    assert context == original


@pytest.mark.parametrize(
    "workflow",
    [name for name, inputs in WORKFLOW_INPUTS.items() if "object_attribute_context" in inputs],
)
def test_older_frozen_attribute_context_remains_readable(workflow: str) -> None:
    values = deepcopy(INPUT_EXAMPLES[workflow])
    for group in values["object_attribute_context"]:
        for attribute in group["attributes"]:
            attribute.pop("registered_is_natural_key")
    reader = FrozenContextReaders(
        workflow=workflow,
        values=values,
        max_result_bytes=None,
        max_page_records=20,
        max_cumulative_result_bytes=None,
    )
    assert reader.invoke("get_object_details", {})["items"] == values["object_attribute_context"]
