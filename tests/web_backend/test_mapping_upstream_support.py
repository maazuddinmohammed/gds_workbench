"""Gold keeps applied Logical and scoped physical evidence without widening inputs."""

from copy import deepcopy
from typing import Any, cast

from gds_etl_workbench.domain.snapshots.model import model_snapshot_records
from gds_workbench_api.features.mapping.execution_context import (
    MappingExecutionContextLimits,
    build_mapping_execution_context,
)
from gds_workbench_api.features.mapping.preparation_contracts import (
    MappingModeledEntity,
    MappingOutputTemplate,
)
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    DownstreamContextReaders,
    downstream_input_contracts,
)
from jsonschema import Draft202012Validator

from tests.mcp.model_test_fixtures import (
    complete_model_graph,
    logical_relationship,
    snapshot_from_graph,
)
from tests.web_backend.mapping_fixtures import mapping_preparation


def test_gold_support_records_keep_upstream_documents_lineage_and_page_completely() -> (
    None
):
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    assert preparation.snapshot is not None
    graph = {
        name: [row.model_dump(mode="json") for row in rows]
        for name, rows in model_snapshot_records(preparation.snapshot).items()
    }
    physical_source = mapping_preparation().context.sources[0]
    physical = physical_source.object
    first = physical.attributes[0]
    physical = physical.model_copy(
        update={
            "object_description": "Enriched customer object.",
            "attributes": (
                first.model_copy(
                    update={"attribute_description": "Enriched customer identifier."}
                ),
                first.model_copy(
                    update={
                        "attribute_id": 802,
                        "attribute_name": "region_id",
                        "attribute_ordinal_position": 2,
                        "attribute_description": "Enriched region reference.",
                    }
                ),
                first.model_copy(
                    update={
                        "attribute_id": 803,
                        "attribute_name": "unused",
                        "attribute_ordinal_position": 3,
                        "attribute_description": "Unrelated field.",
                    }
                ),
            ),
        }
    )
    physical_source = physical_source.model_copy(update={"object": physical})
    first_source = preparation.context.sources[0]
    assert isinstance(first_source.object, MappingModeledEntity)
    peer = first_source.model_copy(
        update={
            "object": first_source.object.model_copy(
                update={
                    "entity_id": 402,
                    "entity_name": "RegionInput",
                    "attributes": (
                        first_source.object.attributes[0].model_copy(
                            update={"attribute_id": 802, "attribute_name": "region_id"}
                        ),
                    ),
                }
            )
        }
    )
    graph["logical_entity"].append(
        {**deepcopy(graph["logical_entity"][0]), "logical_entity_name": "RegionInput"}
    )
    region_attribute = deepcopy(graph["logical_attribute"][0])
    region_attribute.update(
        logical_entity_name="RegionInput", logical_attribute_name="region_id"
    )
    region_attribute["sources"][0]["source_attribute"]["attribute_name"] = "region_id"
    graph["logical_attribute"].append(region_attribute)
    # Same name in another schema and an unrelated entity are not eligible sources.
    graph["logical_entity"].append(
        {
            **deepcopy(graph["logical_entity"][0]),
            "logical_entity_schema_name": "other_schema",
        }
    )
    relation = logical_relationship()
    relation.update(
        from_logical_entity_name="CustomerInput",
        from_logical_attribute_name="customer_id",
        to_logical_entity_name="RegionInput",
        to_logical_attribute_name="region_id",
    )
    graph["logical_relationship"] = [
        relation,
        {
            **relation,
            "logical_relationship_name": "Excluded",
            "to_logical_entity_schema_name": "other_schema",
        },
    ]
    key = {
        name: getattr(physical, name)
        for name in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        )
    }
    graph["profiling_profile"] = [
        {
            **key,
            "attribute_name": name,
            "row_count": 10,
            "non_null_count": 10,
            "null_count": 0,
        }
        for name in ("customer_id", "region_id", "unused")
    ]
    analysis = deepcopy(complete_model_graph()["analysis_result"][0])
    for side, attribute in (("from", "customer_id"), ("to", "region_id")):
        analysis.update({f"{side}_{name}": value for name, value in key.items()})
        analysis[f"{side}_attribute_name"] = attribute
    graph["analysis_result"] = [analysis, {**analysis, "to_attribute_name": "unused"}]
    identity = {
        "modeled_entity_type": "logical_entity",
        "modeled_entity_schema_name": "silver",
        "modeled_entity_name": "CustomerInput",
        "source_system_code": "CRM",
        "output_template_code": "custom_object",
    }
    opaque = {
        "source_tables": [key],
        "custom": {"business_id": 91, "nested": {"rule_id": "keep"}},
    }
    mapping = {
        **identity,
        "object_dependency_order": 0,
        "mapping_transformation_document": opaque,
        "object_mapping_status": "active",
        "object_mapping_is_locked": False,
    }
    graph["mapping_object"] = [
        mapping,
        {**mapping, "source_system_code": "ERP"},
        {**mapping, "modeled_entity_schema_name": "other_schema"},
    ]
    graph["mapping_attribute"] = [
        {
            **identity,
            "output_template_code": None,
            "modeled_attribute_name": "customer_id",
            "attribute_mapping_transformation_document": {
                "transformation_logic": "customer_id",
                "custom_id": False,
            },
            "attribute_mapping_status": "active",
            "attribute_mapping_is_locked": False,
        }
    ]
    template = MappingOutputTemplate.model_validate(
        {
            "output_template_id": 91,
            "code": "custom_object",
            "name": "Custom Object",
            "description": "Custom interpretation.",
            "target_type": "mapping_object",
            "modeled_entity_type": "logical_entity",
            "schema_digest": "a" * 64,
            "schema_digest_is_valid": True,
            "is_active": True,
            "fields": [
                {
                    "name": "source_tables",
                    "description": "Input tables.",
                    "data_type": "array",
                    "array_item_type": "object",
                    "example": None,
                    "is_required": True,
                    "order": 1,
                }
            ],
        },
        strict=False,
    )
    context = preparation.context.model_copy(
        update={
            "sources": (first_source, peer),
            "upstream_physical_sources": (physical_source,),
            "output_templates": preparation.context.output_templates.model_copy(
                update={"ids": (91,), "definitions": (template,)}
            ),
        }
    )
    preparation = preparation.model_copy(
        update={"context": context, "snapshot": snapshot_from_graph(cast(Any, graph))}
    )
    assert preparation.snapshot is not None
    before = preparation.snapshot.model_dump(mode="json")
    execution = build_mapping_execution_context(
        preparation=preparation,
        execution_mode="tool_assisted",
        limits=MappingExecutionContextLimits(
            max_tool_result_bytes=8_000, max_tool_page_records=2
        ),
    )
    assert isinstance(execution.tool_catalog, DownstreamContextReaders)
    values = execution.tool_catalog.prompt_values
    records = values["mapping_support_records"]
    assert cast(
        Any,
        Draft202012Validator(
            downstream_input_contracts("mapping")["mapping_support_records"][0]
        ),
    ).is_valid(records)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        grouped.setdefault(item["evidence_type"], []).append(item["record"])
    assert len(grouped["source_logical_entity"]) == 2
    assert len(grouped["source_logical_attribute"]) == 2
    assert len(grouped["source_logical_relationship"]) == 1
    assert len(grouped["source_object_mapping"]) == 1
    assert (
        grouped["source_object_mapping"][0]["mapping_transformation_document"] == opaque
    )
    assert (
        grouped["source_attribute_mapping"][0][
            "attribute_mapping_transformation_document"
        ]["custom_id"]
        is False
    )
    assert grouped["source_mapping_template"][0]["code"] == "custom_object"
    assert "output_template_id" not in grouped["source_mapping_template"][0]
    assert (
        grouped["physical_object"][0]["object_description"]
        == "Enriched customer object."
    )
    assert {row["attribute_name"] for row in grouped["physical_attribute"]} == {
        "customer_id",
        "region_id",
    }
    assert {row["attribute_name"] for row in grouped["profile"]} == {
        "customer_id",
        "region_id",
    }
    assert len(grouped["analysis_relationship"]) == 1
    assert grouped["analysis_relationship"][0]["validation_result"] == "supported"
    assert all(
        "entity_type" in source["object"] for source in values["source_evidence"]
    )
    assert values["mapping_support"]["profiles"] == []  # Legacy shape is unchanged.
    seen: list[dict[str, Any]] = []
    page = execution.tool_catalog.invoke("get_mapping_support_records", {})
    while True:
        seen.extend(page["items"])
        if page["next_cursor"] is None:
            break
        page = execution.tool_catalog.invoke(
            "get_mapping_support_records", {"cursor": page["next_cursor"]}
        )
    assert seen == records and len(records) > 2
    assert preparation.snapshot.model_dump(mode="json") == before


def test_gold_without_authorized_physical_support_does_not_project_other_system_lineage() -> (
    None
):
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    execution = build_mapping_execution_context(
        preparation=preparation, execution_mode="one_shot"
    )
    values = cast(dict[str, Any], execution.embedded_context)["values"]
    records = values["mapping_support_records"]
    assert not any(
        row["evidence_type"]
        in {"physical_object", "physical_attribute", "profile", "analysis_relationship"}
        for row in records
    )
    logical = [
        row["record"]
        for row in records
        if row["evidence_type"] == "source_logical_attribute"
    ]
    assert logical and all(row["sources"] == [] for row in logical)
