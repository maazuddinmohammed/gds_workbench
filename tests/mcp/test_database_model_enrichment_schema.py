"""Model enrichment storage constraints, using only disposable PostgreSQL."""

# pyright: reportPrivateUsage=false

from uuid import uuid4

import pytest
from psycopg import sql
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_metadata_enrichment_registration import _context, _create
from tests.mcp.test_database_profiling_persistence import _seed_attributes


def test_enrichment_is_independent_per_model_and_preserves_physical_metadata(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    database = bootstrap_postgres_database
    context = _context(database)
    object_id, attribute_id = _seed_attributes(database, context)[0]
    with database.connect_owner() as connection:
        other_model_id = require_row(
            connection.execute(
                """
                INSERT INTO model.model (tenant_id, model_name)
                VALUES (%s, %s) RETURNING model_id
                """,
                (context.tenant_id, f"Other enrichment model {uuid4().hex}"),
            ).fetchone()
        )["model_id"]
        connection.execute(
            "INSERT INTO model.model_input_scope (model_id, object_id) VALUES (%s, %s)",
            (other_model_id, object_id),
        )
        connection.execute(
            "UPDATE core.object SET object_description = 'Physical object' WHERE object_id = %s",
            (object_id,),
        )
        connection.execute(
            """
            UPDATE core.attribute SET attribute_description = 'Physical attribute',
                attribute_inferred_data_type = 'STRING', is_natural_key = FALSE
            WHERE attribute_id = %s
            """,
            (attribute_id,),
        )
        # Attribute enrichment does not require a saved Object enrichment row.
        unknown = require_row(
            connection.execute(
                """
                INSERT INTO workflow.attribute_enrichment (model_id, object_id, attribute_id)
                VALUES (%s, %s, %s)
                RETURNING is_natural_key, is_primary_key, is_nullable, is_pii, is_locked, workflow_run_id
                """,
                (context.model_id, object_id, attribute_id),
            ).fetchone()
        )
        assert unknown == {
            "is_natural_key": None,
            "is_primary_key": None,
            "is_nullable": None,
            "is_pii": None,
            "is_locked": False,
            "workflow_run_id": None,
        }
        connection.execute(
            """
            INSERT INTO workflow.attribute_enrichment (
                model_id, object_id, attribute_id, attribute_description,
                attribute_inferred_data_type, is_natural_key, is_primary_key
            ) VALUES (%s, %s, %s, 'Model attribute', 'BIGINT', TRUE, FALSE)
            """,
            (other_model_id, object_id, attribute_id),
        )
        for model_id, description in (
            (context.model_id, "First model object"),
            (other_model_id, "Second model object"),
        ):
            connection.execute(
                """
                INSERT INTO workflow.object_enrichment (model_id, object_id, object_description)
                VALUES (%s, %s, %s)
                """,
                (model_id, object_id, description),
            )
        for table, columns, values in (
            ("object_enrichment", "model_id, object_id", (context.model_id, object_id)),
            (
                "attribute_enrichment",
                "model_id, object_id, attribute_id",
                (context.model_id, object_id, attribute_id),
            ),
        ):
            with pytest.raises(UniqueViolation), connection.transaction():
                connection.execute(
                    sql.SQL("INSERT INTO workflow.{} ({}) VALUES ({})").format(
                        sql.Identifier(table),
                        sql.SQL(", ").join(
                            sql.Identifier(name) for name in columns.split(", ")
                        ),
                        sql.SQL(", ").join(sql.Placeholder() for _ in values),
                    ),
                    values,
                )
        assert connection.execute(
            """
            SELECT model_id, is_natural_key, is_primary_key
            FROM workflow.attribute_enrichment WHERE attribute_id = %s ORDER BY model_id
            """,
            (attribute_id,),
        ).fetchall() == [
            {
                "model_id": context.model_id,
                "is_natural_key": None,
                "is_primary_key": None,
            },
            {
                "model_id": other_model_id,
                "is_natural_key": True,
                "is_primary_key": False,
            },
        ]
        assert connection.execute(
            """
            SELECT object.object_description, attribute.attribute_description,
                   attribute.attribute_inferred_data_type, attribute.is_natural_key
            FROM core.object AS object JOIN core.attribute AS attribute USING (object_id)
            WHERE attribute.attribute_id = %s
            """,
            (attribute_id,),
        ).fetchone() == {
            "object_description": "Physical object",
            "attribute_description": "Physical attribute",
            "attribute_inferred_data_type": "STRING",
            "is_natural_key": False,
        }


@pytest.mark.parametrize("table", ["object_enrichment", "attribute_enrichment"])
def test_enrichment_rejects_wrong_scope_attribute_and_workflow_model(
    bootstrap_postgres_database: DisposablePostgres,
    table: str,
) -> None:
    database = bootstrap_postgres_database
    context = _context(database)
    other = _context(database)
    attributes = _seed_attributes(database, context)
    object_id, attribute_id = attributes[0]
    run_id = _create(database, context, correlation_id=uuid4())["workflow_run_id"]
    other_run_id = _create(database, other, correlation_id=uuid4())["workflow_run_id"]
    columns = ["model_id", "object_id", "workflow_run_id"]
    valid = [context.model_id, object_id, run_id]
    if table == "attribute_enrichment":
        columns.append("attribute_id")
        valid.append(attribute_id)
    statement = sql.SQL("INSERT INTO workflow.{} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    invalid = [
        ("object_id", other.selected_object_ids[0], f"fk_{table}_scope"),
        ("workflow_run_id", other_run_id, f"fk_{table}_workflow_run"),
    ]
    if table == "attribute_enrichment":
        # Both Objects are in scope, but this Attribute belongs to another Object.
        invalid.append(
            ("attribute_id", attributes[1][1], "fk_attribute_enrichment_attribute")
        )
    with database.connect_owner() as connection:
        for column, value, constraint in invalid:
            values = valid.copy()
            values[columns.index(column)] = value
            # Keep the Attribute/Object pair valid when testing the missing scope.
            if table == "attribute_enrichment" and column == "object_id":
                other_attribute = _seed_attributes(database, other)[0][1]
                values[columns.index("attribute_id")] = other_attribute
            with pytest.raises(ForeignKeyViolation) as error, connection.transaction():
                connection.execute(statement, values)
            assert error.value.diag.constraint_name == constraint
        connection.execute(statement, valid)


@pytest.mark.parametrize("field", ["is_natural_key", "is_primary_key"])
@pytest.mark.parametrize("value", [None, "true", "false", "yes", "1"])
def test_enrichment_history_accepts_only_nullable_boolean_text_for_key_fields(
    bootstrap_postgres_database: DisposablePostgres,
    field: str,
    value: str | None,
) -> None:
    database = bootstrap_postgres_database
    context = _context(database)
    object_id, attribute_id = _seed_attributes(database, context)[0]
    run_id = _create(database, context, correlation_id=uuid4())["workflow_run_id"]
    with database.connect_owner() as connection:
        statement = """
            INSERT INTO application.metadata_enrichment_result (
                workflow_run_id, object_id, attribute_id, field_name,
                status, evidence_method, applied_value, sample_count
            ) VALUES (%s, %s, %s, %s, 'applied', 'agent_key_inference', %s, 0)
        """
        parameters = (run_id, object_id, attribute_id, field, value)
        if value in (None, "true", "false"):
            connection.execute(statement, parameters)
        else:
            with pytest.raises(CheckViolation) as error, connection.transaction():
                connection.execute(statement, parameters)
            assert error.value.diag.constraint_name == "ck_metadata_enrichment_value"
