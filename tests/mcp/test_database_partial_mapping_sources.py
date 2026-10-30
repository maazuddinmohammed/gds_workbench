from __future__ import annotations

# pyright: reportPrivateUsage=false

from typing import TYPE_CHECKING, Literal

import pytest
from psycopg import sql

from tests.mcp.test_database_project_eligibility import (
    _required_row,
    _seed_demo_if_needed,
)

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres


# A peer lookup needs a saved Mapping for its System. A Dimensional pair's Logical inputs
# instead follow lineage (test_dimensional_mapping_sources_are_logical_entities_the_system_feeds).
@pytest.mark.parametrize(
    ("source_layer", "target_layer"),
    [
        ("logical", "logical"),
        ("dimensional", "dimensional"),
    ],
)
def test_peer_lookup_needs_a_saved_mapping_for_its_system(
    postgres_database: DisposablePostgres,
    source_layer: Literal["logical", "dimensional"],
    target_layer: Literal["logical", "dimensional"],
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        tenant = _required_row(
            connection.execute(
                "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
            ).fetchone()
        )
        system = _required_row(
            connection.execute(
                "SELECT system_id FROM core.system WHERE system_code = 'DEMO_CUSTOMER_SYSTEM'"
            ).fetchone()
        )
        project = _required_row(
            connection.execute(
                """INSERT INTO project.project (tenant_id,project_name,logical_schemas,dimensional_schemas)
                   VALUES (%s,%s,'[{"schema_name":"silver","description":null}]',
                           '[{"schema_name":"gold","description":null}]') RETURNING project_id""",
                (tenant["tenant_id"], f"Partial peer {source_layer} to {target_layer}"),
            ).fetchone()
        )
        entity_ids: list[object] = []
        for layer, name in [(source_layer, "Lookup"), (target_layer, "Consumer")]:
            entity = _required_row(
                connection.execute(
                    sql.SQL(
                        "INSERT INTO workflow.{} (project_id,{},{},{},{},{}) "
                        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING {} AS entity_id"
                    ).format(
                        sql.Identifier(f"{layer}_entity"),
                        sql.Identifier(f"{layer}_entity_schema_name"),
                        sql.Identifier(f"{layer}_entity_name"),
                        sql.Identifier(f"{layer}_entity_definition"),
                        sql.Identifier(f"{layer}_entity_type"),
                        sql.Identifier(
                            f"{layer}_entity_grain"
                            if layer == "logical"
                            else "dimensional_entity_grain_definition"
                        ),
                        sql.Identifier(f"{layer}_entity_id"),
                    ),
                    (
                        project["project_id"],
                        "silver" if layer == "logical" else "gold",
                        name,
                        "Synthetic source eligibility fixture",
                        "core" if layer == "logical" else "dimension",
                        "One row per key",
                    ),
                ).fetchone()
            )
            entity_ids.append(entity["entity_id"])
        attribute_ids: list[object] = []
        for ordinal, name in enumerate(["Key", "Name"], 1):
            columns = [
                f"{source_layer}_entity_id",
                f"{source_layer}_attribute_name",
                f"{source_layer}_attribute_definition",
                f"{source_layer}_attribute_data_type",
                f"{source_layer}_attribute_ordinal_position",
            ]
            values = [entity_ids[0], name, "Synthetic source field", "STRING", ordinal]
            attribute = _required_row(
                connection.execute(
                    sql.SQL(
                        "INSERT INTO workflow.{} (project_id,{}) VALUES (%s,{}) RETURNING {} AS attribute_id"
                    ).format(
                        sql.Identifier(f"{source_layer}_attribute"),
                        sql.SQL(",").join(map(sql.Identifier, columns)),
                        sql.SQL(",").join(sql.Placeholder() for _ in values),
                        sql.Identifier(f"{source_layer}_attribute_id"),
                    ),
                    (project["project_id"], *values),
                ).fetchone()
            )
            attribute_ids.append(attribute["attribute_id"])
        mapping = _required_row(
            connection.execute(
                sql.SQL(
                    "INSERT INTO workflow.mapping_object (project_id,modeled_entity_type,{},"
                    "source_system_id,mapping_transformation_document) VALUES (%s,%s,%s,%s,NULL) "
                    "RETURNING mapping_object_id"
                ).format(sql.Identifier(f"{source_layer}_entity_id")),
                (
                    project["project_id"],
                    f"{source_layer}_entity",
                    entity_ids[0],
                    system["system_id"],
                ),
            ).fetchone()
        )
        parameters = (
            project["project_id"],
            entity_ids[1],
            f"{target_layer}_entity",
            system["system_id"],
        )
        query = "SELECT * FROM workflow.list_mapping_source_objects(%s,%s,%s,%s)"
        # An empty Mapping, a blank rule and an inactive rule save nothing for the System.
        assert connection.execute(query, parameters).fetchall() == []
        rule = _required_row(
            connection.execute(
                sql.SQL(
                    "INSERT INTO workflow.mapping_attribute (mapping_object_id,project_id,"
                    "modeled_entity_type,{},{},attribute_mapping_transformation_document) "
                    "VALUES (%s,%s,%s,%s,%s,NULL) RETURNING mapping_attribute_id"
                ).format(
                    sql.Identifier(f"{source_layer}_entity_id"),
                    sql.Identifier(f"{source_layer}_attribute_id"),
                ),
                (
                    mapping["mapping_object_id"],
                    project["project_id"],
                    f"{source_layer}_entity",
                    entity_ids[0],
                    attribute_ids[0],
                ),
            ).fetchone()
        )
        assert connection.execute(query, parameters).fetchall() == []
        connection.execute(
            "UPDATE workflow.mapping_attribute SET attribute_mapping_transformation_document='{}', "
            "attribute_mapping_status='inactive' WHERE mapping_attribute_id=%s",
            (rule["mapping_attribute_id"],),
        )
        assert connection.execute(query, parameters).fetchall() == []
        # One saved rule is enough, though the other Attribute has none: the lookup reads
        # the saved key rule and reports anything still missing.
        connection.execute(
            "UPDATE workflow.mapping_attribute SET attribute_mapping_status='active' "
            "WHERE mapping_attribute_id=%s",
            (rule["mapping_attribute_id"],),
        )
        sources = connection.execute(query, parameters).fetchall()
        assert len(sources) == 1
        assert sources[0][f"source_{source_layer}_entity_id"] == entity_ids[0]
        connection.execute(
            "UPDATE workflow.mapping_object SET object_mapping_status='inactive' "
            "WHERE mapping_object_id=%s",
            (mapping["mapping_object_id"],),
        )
        assert connection.execute(query, parameters).fetchall() == []
