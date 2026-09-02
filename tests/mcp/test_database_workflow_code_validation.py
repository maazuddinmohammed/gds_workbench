from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb
from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from conftest import DisposablePostgres


DATABASE_ROOT = Path(__file__).resolve().parents[2] / "database"


def _seed_code_validation_scope(
    postgres_database: DisposablePostgres,
) -> dict[str, int]:
    with postgres_database.connect_owner() as connection:
        if (
            connection.execute(
                "SELECT 1 FROM core.project WHERE project_code = 'DEMO_PROJECT'"
            ).fetchone()
            is None
        ):
            connection.execute(
                cast(
                    LiteralString,
                    (
                        DATABASE_ROOT / "seed" / "01_metadata_snapshot_demo.sql"
                    ).read_text(encoding="utf-8"),
                )
            )

        seed = require_row(
            connection.execute(
                """
                SELECT tenant.tenant_id,
                       object.object_id,
                       connection.system_id,
                       system.system_type_id
                  FROM core.tenant AS tenant
                  CROSS JOIN LATERAL (
                      SELECT candidate.object_id, candidate.connection_id
                        FROM core.object AS candidate
                       ORDER BY candidate.object_id
                       LIMIT 1
                  ) AS object
                  JOIN core.connection AS connection
                    ON connection.connection_id = object.connection_id
                  JOIN core.system AS system
                    ON system.system_id = connection.system_id
                 WHERE tenant.tenant_code = 'DEMO_TENANT'
                """
            ).fetchone()
        )
        model_id = require_row(
            connection.execute(
                """
                INSERT INTO model.model (tenant_id, model_name)
                VALUES (%s, %s)
                RETURNING model_id
                """,
                (seed["tenant_id"], f"Code Validation {uuid4().hex}"),
            ).fetchone()
        )["model_id"]
        logical_entity_id = require_row(
            connection.execute(
                """
                INSERT INTO workflow.logical_entity (
                    model_id, logical_entity_name, logical_entity_definition,
                    logical_entity_type, logical_entity_grain
                ) VALUES (%s, 'Customer', 'Customer.', 'core', 'One customer')
                RETURNING logical_entity_id
                """,
                (model_id,),
            ).fetchone()
        )["logical_entity_id"]
        model_object_binding_id = require_row(
            connection.execute(
                """
                INSERT INTO workflow.model_object_binding (
                    model_id, object_id, modeled_entity_type, logical_entity_id
                ) VALUES (%s, %s, 'logical_entity', %s)
                RETURNING model_object_binding_id
                """,
                (model_id, seed["object_id"], logical_entity_id),
            ).fetchone()
        )["model_object_binding_id"]

    return {
        "model_id": model_id,
        "tenant_id": seed["tenant_id"],
        "object_id": seed["object_id"],
        "system_id": seed["system_id"],
        "system_type_id": seed["system_type_id"],
        "model_object_binding_id": model_object_binding_id,
    }


def _insert_check(
    connection: object,
    *,
    group_id: int,
    name: str,
    operator: str,
    result_type: str | None,
    value_type: str,
    value: object | None = None,
    query_b: str | None = None,
) -> None:
    connection.execute(  # type: ignore[attr-defined]
        """
        INSERT INTO workflow.validation_check (
            validation_group_id,
            validation_check_name,
            validation_category_code,
            validation_severity,
            validation_query_sql,
            validation_comparison_query_sql,
            validation_result_data_type,
            validation_comparison_operator,
            validation_comparison_value_type,
            validation_comparison_value
        ) VALUES (%s, %s, 'technical', 'blocking', 'SELECT 1', %s, %s, %s, %s, %s)
        """,
        (
            group_id,
            name,
            query_b,
            result_type,
            operator,
            value_type,
            None if value is None else Jsonb(value),
        ),
    )


def test_generated_code_enforces_binding_identity_and_derives_content_digest(
    postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_code_validation_scope(postgres_database)
    large_content = "é" * 204_801
    large_digest = hashlib.sha256(large_content.encode()).hexdigest()

    with postgres_database.connect_owner() as connection:
        row = require_row(
            connection.execute(
                """
                INSERT INTO workflow.generated_code (
                    model_object_binding_id,
                    artifact_name,
                    artifact_type,
                    generated_code_content,
                    code_input_digest
                ) VALUES (%s, 'Customer.sql', 'sql_file', %s, %s)
                RETURNING generated_code_status, generated_code_digest
                """,
                (
                    scope["model_object_binding_id"],
                    large_content,
                    "a" * 64,
                ),
            ).fetchone()
        )
        assert row == {
            "generated_code_status": "active",
            "generated_code_digest": large_digest,
        }

        for artifact_name, input_digest in (
            ("customer.SQL", "b" * 64),
            ("Customer-2.sql", "not-a-digest"),
        ):
            expected_error = (
                UniqueViolation if artifact_name == "customer.SQL" else CheckViolation
            )
            with pytest.raises(expected_error), connection.transaction():
                connection.execute(
                    """
                    INSERT INTO workflow.generated_code (
                        model_object_binding_id, artifact_name, artifact_type,
                        generated_code_content, code_input_digest
                    ) VALUES (%s, %s, 'sql_file', 'SELECT 2', %s)
                    """,
                    (
                        scope["model_object_binding_id"],
                        artifact_name,
                        input_digest,
                    ),
                )

        with pytest.raises(ForeignKeyViolation), connection.transaction():
            connection.execute(
                """
                INSERT INTO workflow.generated_code (
                    model_object_binding_id, artifact_name, artifact_type,
                    generated_code_content, code_input_digest
                ) VALUES (-1, 'Unknown.sql', 'sql_file', 'SELECT 4', %s)
                """,
                ("c" * 64,),
            )


def test_validation_group_enforces_scope_and_normalized_name(
    postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_code_validation_scope(postgres_database)
    with postgres_database.connect_owner() as connection:
        group_id = require_row(
            connection.execute(
                """
                INSERT INTO workflow.validation_group (
                    model_id, tenant_id, system_id, validation_group_name,
                    mapping_context_digest
                ) VALUES (%s, %s, %s, 'Reconciliation', %s)
                RETURNING validation_group_id
                """,
                (
                    scope["model_id"],
                    scope["tenant_id"],
                    scope["system_id"],
                    "a" * 64,
                ),
            ).fetchone()
        )["validation_group_id"]
        assert group_id > 0

        with pytest.raises(UniqueViolation), connection.transaction():
            connection.execute(
                """
                INSERT INTO workflow.validation_group (
                    model_id, tenant_id, system_id, validation_group_name,
                    mapping_context_digest
                ) VALUES (%s, %s, %s, '  RECONCILIATION  ', %s)
                """,
                (
                    scope["model_id"],
                    scope["tenant_id"],
                    scope["system_id"],
                    "a" * 64,
                ),
            )

        with pytest.raises(ForeignKeyViolation), connection.transaction():
            connection.execute(
                """
                INSERT INTO workflow.validation_group (
                    model_id, tenant_id, system_id, validation_group_name,
                    mapping_context_digest
                ) VALUES (%s, -1, %s, 'Wrong tenant', %s)
                """,
                (scope["model_id"], scope["system_id"], "a" * 64),
            )

        with pytest.raises(CheckViolation), connection.transaction():
            connection.execute(
                """
                INSERT INTO workflow.validation_group (
                    model_id, tenant_id, system_id, validation_group_name,
                    mapping_context_digest
                ) VALUES (%s, %s, %s, 'Bad digest', 'not-a-digest')
                """,
                (
                    scope["model_id"],
                    scope["tenant_id"],
                    scope["system_id"],
                ),
            )


def test_validation_check_accepts_deterministic_assertion_shapes(
    postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_code_validation_scope(postgres_database)
    with postgres_database.connect_owner() as connection:
        group_id = require_row(
            connection.execute(
                """
                INSERT INTO workflow.validation_group (
                    model_id, tenant_id, system_id, validation_group_name,
                    mapping_context_digest, code_context_digest
                ) VALUES (%s, %s, %s, 'Business checks', %s, %s)
                RETURNING validation_group_id
                """,
                (
                    scope["model_id"],
                    scope["tenant_id"],
                    scope["system_id"],
                    "a" * 64,
                    "b" * 64,
                ),
            ).fetchone()
        )["validation_group_id"]

        cases = (
            ("executes", "executes_successfully", None, "none", None, None),
            ("not null", "is_not_null", "integer", "none", None, None),
            ("is true", "is_true", "boolean", "none", None, None),
            ("literal equality", "equal", "integer", "literal", 1, None),
            ("query equality", "equal", "integer", "query", None, "SELECT 1"),
            ("minimum", "greater_than_or_equal", "decimal", "literal", 0, None),
            ("allowed values", "in", "text", "literal_list", ["A", "B"], None),
            ("boolean values", "in", "boolean", "literal_list", [True, False], None),
            ("integer values", "in", "integer", "literal_list", [1, -2, 0], None),
            ("decimal values", "in", "decimal", "literal_list", [1, 1.5], None),
        )
        for name, operator, result_type, value_type, value, query_b in cases:
            _insert_check(
                connection,
                group_id=group_id,
                name=name,
                operator=operator,
                result_type=result_type,
                value_type=value_type,
                value=value,
                query_b=query_b,
            )

        count = require_row(
            connection.execute(
                """
                SELECT count(*) AS check_count
                  FROM workflow.validation_check
                 WHERE validation_group_id = %s
                """,
                (group_id,),
            ).fetchone()
        )["check_count"]
        assert count == len(cases)


def test_validation_check_rejects_ambiguous_assertion_shapes(
    postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_code_validation_scope(postgres_database)
    with postgres_database.connect_owner() as connection:
        group_id = require_row(
            connection.execute(
                """
                INSERT INTO workflow.validation_group (
                    model_id, tenant_id, system_id, validation_group_name,
                    mapping_context_digest
                ) VALUES (%s, %s, %s, 'Invalid shapes', %s)
                RETURNING validation_group_id
                """,
                (
                    scope["model_id"],
                    scope["tenant_id"],
                    scope["system_id"],
                    "a" * 64,
                ),
            ).fetchone()
        )["validation_group_id"]

        invalid_cases = (
            ("execution operand", "executes_successfully", None, "literal", 1, None),
            ("boolean type", "is_true", "integer", "none", None, None),
            ("missing equality", "equal", "integer", "none", None, None),
            ("ordered text", "greater_than", "text", "literal", "A", None),
            ("empty list", "in", "text", "literal_list", [], None),
            ("fractional integer", "equal", "integer", "literal", 1.5, None),
            ("mixed boolean list", "in", "boolean", "literal_list", [True, 1], None),
            (
                "fractional integer list",
                "in",
                "integer",
                "literal_list",
                [1, 1.5],
                None,
            ),
            (
                "decimal syntax integer list",
                "in",
                "integer",
                "literal_list",
                [1.0],
                None,
            ),
            ("null integer list", "in", "integer", "literal_list", [1, None], None),
            ("mixed decimal list", "in", "decimal", "literal_list", [1, "2"], None),
            ("mixed text list", "in", "text", "literal_list", ["A", 1], None),
            (
                "mixed date list",
                "in",
                "date",
                "literal_list",
                ["2026-08-31", False],
                None,
            ),
            (
                "mixed timestamp list",
                "in",
                "timestamp",
                "literal_list",
                ["2026-08-31T12:00:00Z", 3],
                None,
            ),
        )
        for name, operator, result_type, value_type, value, query_b in invalid_cases:
            with pytest.raises(CheckViolation), connection.transaction():
                _insert_check(
                    connection,
                    group_id=group_id,
                    name=name,
                    operator=operator,
                    result_type=result_type,
                    value_type=value_type,
                    value=value,
                    query_b=query_b,
                )
