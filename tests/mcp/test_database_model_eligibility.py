from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast

from psycopg import Connection

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres, TestRow


DATABASE_ROOT = Path(__file__).resolve().parents[2] / "database"
type DatabaseRow = dict[str, object]


def _required_row(row: TestRow | None) -> DatabaseRow:
    assert row is not None
    return cast(DatabaseRow, row)


def _required_int(row: DatabaseRow, field: str) -> int:
    value = row[field]
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _required_str(row: DatabaseRow, field: str) -> str:
    value = row[field]
    assert isinstance(value, str)
    return value


def _required_bool(row: DatabaseRow, field: str) -> bool:
    value = row[field]
    assert isinstance(value, bool)
    return value


def _rows(rows: list[TestRow]) -> list[DatabaseRow]:
    return cast(list[DatabaseRow], rows)


def _seed_demo_if_needed(connection: Connection[TestRow]) -> None:
    exists = connection.execute(
        "SELECT 1 FROM core.project WHERE project_code = 'DEMO_PROJECT'"
    ).fetchone()
    if exists is None:
        connection.execute(
            cast(
                LiteralString,
                (DATABASE_ROOT / "seed" / "01_metadata_snapshot_demo.sql").read_text(
                    encoding="utf-8"
                ),
            )
        )


def _seed_inputs(connection: Connection[TestRow], model_id: int) -> None:
    connection.execute(
        """
        INSERT INTO model.model_input_scope (model_id, object_id)
        SELECT %s, object.object_id
          FROM core.object AS object
         WHERE object.object_schema IN ('source_demo', 'bronze_demo')
        """,
        (model_id,),
    )


def test_model_object_eligibility_routes_active_scoped_zones(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        tenant_id = _required_int(
            _required_row(
                connection.execute(
                    "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
                ).fetchone()
            ),
            "tenant_id",
        )
        model_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO model.model (tenant_id, model_name)
                    VALUES (%s, 'Eligibility Model')
                    RETURNING model_id
                    """,
                    (tenant_id,),
                ).fetchone()
            ),
            "model_id",
        )
        _seed_inputs(connection, model_id)
        rows = _rows(
            connection.execute(
                "SELECT * FROM workflow.list_model_object_eligibility(%s)",
                (model_id,),
            ).fetchall()
        )

    rows = [row for row in rows if _required_int(row, "object_tenant_id") == tenant_id]
    by_zone = {_required_str(row, "zone_code"): row for row in rows}
    assert set(by_zone) == {"source", "bronze"}
    assert {_required_int(row, "object_tenant_id") for row in rows} == {tenant_id}
    assert _required_bool(by_zone["source"], "is_model_input_eligible") is True
    assert _required_bool(by_zone["bronze"], "is_model_input_eligible") is True


def test_model_attribute_eligibility_routes_active_scoped_zones(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        tenant_id = _required_int(
            _required_row(
                connection.execute(
                    "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
                ).fetchone()
            ),
            "tenant_id",
        )
        model_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO model.model (tenant_id, model_name)
                    VALUES (%s, 'Attribute Eligibility Model')
                    RETURNING model_id
                    """,
                    (tenant_id,),
                ).fetchone()
            ),
            "model_id",
        )
        _seed_inputs(connection, model_id)
        rows = _rows(
            connection.execute(
                "SELECT * FROM workflow.list_model_attribute_eligibility(%s)",
                (model_id,),
            ).fetchall()
        )

    assert rows
    by_zone: dict[str, list[DatabaseRow]] = {}
    for row in rows:
        by_zone.setdefault(_required_str(row, "zone_code"), []).append(row)
    assert set(by_zone) == {"source", "bronze"}
    assert all(
        _required_bool(row, "is_model_input_eligible")
        for row in by_zone["source"] + by_zone["bronze"]
    )


def test_source_owner_transfer_does_not_implicitly_remove_model_input(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        tenant_id = _required_int(
            _required_row(
                connection.execute(
                    "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
                ).fetchone()
            ),
            "tenant_id",
        )
        model_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO model.model (tenant_id, model_name)
                    VALUES (%s, 'Unassigned GDS Eligibility Model')
                    RETURNING model_id
                    """,
                    (tenant_id,),
                ).fetchone()
            ),
            "model_id",
        )
        bronze_object_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    SELECT object_record.object_id
                      FROM core.object AS object_record
                     WHERE object_record.object_schema = 'bronze_demo'
                    """
                ).fetchone()
            ),
            "object_id",
        )
        connection.execute(
            "INSERT INTO model.model_input_scope (model_id, object_id) VALUES (%s, %s)",
            (model_id, bronze_object_id),
        )
        connection.execute(
            """
            UPDATE core.object AS object_record
               SET source_tenant_id = connection.tenant_id
              FROM core.connection AS connection
             WHERE connection.connection_id = object_record.connection_id
               AND object_record.object_id = %s
            """,
            (bronze_object_id,),
        )
        rows = connection.execute(
            "SELECT * FROM workflow.list_model_object_eligibility(%s)",
            (model_id,),
        ).fetchall()
        connection.rollback()

    assert bronze_object_id in {int(row["object_id"]) for row in rows}
    # Structural eligibility is separate from the caller's Source Tenant access.


def test_gds_eligibility_uses_assigned_tenant_when_connection_owner_is_inactive(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        tenant_id = _required_int(
            _required_row(
                connection.execute(
                    "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
                ).fetchone()
            ),
            "tenant_id",
        )
        model_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO model.model (tenant_id, model_name)
                    VALUES (%s, 'Inactive GDS Owner Eligibility Model')
                    RETURNING model_id
                    """,
                    (tenant_id,),
                ).fetchone()
            ),
            "model_id",
        )
        connection.execute(
            """
            INSERT INTO model.model_input_scope (model_id, object_id)
            SELECT %s, object_record.object_id
              FROM core.object AS object_record
             WHERE object_record.object_schema = 'bronze_demo'
            """,
            (model_id,),
        )
        connection.execute(
            """
            UPDATE core.tenant
               SET is_active = FALSE
             WHERE tenant_code = 'DEMO_GDS_TENANT'
            """
        )
        rows = _rows(
            connection.execute(
                "SELECT * FROM workflow.list_model_object_eligibility(%s)",
                (model_id,),
            ).fetchall()
        )
        connection.rollback()

    bronze = next(
        row
        for row in rows
        if _required_str(row, "zone_code") == "bronze"
        and _required_int(row, "object_tenant_id") == tenant_id
    )
    assert _required_int(bronze, "object_tenant_id") == tenant_id
    assert _required_bool(bronze, "is_model_input_eligible") is True


def test_dimensional_mapping_sources_are_logical_entities_with_applied_mapping(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        tenant = _required_row(
            connection.execute(
                "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
            ).fetchone()
        )
        model = _required_row(
            connection.execute(
                "INSERT INTO model.model (tenant_id,model_name,logical_schemas,dimensional_schemas) "
                'VALUES (%s,\'Logical source eligibility\',\'[{"schema_name":"silver","description":null}]\','
                '\'[{"schema_name":"gold","description":null}]\') RETURNING model_id',
                (tenant["tenant_id"],),
            ).fetchone()
        )
        logical = _required_row(
            connection.execute(
                "INSERT INTO workflow.logical_entity (model_id,logical_entity_schema_name,logical_entity_name,logical_entity_definition,logical_entity_type,logical_entity_grain) "
                "VALUES (%s,'silver','Customer','Customer','core','One customer') RETURNING logical_entity_id",
                (model["model_id"],),
            ).fetchone()
        )
        dimensional = _required_row(
            connection.execute(
                "INSERT INTO workflow.dimensional_entity (model_id,dimensional_entity_schema_name,dimensional_entity_name,dimensional_entity_definition,dimensional_entity_type) "
                "VALUES (%s,'gold','Customer','Customer','dimension') RETURNING dimensional_entity_id",
                (model["model_id"],),
            ).fetchone()
        )
        system = _required_row(
            connection.execute(
                "SELECT system_id FROM core.system WHERE system_code = 'DEMO_CUSTOMER_SYSTEM'"
            ).fetchone()
        )
        parameters = (
            model["model_id"],
            dimensional["dimensional_entity_id"],
            system["system_id"],
        )
        assert (
            connection.execute(
                "SELECT * FROM workflow.list_mapping_source_objects(%s,%s,'dimensional_entity',%s)",
                parameters,
            ).fetchall()
            == []
        )
        mapping = _required_row(
            connection.execute(
                "INSERT INTO workflow.mapping_object (model_id,modeled_entity_type,logical_entity_id,source_system_id,mapping_transformation_document) "
                "VALUES (%s,'logical_entity',%s,%s,'{}') RETURNING mapping_object_id",
                (model["model_id"], logical["logical_entity_id"], system["system_id"]),
            ).fetchone()
        )
        sources = connection.execute(
            "SELECT * FROM workflow.list_mapping_source_objects(%s,%s,'dimensional_entity',%s)",
            parameters,
        ).fetchall()
        assert (
            len(sources) == 1
            and sources[0]["source_logical_entity_id"] == logical["logical_entity_id"]
        )
        assert sources[0]["source_object_id"] is None
        connection.execute(
            "UPDATE workflow.mapping_object SET object_mapping_status = 'inactive' WHERE mapping_object_id = %s",
            (mapping["mapping_object_id"],),
        )
        assert (
            connection.execute(
                "SELECT * FROM workflow.list_mapping_source_objects(%s,%s,'dimensional_entity',%s)",
                parameters,
            ).fetchall()
            == []
        )


def test_fresh_model_can_add_unscoped_inputs_without_registered_targets(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        _seed_demo_if_needed(connection)
        tenant_id = _required_int(
            _required_row(
                connection.execute(
                    "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
                ).fetchone()
            ),
            "tenant_id",
        )
        model_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO model.model (tenant_id, model_name)
                    VALUES (%s, 'Fresh Eligibility Model')
                    RETURNING model_id
                    """,
                    (tenant_id,),
                ).fetchone()
            ),
            "model_id",
        )
        rows = _rows(
            connection.execute(
                "SELECT * FROM workflow.list_model_object_eligibility(%s)",
                (model_id,),
            ).fetchall()
        )
        by_zone = {_required_str(row, "zone_code"): row for row in rows}
        assert _required_bool(by_zone["source"], "is_model_input_eligible")
        assert _required_bool(by_zone["bronze"], "is_model_input_eligible")
        assert set(by_zone) == {"source", "bronze"}

        connection.execute(
            """
            INSERT INTO model.model_input_scope (model_id, object_id)
            VALUES (%s, %s)
            """,
            (model_id, _required_int(by_zone["bronze"], "object_id")),
        )


def test_model_eligibility_is_internal_to_the_runtime_roles(
    postgres_database: DisposablePostgres,
) -> None:
    signatures = (
        "workflow.list_model_object_eligibility(bigint)",
        "workflow.list_model_attribute_eligibility(bigint)",
    )
    with postgres_database.connect_owner() as connection:
        rows = _rows(
            connection.execute(
                """
                SELECT signature,
                       has_function_privilege('public', signature, 'EXECUTE')
                           AS public_execute,
                       has_function_privilege('gds_app_write', signature, 'EXECUTE')
                           AS mcp_execute,
                       has_function_privilege('gds_web_write', signature, 'EXECUTE')
                           AS web_execute
                  FROM unnest(%s::TEXT[]) AS signature
                """,
                (list(signatures),),
            ).fetchall()
        )

    assert len(rows) == 2
    assert not any(_required_bool(row, "public_execute") for row in rows)
    assert all(_required_bool(row, "mcp_execute") for row in rows)
    assert all(_required_bool(row, "web_execute") for row in rows)
