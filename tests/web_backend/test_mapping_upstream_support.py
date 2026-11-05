"""Gold keeps applied Logical and scoped physical evidence without widening inputs."""

import json
from copy import deepcopy
from typing import Any, cast

import pytest
from atlas_mcp.domain.modeling_records import ContextTypeRecord
from atlas_mcp.domain.snapshots.project import project_snapshot_records
from atlas_platform.features.mapping.execution_context import (
    MappingExecutionContextLimits,
    build_mapping_execution_context,
)
from atlas_platform.features.mapping.preparation_contracts import (
    MappingModeledEntity,
    MappingOutputTemplate,
    MappingSource,
)
from atlas_platform.features.workflows.authoring.downstream_inputs import (
    DownstreamContextReaders,
    downstream_input_contracts,
    project_downstream_inputs,
)
from atlas_platform.features.workflows.authoring.plan import WorkflowExecutionMode
from atlas_platform.prompt_rendering import PromptComponentTemplates
from jsonschema import Draft202012Validator

from tests.mcp.project_test_fixtures import (
    complete_project_graph,
    dimensional_attribute,
    dimensional_entity,
    dimensional_relationship,
    logical_relationship,
    snapshot_from_graph,
)
from tests.web_backend.mapping_fixtures import mapping_preparation


@pytest.mark.parametrize("layer", ["logical", "dimensional"])
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_parent_lookup_keeps_key_lineage_and_its_own_system_rules(
    layer: str, mode: WorkflowExecutionMode
) -> None:
    preparation = mapping_preparation(
        modeled_entity_type="logical_entity" if layer == "logical" else "dimensional_entity",
        execution_mode=mode,
    )
    assert preparation.snapshot is not None
    graph = {
        name: [row.model_dump(mode="json") for row in rows]
        for name, rows in project_snapshot_records(preparation.snapshot).items()
    }
    schema = "silver" if layer == "logical" else "gold"
    prototype = preparation.context.target
    parent = prototype.model_copy(
        update={
            "entity_id": 202,
            "entity_name": "CustomerDirectory",
            "attributes": (
                prototype.attributes[0].model_copy(
                    update={"attribute_name": "CustomerKey", "is_surrogate_key": True}
                ),
                prototype.attributes[0].model_copy(
                    update={
                        "attribute_id": 702,
                        "attribute_name": "SourceCustomerID",
                        "ordinal_position": 2,
                        "is_natural_key": True,
                    }
                ),
            ),
        }
    )
    parent_record = deepcopy(graph[f"{layer}_entity"][0])
    parent_record[f"{layer}_entity_name"] = "CustomerDirectory"
    graph[f"{layer}_entity"].append(parent_record)
    business_key = deepcopy(graph[f"{layer}_attribute"][0])
    business_key.update(
        {
            f"{layer}_entity_name": "CustomerDirectory",
            f"{layer}_attribute_name": "SourceCustomerID",
            f"{layer}_attribute_is_natural_key": True,
            f"{layer}_attribute_ordinal_position": 2,
        }
    )
    # Its lineage belongs to the parent's System, outside this branch's eligible
    # execution inputs. Preserve it as provenance without widening the source list.
    if layer == "logical":
        source_key = dict(parent_record["sources"][0]["source_object"])
        source_key.update(system_code="ERP", object_name="directory_customer")
        parent_record["sources"][0]["source_object"] = source_key
        business_key["sources"][0]["source_attribute"] = {
            **source_key,
            "attribute_name": "customer_number",
        }
        graph["project_input_scope"].append(
            {**source_key, "is_active": True, "project_input_scope_is_locked": False}
        )
    else:
        directory = deepcopy(graph["logical_entity"][0])
        directory["logical_entity_name"] = "DirectoryInput"
        graph["logical_entity"].append(directory)
        directory_key = deepcopy(graph["logical_attribute"][0])
        directory_key["logical_entity_name"] = "DirectoryInput"
        graph["logical_attribute"].append(directory_key)
        parent_record["sources"][0]["source_logical_entity"]["logical_entity_name"] = (
            "DirectoryInput"
        )
        business_key["sources"][0]["source_logical_attribute"]["logical_entity_name"] = (
            "DirectoryInput"
        )
    returned_key = deepcopy(business_key)
    returned_key.update(
        {
            f"{layer}_attribute_name": "CustomerKey",
            f"{layer}_attribute_is_natural_key": False,
            f"{layer}_attribute_is_surrogate_key": True,
            f"{layer}_attribute_ordinal_position": 1,
            "sources": [],
        }
    )
    graph[f"{layer}_attribute"].extend((returned_key, business_key))
    relationship = logical_relationship() if layer == "logical" else dimensional_relationship()
    relationship.update(
        {
            f"from_{layer}_entity_schema_name": schema,
            f"from_{layer}_entity_name": prototype.entity_name,
            f"from_{layer}_attribute_name": "CustomerID",
            f"to_{layer}_entity_schema_name": schema,
            f"to_{layer}_entity_name": "CustomerDirectory",
            f"to_{layer}_attribute_name": "CustomerKey",
            f"{layer}_relationship_basis": "Look up the source customer number in ERP.",
        }
    )
    graph[f"{layer}_relationship"] = [relationship]
    mapping_identity = {
        "modeled_entity_type": f"{layer}_entity",
        "modeled_entity_schema_name": schema,
        "modeled_entity_name": "CustomerDirectory",
        "source_system_code": "ERP",
        "output_template_code": None,
    }
    graph["mapping_object"] = [
        {
            **mapping_identity,
            "object_dependency_order": 0,
            "mapping_transformation_document": {"custom_rule": "ERP owns this directory."},
            "object_mapping_status": "active",
            "object_mapping_is_locked": False,
        }
    ]
    graph["mapping_attribute"] = [
        {
            **mapping_identity,
            "modeled_attribute_name": "SourceCustomerID",
            "attribute_mapping_transformation_document": {"custom_rule": "Keep the exact number."},
            "attribute_mapping_status": "active",
            "attribute_mapping_is_locked": False,
        }
    ]
    for index in range(60):
        for dataset, field in (
            ("mapping_object", "mapping_transformation_document"),
            ("mapping_attribute", "attribute_mapping_transformation_document"),
        ):
            graph[dataset].append(
                {
                    **graph[dataset][0],
                    "source_system_code": f"OTHER_{index}",
                    field: {"custom_rule": "Wide foreign-System rule. " * 80},
                }
            )
    agent_plan = preparation.plan.agent_plan
    stage = agent_plan.stages[0].model_copy(
        update={
            "templates": PromptComponentTemplates(system="Map.", instruction="{{ mapping_basis }}")
        }
    )
    preparation = preparation.model_copy(
        update={
            "snapshot": snapshot_from_graph(cast(Any, graph)),
            "context": preparation.context.model_copy(
                update={
                    "sources": (
                        *preparation.context.sources,
                        MappingSource(
                            source_mapping_id=None,
                            modeled_entity_id=prototype.entity_id,
                            role="lookup",
                            rationale="Modeled relationship parent.",
                            is_locked=False,
                            object=parent,
                        ),
                    )
                }
            ),
            "plan": preparation.plan.model_copy(
                update={"agent_plan": agent_plan.model_copy(update={"stages": (stage,)})}
            ),
        }
    )
    execution = build_mapping_execution_context(preparation=preparation, execution_mode=mode)
    if mode == "tool_assisted":
        assert isinstance(execution.tool_catalog, DownstreamContextReaders)
        cards = execution.tool_catalog.invoke("get_mapping_basis", {})["items"]
    else:
        cards = cast(dict[str, Any], execution.embedded_context)["values"]["mapping_basis"]
    key = next(
        card["record"]
        for card in cards
        if card["kind"] == f"source_{layer}_attribute"
        and card["record"][f"{layer}_entity_name"] == "CustomerDirectory"
        and card["record"][f"{layer}_attribute_name"] == "SourceCustomerID"
    )
    assert key[f"{layer}_attribute_is_natural_key"] is True
    assert key["sources"] == business_key["sources"]
    assert not any(
        card["kind"] == "source"
        and card["record"].get("entity_name", card["record"].get("object_name"))
        in {"DirectoryInput", "directory_customer"}
        for card in cards
    )
    assert any(
        card["kind"] == "source_attribute_mapping"
        and card["record"]["source_system_code"] == "ERP"
        and card["record"]["modeled_entity_name"] == "CustomerDirectory"
        for card in cards
    )
    assert len(json.dumps(cards)) < 25_000
    assert "Wide foreign-System rule" not in json.dumps(cards)
    parent_card = next(
        card["record"]
        for card in cards
        if card["kind"] == "source" and card["record"].get("entity_name") == "CustomerDirectory"
    )
    assert set(parent_card["deferred_mapping_systems"]) == {f"OTHER_{index}" for index in range(60)}
    if mode == "tool_assisted":
        assert isinstance(execution.tool_catalog, DownstreamContextReaders)
        page = execution.tool_catalog.invoke("get_mapping_basis", {"candidate_refs": [parent_card["ref"]]})
        details = list(page["items"])
        while page["next_cursor"]:
            page = execution.tool_catalog.invoke("get_mapping_basis", {"cursor": page["next_cursor"]})
            details.extend(page["items"])
        assert any("Wide foreign-System rule" in json.dumps(card) for card in details)
        assert len([card for card in details if card["kind"] == "source_attribute_mapping"]) == 61


def test_gold_support_records_keep_upstream_documents_lineage_and_page_completely() -> None:
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    assert preparation.snapshot is not None
    graph = {
        name: [row.model_dump(mode="json") for row in rows]
        for name, rows in project_snapshot_records(preparation.snapshot).items()
    }
    physical_source = mapping_preparation().context.sources[0]
    physical = physical_source.object
    first = physical.attributes[0]
    physical = physical.model_copy(
        update={
            "object_description": "Enriched customer object.",
            "attributes": (
                first.model_copy(update={"attribute_description": "Enriched customer identifier."}),
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
    region_attribute.update(logical_entity_name="RegionInput", logical_attribute_name="region_id")
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
    # One foreign key per relationship: the excluded one starts in another schema.
    graph["logical_relationship"] = [
        relation,
        {**relation, "from_logical_entity_schema_name": "other_schema"},
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
    analysis = deepcopy(complete_project_graph()["analysis_result"][0])
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
        limits=MappingExecutionContextLimits(max_tool_result_bytes=8_000, max_tool_page_records=2),
    )
    assert isinstance(execution.tool_catalog, DownstreamContextReaders)
    values = execution.tool_catalog.prompt_values
    records = values["mapping_support_records"]
    assert cast(
        Any,
        Draft202012Validator(downstream_input_contracts("mapping")["mapping_support_records"][0]),
    ).is_valid(records)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        grouped.setdefault(item["evidence_type"], []).append(item["record"])
    assert len(grouped["source_logical_entity"]) == 2
    assert len(grouped["source_logical_attribute"]) == 2
    assert len(grouped["source_logical_relationship"]) == 1
    assert len(grouped["source_object_mapping"]) == 1
    assert grouped["source_object_mapping"][0]["mapping_transformation_document"] == opaque
    assert (
        grouped["source_attribute_mapping"][0]["attribute_mapping_transformation_document"][
            "custom_id"
        ]
        is False
    )
    assert grouped["source_mapping_template"][0]["code"] == "custom_object"
    assert "output_template_id" not in grouped["source_mapping_template"][0]
    assert grouped["physical_object"][0]["object_description"] == "Enriched customer object."
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
    assert all("entity_type" in source["object"] for source in values["source_evidence"])
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


def test_gold_without_authorized_physical_support_does_not_project_other_system_lineage() -> None:
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    execution = build_mapping_execution_context(preparation=preparation, execution_mode="one_shot")
    values = cast(dict[str, Any], execution.embedded_context)["values"]
    records = values["mapping_support_records"]
    assert not any(
        row["evidence_type"]
        in {"physical_object", "physical_attribute", "profile", "analysis_relationship"}
        for row in records
    )
    logical = [
        row["record"] for row in records if row["evidence_type"] == "source_logical_attribute"
    ]
    assert logical and all(row["sources"] == [] for row in logical)


def test_gold_support_works_out_dimensional_link_kind_optionality_and_cardinality() -> None:
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    assert preparation.snapshot is not None
    graph = {
        name: [row.model_dump(mode="json") for row in rows]
        for name, rows in project_snapshot_records(preparation.snapshot).items()
    }
    # A fact's nullable foreign key points at the target dimension's key.
    graph["dimensional_entity"].append(dimensional_entity("SalesFact", "fact"))
    graph["dimensional_attribute"].append(
        {
            **dimensional_attribute("SalesFact", "CustomerKey", key_role="foreign"),
            "dimensional_attribute_is_nullable": True,
        }
    )
    graph["dimensional_relationship"] = [
        {
            **dimensional_relationship(),
            "to_dimensional_entity_name": "Customer",
            "to_dimensional_attribute_name": "CustomerID",
        }
    ]
    preparation = preparation.model_copy(update={"snapshot": snapshot_from_graph(cast(Any, graph))})
    execution = build_mapping_execution_context(preparation=preparation, execution_mode="one_shot")
    values = cast(dict[str, Any], execution.embedded_context)["values"]
    (link,) = values["mapping_support"]["modeled_relationships"]
    assert link["from_dimensional_entity_name"] == "SalesFact"
    assert link["dimensional_relationship_kind"] == "fact_dimension"
    assert link["dimensional_relationship_cardinality"] == "many_to_one"
    assert link["dimensional_relationship_is_optional"] is True
    assert "dimensional_relationship_is_active" not in link
    assert "dimensional_relationship_is_locked" not in link


def test_gold_support_keeps_context_an_upstream_logical_entity_cites_whatever_its_type() -> None:
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    assert preparation.snapshot is not None
    graph = {
        name: [row.model_dump(mode="json") for row in rows]
        for name, rows in project_snapshot_records(preparation.snapshot).items()
    }
    record_id = "00000000-0000-4000-8000-000000000009"
    # A Logical Requirement is routed to Logical only, never to Mapping.
    graph["context_group"] = [
        {
            "context_group_name": "Silver rules",
            "context_type_name": "Logical Requirement",
            "source_system_code": None,
            "context_group_description": None,
            "is_active": True,
        }
    ]
    graph["context_record"] = [
        {
            "context_record_id": record_id,
            "context_group_name": "Silver rules",
            "context_text": "Keep one Customer per CRM account.",
            "source_reference": None,
            "status": "active",
            "is_locked": False,
        }
    ]
    citation = {
        "support_source_type": "context_record",
        "context_record": {"context_record_id": record_id},
        "rationale": "Silver rule.",
        "is_active": True,
        "is_locked": False,
    }
    graph["logical_entity"][0]["sources"].append(citation)
    graph["logical_attribute"][0]["sources"].append(citation)
    snapshot = snapshot_from_graph(cast(Any, graph))
    snapshot = snapshot.model_copy(
        update={
            "context": snapshot.context.model_copy(
                update={
                    "types": (
                        ContextTypeRecord(
                            context_type_name="Logical Requirement",
                            context_type_description="Silver model requirements.",
                            context_type_workflows=("logical",),
                        ),
                    )
                }
            )
        }
    )
    execution = build_mapping_execution_context(
        preparation=preparation.model_copy(update={"snapshot": snapshot}),
        execution_mode="one_shot",
    )
    values = cast(dict[str, Any], execution.embedded_context)["values"]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in values["mapping_support_records"]:
        grouped.setdefault(item["evidence_type"], []).append(item["record"])
    assert [row["context_record_id"] for row in grouped["context_record"]] == [record_id]
    for kind in ("source_logical_entity", "source_logical_attribute"):
        assert [
            source["context_record"]["context_record_id"]
            for source in grouped[kind][0]["sources"]
            if source["support_source_type"] == "context_record"
        ] == [record_id]


def test_gold_pair_defers_unrelated_eligible_model_and_mapping_until_requested() -> None:
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    assert preparation.snapshot is not None
    graph = {
        name: [row.model_dump(mode="json") for row in rows]
        for name, rows in project_snapshot_records(preparation.snapshot).items()
    }
    source = preparation.context.sources[0]
    assert isinstance(source.object, MappingModeledEntity)
    alternatives: list[MappingSource] = []
    for index in range(20):
        name = f"Unrelated{index}"
        alternatives.append(
            source.model_copy(
                update={
                    "role": "candidate",
                    "object": source.object.model_copy(
                        update={"entity_name": name, "entity_id": 2000 + index}
                    ),
                }
            )
        )
        graph["logical_entity"].append({**graph["logical_entity"][0], "logical_entity_name": name})
        graph["logical_attribute"].append(
            {**graph["logical_attribute"][0], "logical_entity_name": name}
        )
        graph.setdefault("mapping_object", []).append(
            {
                "modeled_entity_type": "logical_entity",
                "modeled_entity_schema_name": "silver",
                "modeled_entity_name": name,
                "source_system_code": "CRM",
                "output_template_code": None,
                "object_dependency_order": 0,
                "object_mapping_status": "active",
                "object_mapping_is_locked": False,
                "mapping_transformation_document": {"sample_query": f"mapping for {name}"},
            }
        )
    preparation = preparation.model_copy(
        update={
            "snapshot": snapshot_from_graph(cast(Any, graph)),
            "context": preparation.context.model_copy(update={"sources": (source, *alternatives)}),
        }
    )
    execution = build_mapping_execution_context(preparation=preparation, execution_mode="one_shot")
    cards = project_downstream_inputs("mapping", cast(dict[str, Any], execution.embedded_context))[
        "mapping_basis"
    ]
    assert not any(c["kind"] == "source_object_mapping" for c in cards)
    assert len([c for c in cards if c["kind"] == "column"]) == 1
    # An editable template can still ask for the full original support contract.
    values = cast(dict[str, Any], execution.embedded_context)["values"]
    assert (
        sum(
            c["evidence_type"] == "source_object_mapping" for c in values["mapping_support_records"]
        )
        == 20
    )
    agent_plan = preparation.plan.agent_plan
    stage = agent_plan.stages[0].model_copy(
        update={
            "templates": PromptComponentTemplates(
                system="Write Mapping.", instruction="{{ mapping_basis }}"
            )
        }
    )
    compact_plan = preparation.plan.model_copy(
        update={"agent_plan": agent_plan.model_copy(update={"stages": (stage,)})}
    )
    compact = build_mapping_execution_context(
        preparation=preparation.model_copy(update={"plan": compact_plan}), execution_mode="one_shot"
    )
    compact_values = cast(dict[str, Any], compact.embedded_context)["values"]
    assert compact_values["mapping_support_records"] == []
    assert compact_values["mapping_basis"] == cards
    assisted = build_mapping_execution_context(
        preparation=preparation, execution_mode="tool_assisted"
    )
    reader = assisted.tool_catalog
    assert isinstance(reader, DownstreamContextReaders)
    core = reader.invoke("get_mapping_basis", {})["items"]
    assert not any(c["kind"] == "source_object_mapping" for c in core)
    ref = next(
        c["record"]["ref"]
        for c in core
        if c["kind"] == "source" and c["record"].get("entity_name") == "Unrelated17"
    )
    picked = reader.invoke("get_mapping_basis", {"candidate_refs": [ref]})["items"]
    assert [
        c["record"]["modeled_entity_name"] for c in picked if c["kind"] == "source_object_mapping"
    ] == ["Unrelated17"]
    # Saved custom readers still expose the complete eligible frozen inventory.
    assert len(reader.invoke("get_mapping_sources", {})["items"]) == 21


@pytest.mark.parametrize(
    ("saved_rule", "expected"),
    [
        ("Read warehouse.archive.Registry", {"archive"}),
        ("Read `warehouse`.`current`.`Registry`", {"current"}),
        ("Use the Registry entry", {"current", "archive"}),
    ],
)
def test_pair_preserves_saved_rule_sources_and_disambiguates_qualified_names(
    saved_rule: str, expected: set[str]
) -> None:
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity", existing=True)
    driver = preparation.context.sources[0]
    assert isinstance(driver.object, MappingModeledEntity)
    peers = tuple(
        driver.model_copy(
            update={
                "role": "lookup",
                "object": driver.object.model_copy(
                    update={
                        "entity_schema_name": schema,
                        "entity_name": name,
                    }
                ),
            }
        )
        for schema, name in (("archive", "Registry"), ("current", "Registry"), ("other", "Spare"))
    )
    header = preparation.context.headers[0].model_copy(
        update={
            "transformation_document": {"custom": {"opaque_rule": saved_rule}},
        }
    )
    preparation = preparation.model_copy(
        update={
            "context": preparation.context.model_copy(
                update={
                    "sources": (driver, *peers),
                    "headers": (header,),
                }
            )
        }
    )
    execution = build_mapping_execution_context(preparation=preparation, execution_mode="one_shot")
    cards = cast(dict[str, Any], execution.embedded_context)["values"]["mapping_basis"]
    assert {
        c["record"]["entity_schema_name"]
        for c in cards
        if c["kind"] == "source" and c["record"]["role"] == "lookup"
    } == expected


def test_pair_keeps_all_possible_drivers_when_only_a_lookup_is_named() -> None:
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    prototype = preparation.context.sources[0]
    assert isinstance(prototype.object, MappingModeledEntity)
    sources = tuple(
        prototype.model_copy(
            update={
                "role": role,
                "object": prototype.object.model_copy(update={"entity_name": name}),
            }
        )
        for role, name in (
            ("candidate", "FeedA"),
            ("candidate", "FeedB"),
            ("lookup", "Directory"),
            ("lookup", "UnrelatedPeer"),
        )
    )
    header = preparation.context.headers[0].model_copy(
        update={"transformation_document": {"custom": "Use Directory"}}
    )
    preparation = preparation.model_copy(
        update={
            "context": preparation.context.model_copy(
                update={"sources": sources, "headers": (header,)}
            )
        }
    )
    ex = build_mapping_execution_context(preparation=preparation, execution_mode="one_shot")
    cards = cast(dict[str, Any], ex.embedded_context)["values"]["mapping_basis"]
    assert {c["record"]["entity_name"] for c in cards if c["kind"] == "source"} == {
        "FeedA",
        "FeedB",
        "Directory",
    }


def test_compact_one_shot_keeps_upstream_evidence_for_a_single_supported_source() -> None:
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    agent_plan = preparation.plan.agent_plan
    stage = agent_plan.stages[0].model_copy(
        update={
            "templates": PromptComponentTemplates(
                system="Map the target.", instruction="{{ mapping_basis }}"
            )
        }
    )
    plan = preparation.plan.model_copy(
        update={"agent_plan": agent_plan.model_copy(update={"stages": (stage,)})}
    )
    execution = build_mapping_execution_context(
        preparation=preparation.model_copy(update={"plan": plan}), execution_mode="one_shot"
    )
    values = cast(dict[str, Any], execution.embedded_context)["values"]
    assert values["mapping_support_records"] == []
    cards = values["mapping_basis"]
    assert [
        c["record"]["logical_entity_name"] for c in cards if c["kind"] == "source_logical_entity"
    ] == ["CustomerInput"]
    assert [
        c["record"]["logical_attribute_name"]
        for c in cards
        if c["kind"] == "source_logical_attribute"
    ] == ["customer_id"]


def test_logical_pair_keeps_cross_source_join_evidence_without_promoting_whole_sources() -> None:
    preparation = mapping_preparation()
    assert preparation.snapshot is not None
    driver = preparation.context.sources[0]
    assert not isinstance(driver.object, MappingModeledEntity)
    peers = tuple(
        driver.model_copy(
            update={
                "role": "candidate",
                "object": driver.object.model_copy(update={"object_name": name}),
            }
        )
        for name in ("registry", "history", "region", "unrelated")
    )
    graph = {
        name: [row.model_dump(mode="json") for row in rows]
        for name, rows in project_snapshot_records(preparation.snapshot).items()
    }
    prototype = complete_project_graph()["analysis_result"][0]
    physical = driver.object.model_dump()
    graph["analysis_result"] = []
    for first, second, validated in (
        ("customer", "registry", True),
        ("history", "customer", False),
        ("registry", "region", True),
        ("customer", "outside_scope", True),
    ):
        row = dict(prototype)
        for side, object_name in (("from", first), ("to", second)):
            for key in ("tenant_code", "system_code", "connection_code", "object_schema"):
                row[f"{side}_{key}"] = physical[key]
            row[f"{side}_object_name"] = object_name
        if not validated:
            row.update({key: None for key in row if key.startswith("validation_")})
        graph["analysis_result"].append(row)
    preparation = preparation.model_copy(
        update={
            "snapshot": snapshot_from_graph(cast(Any, graph)),
            "context": preparation.context.model_copy(update={"sources": (driver, *peers)}),
        }
    )
    inline = build_mapping_execution_context(preparation=preparation, execution_mode="one_shot")
    cards = cast(dict[str, Any], inline.embedded_context)["values"]["mapping_basis"]
    sources = {
        c["record"]["object_name"]: c["record"]["ref"] for c in cards if c["kind"] == "source"
    }
    assert set(sources) == {"customer", "registry", "history"}
    assert {c["record"]["source"] for c in cards if c["kind"] == "column"} == {sources["customer"]}
    assert {
        (r["from_source_ref"], r["to_source_ref"], r["validation_result"])
        for c in cards
        if c["kind"] == "analysis_relationship" and (r := c["record"])
    } == {
        (sources["customer"], sources["registry"], "supported"),
        (sources["history"], sources["customer"], None),
    }
    assert all(
        r["from_attribute_name"] == r["to_attribute_name"] == "customer_id"
        for c in cards
        if c["kind"] == "analysis_relationship" and (r := c["record"])
    )
    assisted = build_mapping_execution_context(
        preparation=preparation, execution_mode="tool_assisted"
    )
    reader = assisted.tool_catalog
    assert isinstance(reader, DownstreamContextReaders)
    core = reader.invoke("get_mapping_basis", {})["items"]
    assert [c for c in cards if c["kind"] == "analysis_relationship"] == [
        c for c in core if c["kind"] == "analysis_relationship"
    ]
    assert len([c for c in core if c["kind"] == "source"]) == len(peers) + 1
    selected = reader.invoke("get_mapping_basis", {"candidate_refs": [sources["registry"]]})[
        "items"
    ]
    assert {c["record"]["object_name"] for c in selected if c["kind"] == "source"} == {"registry"}
    edges = [c["record"] for c in selected if c["kind"] == "analysis_relationship"]
    assert [
        (r["from_object_name"], r["to_object_name"], r["validation_source_distinct_count"])
        for r in edges
    ] == [("customer", "registry", 5)]


def test_gold_pair_keeps_silver_join_across_focused_and_deferred_sources() -> None:
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    assert preparation.snapshot is not None
    driver = preparation.context.sources[0]
    assert isinstance(driver.object, MappingModeledEntity)
    peer = driver.model_copy(
        update={
            "role": "candidate",
            "object": driver.object.model_copy(update={"entity_name": "Registry"}),
        }
    )
    graph = {
        name: [row.model_dump(mode="json") for row in rows]
        for name, rows in project_snapshot_records(preparation.snapshot).items()
    }
    graph["logical_entity"].append(
        {**graph["logical_entity"][0], "logical_entity_name": "Registry"}
    )
    graph["logical_attribute"].append(
        {**graph["logical_attribute"][0], "logical_entity_name": "Registry"}
    )
    relation = {
        **logical_relationship(),
        "from_logical_entity_name": "CustomerInput",
        "from_logical_attribute_name": "customer_id",
        "to_logical_entity_name": "Registry",
        "to_logical_attribute_name": "customer_id",
    }
    graph["logical_relationship"] = [
        relation,
        {**relation, "to_logical_attribute_name": "missing"},
        {**relation, "to_logical_entity_schema_name": "other"},
    ]
    preparation = preparation.model_copy(
        update={
            "snapshot": snapshot_from_graph(cast(Any, graph)),
            "context": preparation.context.model_copy(update={"sources": (driver, peer)}),
        }
    )
    execution = build_mapping_execution_context(
        preparation=preparation, execution_mode="tool_assisted"
    )
    reader = execution.tool_catalog
    assert isinstance(reader, DownstreamContextReaders)
    core = reader.invoke("get_mapping_basis", {})["items"]
    edges = [c["record"] for c in core if c["kind"] == "source_logical_relationship"]
    assert len(edges) == 1
    assert edges[0]["logical_relationship_basis"] == relation["logical_relationship_basis"]
    assert len([c for c in core if c["kind"] == "column"]) == 1
    peer_ref = next(
        c["record"]["ref"] for c in core if c["kind"] == "source" and c["record"].get("deferred")
    )
    details = reader.invoke("get_mapping_basis", {"candidate_refs": [peer_ref]})["items"]
    assert [
        c["record"]["to_logical_entity_name"]
        for c in details
        if c["kind"] == "source_logical_relationship"
    ] == ["Registry"]
