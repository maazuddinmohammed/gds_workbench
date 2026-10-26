"""Atlas's local technical-column projection must equal the web backend's projection.

The plugin cannot import the backend, so `workbench/policy-projection.js` ports the
deterministic rules. These tests run the real Python projections and the port on the
same candidates and require identical records or the same rejection.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.domain.modeling_records import (
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    LogicalAttributeRecord,
    LogicalEntityRecord,
)
from gds_etl_workbench.domain.snapshots.project import DimensionalSection, LogicalSection
from gds_workbench_api.features.dimensional.policy import project_dimensional_gold_policy
from gds_workbench_api.features.logical.policy import project_logical_audit_policy
from gds_workbench_api.features.workflows.authoring.gold_policy import effective_gold_templates

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "atlas/atlas-plugin/workbench/policy-projection.js"
SOURCE = {
    "support_source_type": "attribute",
    "source_attribute": {
        "tenant_code": "GDS",
        "system_code": "CRM",
        "connection_code": "MAIN",
        "object_schema": "bronze",
        "object_name": "customer",
        "attribute_name": "code",
    },
    "rationale": "Customer code from CRM.",
    "is_active": True,
    "is_locked": False,
}


def _load[
    T: (
        LogicalEntityRecord,
        LogicalAttributeRecord,
        DimensionalEntityRecord,
        DimensionalAttributeRecord,
    )
](model: type[T], value: Any) -> T:
    return model.model_validate_json(json.dumps(value))


def _js(function: str, *arguments: Any) -> Any:
    script = (
        f"const p = require({json.dumps(str(MODULE))});"
        "const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
        f"try {{ process.stdout.write(JSON.stringify({{ok: p.{function}(...input)}})); }}"
        "catch (error) { process.stdout.write(JSON.stringify({error: error.message})); }"
    )
    completed = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(arguments),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def _logical_entity(name: str, *, is_active: bool = True) -> dict[str, Any]:
    return _load(
        LogicalEntityRecord,
        {
            "logical_entity_schema_name": "silver",
            "logical_entity_name": name,
            "logical_entity_definition": f"One {name}.",
            "logical_entity_type": "core",
            "logical_entity_grain": f"One {name}",
            "logical_entity_dependency_order": 0,
            "logical_entity_is_active": is_active,
            "logical_entity_is_locked": False,
            "sources": [],
        },
    ).model_dump(mode="json")


def _logical_attribute(entity: str, name: str, ordinal: int, **changes: Any) -> dict[str, Any]:
    record = {
        "logical_entity_schema_name": "silver",
        "logical_entity_name": entity,
        "logical_attribute_name": name,
        "logical_attribute_definition": f"{name} of {entity}.",
        "logical_attribute_data_type": "STRING",
        "logical_attribute_is_nullable": True,
        "logical_attribute_is_natural_key": False,
        "logical_attribute_is_surrogate_key": False,
        "logical_attribute_ordinal_position": ordinal,
        "logical_attribute_is_audit_column": False,
        "logical_attribute_is_active": True,
        "logical_attribute_is_locked": False,
        "sources": [],
        **changes,
    }
    return _load(LogicalAttributeRecord, record).model_dump(mode="json")


def _python_logical(
    candidate: dict[str, list[dict[str, Any]]],
    baseline: dict[str, list[dict[str, Any]]],
    template: dict[str, Any] | None,
) -> dict[str, Any]:
    changes = tuple(
        StageProjectChange(dataset=f"logical_{name}", records=records)
        for name, records in (
            ("entity", candidate["entities"]),
            ("attribute", candidate["attributes"]),
        )
        if records
    )
    applied = LogicalSection(
        entities=tuple(_load(LogicalEntityRecord, row) for row in baseline["entities"]),
        attributes=tuple(_load(LogicalAttributeRecord, row) for row in baseline["attributes"]),
        relationships=(),
    )
    try:
        projected = project_logical_audit_policy(
            changes=changes, applied=applied, raw_template=template
        )
    except Exception as error:
        return {"error": str(error)}
    rows = next((item.records for item in projected if item.dataset == "logical_attribute"), [])
    return {"ok": [_load(LogicalAttributeRecord, row).model_dump(mode="json") for row in rows]}


LOGICAL_CASES: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]] = {
    "new entity gets surrogate, order and default audit block": (
        {
            "entities": [_logical_entity("Customer")],
            "attributes": [
                _logical_attribute("Customer", "CustomerName", 3),
                _logical_attribute(
                    "Customer",
                    "CustomerCode",
                    1,
                    logical_attribute_is_natural_key=True,
                    logical_attribute_is_nullable=False,
                    sources=[SOURCE],
                ),
            ],
        },
        {"entities": [], "attributes": []},
        None,
    ),
    "existing entity keeps layout and gains a custom audit block": (
        {"entities": [], "attributes": [_logical_attribute("Order", "OrderStatus", 3)]},
        {
            "entities": [_logical_entity("Order")],
            "attributes": [
                _logical_attribute("Order", "OrderNumber", 1),
                _logical_attribute(
                    "Order",
                    "SourceSystemID",
                    2,
                    logical_attribute_data_type="BIGINT",
                    logical_attribute_is_audit_column=True,
                    sources=[SOURCE],
                ),
            ],
        },
        {
            "schema_version": "1.0",
            "columns": [
                {
                    "semantic_name": "SourceSystemID",
                    "data_type": "BIGINT",
                    "nullable": True,
                    "definition": "Origin.",
                },
                {
                    "semantic_name": "LoadedAt",
                    "data_type": "TIMESTAMP",
                    "nullable": False,
                    "definition": None,
                },
            ],
        },
    ),
    "inactive entities are skipped": (
        {"entities": [_logical_entity("Retired", is_active=False)], "attributes": []},
        {"entities": [], "attributes": []},
        None,
    ),
    "generated key name collides with a business attribute": (
        {
            "entities": [_logical_entity("Customer")],
            "attributes": [_logical_attribute("Customer", "CustomerID", 1)],
        },
        {"entities": [], "attributes": []},
        None,
    ),
    "audit column with a conflicting type is rejected": (
        {
            "entities": [_logical_entity("Customer")],
            "attributes": [
                _logical_attribute(
                    "Customer",
                    "HashKey",
                    2,
                    logical_attribute_is_audit_column=True,
                    logical_attribute_data_type="BIGINT",
                )
            ],
        },
        {"entities": [], "attributes": []},
        None,
    ),
}


@pytest.mark.parametrize("case", list(LOGICAL_CASES))
def test_logical_projection_matches_the_backend(case: str) -> None:
    candidate, baseline, template = LOGICAL_CASES[case]
    expected = _python_logical(candidate, baseline, template)
    actual = _js("projectLogical", candidate, baseline, template)
    assert actual == expected
    if case == "new entity gets surrogate, order and default audit block":
        ordinals = {
            row["logical_attribute_name"]: row["logical_attribute_ordinal_position"]
            for row in actual["ok"]
        }
        assert (ordinals["CustomerID"], ordinals["CustomerCode"], ordinals["SourceSystemID"]) == (
            1,
            2,
            4,
        )


def _dimensional_entity(name: str, kind: str = "dimension") -> dict[str, Any]:
    return _load(
        DimensionalEntityRecord,
        {
            "dimensional_entity_schema_name": "gold",
            "dimensional_entity_name": name,
            "dimensional_entity_definition": f"{name} analysis.",
            "dimensional_entity_type": kind,
            "dimensional_fact_type": "transaction" if kind == "fact" else None,
            "dimensional_entity_grain_definition": f"One {name}",
            "dimensional_entity_dependency_order": 0,
            "dimensional_entity_is_active": True,
            "dimensional_entity_is_locked": False,
            "sources": [],
        },
    ).model_dump(mode="json")


def _dimensional_attribute(entity: str, name: str, ordinal: int, **changes: Any) -> dict[str, Any]:
    record = {
        "dimensional_entity_schema_name": "gold",
        "dimensional_entity_name": entity,
        "dimensional_attribute_name": name,
        "dimensional_attribute_definition": f"{name} of {entity}.",
        "dimensional_attribute_data_type": "STRING",
        "dimensional_attribute_is_nullable": True,
        "dimensional_attribute_ordinal_position": ordinal,
        "dimensional_attribute_is_natural_key": False,
        "dimensional_attribute_is_surrogate_key": False,
        "dimensional_attribute_is_audit_column": False,
        "dimensional_attribute_is_active": True,
        "dimensional_attribute_is_locked": False,
        "sources": [],
        **changes,
    }
    return _load(DimensionalAttributeRecord, record).model_dump(mode="json")


def _python_dimensional(
    candidate: dict[str, list[dict[str, Any]]],
    baseline: dict[str, list[dict[str, Any]]],
    technical: dict[str, Any],
    audit: dict[str, Any],
    scd: str | None,
) -> dict[str, Any]:
    changes = tuple(
        StageProjectChange(dataset=f"dimensional_{name}", records=records)
        for name, records in (
            ("entity", candidate["entities"]),
            ("attribute", candidate["attributes"]),
        )
        if records
    )
    applied = DimensionalSection(
        entities=tuple(_load(DimensionalEntityRecord, row) for row in baseline["entities"]),
        attributes=tuple(_load(DimensionalAttributeRecord, row) for row in baseline["attributes"]),
        relationships=(),
    )
    try:
        projected = project_dimensional_gold_policy(
            changes=changes,
            applied=applied,
            raw_technical_template=technical,
            raw_audit_template=audit,
            scd_type=scd,  # pyright: ignore[reportArgumentType]
        )
    except Exception as error:
        return {"error": str(error)}
    rows = next((item.records for item in projected if item.dataset == "dimensional_attribute"), [])
    return {"ok": [_load(DimensionalAttributeRecord, row).model_dump(mode="json") for row in rows]}


DIMENSIONAL_CASES: dict[str, tuple[dict[str, Any], dict[str, Any], str | None]] = {
    "type 2 dimension gets key, history after SourceSystemID and audit block": (
        {
            "entities": [_dimensional_entity("Customer")],
            "attributes": [
                _dimensional_attribute("Customer", "CustomerName", 2),
                _dimensional_attribute(
                    "Customer",
                    "CustomerCode",
                    1,
                    dimensional_attribute_is_natural_key=True,
                    dimensional_attribute_is_nullable=False,
                ),
            ],
        },
        {"entities": [], "attributes": []},
        "type_2",
    ),
    "type 1 dimension has no history fields": (
        {
            "entities": [_dimensional_entity("Product")],
            "attributes": [_dimensional_attribute("Product", "ProductName", 1)],
        },
        {"entities": [], "attributes": []},
        "type_1",
    ),
    "new fact gets an own key but no history": (
        {
            "entities": [_dimensional_entity("Sales", "fact")],
            "attributes": [
                _dimensional_attribute(
                    "Sales", "Amount", 1, dimensional_attribute_data_type="DECIMAL(18,2)"
                )
            ],
        },
        {"entities": [], "attributes": []},
        "type_2",
    ),
    "existing dimension keeps its key ordinal": (
        {"entities": [], "attributes": [_dimensional_attribute("Store", "StoreCity", 3)]},
        {
            "entities": [_dimensional_entity("Store")],
            "attributes": [
                _dimensional_attribute("Store", "StoreName", 1),
                _dimensional_attribute(
                    "Store",
                    "StoreKey",
                    2,
                    dimensional_attribute_data_type="BIGINT",
                    dimensional_attribute_is_nullable=False,
                    dimensional_attribute_is_surrogate_key=True,
                ),
            ],
        },
        None,
    ),
    "natural key cannot become a policy column": (
        {
            "entities": [_dimensional_entity("Customer")],
            "attributes": [
                _dimensional_attribute(
                    "Customer",
                    "CustomerKey",
                    1,
                    dimensional_attribute_data_type="BIGINT",
                    dimensional_attribute_is_nullable=False,
                    dimensional_attribute_is_natural_key=True,
                )
            ],
        },
        {"entities": [], "attributes": []},
        None,
    ),
}


@pytest.mark.parametrize("case", list(DIMENSIONAL_CASES))
def test_dimensional_projection_matches_the_backend(case: str) -> None:
    candidate, baseline, scd = DIMENSIONAL_CASES[case]
    technical, audit = effective_gold_templates(None, None)
    expected = _python_dimensional(candidate, baseline, technical, audit, scd)
    actual = _js("projectDimensional", candidate, baseline, technical, audit, scd)
    assert actual == expected
    if case.startswith("type 2"):
        names = [
            row["dimensional_attribute_name"]
            for row in sorted(
                actual["ok"], key=lambda row: row["dimensional_attribute_ordinal_position"]
            )
        ]
        assert names[:6] == [
            "CustomerKey",
            "CustomerCode",
            "CustomerName",
            "SourceSystemID",
            "IsCurrentRecord",
            "RecordStartTime",
        ]


def test_effective_gold_templates_match_the_backend() -> None:
    combined = {
        "schema_version": "1.0",
        "columns": [
            {"semantic_name": "LoadID", "data_type": "BIGINT", "nullable": True, "definition": None}
        ],
        "type_2": None,
    }
    for technical, audit in ((None, None), (None, combined)):
        expected = list(effective_gold_templates(technical, audit))
        assert _js("effectiveGoldTemplates", technical, audit) == {"ok": expected}
