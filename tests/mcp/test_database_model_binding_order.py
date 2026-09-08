"""Apply a complete two-layer graph against immediate database dependencies."""

from copy import deepcopy
from dataclasses import replace
import json
from typing import Any
from uuid import uuid4

import pytest
from mcp import Client
from mcp.server.mcpserver import MCPServer

from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import (
    load_model_physical_scope,
    register_model_change_set_tools,
)
from gds_etl_workbench.application.change_sets.model_validation import (
    ValidatedModelChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset, ModelSnapshot
from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import (
    SILVER_ORDER,
    complete_model_graph,
    physical_attribute,
    physical_object,
)
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,  # pyright: ignore[reportPrivateUsage]
    _replace_codes,  # pyright: ignore[reportPrivateUsage]
    _seed_model_foundation,  # pyright: ignore[reportPrivateUsage]
)


def bound_layer_graph(prefix: str) -> dict[ModelChangeSetDataset, list[dict[str, Any]]]:
    complete = complete_model_graph()
    datasets: tuple[ModelChangeSetDataset, ...] = (
        "model_input_scope",
        "logical_submodel",
        "logical_entity",
        "logical_attribute",
        "dimensional_submodel",
        "dimensional_entity",
        "dimensional_attribute",
        "mapping_dependency",
        "mapping_object",
        "mapping_attribute",
    )
    graph: dict[ModelChangeSetDataset, list[dict[str, Any]]] = {
        key: deepcopy(complete[key][:1]) for key in datasets
    }
    # Both layers are new: Silver must precede physical Dimensional sources, but
    # Gold bindings must follow the new Dimensional entities and attributes.
    graph["model_object_binding"] = [
        deepcopy(complete["model_object_binding"][index]) for index in (0, 2)
    ]
    graph["model_attribute_binding"] = [
        deepcopy(complete["model_attribute_binding"][index]) for index in (0, 1, 3, 4)
    ]
    for dataset in ("logical_attribute", "dimensional_attribute", "mapping_attribute"):
        graph[dataset] = deepcopy(complete[dataset][:2])
    graph["dimensional_entity"][0]["sources"] = [
        {
            "support_source_type": "object",
            "source_object": physical_object(SILVER_ORDER),
            "source_role": "transaction",
            "source_order": 1,
            "rationale": "Realized Silver source.",
            "status": "active",
            "is_locked": False,
        }
    ]
    for record, attribute_name in zip(
        graph["dimensional_attribute"], ("OrderID", "CustomerID"), strict=True
    ):
        record["sources"] = [
            {
                "support_source_type": "attribute",
                "source_attribute": physical_attribute(SILVER_ORDER, attribute_name),
                "source_order": 1,
                "rationale": "Realized Silver Attribute.",
                "status": "active",
                "is_locked": False,
            }
        ]
    return _replace_codes(graph, code_prefix=prefix)


def assert_bound_layers_preserved(
    snapshot: ModelSnapshot, validation: ValidatedModelChangeSet
) -> None:
    assert len(snapshot.model_binding.objects) == 2
    assert len(snapshot.model_binding.attributes) == 4
    assert len(snapshot.logical.entities) == len(snapshot.dimensional.entities) == 1
    assert len(snapshot.logical.attributes) == len(snapshot.dimensional.attributes) == 2
    assert len(snapshot.mapping.objects) == 1
    assert len(snapshot.mapping.attributes) == 2
    for dataset, records in (
        ("model_object_binding", snapshot.model_binding.objects),
        ("model_attribute_binding", snapshot.model_binding.attributes),
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
        ), "Apply must preserve every canonical Binding, source and Mapping field."


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_contribution", [None, "mapping_object", "mapping_attribute"])
async def test_public_model_apply_orders_new_bindings_and_rejects_missing_contributions(
    postgres_database: DisposablePostgres,
    missing_contribution: str | None,
) -> None:
    prefix = f"BINDING_ORDER_{uuid4().hex}"
    model_id, tenant_id = _seed_model_foundation(postgres_database, code_prefix=prefix)
    _acquire_tenant_lock(postgres_database, tenant_id)
    graph = bound_layer_graph(prefix)
    if missing_contribution == "mapping_object":
        graph["mapping_object"] = []
        graph["mapping_attribute"] = []
    elif missing_contribution == "mapping_attribute":
        graph["mapping_attribute"] = []
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
    server = MCPServer[None](name="model-binding-order-test", middleware=[audit])
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
            assert canonical.valid is (missing_contribution is None)
            if missing_contribution is not None:
                assert any(
                    issue.dataset.startswith("dimensional_")
                    and any(field.startswith("source_") for field in issue.fields)
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
            assert validated.structured_content["valid"] is (missing_contribution is None)
            applied = await client.call_tool("apply_model_change_set", command)
            if missing_contribution is None:
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
                replace(model, model_revision=2) if missing_contribution is None else model,
            )
            if missing_contribution is None:
                assert_bound_layers_preserved(snapshot, canonical)
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
            assert row == {"model_revision": 2 if missing_contribution is None else 1}
            events = connection.execute(
                "SELECT count(*) AS count FROM mcp.model_change_set_event "
                "WHERE model_change_set_id = %s AND event_type = 'applied'",
                (change_set_id,),
            ).fetchone()
            assert events == {"count": 1 if missing_contribution is None else 0}
    finally:
        await database.close()
