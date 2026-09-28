"""Code context preserves transformation semantics independently of runtime order."""

# Reuse the governed fixture's existing Entity and complete Mapping.
# pyright: reportPrivateUsage=false

from typing import LiteralString

from gds_etl_workbench.application.mapping_context import project_mapping_inputs
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_database_mapping_source_context import _seed_mapping_scope
from tests.web_backend.test_database_model_change_sets import _required_id


def test_code_system_sort_is_not_entity_order_or_runtime_precedence(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=False, create_run=False)
    model_id = scope.plan.model_id
    entity_id = scope.logical_entity_id
    context_sql: LiteralString = """
        SELECT code_input_digest, source_context
          FROM workflow.list_code_generation_target_context(%s, 'logical_entity', NULL)
         WHERE modeled_entity_id = %s
    """
    with web_postgres_database.connect_owner() as connection:
        original = connection.execute(
            "SELECT system_type_id FROM core.system WHERE system_id=%s",
            (scope.source_system_id,),
        ).fetchone()
        assert original is not None
        # Deliberately insert the alphabetically later branch first, with lower Entity order.
        z_code, a_code = f"Z_{model_id}", f"A_{model_id}"
        connection.execute(
            "UPDATE core.system SET system_code=%s WHERE system_id=%s",
            (z_code, scope.source_system_id),
        )
        other_system_id = _required_id(
            connection.execute(
                """INSERT INTO core.system (system_code, system_name, system_type_id)
                   VALUES (%s, 'Earlier alphabetical source', %s) RETURNING system_id""",
                (a_code, original["system_type_id"]),
            ).fetchone(),
            "system_id",
        )
        precedence = {"source_precedence": [z_code, a_code], "rule": "First non-null value wins"}
        connection.execute(
            """UPDATE workflow.mapping_object
                  SET object_dependency_order=1, mapping_transformation_document=%s
                WHERE model_id=%s AND logical_entity_id=%s""",
            (Jsonb(precedence), model_id, entity_id),
        )
        new_mapping_id = _required_id(
            connection.execute(
                """INSERT INTO workflow.mapping_object (
                       model_id, modeled_entity_type, logical_entity_id, source_system_id,
                       object_dependency_order, mapping_transformation_document
                   ) VALUES (%s, 'logical_entity', %s, %s, 20, %s)
                   RETURNING mapping_object_id""",
                (model_id, entity_id, other_system_id, Jsonb(precedence)),
            ).fetchone(),
            "mapping_object_id",
        )
        connection.execute(
            """INSERT INTO workflow.mapping_attribute (
                   mapping_object_id, model_id, modeled_entity_type, logical_entity_id,
                   logical_attribute_id, attribute_mapping_transformation_document
               ) SELECT %s, model_id, 'logical_entity', logical_entity_id,
                        logical_attribute_id, '{}'::JSONB
                   FROM workflow.logical_attribute
                  WHERE model_id=%s AND logical_entity_id=%s""",
            (new_mapping_id, model_id, entity_id),
        )
        initial = connection.execute(context_sql, (model_id, entity_id)).fetchone()
        assert initial is not None
        raw = initial["source_context"]
        assert raw["consumer_context_version"] == "entity-3"
        assert [row["system_code"] for row in raw["source_systems"]] == [a_code, z_code]
        assert all("dependency_order" not in row for row in raw["source_systems"])
        assert [row["object_dependency_order"] for row in raw["object_mappings"]] == [20, 1]
        assert all(row["transformation"] == precedence for row in raw["object_mappings"])
        public = project_mapping_inputs(raw)
        assert [row["system_code"] for row in public["source_systems"]] == [a_code, z_code]
        assert all("dependency_order" not in row for row in public["source_systems"])
        assert all(row["transformation"] == precedence for row in public["object_transformations"])

        copy_group_id = _required_id(
            connection.execute(
                """INSERT INTO core.copy_group (tenant_id, system_id, copy_group_name)
                   VALUES (%s, %s, 'Runtime scheduling fixture') RETURNING copy_group_id""",
                (scope.tenant_id, scope.source_system_id),
            ).fetchone(),
            "copy_group_id",
        )
        process_group_id = _required_id(
            connection.execute(
                """INSERT INTO core.process_group (
                       tenant_id, system_id, zone_id, copy_group_id,
                       process_group_name, process_group_dependency_order
                   ) SELECT %s, %s, zone_id, %s, 'Runtime scheduling fixture', 1
                       FROM core.object WHERE object_id=%s
                   RETURNING process_group_id""",
                (scope.tenant_id, scope.source_system_id, copy_group_id, scope.bronze_object_id),
            ).fetchone(),
            "process_group_id",
        )
        connection.execute(
            "UPDATE core.process_group SET process_group_dependency_order=50 "
            "WHERE process_group_id=%s",
            (process_group_id,),
        )
        assert connection.execute(context_sql, (model_id, entity_id)).fetchone() == initial

        # A genuine transformation-precedence edit still makes generated Code stale.
        connection.execute(
            "UPDATE workflow.mapping_object SET mapping_transformation_document=%s "
            "WHERE mapping_object_id=%s",
            (Jsonb({**precedence, "source_precedence": [a_code, z_code]}), new_mapping_id),
        )
        changed = connection.execute(context_sql, (model_id, entity_id)).fetchone()
        assert changed is not None
        assert changed["code_input_digest"] != initial["code_input_digest"]
