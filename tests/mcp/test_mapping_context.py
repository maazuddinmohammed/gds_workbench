"""Mapping consumer integrity, pagination and metadata drift without database access."""

from copy import deepcopy

import pytest
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.application.mapping_context import project_mapping_inputs
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.tools.modeling.read_mapping_context import mapping_context_page


def context():
    target = {
        "tenant_code": "GDS",
        "system_code": "GDS",
        "connection_code": "Lake",
        "object_schema": "silver",
        "object_name": "Customer",
        "zone_code": "silver",
        "tenant_catalog": "demo",
        "source_tenant_id": 1,
        "audit_columns_template": {"columns": [{"semantic_name": "HashKey"}]},
        "attributes": [
            {"attribute_name": name, "is_active": True, "is_surrogate_key": generated}
            for name, generated in (
                ("CustomerID", True),
                ("Name", False),
                ("HashKey", False),
            )
        ],
    }
    source = {
        **target,
        "object_schema": "bronze",
        "object_name": "Customer",
        "zone_code": "bronze",
        "attributes": [{"attribute_name": "Name", "is_active": True}],
    }
    ref = {
        key: source[key]
        for key in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        )
    }
    return {
        "target": target,
        "physical_sources": [{"selected_source_system_id": 10, "object": source}],
        "source_systems": [{"source_system_id": 10, "system_code": "CRM"}],
        "object_mappings": [
            {
                "mapping_object_id": 20,
                "source_system_id": 10,
                "entity": {"entity_type": "logical_entity", "entity_name": "Customer"},
                "transformation": {
                    "source_objects": [ref],
                    "steps": ["Read Customer."],
                },
            }
        ],
        "attribute_mappings": [
            {
                "mapping_object_id": 20,
                "source_system_id": 10,
                "target_attribute_name": name,
                "transformation": {
                    "source_attributes": None,
                    "transformation": "Generated.",
                },
            }
            for name in ("CustomerID", "Name", "HashKey")
        ],
    }


def page(value, **options):
    return mapping_context_page(
        context=value,
        model_id=1,
        model_revision=3,
        entity_type="logical_entity",
        entity_name="Customer",
        component="attribute_transformations",
        source_system_codes=[],
        page_size=1,
        cursor=options.get("cursor"),
        expected_context_digest=options.get("digest"),
        cursors=CursorCodec(b"test-signing-key"),
    )


def test_mapping_pages_are_bound_to_metadata_digest_and_complete_applied_revision():
    value = context()
    first = page(value)
    assert first.complete and not first.issues
    assert first.next_cursor
    second = page(value, cursor=first.next_cursor, digest=first.context_digest)
    assert second.records[0]["target_attribute_name"] == "Name"
    changed = deepcopy(value)
    changed["target"]["attributes"][0]["is_surrogate_key"] = False
    with pytest.raises(InvalidRequestError, match="changed"):
        page(changed, digest=first.context_digest)
    with pytest.raises(InvalidRequestError, match="cursor"):
        page(changed, cursor=first.next_cursor)


def test_mapping_reports_missing_references_without_inventing_context():
    value = context()
    value["object_mappings"][0]["transformation"]["source_objects"][0]["object_name"] = "Missing"
    result = page(value)
    assert not result.complete
    assert "mapping_source_object_missing_or_ineligible" in result.issues


def test_mapping_population_and_source_system_value_survive_id_stripping():
    projected = project_mapping_inputs(context())
    assert projected["source_systems"] == [{"system_code": "CRM", "source_system_value": 10}]
    assert "source_tenant_id" not in projected["target_metadata"]
    assert [row["population"] for row in projected["target_metadata"]["attributes"]] == [
        "database",
        "mapping",
        "framework",
    ]


def test_mapping_reports_missing_physical_source_columns_and_inactive_batch():
    value = context()
    source = value["physical_sources"][0]["object"]
    source.update(
        zone_code="source",
        foreign_catalog="foreign",
        fc_object_schema="remote",
        fc_object_name="Customer",
        batch_attribute_name="Batch",
    )
    source["attributes"].append({"attribute_name": "Batch", "is_active": False})
    result = page(value)
    assert not result.complete
    assert "query_attribute_coordinates_missing" in result.issues
    assert "batch_attribute_missing" in result.issues
