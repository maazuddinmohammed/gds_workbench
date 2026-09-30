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
                "entity": {
                    "entity_type": "logical_entity",
                    "entity_schema_name": "silver",
                    "entity_name": "Customer",
                },
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
        entity_schema_name="silver",
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
    value["object_mappings"][0]["transformation"]["source_objects"][0][
        "object_name"
    ] = "Missing"
    result = page(value)
    assert not result.complete
    assert "mapping_source_object_missing_or_ineligible" in result.issues


@pytest.mark.parametrize("invalid", [None, "table", "column", "system"])
def test_current_default_references_are_checked_without_legacy_field_requirement(
    invalid,
):
    value = context()
    source = value["object_mappings"][0]["transformation"]["source_objects"][0]
    value["object_mappings"][0]["transformation"] = {
        "source_tables": [deepcopy(source)],
        "filter_criteria": None,
        "sample_query": None,
    }
    attribute = value["attribute_mappings"][1]
    attribute["transformation"] = {
        "transformation_logic": "TRIM(Name)",
        "default_record": None,
        "source_columns": [{**source, "attribute_name": "Name"}],
    }
    if invalid == "table":
        value["object_mappings"][0]["transformation"]["source_tables"][0][
            "object_name"
        ] = "Missing"
    elif invalid == "column":
        attribute["transformation"]["source_columns"][0]["attribute_name"] = "Missing"
    elif invalid == "system":
        value["source_systems"].append({"source_system_id": 11, "system_code": "ERP"})
        value["physical_sources"][0]["selected_source_system_id"] = 11
    result = page(value)
    assert result.complete is (invalid is None)
    assert "mapping_document_not_canonical" not in result.issues
    if invalid in {"table", "system"}:
        assert "mapping_source_object_missing_or_ineligible" in result.issues
    if invalid in {"column", "system"}:
        assert "mapping_source_attribute_missing_or_ineligible" in result.issues


@pytest.mark.parametrize("wrong_schema", [False, True])
def test_current_dimensional_reference_uses_exact_logical_identity(wrong_schema):
    value = context()
    value["target"]["modeled_entity_type"] = "dimensional_entity"
    source = value["physical_sources"][0]["object"]
    source.update(
        modeled_entity_type="logical_entity",
        logical_entity_schema_name="silver_crm",
        logical_entity_name="Customer",
    )
    ref = {
        "entity_type": "logical_entity",
        "entity_schema_name": "other" if wrong_schema else "silver_crm",
        "entity_name": "Customer",
    }
    value["object_mappings"][0]["transformation"] = {
        "source_tables": [ref],
        "filter_criteria": None,
        "sample_query": None,
    }
    value["attribute_mappings"][1]["transformation"] = {
        "transformation_logic": "Name",
        "default_record": None,
        "source_columns": [{**ref, "attribute_name": "Name"}],
    }
    result = page(value)
    assert result.complete is not wrong_schema
    if wrong_schema:
        assert "mapping_source_attribute_missing_or_ineligible" in result.issues


def test_custom_mapping_document_does_not_require_default_or_legacy_keys():
    value = context()
    value["object_mappings"][0].update(
        output_template_code="custom",
        transformation={
            "custom_business_id": 31,
            "instructions": "Read the approved source.",
        },
    )
    assert page(value).complete


@pytest.mark.parametrize("legacy_names", [False, True])
def test_custom_template_controls_meaning_of_reference_named_fields(legacy_names):
    value = context()
    object_field = "source_objects" if legacy_names else "source_tables"
    attribute_field = "source_attributes" if legacy_names else "source_columns"
    value["object_mappings"][0].update(
        output_template_code="custom.source_labels",
        transformation={object_field: ["customer_source"]},
    )
    for row in value["attribute_mappings"]:
        row.update(
            output_template_code="custom.column_labels",
            transformation={attribute_field: ["external_label"]},
        )
    assert page(value).complete


def test_named_default_template_still_rejects_invalid_current_references():
    value = context()
    value["object_mappings"][0].update(
        output_template_code="mapping_logical_object_default",
        transformation={"source_tables": ["customer_source"]},
    )
    value["attribute_mappings"][1].update(
        output_template_code="mapping_logical_attribute_default",
        transformation={"source_columns": ["external_label"]},
    )
    result = page(value)
    assert not result.complete
    assert "mapping_source_object_missing_or_ineligible" in result.issues
    assert "mapping_source_attribute_missing_or_ineligible" in result.issues


@pytest.mark.parametrize("invalid", [None, "table", "column"])
def test_historical_default_templates_retain_legacy_reference_checks(invalid):
    value = context()
    value["object_mappings"][0]["output_template_code"] = "mapping_object_default"
    reference = deepcopy(
        value["object_mappings"][0]["transformation"]["source_objects"][0]
    )
    for row in value["attribute_mappings"]:
        row["output_template_code"] = "mapping_attribute_default"
    value["attribute_mappings"][1]["transformation"]["source_attributes"] = [
        {**reference, "attribute_name": "Name"}
    ]
    if invalid == "table":
        value["object_mappings"][0]["transformation"]["source_objects"][0][
            "object_name"
        ] = "Missing"
    elif invalid == "column":
        value["attribute_mappings"][1]["transformation"]["source_attributes"][0][
            "attribute_name"
        ] = "Missing"
    result = page(value)
    assert result.complete is (invalid is None)
    if invalid is not None:
        assert (
            f"mapping_source_{'object' if invalid == 'table' else 'attribute'}_missing_or_ineligible"
            in result.issues
        )


@pytest.mark.parametrize("missing_object", [False, True])
def test_partial_mapping_pages_preserve_blank_documents_and_report_incomplete(
    missing_object,
):
    value = context()
    value["attribute_mappings"][0]["transformation"] = None
    if missing_object:
        value["object_mappings"][0]["transformation"] = None
    original = deepcopy(value)
    result = page(value)
    assert not result.complete
    assert "mapping_document_not_canonical" in result.issues
    assert result.records[0]["transformation"] is None
    assert value == original
    following = page(value, cursor=result.next_cursor, digest=result.context_digest)
    assert not following.complete
    assert following.context_digest == result.context_digest
    assert (
        following.records[0]["transformation"]
        == (value["attribute_mappings"][1]["transformation"])
    )


def test_missing_attribute_rows_report_incomplete_coverage_without_inventing_rules():
    value = context()
    value["attribute_mappings"] = value["attribute_mappings"][:1]
    result = page(value)
    assert not result.complete
    assert "mapping_attribute_coverage_incomplete" in result.issues
    assert len(result.records) == 1
    assert result.next_cursor is None


def test_mapping_population_and_source_system_value_survive_id_stripping():
    projected = project_mapping_inputs(context())
    assert projected["source_systems"] == [
        {"system_code": "CRM", "source_system_value": 10}
    ]
    assert "source_tenant_id" not in projected["target_metadata"]
    assert [
        row["population"] for row in projected["target_metadata"]["attributes"]
    ] == [
        "database",
        "mapping",
        "framework",
    ]


def test_legacy_mapping_templates_are_explicitly_unavailable():
    projected = project_mapping_inputs(context())
    assert projected["mapping_templates"] == []
    assert projected["object_transformations"][0]["output_template_code"] is None
    assert all(
        row["output_template_code"] is None
        for row in projected["attribute_transformations"]
    )


def test_template_projection_preserves_custom_documents_examples_and_saved_inactive_schema():
    value = context()
    value["object_mappings"][0]["output_template_code"] = "custom.object"
    value["attribute_mappings"][0]["output_template_code"] = "custom.attribute"
    value["object_mappings"][0]["transformation"]["business_id"] = {"source_id": 42}
    value["attribute_mappings"][0]["transformation"]["rule_id"] = {"value_id": 7}
    value["mapping_templates"] = [
        {
            "output_template_id": position,
            "code": code,
            "is_active": False,
            "fields": [
                {"name": "rule_id", "example": {"business_id": {"source_id": 42}}}
            ],
        }
        for position, code in enumerate(
            ("custom.object", "custom.attribute", "unused"), start=1
        )
    ]
    original = deepcopy(value)
    projected = project_mapping_inputs(value)
    assert [item["code"] for item in projected["mapping_templates"]] == [
        "custom.object",
        "custom.attribute",
    ]
    assert projected["mapping_templates"][0]["is_active"] is False
    assert projected["mapping_templates"][0]["fields"][0]["example"] == {
        "business_id": {"source_id": 42}
    }
    assert "output_template_id" not in projected["mapping_templates"][0]
    assert projected["object_transformations"][0]["transformation"]["business_id"] == {
        "source_id": 42
    }
    assert projected["attribute_transformations"][0]["transformation"]["rule_id"] == {
        "value_id": 7
    }
    assert value == original


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


@pytest.mark.parametrize("reference_part", ["schema", "entity", "attribute", None])
def test_logical_mapping_resolves_schema_qualified_peer_lookup(
    reference_part: str | None,
):
    value = context()
    logical_key = {
        "logical_entity_schema_name": "reference",
        "logical_entity_name": "Country",
    }
    lookup = {
        **value["target"],
        "object_schema": "reference",
        "object_name": "Country",
        **logical_key,
        "attributes": [{"attribute_name": "CountryID", "is_active": True}],
    }
    value["physical_sources"].append(
        {"selected_source_system_id": 10, "object": lookup}
    )
    entity_ref = dict(logical_key)
    attribute_ref = {**logical_key, "logical_attribute_name": "CountryID"}
    if reference_part == "schema":
        entity_ref["logical_entity_schema_name"] = "wrong"
    elif reference_part == "entity":
        entity_ref["logical_entity_name"] = "Missing"
    elif reference_part == "attribute":
        attribute_ref["logical_attribute_name"] = "Missing"
    value["object_mappings"][0]["transformation"]["source_logical_entities"] = [
        entity_ref
    ]
    value["attribute_mappings"][0]["transformation"]["source_logical_attributes"] = [
        attribute_ref
    ]
    result = page(value)
    assert result.complete is (reference_part is None)
    if reference_part is not None:
        assert any(issue.endswith("missing_or_ineligible") for issue in result.issues)


@pytest.mark.parametrize("wrong_schema", [False, True])
def test_dimensional_mapping_resolves_gold_peer_lookup_without_registration(
    wrong_schema: bool,
):
    value = context()
    value["target"].update(
        modeled_entity_type="dimensional_entity", object_schema="gold"
    )
    entity_key = {
        "dimensional_entity_schema_name": "gold_reference",
        "dimensional_entity_name": "Country",
    }
    value["physical_sources"] = [
        {
            "selected_source_system_id": 10,
            "object": {
                **value["target"],
                **entity_key,
                "object_schema": "gold_reference",
                "object_name": "Country",
                "attributes": [{"attribute_name": "CountryKey", "is_active": True}],
            },
        }
    ]
    value["object_mappings"][0]["transformation"] = {
        "source_objects": None,
        "source_logical_entities": None,
        "source_dimensional_entities": [entity_key],
        "steps": ["Join Country by business key."],
    }
    value["attribute_mappings"][0]["transformation"][
        "source_dimensional_attributes"
    ] = [
        {
            **entity_key,
            "dimensional_entity_schema_name": "wrong"
            if wrong_schema
            else "gold_reference",
            "dimensional_attribute_name": "CountryKey",
        }
    ]
    result = page(value)
    assert result.complete is not wrong_schema
    if wrong_schema:
        assert "mapping_source_attribute_missing_or_ineligible" in result.issues
