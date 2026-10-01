"""Attribute findings require exact scope and real nullable booleans."""

from copy import deepcopy

import pytest
from gds_workbench_api.features.metadata_enrichment.service import DescriptionValidator
from pydantic import JsonValue


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        None,
        "missing_flag",
        "missing_attribute",
        "extra_attribute",
        "text_boolean",
        "number_boolean",
    ],
)
async def test_attribute_findings_validate_composite_members_and_unknowns(
    fault: str | None,
) -> None:
    flags: dict[str, JsonValue] = {
        "is_natural_key": True,
        "is_primary_key": True,
        "is_nullable": False,
        "is_pii": None,
    }
    findings: dict[str, JsonValue] = {
        "first": deepcopy(flags),
        "second": deepcopy(flags),
    }
    validator = DescriptionValidator(
        {"first": "account_id", "second": "region_id"}, attributes=True
    )
    if fault == "missing_flag":
        del flags["is_pii"]
        findings["first"] = flags
    elif fault == "missing_attribute":
        del findings["second"]
    elif fault == "extra_attribute":
        findings["outside"] = flags
    elif fault in ("text_boolean", "number_boolean"):
        flags["is_primary_key"] = "true" if fault == "text_boolean" else 1
        findings["first"] = flags
    candidate: JsonValue = {
        "descriptions": {
            "first": "Account identifier within a region.",
            "second": None,
        },
        "attributes": findings,
    }
    result = await validator.validate(candidate)
    assert bool(result.issues) is (fault is not None)
