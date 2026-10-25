"""Complete snapshots preserve owned physical evidence through deactivation."""

from copy import deepcopy
from typing import Literal, cast
from uuid import uuid4

import pytest
from gds_etl_workbench.application.change_sets.project import (
    load_project_physical_scope,
)
from gds_etl_workbench.application.change_sets.project_apply import ProjectMaterializer
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.application.project_snapshot import (
    build_project_snapshot,
    read_project_review_snapshot,
)
from gds_etl_workbench.application.modeling.modeled_layer import (
    DIMENSIONAL,
    LOGICAL,
    attributes_sql,
    entities_sql,
)
from gds_etl_workbench.application.modeling.subject_area import (
    CURRENT_SUBJECT_AREA_TABLES_SQL,
)
from gds_etl_workbench.domain.snapshots.project import project_snapshot_records

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.project_test_fixtures import (
    complete_project_graph,
)
from tests.mcp.test_database_project_change_set_round_trip import (
    _replace_codes,  # pyright: ignore[reportPrivateUsage]
    _seed_project_foundation,  # pyright: ignore[reportPrivateUsage]
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
    project_id, tenant_id = _seed_project_foundation(
        postgres_database, code_prefix=prefix
    )
    graph = complete_project_graph()
    # Cover locked evidence on both modeled layers and locked Subject Area tables.
    graph["dimensional_entity"][0]["sources"] = [
        {
            "support_source_type": "logical_entity",
            "source_logical_entity": {
                "logical_entity_schema_name": "silver",
                "logical_entity_name": "Order",
            },
            "source_order": 1,
            "rationale": "Applied Logical mapping contribution.",
            "status": "active",
            "is_locked": True,
        }
    ]
    graph["dimensional_attribute"][0]["sources"] = [
        {
            "support_source_type": "logical_attribute",
            "source_logical_attribute": {
                "logical_entity_schema_name": "silver",
                "logical_entity_name": "Order",
                "logical_attribute_name": "OrderID",
            },
            "source_order": 1,
            "rationale": "Applied Logical mapping contribution.",
            "status": "active",
            "is_locked": True,
        }
    ]
    for dataset in ("logical_entity", "logical_attribute"):
        for record in graph[dataset]:
            for evidence in cast(list[dict[str, object]], record["sources"]):
                evidence["is_locked"] = True
    for membership in graph["subject_area_table"]:
        membership["subject_area_table_is_locked"] = True
    staged = _replace_codes(graph, code_prefix=prefix)
    initial = deepcopy(staged)
    for dataset in ("dimensional_entity", "dimensional_attribute"):
        initial[dataset][0]["sources"] = _replace_codes(
            complete_project_graph(), code_prefix=prefix
        )[dataset][0]["sources"]
    project = ProjectReadContext(
        project_id=project_id,
        tenant_id=tenant_id,
        project_name="Project Tool Round Trip",
        project_revision=1,
    )
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        async with database.write_transaction() as transaction:
            empty = await build_project_snapshot(transaction, project)
            physical = await load_project_physical_scope(transaction, project)
            authored = validate_future_graph(
                snapshot=empty, staged_documents=initial, physical_scope=physical
            )
            assert authored.valid
            await ProjectMaterializer(transaction, project_id, "a" * 64).apply(
                authored.records
            )
            # Dimensional evidence references the applied Logical definition.
            applied = await build_project_snapshot(transaction, project)
            physical = await load_project_physical_scope(transaction, project)
            dimensional = validate_future_graph(
                snapshot=applied,
                staged_documents={
                    "dimensional_entity": staged["dimensional_entity"],
                    "dimensional_attribute": staged["dimensional_attribute"],
                },
                physical_scope=physical,
            )
            assert dimensional.valid
            await ProjectMaterializer(transaction, project_id, "b" * 64).apply(
                dimensional.records
            )
        async with database.read_transaction() as transaction:
            baseline = await build_project_snapshot(transaction, project)
            review = await read_project_review_snapshot(transaction, project)
            assert review.snapshot == baseline
            canonical_records = project_snapshot_records(baseline)
            for dataset, indexed in review.records_by_id.items():
                assert len(indexed) == len(canonical_records[dataset])
                assert all(
                    record in canonical_records[dataset] for record in indexed.values()
                )
                assert all(
                    (isinstance(record_id, str) and len(record_id) == 36)
                    if dataset == "context_record"
                    else (type(record_id) is int and record_id > 0)
                    for record_id in indexed
                )
            identities = await transaction.fetch_all(
                "SELECT subject_area_id, subject_area_name "
                "FROM workflow.subject_area "
                "WHERE project_id = %s",
                (project_id,),
            )
            assert identities
            for identity in identities:
                record = review.records_by_id["subject_area"][
                    identity["subject_area_id"]
                ]
                assert (
                    record.model_dump()["subject_area_name"]
                    == identity["subject_area_name"]
                )
            current = await load_project_physical_scope(transaction, project)
            assert validate_future_graph(
                snapshot=baseline, staged_documents={}, physical_scope=current
            ).valid
        assert [
            (table.object_name, table.subject_area_table_is_locked)
            for table in baseline.subject_area.tables
        ] == [("customers", True), ("orders", True)]
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
            retained = await build_project_snapshot(transaction, project)
            history = await load_project_physical_scope(transaction, project)
            assert retained == baseline
            assert validate_future_graph(
                snapshot=retained, staged_documents={}, physical_scope=history
            ).valid
            # Focused workflow reads continue to omit currently ineligible evidence.
            config = LOGICAL if source_layer == "source" else DIMENSIONAL
            query = (
                entities_sql(config)
                if record_type == "object"
                else attributes_sql(config)
            )
            focused = await transaction.fetch_all(query, (project_id, [], [], 100, 0))
            entity_name = "Order" if source_layer == "source" else "SalesFact"
            attribute_name = "OrderID" if source_layer == "source" else "SalesKey"
            name_field = (
                f"{config.layer}_{record_type.replace('object', 'entity')}_name"
            )
            modeled_name = entity_name if record_type == "object" else attribute_name
            focused_record = next(
                row for row in focused if row[name_field] == modeled_name
            )
            assert not any(
                evidence["support_source_type"] in {"object", "attribute"}
                for evidence in focused_record["sources"]
            )
            # The complete snapshot keeps the membership; the focused read hides a
            # table that left eligible Scope.
            memberships = await transaction.fetch_all(
                CURRENT_SUBJECT_AREA_TABLES_SQL,
                (project_id, project_id, project_id, [], 100, 0),
            )
            assert [row["object_name"] for row in memberships] == (
                ["customers"]
                if source_layer == "source" and record_type == "object"
                else ["customers", "orders"]
            )

        # Placement in this Tenant does not authorize another SourceTenant's evidence.
        _, foreign_tenant = _seed_project_foundation(
            postgres_database, code_prefix=f"FOREIGN_{uuid4().hex}"
        )
        with postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.object SET source_tenant_id=%s WHERE object_id=%s",
                (foreign_tenant, target["object_id"]),
            )
        async with database.read_transaction() as transaction:
            reowned = await build_project_snapshot(transaction, project)
            foreign_scope = await load_project_physical_scope(transaction, project)
        assert validate_future_graph(
            snapshot=retained, staged_documents={}, physical_scope=foreign_scope
        ).valid is (source_layer == "silver")
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
        assert not any(
            source.support_source_type == "object" for source in reowned_entity.sources
        )
        assert not any(
            source.support_source_type == "attribute"
            for source in reowned_attribute.sources
        )
        # Subject Area tables are src Objects, so only the source case hides one.
        assert [table.object_name for table in reowned.subject_area.tables] == (
            ["customers"] if source_layer == "source" else ["customers", "orders"]
        )
    finally:
        await database.close()
