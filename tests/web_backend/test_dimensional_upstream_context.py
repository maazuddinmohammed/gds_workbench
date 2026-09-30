"""Selected Logical lineage supplies physical evidence without writable scope changes."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, LiteralString, cast

import pytest
from gds_etl_workbench.application.change_sets.model_validation import (
    PhysicalModelCatalog,
)
from gds_etl_workbench.domain.modeling_records import (
    AttributePhysicalSourceRecord,
    LogicalObjectSourceRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
)
from gds_etl_workbench.domain.snapshots.model import ModelSnapshot
from gds_workbench_api.features.dimensional.service import _candidate_validator
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextLimits,
    AgentContextUnavailableError,
    PostgresAgentContextRepository,
)
from gds_workbench_api.features.workflows.authoring.context_contracts import (
    workflow_input_contracts,
)
from gds_workbench_api.features.workflows.authoring.context_inputs import (
    OBJECT_FIELDS,
    natural_key,
)
from gds_workbench_api.features.workflows.authoring.context_readers import (
    FrozenContextReaders,
)
from jsonschema import Draft202012Validator
from pydantic import JsonValue

from tests.web_backend.test_agent_context import (
    ContextTransaction,
    DimensionalContextTransaction,
    _dimensional_snapshot,
    _object_key,
    _plan,
)
from tests.web_backend.test_dimensional_candidate import _candidate
from tests.web_backend.test_dimensional_executor import (
    _audit_template,
    _technical_template,
)


def _snapshot(*, attribute_only: bool = False) -> ModelSnapshot:
    snapshot = _dimensional_snapshot()
    source = LogicalObjectSourceRecord(
        support_source_type="object",
        source_object=PhysicalObjectKey.model_validate(_object_key("customers")),
        source_order=1,
        rationale="Selected Logical source.",
        status="active",
        is_locked=False,
    )
    inactive = source.model_copy(
        update={
            "source_object": PhysicalObjectKey.model_validate(_object_key("orders")),
            "status": "inactive",
        }
    )
    unauthorized = source.model_copy(
        update={
            "source_object": PhysicalObjectKey.model_validate(
                _object_key("private_customers", tenant_code="OTHER")
            ),
        }
    )
    entity = snapshot.logical.entities[0].model_copy(
        update={
            "sources": (inactive, unauthorized)
            if attribute_only
            else (source, inactive, unauthorized),
        }
    )
    attribute_source = AttributePhysicalSourceRecord(
        support_source_type="attribute",
        source_attribute=PhysicalAttributeKey.model_validate(
            {**_object_key("customers"), "attribute_name": "customer_id"}
        ),
        source_order=1,
        rationale="Physical Attribute lineage.",
        status="active",
        is_locked=False,
    )
    attribute = snapshot.logical.attributes[0].model_copy(
        update={"sources": (attribute_source,)}
    )
    inactive_attribute = attribute.model_copy(
        update={
            "logical_attribute_name": "OldOrderRef",
            "logical_attribute_status": "inactive",
            "sources": (
                attribute_source.model_copy(
                    update={
                        "source_attribute": PhysicalAttributeKey.model_validate(
                            {**_object_key("orders"), "attribute_name": "customer_id"}
                        ),
                    }
                ),
            ),
        }
    )
    unselected_entity = entity.model_copy(
        update={
            "logical_entity_name": "UnselectedOrder",
            "sources": (inactive.model_copy(update={"status": "active"}),),
        }
    )
    return snapshot.model_copy(
        update={
            "model_input_scope": snapshot.model_input_scope.model_copy(
                update={
                    "details": snapshot.model_input_scope.details.model_copy(
                        update={
                            "gold_model_audit_columns_template": _audit_template(),
                            "gold_model_technical_columns_template": _technical_template(),
                        }
                    ),
                }
            ),
            "logical": snapshot.logical.model_copy(
                update={
                    "entities": (entity, unselected_entity),
                    "attributes": (attribute, inactive_attribute),
                }
            ),
            "analysis": snapshot.analysis.model_copy(
                update={
                    "relationships": (
                        snapshot.analysis.relationships[0].model_copy(
                            update={
                                "validation_policy_version": "1.0.0",
                                "validation_result": "unsupported",
                                "validation_source_non_null_count": 10,
                                "validation_source_distinct_count": 10,
                                "validation_target_non_null_count": 12,
                                "validation_target_distinct_count": 10,
                                "validation_source_missing_target_count": 0,
                                "validation_unused_target_count": 0,
                                "validation_duplicate_target_key_count": 2,
                            }
                        ),
                        snapshot.analysis.relationships[1],
                    ),
                }
            ),
        }
    )


class SupportingContextTransaction(DimensionalContextTransaction):
    def __init__(self) -> None:
        super().__init__()
        self.requested_support: list[dict[str, str]] = []

    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        if "jsonb_to_recordset" in query:
            self.requested_support = parameters[0].obj
            assert self.requested_support == [_object_key("customers")]
            assert parameters[1] == 7
            assert "object_record.source_tenant_id = %s" in query
            return [{"object_id": 501, **_object_key("customers")}]
        if "source_zone_description" in query and parameters[0]:
            return await ContextTransaction().fetch_all(query, parameters)
        if "profile.updated_time AS profiled_at" in query and parameters[1]:
            assert parameters == (18, [501])
            return [
                {
                    **_object_key("customers"),
                    "attribute_name": "customer_id",
                    "profiled_at": datetime(2026, 9, 1, tzinfo=UTC),
                    "row_scope": "batch",
                    "batch_attribute_name": None,
                    "batch_id": "42",
                }
            ]
        if parameters and parameters[0] == [501] and len(parameters) >= 3:
            assert parameters[2] == "dimensional"
            rows = await ContextTransaction().fetch_all(
                query, (*parameters[:2], "conceptual", *parameters[3:])
            )
            if "attribute_ordinal_position" in query:
                rows.append(
                    {
                        **rows[0],
                        "attribute_id": 602,
                        "attribute_name": "region",
                        "attribute_description": "Enriched customer region.",
                        "attribute_data_type": "STRING",
                        "attribute_inferred_data_type": "STRING",
                        "attribute_ordinal_position": 2,
                        "is_natural_key": False,
                    }
                )
            return rows
        return await super().fetch_all(query, parameters)


@pytest.mark.asyncio
async def test_dimensional_rejects_physical_authoring_selection_before_loading() -> None:
    plan = _plan(model_workflow="dimensional", selected_object_ids=(701,)).model_copy(
        update={"selected_object_ids": (501,)}
    )
    with pytest.raises(AgentContextUnavailableError):
        await PostgresAgentContextRepository().load(
            DimensionalContextTransaction(), tenant_id=7, plan=plan
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("attribute_only", [False, True])
async def test_dimensional_support_preserves_enrichment_profiles_and_scope(
    mode: Any, attribute_only: bool
) -> None:
    snapshot = _snapshot(attribute_only=attribute_only)
    transaction = SupportingContextTransaction()

    async def snapshot_loader(*_: Any) -> ModelSnapshot:
        return snapshot

    async def scope_loader(*_: Any) -> PhysicalModelCatalog:
        # Orders is authorized but has only inactive or unselected Logical lineage.
        keys = frozenset(
            natural_key(_object_key(name)) for name in ("customers", "orders")
        )
        attrs = frozenset((*key, "customer_id") for key in keys)
        return PhysicalModelCatalog(
            model_tenant_code="SOURCE",
            active_system_codes=frozenset({"ERP"}),
            objects=keys,
            attributes=attrs,
            model_input_objects=keys,
            model_input_attributes=attrs,
        )

    result = await PostgresAgentContextRepository(
        snapshot_loader=snapshot_loader,
        physical_scope_loader=scope_loader,
        limits=AgentContextLimits(max_selected_objects=10, max_selected_attributes=100),
    ).load(
        transaction,
        tenant_id=7,
        plan=_plan(
            model_workflow="dimensional",
            execution_mode=mode,
            selected_object_ids=(701,),
        ),
    )
    assert result.context.selected_objects == ()
    assert len(result.context.selected_logical_entities) == 1
    assert [
        a.logical_attribute_name
        for a in result.context.selected_logical_entities[0].attributes
    ] == ["CustomerID"]
    assert [g.object.object_name for g in result.context.supporting_objects] == [
        "customers"
    ]
    assert len(result.context.profiles) == 1
    values = (
        result.tool_catalog.prompt_values
        if result.tool_catalog
        else cast(dict[str, Any], result.embedded_context)["prompt_inputs"]
    )
    for name, contract in workflow_input_contracts("dimensional").items():
        assert cast(Any, Draft202012Validator(contract["schema"])).is_valid(
            values[name]
        )
    assert [row["object_name"] for row in values["object_context"]] == ["customers"]
    assert (
        values["object_context"][0]["object_description"]
        == "sensitive physical description"
    )
    attribute = values["object_attribute_context"][0]["attributes"][0]
    assert attribute["attribute_description"] == "Customer identifier."
    assert attribute["profile"]["row_count"] == 10
    assert attribute["profile"]["avg_data_length"] == 3.0
    assert attribute["profile"]["profiled_at"] == "2026-09-01T00:00:00+00:00"
    other_attribute = values["object_attribute_context"][0]["attributes"][1]
    assert other_attribute["attribute_name"] == "region"
    assert other_attribute["attribute_inferred_data_type"] == "STRING"
    assert other_attribute["profile"] is None
    assert (
        attribute["profile"]["row_scope"] == "batch"
        and attribute["profile"]["batch_id"] == "42"
    )
    assert values["source_context"][0]["connection_code"] == "SOURCE"
    assert values["ingestion_mapping"][0]["target"]["connection_code"] == "GDS"
    assert [row["zone_code"] for row in values["gds_context"]] == ["gold"]
    relation = values["object_relationship_context"][0]["outgoing_relationships"][0]
    assert relation["to_object_name"] == "orders"
    assert relation["validation_result"] == "unsupported"
    assert relation["validation_duplicate_target_key_count"] == 2
    if result.tool_catalog:
        for tool, variable in (
            ("get_objects", "object_context"),
            ("get_object_details", "object_attribute_context"),
            ("get_object_relationships", "object_relationship_context"),
            ("get_source_context", "source_context"),
        ):
            assert (
                cast(dict[str, Any], result.tool_catalog.invoke(tool, {}))["items"]
                == values[variable]
            )

    # Physical evidence and an unselected Logical Entity never become candidate sources.
    candidate = cast(dict[str, Any], _candidate())
    candidate["entities"][0]["sources"][0]["source_logical_entity"] = {
        "logical_entity_schema_name": "silver_sales",
        "logical_entity_name": "UnselectedOrder",
    }
    issues = (
        await _candidate_validator(result).validate(cast(JsonValue, candidate))
    ).issues
    assert "candidate.source_outside_selection" in {issue.code for issue in issues}


def test_dimensional_physical_detail_reader_pages_existing_attribute_cards() -> None:
    values = {
        name: spec["example"]
        for name, spec in workflow_input_contracts("dimensional").items()
    }
    group = values["object_attribute_context"][0]
    prototype = group["attributes"][0]
    group["attributes"] = [
        {**prototype, "attribute_name": f"context_column_{n}"} for n in range(12)
    ]
    group["selected_attribute_names"] = [
        a["attribute_name"] for a in group["attributes"]
    ]
    readers = FrozenContextReaders(
        workflow="dimensional",
        values=values,
        max_result_bytes=2500,
        max_page_records=20,
        max_cumulative_result_bytes=200_000,
    )
    page = readers.invoke("get_object_details", {})
    assert page["incomplete_object_key"] == {
        name: group[name] for name in OBJECT_FIELDS
    }
    recovered: list[dict[str, Any]] = []
    while True:
        recovered.extend(page["items"][0]["attributes"])
        if page["is_complete"]:
            assert page["incomplete_object_key"] is None
            break
        page = readers.invoke("get_object_details", {"cursor": page["next_cursor"]})
    assert recovered == group["attributes"]
