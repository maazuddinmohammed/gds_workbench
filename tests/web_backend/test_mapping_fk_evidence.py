"""Use the branch's registered FK evidence across a Bronze bridge in both modes."""

import json
from typing import Any

import pytest
from atlas_platform.features.workflows.authoring.context import (
    AgentContextToolRequestError,
)
from atlas_platform.features.workflows.authoring.downstream_inputs import (
    build_downstream_readers,
    compact_mapping_basis,
)
from pydantic import JsonValue


def test_two_hop_fk_role_evidence_is_scoped_pageable_and_matches_one_shot() -> None:
    base = {
        "tenant_code": "t",
        "system_code": "gds",
        "connection_code": "bronze",
        "object_schema": "erp",
    }

    def obj(name: str) -> dict[str, str]:
        return {**base, "object_name": name}

    def link(a: str, a_key: str, b: str, b_key: str) -> dict[str, Any]:
        return {
            **{f"from_{k}": v for k, v in obj(a).items()},
            **{f"to_{k}": v for k, v in obj(b).items()},
            "from_attribute_name": a_key,
            "to_attribute_name": b_key,
            "validation_result": "supported",
        }

    def source(name: str, cols: list[str]) -> dict[str, Any]:
        return {
            "role": "support" if name == "orders" else "candidate",
            "rationale": None,
            "object": {
                **obj(name),
                "batch_attribute_name": "LoadID",
                "attributes": [
                    {"attribute_name": col, "attribute_data_type": "STRING"}
                    for col in cols
                ],
            },
        }

    records: list[dict[str, Any]] = []
    for rank, (name, operand) in enumerate(
        (("BillingKey", "bill_code"), ("ShippingKey", "ship_code"))
    ):
        records.extend(
            (
                {
                    "evidence_type": "target_relationship",
                    "record": {
                        "from_logical_entity_schema_name": "silver",
                        "from_logical_entity_name": "Order",
                        "from_logical_attribute_name": name,
                        "to_logical_entity_schema_name": "silver",
                        "to_logical_entity_name": "Customer",
                        "to_logical_attribute_name": "CustomerKey",
                        "logical_relationship_basis": f"role {rank}",
                    },
                },
                {
                    "evidence_type": "target_attribute_lineage",
                    "record": {
                        "modeled_attribute_name": name,
                        "sources": [
                            {
                                "source_attribute": {
                                    **obj("orders"),
                                    "attribute_name": operand,
                                },
                                "rationale": "Use the role-specific code.",
                            }
                        ],
                    },
                },
            )
        )
    records.append(
        {
            "evidence_type": "source_logical_attribute",
            "record": {
                "logical_entity_schema_name": "silver",
                "logical_entity_name": "Customer",
                "logical_attribute_name": "CustomerCode",
                "logical_attribute_is_natural_key": True,
                "sources": [
                    {
                        "source_attribute": {
                            **obj("customer"),
                            "attribute_name": "customer_no",
                        }
                    }
                ],
            },
        }
    )
    records.extend(
        {"evidence_type": "analysis_relationship", "record": edge}
        for edge in (
            link("orders", "bill_code", "bridge", "ext_code"),
            link("bridge", "resolved_code", "customer", "customer_no"),
            link("orders", "bill_code", "outside", "code"),
        )
    )
    values: dict[str, Any] = {
        "target_metadata": {
            "entity_type": "logical_entity",
            "entity_schema_name": "silver",
            "entity_name": "Order",
            "attributes": [
                {"attribute_name": name, "ordinal_position": i}
                for i, name in enumerate(("BillingKey", "ShippingKey"), 1)
            ],
        },
        "existing_mapping": [
            {
                "attribute_mappings": [
                    {
                        "modeled_attribute_name": "BillingKey",
                        "transformation_document": {"transformation_logic": "bill.CustomerKey"},
                    }
                ],
                "object_dependency_order": 1,
                "transformation_document": None,
            }
        ],
        "readiness": {
            "headers": [
                {
                    "attribute_actions": [
                        {"modeled_attribute_name": "BillingKey", "action": "preserve"},
                        {"modeled_attribute_name": "ShippingKey", "action": "author"},
                    ]
                }
            ]
        },
        "source_evidence": [
            source("orders", ["bill_code", "ship_code"]),
            source("bridge", ["ext_code", "resolved_code", "private_note"]),
            source("customer", ["customer_no"]),
        ],
        "mapping_support_records": records,
    }
    inline = compact_mapping_basis(values)
    # An active modeled parent is already useful before its Mapping exists.
    assert len([c for c in inline if c["kind"] == "fk_role"]) == 2
    wide_rule = "preserve registered customer code " * 25
    records.append(
        {
            "evidence_type": "source_attribute_mapping",
            "record": {
                "modeled_entity_type": "logical_entity",
                "modeled_entity_schema_name": "silver",
                "modeled_entity_name": "Customer",
                "modeled_attribute_name": "CustomerCode",
                "source_system_code": "erp",
                "attribute_mapping_transformation_document": {"rule": wide_rule},
            },
        }
    )
    inline = compact_mapping_basis(values)
    assert json.dumps(inline).count(wide_rule) == 1
    reader = build_downstream_readers(
        "mapping",
        {**values, "mapping_basis": inline},
        max_result_bytes=2_000,
        max_page_records=1,
        max_cumulative_result_bytes=None,
    )

    def read(tool: str, arguments: dict[str, JsonValue]) -> list[dict[str, Any]]:
        page = reader.invoke(tool, arguments)
        items = list(page["items"])
        while page["next_cursor"]:
            page = reader.invoke(tool, {"cursor": page["next_cursor"]})
            items.extend(page["items"])
        return items

    assert json.dumps(read("get_mapping_basis", {})).count(wide_rule) == 1
    reader.defer_fk_details = True
    core = read("get_mapping_basis", {})
    fields = {c["record"]["attribute_name"]: c["record"] for c in core if c["kind"] == "field"}
    assert fields["BillingKey"]["action"] == "preserve"
    assert fields["BillingKey"]["has_saved_rule"] is True
    assert "saved" not in fields["BillingKey"]
    assert fields["ShippingKey"]["has_saved_rule"] is False
    assert [c["kind"] for c in core if c["kind"].startswith("fk_")] == [
        "fk_role",
        "fk_role",
    ]
    assert wide_rule not in json.dumps(core)
    both_roles = read(
        "get_mapping_fk_evidence",
        {"target_attribute_names": ["BillingKey", "ShippingKey"]},
    )
    assert json.dumps(both_roles).count(wide_rule) == 1
    selected = read(
        "get_mapping_fk_evidence", {"target_attribute_names": ["BillingKey"]}
    )
    assert [c for c in selected if c["kind"].startswith("fk_")] == [
        c
        for c in inline
        if c["kind"].startswith("fk_")
        and c["record"]["target_attribute_name"] == "BillingKey"
    ]
    assert [
        c["record"]["attribute_name"] for c in selected if c["kind"] == "field"
    ] == ["BillingKey"]
    assert not any(
        c["kind"] == "fk_source_link"
        and c["record"]["target_attribute_name"] == "ShippingKey"
        for c in inline
    )
    assert len([c for c in inline if c["kind"] == "source_logical_attribute"]) == 1
    assert all(
        c["record"]["parent_key_names"] == ["CustomerCode"]
        for c in inline
        if c["kind"] == "fk_role"
    )
    assert [
        (c["record"]["from"]["attribute_name"], c["record"]["to"]["attribute_name"])
        for c in selected
        if c["kind"] == "fk_source_link"
    ] == [
        ("bill_code", "ext_code"),
        ("resolved_code", "customer_no"),
    ]
    with pytest.raises(AgentContextToolRequestError):
        reader.invoke(
            "get_mapping_fk_evidence", {"target_attribute_names": ["OutsideFK"]}
        )
