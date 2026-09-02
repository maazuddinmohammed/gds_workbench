from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast

from psycopg import Connection

if TYPE_CHECKING:
    from conftest import DisposablePostgres, TestRow


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


def _seed_inputs_and_target_bindings(
    connection: Connection[TestRow], model_id: int
) -> None:
    connection.execute(
        """
        INSERT INTO model.model_input_scope (model_id, object_id)
        SELECT %s, object.object_id
          FROM core.object AS object
         WHERE object.object_schema IN ('source_demo', 'bronze_demo')
        """,
        (model_id,),
    )
    logical_entity_id = _required_int(
        _required_row(
            connection.execute(
                """
                INSERT INTO workflow.logical_entity (
                    model_id,
                    logical_entity_name,
                    logical_entity_definition,
                    logical_entity_type,
                    logical_entity_grain
                ) VALUES (%s, 'Customer', 'Customer', 'core', 'One customer')
                RETURNING logical_entity_id
                """,
                (model_id,),
            ).fetchone()
        ),
        "logical_entity_id",
    )
    dimensional_entity_id = _required_int(
        _required_row(
            connection.execute(
                """
                INSERT INTO workflow.dimensional_entity (
                    model_id,
                    dimensional_entity_name,
                    dimensional_entity_definition,
                    dimensional_entity_type
                ) VALUES (%s, 'DimCustomer', 'Customer dimension', 'dimension')
                RETURNING dimensional_entity_id
                """,
                (model_id,),
            ).fetchone()
        ),
        "dimensional_entity_id",
    )
    connection.execute(
        """
        INSERT INTO workflow.model_object_binding (
            model_id,
            object_id,
            modeled_entity_type,
            logical_entity_id,
            dimensional_entity_id
        )
        SELECT %s,
               object.object_id,
               CASE object.object_schema
                   WHEN 'silver_demo' THEN 'logical_entity'
                   ELSE 'dimensional_entity'
               END,
               CASE object.object_schema
                   WHEN 'silver_demo' THEN %s
               END,
               CASE object.object_schema
                   WHEN 'gold_demo' THEN %s
               END
          FROM core.object AS object
         WHERE object.object_schema IN ('silver_demo', 'gold_demo')
        """,
        (model_id, logical_entity_id, dimensional_entity_id),
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
        _seed_inputs_and_target_bindings(connection, model_id)
        rows = _rows(
            connection.execute(
                "SELECT * FROM workflow.list_model_object_eligibility(%s)",
                (model_id,),
            ).fetchall()
        )

    by_zone = {_required_str(row, "zone_code"): row for row in rows}
    assert set(by_zone) == {"source", "bronze", "silver", "gold"}
    assert {_required_int(row, "object_tenant_id") for row in rows} == {tenant_id}
    assert _required_bool(by_zone["source"], "is_model_input_eligible") is True
    assert _required_bool(by_zone["bronze"], "is_model_input_eligible") is True
    assert _required_bool(by_zone["bronze"], "is_dimensional_source_eligible") is False
    assert (
        _required_bool(by_zone["bronze"], "is_logical_mapping_target_eligible") is False
    )
    assert (
        _required_bool(by_zone["bronze"], "is_dimensional_mapping_target_eligible")
        is False
    )
    assert _required_bool(by_zone["silver"], "is_model_input_eligible") is False
    assert _required_bool(by_zone["silver"], "is_dimensional_source_eligible") is False
    assert (
        _required_bool(by_zone["silver"], "is_logical_mapping_target_eligible") is True
    )
    assert (
        _required_bool(by_zone["silver"], "is_dimensional_mapping_target_eligible")
        is False
    )
    assert _required_bool(by_zone["gold"], "is_model_input_eligible") is False
    assert _required_bool(by_zone["gold"], "is_dimensional_source_eligible") is False
    assert (
        _required_bool(by_zone["gold"], "is_logical_mapping_target_eligible") is False
    )
    assert (
        _required_bool(by_zone["gold"], "is_dimensional_mapping_target_eligible")
        is True
    )


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
        _seed_inputs_and_target_bindings(connection, model_id)
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
    assert set(by_zone) == {"source", "bronze", "silver", "gold"}
    assert all(
        _required_bool(row, "is_model_input_eligible")
        for row in by_zone["source"] + by_zone["bronze"]
    )
    assert all(
        _required_bool(row, "is_logical_mapping_target_eligible")
        for row in by_zone["silver"]
    )
    assert all(
        _required_bool(row, "is_dimensional_mapping_target_eligible")
        for row in by_zone["gold"]
    )
    assert not any(
        _required_bool(row, "is_dimensional_source_eligible") for row in rows
    )


def test_unassigned_gds_object_is_not_workflow_eligible(
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

    assert bronze_object_id not in {int(row["object_id"]) for row in rows}


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

    bronze = next(row for row in rows if _required_str(row, "zone_code") == "bronze")
    assert _required_int(bronze, "object_tenant_id") == tenant_id
    assert _required_bool(bronze, "is_model_input_eligible") is True


def test_only_active_logical_mapping_enables_silver_dimensional_eligibility(
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
                    VALUES (%s, 'Applied Mapping Eligibility Model')
                    RETURNING model_id
                    """,
                    (tenant_id,),
                ).fetchone()
            ),
            "model_id",
        )
        silver = _required_row(
            connection.execute(
                """
                SELECT object.object_id, attribute.attribute_id
                  FROM core.object AS object
                  JOIN core.attribute AS attribute
                    ON attribute.object_id = object.object_id
                 WHERE object.object_schema = 'silver_demo'
                 ORDER BY attribute.attribute_ordinal_position
                 LIMIT 1
                """
            ).fetchone()
        )
        silver_object_id = _required_int(silver, "object_id")
        silver_attribute_id = _required_int(silver, "attribute_id")
        source_system_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    SELECT system_id
                      FROM core.system
                     WHERE system_code = 'DEMO_CUSTOMER_SYSTEM'
                    """
                ).fetchone()
            ),
            "system_id",
        )
        logical_entity_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO workflow.logical_entity (
                        model_id,
                        logical_entity_name,
                        logical_entity_definition,
                        logical_entity_type,
                        logical_entity_grain
                    ) VALUES (%s, 'Customer', 'Customer', 'core', 'One customer')
                    RETURNING logical_entity_id
                    """,
                    (model_id,),
                ).fetchone()
            ),
            "logical_entity_id",
        )
        logical_attribute_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO workflow.logical_attribute (
                        model_id,
                        logical_entity_id,
                        logical_attribute_name,
                        logical_attribute_definition,
                        logical_attribute_data_type,
                        logical_attribute_ordinal_position
                    ) VALUES (
                        %s, %s, 'CustomerID', 'Customer ID', 'bigint', 1
                    )
                    RETURNING logical_attribute_id
                    """,
                    (model_id, logical_entity_id),
                ).fetchone()
            ),
            "logical_attribute_id",
        )
        binding_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO workflow.model_object_binding (
                        model_id,
                        object_id,
                        modeled_entity_type,
                        logical_entity_id
                    ) VALUES (%s, %s, 'logical_entity', %s)
                    RETURNING model_object_binding_id
                    """,
                    (model_id, silver_object_id, logical_entity_id),
                ).fetchone()
            ),
            "model_object_binding_id",
        )
        attribute_binding_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO workflow.model_attribute_binding (
                        model_object_binding_id,
                        logical_attribute_id,
                        attribute_id
                    ) VALUES (%s, %s, %s)
                    RETURNING model_attribute_binding_id
                    """,
                    (binding_id, logical_attribute_id, silver_attribute_id),
                ).fetchone()
            ),
            "model_attribute_binding_id",
        )
        connection.execute(
            """
            INSERT INTO workflow.mapping_source_system_dependency (
                model_id,
                modeled_entity_type,
                source_system_id,
                mapping_source_system_dependency_status
            ) VALUES (%s, 'logical_entity', %s, 'active')
            """,
            (model_id, source_system_id),
        )
        mapping_object_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO workflow.mapping_object (
                        model_id,
                        model_object_binding_id,
                        source_system_id,
                        mapping_transformation_document,
                        object_mapping_status
                    ) VALUES (%s, %s, %s, '{"kind":"direct"}'::JSONB, 'inactive')
                    RETURNING mapping_object_id
                    """,
                    (model_id, binding_id, source_system_id),
                ).fetchone()
            ),
            "mapping_object_id",
        )

        object_before = _required_row(
            connection.execute(
                """
                SELECT *
                  FROM workflow.list_model_object_eligibility(%s)
                 WHERE object_id = %s
                """,
                (model_id, silver_object_id),
            ).fetchone()
        )
        attribute_before = _required_row(
            connection.execute(
                """
                SELECT *
                  FROM workflow.list_model_attribute_eligibility(%s)
                 WHERE attribute_id = %s
                """,
                (model_id, silver_attribute_id),
            ).fetchone()
        )
        connection.execute(
            """
            INSERT INTO workflow.mapping_attribute (
                mapping_object_id,
                model_attribute_binding_id,
                attribute_mapping_transformation_document,
                attribute_mapping_status
            ) VALUES (%s, %s, '{"expression":"CustomerID"}'::JSONB, 'inactive')
            """,
            (mapping_object_id, attribute_binding_id),
        )
        attribute_inactive = _required_row(
            connection.execute(
                """
                SELECT *
                  FROM workflow.list_model_attribute_eligibility(%s)
                 WHERE attribute_id = %s
                """,
                (model_id, silver_attribute_id),
            ).fetchone()
        )
        connection.execute(
            """
            UPDATE workflow.mapping_object
               SET object_mapping_status = 'active'
             WHERE mapping_object_id = %s
            """,
            (mapping_object_id,),
        )
        connection.execute(
            """
            UPDATE workflow.mapping_attribute
               SET attribute_mapping_status = 'active'
             WHERE mapping_object_id = %s
            """,
            (mapping_object_id,),
        )
        object_active = _required_row(
            connection.execute(
                """
                SELECT *
                  FROM workflow.list_model_object_eligibility(%s)
                 WHERE object_id = %s
                """,
                (model_id, silver_object_id),
            ).fetchone()
        )
        attribute_active = _required_row(
            connection.execute(
                """
                SELECT *
                  FROM workflow.list_model_attribute_eligibility(%s)
                 WHERE attribute_id = %s
                """,
                (model_id, silver_attribute_id),
            ).fetchone()
        )

    assert _required_bool(object_before, "is_dimensional_source_eligible") is False
    assert _required_bool(attribute_before, "is_dimensional_source_eligible") is False
    assert _required_bool(attribute_inactive, "is_dimensional_source_eligible") is False
    assert _required_bool(object_active, "is_dimensional_source_eligible") is True
    assert _required_bool(attribute_active, "is_dimensional_source_eligible") is True


def test_fresh_model_can_add_unscoped_inputs_and_unbound_targets(
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
        assert _required_bool(by_zone["silver"], "is_logical_mapping_target_eligible")
        assert _required_bool(by_zone["gold"], "is_dimensional_mapping_target_eligible")

        connection.execute(
            """
            INSERT INTO model.model_input_scope (model_id, object_id)
            VALUES (%s, %s)
            """,
            (model_id, _required_int(by_zone["bronze"], "object_id")),
        )
        logical_entity_id = _required_int(
            _required_row(
                connection.execute(
                    """
                    INSERT INTO workflow.logical_entity (
                        model_id, logical_entity_name, logical_entity_definition,
                        logical_entity_type, logical_entity_grain
                    ) VALUES (%s, 'Customer', 'Customer', 'core', 'One customer')
                    RETURNING logical_entity_id
                    """,
                    (model_id,),
                ).fetchone()
            ),
            "logical_entity_id",
        )
        binding = _required_row(
            connection.execute(
                """
                INSERT INTO workflow.model_object_binding (
                    model_id, object_id, modeled_entity_type, logical_entity_id
                ) VALUES (%s, %s, 'logical_entity', %s)
                RETURNING model_object_binding_id, object_id
                """,
                (
                    model_id,
                    _required_int(by_zone["silver"], "object_id"),
                    logical_entity_id,
                ),
            ).fetchone()
        )

    assert _required_int(binding, "object_id") == _required_int(
        by_zone["silver"], "object_id"
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
