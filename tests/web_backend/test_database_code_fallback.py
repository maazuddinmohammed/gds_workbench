"""Assertion-defined Mapping remains source-free through Code context selection."""

# Shared disposable fixture seed helpers are intentionally imported.
# pyright: reportPrivateUsage=false

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.web_backend.test_database_mapping_source_context import (
    _seed_assertion_mapping_target,
    _seed_mapping_scope,
)


@pytest.mark.parametrize("dimensional", [False, True])
def test_code_context_covers_default_mapping_without_unrelated_physical_sources(
    web_postgres_database: DisposablePostgres,
    dimensional: bool,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=False, create_run=False)
    entity_id, _ = _seed_assertion_mapping_target(
        web_postgres_database,
        scope,
        dimensional=dimensional,
    )
    layer = "dimensional" if dimensional else "logical"
    entity_type = f"{layer}_entity"
    with web_postgres_database.connect_owner() as connection:
        attribute_id = require_row(
            connection.execute(
                "SELECT modeled_attribute_id FROM workflow.modeled_attribute "
                "WHERE model_id=%s AND modeled_entity_type=%s AND modeled_entity_id=%s",
                (scope.plan.model_id, entity_type, entity_id),
            ).fetchone()
        )["modeled_attribute_id"]
        mapping_id = require_row(
            connection.execute(
                sql.SQL(
                    "INSERT INTO workflow.mapping_object "
                    "(model_id, modeled_entity_type, {}, source_system_id, "
                    "mapping_transformation_document) VALUES (%s,%s,%s,%s,%s) "
                    "RETURNING mapping_object_id"
                ).format(sql.Identifier(f"{layer}_entity_id")),
                (
                    scope.plan.model_id,
                    entity_type,
                    entity_id,
                    scope.source_system_id,
                    Jsonb({"kind": "generated", "rule": "Produce one reference row."}),
                ),
            ).fetchone()
        )["mapping_object_id"]
        connection.execute(
            sql.SQL(
                "INSERT INTO workflow.mapping_attribute "
                "(mapping_object_id, model_id, modeled_entity_type, {}, {}, "
                "attribute_mapping_transformation_document) VALUES (%s,%s,%s,%s,%s,%s)"
            ).format(sql.Identifier(f"{layer}_entity_id"), sql.Identifier(f"{layer}_attribute_id")),
            (
                mapping_id,
                scope.plan.model_id,
                entity_type,
                entity_id,
                attribute_id,
                Jsonb({"kind": "constant", "expression": "1"}),
            ),
        )
        context = require_row(
            connection.execute(
                "SELECT source_system_count, source_context "
                "FROM workflow.list_code_generation_target_context(%s,%s) "
                "WHERE modeled_entity_id=%s",
                (scope.plan.model_id, entity_type, entity_id),
            ).fetchone()
        )

    assert context["source_system_count"] == 1
    assert context["source_context"]["physical_sources"] == []
    assert [
        system["source_system_id"] for system in context["source_context"]["source_systems"]
    ] == [scope.source_system_id]
    assert len(context["source_context"]["object_mappings"]) == 1
    assert len(context["source_context"]["attribute_mappings"]) == 1
    assert context["source_context"]["object_mappings"][0]["entity"]["assertions"]
