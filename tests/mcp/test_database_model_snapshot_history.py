"""Complete snapshots preserve owned physical evidence through deactivation."""

from copy import deepcopy
from typing import Literal, cast
from uuid import uuid4

import pytest
from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.application.change_sets.model_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import (
    build_model_snapshot,
    read_model_review_snapshot,
)
from gds_etl_workbench.application.modeling.conceptual import (
    CONCEPTUAL_OBJECTS_SQL,
    CONCEPTUAL_RELATIONSHIPS_SQL,
)
from gds_etl_workbench.application.modeling.modeled_layer import (
    DIMENSIONAL,
    LOGICAL,
    attributes_sql,
    entities_sql,
)
from gds_etl_workbench.domain.snapshots.model import model_snapshot_records

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import (
    SILVER_ORDER,
    complete_model_graph,
    physical_attribute,
    physical_object,
)
from tests.mcp.test_database_model_change_set_round_trip import (
    _replace_codes,  # pyright: ignore[reportPrivateUsage]
    _seed_model_foundation,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.asyncio
@pytest.mark.parametrize("source_layer", ["source", "silver"])
@pytest.mark.parametrize("record_type", ["object", "attribute"])
async def test_locked_nested_evidence_survives_physical_deactivation(
    postgres_database: DisposablePostgres,
    source_layer: Literal["source", "silver"],
    record_type: Literal["object", "attribute"],
) -> None:
    prefix = f"HISTORY_{uuid4().hex}"
    model_id, tenant_id = _seed_model_foundation(postgres_database, code_prefix=prefix)
    graph = complete_model_graph()
    # Cover physical evidence on both Conceptual parent types and both modeled layers.
    graph["conceptual_relationship"][0]["supports"] = deepcopy(
        graph["conceptual_object"][0]["supports"]
    )
    graph["dimensional_entity"][0]["sources"] = [
        {
            "support_source_type": "object",
            "source_object": physical_object(SILVER_ORDER),
            "source_role": "transaction",
            "source_order": 1,
            "rationale": "Applied Logical mapping contribution.",
            "status": "active",
            "is_locked": True,
        }
    ]
    graph["dimensional_attribute"][0]["sources"] = [
        {
            "support_source_type": "attribute",
            "source_attribute": physical_attribute(SILVER_ORDER, "OrderID"),
            "source_order": 1,
            "rationale": "Applied Logical mapping contribution.",
            "status": "active",
            "is_locked": True,
        }
    ]
    for dataset in (
        "conceptual_object",
        "conceptual_relationship",
        "logical_entity",
        "logical_attribute",
    ):
        nested_field = "supports" if dataset.startswith("conceptual") else "sources"
        lock_field = "support_is_locked" if nested_field == "supports" else "is_locked"
        for record in graph[dataset]:
            for evidence in cast(list[dict[str, object]], record[nested_field]):
                evidence[lock_field] = True
    staged = _replace_codes(graph, code_prefix=prefix)
    initial = deepcopy(staged)
    for dataset in ("dimensional_entity", "dimensional_attribute"):
        initial[dataset][0]["sources"] = complete_model_graph()[dataset][0]["sources"]
    model = ModelReadContext(
        model_id=model_id,
        tenant_id=tenant_id,
        model_name="Model Tool Round Trip",
        model_revision=1,
    )
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        async with database.write_transaction() as transaction:
            empty = await build_model_snapshot(transaction, model)
            physical = await load_model_physical_scope(transaction, model)
            authored = validate_future_graph(
                snapshot=empty, staged_documents=initial, physical_scope=physical
            )
            assert authored.valid
            await ModelMaterializer(transaction, model_id, "a" * 64).apply(authored.records)
            # Silver evidence depends on the previously applied Logical Binding/Mapping.
            applied = await build_model_snapshot(transaction, model)
            physical = await load_model_physical_scope(transaction, model)
            dimensional = validate_future_graph(
                snapshot=applied,
                staged_documents={
                    "dimensional_entity": staged["dimensional_entity"],
                    "dimensional_attribute": staged["dimensional_attribute"],
                },
                physical_scope=physical,
            )
            assert dimensional.valid
            await ModelMaterializer(transaction, model_id, "b" * 64).apply(dimensional.records)
        async with database.read_transaction() as transaction:
            baseline = await build_model_snapshot(transaction, model)
            review = await read_model_review_snapshot(transaction, model)
            assert review.snapshot == baseline
            canonical_records = model_snapshot_records(baseline)
            for dataset, indexed in review.records_by_id.items():
                assert len(indexed) == len(canonical_records[dataset])
                assert all(record in canonical_records[dataset] for record in indexed.values())
                assert all(type(record_id) is int and record_id > 0 for record_id in indexed)
            identities = await transaction.fetch_all(
                "SELECT conceptual_object_id, conceptual_object_name "
                "FROM workflow.conceptual_object "
                "WHERE model_id = %s",
                (model_id,),
            )
            assert identities
            for identity in identities:
                record = review.records_by_id["conceptual_object"][identity["conceptual_object_id"]]
                assert (
                    record.model_dump()["conceptual_object_name"]
                    == identity["conceptual_object_name"]
                )
            current = await load_model_physical_scope(transaction, model)
            assert validate_future_graph(
                snapshot=baseline, staged_documents={}, physical_scope=current
            ).valid
        assert baseline.conceptual.relationships[0].supports[0].support_is_locked
        assert any(entity.sources[0].is_locked for entity in baseline.logical.entities)
        assert any(
            source.is_locked
            for entity in baseline.dimensional.entities
            for source in entity.sources
        )
        with postgres_database.connect_owner() as connection:
            target = connection.execute(
                """
                SELECT object.object_id, attribute.attribute_id
                  FROM core.object AS object
                  JOIN core.attribute AS attribute USING (object_id)
                 WHERE object.source_tenant_id=%s
                   AND object.object_schema=%s AND object.object_name=%s
                   AND attribute.attribute_name=%s
                """,
                (
                    tenant_id,
                    "src" if source_layer == "source" else "silver",
                    "orders" if source_layer == "source" else "Order",
                    "order_id" if source_layer == "source" else "OrderID",
                ),
            ).fetchone()
            assert target is not None
            if record_type == "object":
                connection.execute(
                    "UPDATE core.object SET is_active=FALSE WHERE object_id=%s",
                    (target["object_id"],),
                )
            else:
                connection.execute(
                    "UPDATE core.attribute SET is_active=FALSE WHERE attribute_id=%s",
                    (target["attribute_id"],),
                )
        async with database.read_transaction() as transaction:
            retained = await build_model_snapshot(transaction, model)
            history = await load_model_physical_scope(transaction, model)
            assert retained == baseline
            assert validate_future_graph(
                snapshot=retained, staged_documents={}, physical_scope=history
            ).valid
            # Focused workflow reads continue to omit currently ineligible evidence.
            config = LOGICAL if source_layer == "source" else DIMENSIONAL
            query = entities_sql(config) if record_type == "object" else attributes_sql(config)
            focused = await transaction.fetch_all(query, (model_id, [], [], 100, 0))
            entity_name = "Order" if source_layer == "source" else "SalesFact"
            attribute_name = "OrderID" if source_layer == "source" else "SalesKey"
            name_field = f"{config.layer}_{record_type.replace('object', 'entity')}_name"
            modeled_name = entity_name if record_type == "object" else attribute_name
            focused_record = next(row for row in focused if row[name_field] == modeled_name)
            assert not any(
                evidence["support_source_type"] in {"object", "attribute"}
                for evidence in focused_record["sources"]
            )
            if source_layer == "source" and record_type == "object":
                objects = await transaction.fetch_all(
                    CONCEPTUAL_OBJECTS_SQL, (model_id, [], [], 100, 0)
                )
                relationships = await transaction.fetch_all(
                    CONCEPTUAL_RELATIONSHIPS_SQL, (model_id, [], [], [], 100, 0)
                )
                assert any(not row["supports"] for row in objects)
                assert not relationships[0]["supports"]

        # Placement in this Tenant does not authorize another SourceTenant's evidence.
        _, foreign_tenant = _seed_model_foundation(
            postgres_database, code_prefix=f"FOREIGN_{uuid4().hex}"
        )
        with postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.object SET source_tenant_id=%s WHERE object_id=%s",
                (foreign_tenant, target["object_id"]),
            )
        async with database.read_transaction() as transaction:
            reowned = await build_model_snapshot(transaction, model)
            foreign_scope = await load_model_physical_scope(transaction, model)
        assert not validate_future_graph(
            snapshot=retained, staged_documents={}, physical_scope=foreign_scope
        ).valid
        layer = reowned.logical if source_layer == "source" else reowned.dimensional
        reowned_entity = next(
            entity
            for entity in layer.entities
            if getattr(entity, f"{config.layer}_entity_name") == entity_name
        )
        reowned_attribute = next(
            attribute
            for attribute in layer.attributes
            if getattr(attribute, f"{config.layer}_attribute_name") == attribute_name
        )
        assert not any(source.support_source_type == "object" for source in reowned_entity.sources)
        assert not any(
            source.support_source_type == "attribute" for source in reowned_attribute.sources
        )
        if source_layer == "source":
            assert any(not obj.supports for obj in reowned.conceptual.objects)
            assert not reowned.conceptual.relationships[0].supports
    finally:
        await database.close()
