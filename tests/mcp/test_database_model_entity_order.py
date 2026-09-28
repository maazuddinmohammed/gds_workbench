"""Apply a complete two-layer graph against immediate database dependencies."""

import json
from copy import deepcopy
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pytest
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import (
    load_model_physical_scope,
)
from gds_etl_workbench.application.change_sets.model_validation import (
    ValidatedModelChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset, ModelSnapshot
from gds_etl_workbench.tools.change_sets.model import register_model_change_set_tools
from mcp import Client
from mcp.server.mcpserver import MCPServer

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import (
    complete_model_graph,
)
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,  # pyright: ignore[reportPrivateUsage]
    _replace_codes,  # pyright: ignore[reportPrivateUsage]
    _seed_model_foundation,  # pyright: ignore[reportPrivateUsage]
)


def entity_layer_graph(prefix: str) -> dict[ModelChangeSetDataset, list[dict[str, Any]]]:
    complete = complete_model_graph()
    datasets: tuple[ModelChangeSetDataset, ...] = (
        "model_input_scope",
        "logical_submodel",
        "logical_entity",
        "logical_attribute",
        "dimensional_submodel",
        "dimensional_entity",
        "dimensional_attribute",
        "mapping_object",
        "mapping_attribute",
    )
    graph: dict[ModelChangeSetDataset, list[dict[str, Any]]] = {
        key: deepcopy(complete[key][:1]) for key in datasets
    }
    # Logical definitions precede their Dimensional lineage consumers.
    for dataset in ("logical_attribute", "dimensional_attribute", "mapping_attribute"):
        graph[dataset] = deepcopy(complete[dataset][:2])
    graph["dimensional_entity"][0]["sources"] = [
        {
            "support_source_type": "logical_entity",
            "source_logical_entity": {"logical_entity_schema_name": "silver", "logical_entity_name": "Order"},
            "source_role": "transaction",
            "source_order": 1,
            "rationale": "Logical source.",
            "status": "active",
            "is_locked": False,
        }
    ]
    for record, attribute_name in zip(
        graph["dimensional_attribute"], ("OrderID", "CustomerID"), strict=True
    ):
        record["sources"] = [
            {
                "support_source_type": "logical_attribute",
                "source_logical_attribute": {"logical_entity_schema_name": "silver", "logical_entity_name": "Order", "logical_attribute_name": attribute_name},
                "source_order": 1,
                "rationale": "Logical Attribute.",
                "status": "active",
                "is_locked": False,
            }
        ]
    return _replace_codes(graph, code_prefix=prefix)


def assert_entity_layers_preserved(
    snapshot: ModelSnapshot, validation: ValidatedModelChangeSet
) -> None:
    assert len(snapshot.logical.entities) == len(snapshot.dimensional.entities) == 1
    assert len(snapshot.logical.attributes) == len(snapshot.dimensional.attributes) == 2
    assert len(snapshot.mapping.objects) == len(validation.records["mapping_object"])
    assert len(snapshot.mapping.attributes) == len(validation.records["mapping_attribute"])
    for dataset, records in (
        ("logical_entity", snapshot.logical.entities),
        ("logical_attribute", snapshot.logical.attributes),
        ("dimensional_entity", snapshot.dimensional.entities),
        ("dimensional_attribute", snapshot.dimensional.attributes),
        ("mapping_object", snapshot.mapping.objects),
        ("mapping_attribute", snapshot.mapping.attributes),
    ):
        assert sorted(
            json.dumps(record.model_dump(mode="json"), sort_keys=True) for record in records
        ) == sorted(
            json.dumps(record.model_dump(mode="json"), sort_keys=True)
            for record in validation.records[dataset]
        ), "Apply must preserve every canonical Entity, source and Mapping field."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing_contribution",
    [None, "mapping_object", "mapping_attribute", "object_document", "empty_pair", "blank_attribute"],
)
async def test_public_model_apply_orders_entities_and_preserves_partial_mapping(
    postgres_database: DisposablePostgres,
    missing_contribution: str | None,
) -> None:
    prefix = f"ENTITY_ORDER_{uuid4().hex}"
    model_id, tenant_id = _seed_model_foundation(postgres_database, code_prefix=prefix)
    _acquire_tenant_lock(postgres_database, tenant_id)
    graph = entity_layer_graph(prefix)
    if missing_contribution == "mapping_object":
        graph["mapping_object"] = []
        graph["mapping_attribute"] = []
    elif missing_contribution == "mapping_attribute":
        graph["mapping_attribute"] = []
    elif missing_contribution == "object_document":
        graph["mapping_object"][0]["mapping_transformation_document"] = None
        graph["mapping_attribute"] = graph["mapping_attribute"][:1]
    elif missing_contribution == "empty_pair":
        graph["mapping_object"][0]["mapping_transformation_document"] = None
        graph["mapping_attribute"] = []
    elif missing_contribution == "blank_attribute":
        graph["mapping_attribute"][0]["attribute_mapping_transformation_document"] = None
    expected_valid = missing_contribution != "empty_pair"
    model = ModelReadContext(
        model_id=model_id,
        tenant_id=tenant_id,
        model_name="Model Tool Round Trip",
        model_revision=1,
    )
    database = postgres_database.create_runtime_adapter()
    identity = StaticIdentityProvider()
    authorizer = AuthorizationService()
    audit = ToolCallAuditMiddleware(
        database=database, identity_provider=identity, authorizer=authorizer
    )
    server = MCPServer[None](name="model-entity-order-test", middleware=[audit])
    register_model_change_set_tools(
        server, database=database, identity_provider=identity, authorizer=authorizer, audit=audit
    )
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            baseline = await build_model_snapshot(transaction, model)
            physical = await load_model_physical_scope(transaction, model)
            canonical = validate_future_graph(
                snapshot=baseline, staged_documents=graph, physical_scope=physical
            )
            assert canonical.valid is expected_valid
            if not expected_valid:
                assert any(
                    issue.dataset == "mapping_object"
                    for issue in canonical.issues
                )

        async with Client(server) as client:
            created = await client.call_tool("create_model_change_set", {"model_id": model_id})
            assert not created.is_error
            change_set_id = created.structured_content["model_change_set_id"]
            staged = await client.call_tool(
                "stage_model_change_set",
                {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": 1,
                    "changes": [{"dataset": key, "records": rows} for key, rows in graph.items()],
                },
            )
            assert not staged.is_error
            draft_revision = staged.structured_content["draft_revision"]
            command = {
                "model_id": model_id,
                "model_change_set_id": change_set_id,
                "expected_draft_revision": draft_revision,
            }
            validated = await client.call_tool("validate_model_change_set", command)
            assert not validated.is_error
            assert validated.structured_content["valid"] is expected_valid
            applied = await client.call_tool("apply_model_change_set", command)
            if expected_valid:
                assert not applied.is_error, "A canonically valid graph must Apply successfully."
                assert applied.structured_content["model_revision"] == 2
                assert applied.structured_content["action_count"] > 0
                repeated = await client.call_tool("apply_model_change_set", command)
                assert repeated.is_error, "Ordinary MCP Apply requires a validated draft."
            else:
                assert applied.is_error

        async with database.read_transaction() as transaction:
            snapshot = await build_model_snapshot(
                transaction,
                replace(model, model_revision=2) if expected_valid else model,
            )
            if expected_valid:
                assert_entity_layers_preserved(snapshot, canonical)
                current_physical = await load_model_physical_scope(transaction, model)
                assert validate_future_graph(
                    snapshot=snapshot, staged_documents={}, physical_scope=current_physical
                ).valid
            else:
                assert snapshot == baseline, (
                    "Rejected graph must leave all Model records unchanged."
                )
        with postgres_database.connect_owner() as connection:
            row = connection.execute(
                "SELECT model_revision FROM model.model WHERE model_id = %s", (model_id,)
            ).fetchone()
            assert row == {"model_revision": 2 if expected_valid else 1}
            events = connection.execute(
                "SELECT count(*) AS count FROM mcp.model_change_set_event "
                "WHERE model_change_set_id = %s AND event_type = 'applied'",
                (change_set_id,),
            ).fetchone()
            assert events == {"count": 1 if expected_valid else 0}
        if missing_contribution is None:
            with postgres_database.connect_owner() as connection:
                original_ids = connection.execute(
                    "SELECT mapping_object_id FROM workflow.mapping_object WHERE model_id=%s",
                    (model_id,),
                ).fetchall()
            cleared = {
                "mapping_object": [
                    {**row, "mapping_transformation_document": None}
                    for row in graph["mapping_object"]
                ],
                "mapping_attribute": [
                    {**row, "attribute_mapping_transformation_document": None}
                    for row in graph["mapping_attribute"]
                ],
            }
            async with Client(server) as client:
                created = await client.call_tool("create_model_change_set", {"model_id": model_id})
                assert not created.is_error
                change_set_id = created.structured_content["model_change_set_id"]
                staged = await client.call_tool(
                    "stage_model_change_set",
                    {
                        "model_id": model_id,
                        "model_change_set_id": change_set_id,
                        "expected_draft_revision": created.structured_content["draft_revision"],
                        "changes": [
                            {"dataset": key, "records": rows} for key, rows in cleared.items()
                        ],
                    },
                )
                assert not staged.is_error
                command = {
                    "model_id": model_id,
                    "model_change_set_id": change_set_id,
                    "expected_draft_revision": staged.structured_content["draft_revision"],
                }
                validated = await client.call_tool("validate_model_change_set", command)
                assert not validated.is_error and validated.structured_content["valid"]
                applied = await client.call_tool("apply_model_change_set", command)
                assert not applied.is_error
                assert applied.structured_content["model_revision"] == 3
            async with database.read_transaction() as transaction:
                cleared_snapshot = await build_model_snapshot(
                    transaction, replace(model, model_revision=3)
                )
            assert len(cleared_snapshot.mapping.objects) == len(graph["mapping_object"])
            assert len(cleared_snapshot.mapping.attributes) == len(graph["mapping_attribute"])
            assert all(
                row.mapping_transformation_document is None
                for row in cleared_snapshot.mapping.objects
            )
            assert all(
                row.attribute_mapping_transformation_document is None
                for row in cleared_snapshot.mapping.attributes
            )
            with postgres_database.connect_owner() as connection:
                retained_ids = connection.execute(
                    "SELECT mapping_object_id FROM workflow.mapping_object WHERE model_id=%s",
                    (model_id,),
                ).fetchall()
            assert retained_ids == original_ids
    finally:
        await database.close()
