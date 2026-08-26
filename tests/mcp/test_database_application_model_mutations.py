from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, LiteralString
from uuid import UUID, uuid4

import psycopg
import pytest
from tests.mcp.database_test_support import require_row
from psycopg.errors import InsufficientPrivilege, RaiseException
from psycopg.rows import dict_row

if TYPE_CHECKING:
    from conftest import DisposablePostgres

type TestRow = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelMutationContext:
    entra_tenant_id: UUID
    entra_object_id: UUID
    tenant_id: int
    principal_id: int


CREATE_MODEL_SQL: LiteralString = """
    SELECT *
      FROM application.create_model(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::TEXT,
          %s::JSONB,
          %s::TEXT,
          %s::JSONB,
          %s::JSONB,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::INTEGER,
          %s::INTEGER
      )
"""

UPDATE_MODEL_SQL: LiteralString = """
    SELECT *
      FROM application.update_model(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::TEXT,
          %s::JSONB,
          %s::TEXT,
          %s::JSONB,
          %s::JSONB,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::INTEGER,
          %s::INTEGER
      )
"""

ARCHIVE_MODEL_SQL: LiteralString = """
    SELECT *
      FROM application.archive_model(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT
      )
"""

REPLACE_MODEL_SCOPE_SQL: LiteralString = """
    SELECT *
      FROM application.replace_model_scope(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::BIGINT[]
      )
"""


def _seed_model_mutation_context(
    postgres_database: DisposablePostgres,
) -> ModelMutationContext:
    suffix = uuid4().hex
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()

    with postgres_database.connect_owner() as connection:
        project_id = require_row(
            connection.execute(
                """
                INSERT INTO core.project (project_code, project_name)
                VALUES (%s, %s)
                RETURNING project_id
                """,
                (f"model_project_{suffix}", f"Model Project {suffix}"),
            ).fetchone()
        )["project_id"]
        tenant_id = require_row(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    project_id,
                    tenant_code,
                    tenant_name,
                    tenant_catalog,
                    gds_admin_catalog
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id
                """,
                (
                    project_id,
                    f"model_tenant_{suffix}",
                    f"Model Tenant {suffix}",
                    f"model_catalog_{suffix}",
                    f"model_admin_{suffix}",
                ),
            ).fetchone()
        )["tenant_id"]
        principal_id = require_row(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type,
                    principal_display_name,
                    principal_email
                ) VALUES ('user', %s, %s)
                RETURNING principal_id
                """,
                (f"Model Architect {suffix}", f"model_{suffix}@example.test"),
            ).fetchone()
        )["principal_id"]
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            ) VALUES (%s, %s, 'architect', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_lock (
                tenant_id,
                locked_by_principal_id,
                tenant_lock_purpose,
                tenant_lock_expires_time
            ) VALUES (%s, %s, 'Model authoring', CURRENT_TIMESTAMP + INTERVAL '1 hour')
            """,
            (tenant_id, principal_id),
        )

    return ModelMutationContext(
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
        tenant_id=tenant_id,
        principal_id=principal_id,
    )


def _connect_web(
    postgres_database: DisposablePostgres,
) -> psycopg.Connection[TestRow]:
    connection = psycopg.Connection[TestRow].connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    )
    connection.execute("SET ROLE gds_web_write")
    return connection


def _create_model(
    postgres_database: DisposablePostgres,
    context: ModelMutationContext,
) -> TestRow:
    with _connect_web(postgres_database) as connection:
        return require_row(
            connection.execute(
                CREATE_MODEL_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    context.tenant_id,
                    "Customer 360",
                    "Cross-system customer model",
                    "Use clear business names.",
                    '[{"name":"created_time","type":"timestamp"}]',
                    "Use dimensional business names.",
                    '[{"name":"effective_date","type":"date"}]',
                    '[{"name":"updated_time","type":"timestamp"}]',
                    "openai_agents_sdk",
                    "microsoft_foundry",
                    "model-1",
                    "medium",
                    12,
                    2,
                ),
            ).fetchone()
        )


def _seed_scope_objects(
    postgres_database: DisposablePostgres,
    context: ModelMutationContext,
    *,
    model_id: int,
) -> tuple[int, int, int]:
    suffix = uuid4().hex
    with postgres_database.connect_owner() as connection:
        project_id = require_row(
            connection.execute(
                "SELECT project_id FROM core.tenant WHERE tenant_id = %s",
                (context.tenant_id,),
            ).fetchone()
        )["project_id"]
        other_tenant_id = require_row(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    project_id,
                    tenant_code,
                    tenant_name,
                    tenant_catalog,
                    gds_admin_catalog
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id
                """,
                (
                    project_id,
                    f"scope_other_{suffix}",
                    f"Scope Other {suffix}",
                    f"scope_other_catalog_{suffix}",
                    f"scope_other_admin_{suffix}",
                ),
            ).fetchone()
        )["tenant_id"]
        reference_row = require_row(
            connection.execute(
                """
                WITH system_type AS (
                    INSERT INTO reference.system_type (
                        system_type_code,
                        system_type_name
                    ) VALUES (%s, %s)
                    RETURNING system_type_id
                ),
                connection_type AS (
                    INSERT INTO reference.connection_type (
                        connection_type_code,
                        connection_type_name
                    ) VALUES (%s, %s)
                    RETURNING connection_type_id
                ),
                object_type AS (
                    INSERT INTO reference.object_type (
                        object_type_code,
                        object_type_name
                    ) VALUES (%s, %s)
                    RETURNING object_type_id
                ),
                source_zone AS (
                    INSERT INTO reference.zone (zone_code, zone_name)
                    VALUES (%s, %s)
                    RETURNING zone_id
                ),
                gold_zone AS (
                    INSERT INTO reference.zone (zone_code, zone_name)
                    VALUES (%s, %s)
                    RETURNING zone_id
                )
                SELECT system_type_id,
                       connection_type_id,
                       object_type_id,
                       source_zone.zone_id AS source_zone_id,
                       gold_zone.zone_id AS gold_zone_id
                  FROM system_type,
                       connection_type,
                       object_type,
                       source_zone,
                       gold_zone
                """,
                (
                    f"scope_system_type_{suffix}",
                    f"Scope System Type {suffix}",
                    f"scope_connection_type_{suffix}",
                    f"Scope Connection Type {suffix}",
                    f"scope_object_type_{suffix}",
                    f"Scope Object Type {suffix}",
                    f"source_{suffix[:12]}",
                    f"Source {suffix}",
                    f"gold_{suffix[:14]}",
                    f"Gold {suffix}",
                ),
            ).fetchone()
        )
        system_id = require_row(
            connection.execute(
                """
                INSERT INTO core.system (
                    system_code,
                    system_name,
                    system_type_id
                ) VALUES (%s, %s, %s)
                RETURNING system_id
                """,
                (
                    f"scope_system_{suffix}",
                    f"Scope System {suffix}",
                    reference_row["system_type_id"],
                ),
            ).fetchone()
        )["system_id"]
        connection_rows = connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id,
                system_id,
                connection_code,
                connection_name,
                connection_type_id
            ) VALUES
                (%s, %s, %s, %s, %s),
                (%s, %s, %s, %s, %s)
            RETURNING connection_id
            """,
            (
                context.tenant_id,
                system_id,
                f"scope_connection_{suffix}",
                f"Scope Connection {suffix}",
                reference_row["connection_type_id"],
                other_tenant_id,
                system_id,
                f"scope_other_connection_{suffix}",
                f"Scope Other Connection {suffix}",
                reference_row["connection_type_id"],
            ),
        ).fetchall()
        object_rows = connection.execute(
            """
            INSERT INTO core.object (
                connection_id,
                object_schema,
                object_name,
                object_type_id,
                zone_id
            ) VALUES
                (%s, 'source_schema', %s, %s, %s),
                (%s, 'gold_schema', %s, %s, %s),
                (%s, 'source_schema', %s, %s, %s)
            RETURNING object_id
            """,
            (
                connection_rows[0]["connection_id"],
                f"source_object_{suffix}",
                reference_row["object_type_id"],
                reference_row["source_zone_id"],
                connection_rows[1]["connection_id"],
                f"gold_object_{suffix}",
                reference_row["object_type_id"],
                reference_row["gold_zone_id"],
                connection_rows[1]["connection_id"],
                f"removed_object_{suffix}",
                reference_row["object_type_id"],
                reference_row["source_zone_id"],
            ),
        ).fetchall()
        source_object_id = object_rows[0]["object_id"]
        cross_tenant_gold_object_id = object_rows[1]["object_id"]
        removed_object_id = object_rows[2]["object_id"]
        connection.execute(
            """
            INSERT INTO core.ingestion_object_mapping (
                source_object_id,
                target_object_id
            ) VALUES (%s, %s)
            """,
            (source_object_id, cross_tenant_gold_object_id),
        )
        connection.execute(
            """
            INSERT INTO model.model_scope (
                model_id,
                object_id,
                model_scope_is_locked,
                is_active
            ) VALUES
                (%s, %s, TRUE, FALSE),
                (%s, %s, FALSE, TRUE)
            """,
            (
                model_id,
                cross_tenant_gold_object_id,
                model_id,
                removed_object_id,
            ),
        )

    return source_object_id, cross_tenant_gold_object_id, removed_object_id


def test_web_can_create_tenant_owned_model_with_agent_defaults(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)

    assert created["tenant_id"] == context.tenant_id
    assert created["model_name"] == "Customer 360"
    assert created["model_revision"] == 1
    assert created["default_agent_model_code"] == "model-1"
    assert created["default_validation_retry_count"] == 2
    assert created["is_active"] is True


def test_model_creation_requires_current_tenant_lock(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "DELETE FROM security.tenant_lock WHERE tenant_id = %s",
            (context.tenant_id,),
        )

    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="tenant_lock_required"),
    ):
        connection.execute(
            CREATE_MODEL_SQL,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                context.tenant_id,
                "Denied Model",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            ),
        )

    with postgres_database.connect_owner() as connection:
        model_count = require_row(
            connection.execute(
                "SELECT count(*) AS count FROM model.model WHERE tenant_id = %s",
                (context.tenant_id,),
            ).fetchone()
        )["count"]

    assert model_count == 0


def test_web_can_update_model_and_advance_revision_once(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)

    with _connect_web(postgres_database) as connection:
        updated = require_row(
            connection.execute(
                UPDATE_MODEL_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    created["model_revision"],
                    "Customer Domain",
                    "Curated customer domain",
                    "Prefer complete business terms.",
                    '[{"name":"created_time","type":"timestamp"}]',
                    "Prefer dimensional business terms.",
                    '[{"name":"effective_date","type":"date"}]',
                    '[{"name":"updated_time","type":"timestamp"}]',
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ).fetchone()
        )

    with postgres_database.connect_owner() as connection:
        revision_kinds = connection.execute(
            """
            SELECT change_kind
              FROM model.model_revision_transaction
             WHERE model_id = %s
             ORDER BY transaction_id
            """,
            (created["model_id"],),
        ).fetchall()

    assert updated["model_name"] == "Customer Domain"
    assert updated["model_revision"] == 2
    assert updated["default_agent_sdk_code"] is None
    assert [row["change_kind"] for row in revision_kinds] == [
        "web_model_create",
        "web_model_update",
    ]


def test_equivalent_model_update_is_a_revision_stable_noop(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)

    with _connect_web(postgres_database) as connection:
        unchanged = require_row(
            connection.execute(
                UPDATE_MODEL_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    created["model_revision"],
                    "Customer 360",
                    "Cross-system customer model",
                    "Use clear business names.",
                    '[{"name":"created_time","type":"timestamp"}]',
                    "Use dimensional business names.",
                    '[{"name":"effective_date","type":"date"}]',
                    '[{"name":"updated_time","type":"timestamp"}]',
                    "openai_agents_sdk",
                    "microsoft_foundry",
                    "model-1",
                    "medium",
                    12,
                    2,
                ),
            ).fetchone()
        )

    with postgres_database.connect_owner() as connection:
        revision_count = require_row(
            connection.execute(
                """
                SELECT count(*) AS count
                  FROM model.model_revision_transaction
                 WHERE model_id = %s
                """,
                (created["model_id"],),
            ).fetchone()
        )["count"]

    assert unchanged["model_revision"] == 1
    assert unchanged["updated_time"] == created["updated_time"]
    assert revision_count == 1


def test_model_update_rejects_stale_revision_without_writes(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)

    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="stale_model_revision"),
    ):
        connection.execute(
            UPDATE_MODEL_SQL,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                created["model_id"],
                999,
                "Stale Change",
                created["model_description"],
                created["silver_model_naming_instructions"],
                '[{"name":"created_time","type":"timestamp"}]',
                created["gold_model_naming_instructions"],
                '[{"name":"effective_date","type":"date"}]',
                '[{"name":"updated_time","type":"timestamp"}]',
                created["default_agent_sdk_code"],
                created["default_agent_provider_code"],
                created["default_agent_model_code"],
                created["default_reasoning_effort_code"],
                created["default_max_turns"],
                created["default_validation_retry_count"],
            ),
        )

    with postgres_database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                """
                SELECT model_name, model_revision
                  FROM model.model
                 WHERE model_id = %s
                """,
                (created["model_id"],),
            ).fetchone()
        )

    assert stored == {"model_name": "Customer 360", "model_revision": 1}


def test_model_update_rejects_a_null_expected_revision(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)

    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="stale_model_revision"),
    ):
        connection.execute(
            UPDATE_MODEL_SQL,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                created["model_id"],
                None,
                "Changed without a revision fence",
                created["model_description"],
                created["silver_model_naming_instructions"],
                '[{"name":"created_time","type":"timestamp"}]',
                created["gold_model_naming_instructions"],
                '[{"name":"effective_date","type":"date"}]',
                '[{"name":"updated_time","type":"timestamp"}]',
                created["default_agent_sdk_code"],
                created["default_agent_provider_code"],
                created["default_agent_model_code"],
                created["default_reasoning_effort_code"],
                created["default_max_turns"],
                created["default_validation_retry_count"],
            ),
        )


def test_web_can_archive_model_and_advance_revision_once(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)

    with _connect_web(postgres_database) as connection:
        archived = require_row(
            connection.execute(
                ARCHIVE_MODEL_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    created["model_revision"],
                ),
            ).fetchone()
        )

    with postgres_database.connect_owner() as connection:
        revision_kinds = connection.execute(
            """
            SELECT change_kind
              FROM model.model_revision_transaction
             WHERE model_id = %s
             ORDER BY transaction_id
            """,
            (created["model_id"],),
        ).fetchall()

    assert archived["is_active"] is False
    assert archived["model_revision"] == 2
    assert [row["change_kind"] for row in revision_kinds] == [
        "web_model_create",
        "web_model_archive",
    ]


def test_model_mutation_rejects_a_null_expected_revision(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)

    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="stale_model_revision"),
    ):
        connection.execute(
            ARCHIVE_MODEL_SQL,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                created["model_id"],
                None,
            ),
        )


def test_model_mutation_derives_owning_tenant_from_model(
    postgres_database: DisposablePostgres,
) -> None:
    owner_context = _seed_model_mutation_context(postgres_database)
    other_context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, owner_context)

    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="authorization_denied"),
    ):
        connection.execute(
            ARCHIVE_MODEL_SQL,
            (
                other_context.entra_tenant_id,
                other_context.entra_object_id,
                created["model_id"],
                created["model_revision"],
            ),
        )

    with postgres_database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                "SELECT is_active, model_revision FROM model.model WHERE model_id = %s",
                (created["model_id"],),
            ).fetchone()
        )

    assert stored == {"is_active": True, "model_revision": 1}


def test_archive_and_scope_replacement_reject_stale_revision(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)
    object_id, _, _ = _seed_scope_objects(
        postgres_database,
        context,
        model_id=int(created["model_id"]),
    )

    calls: tuple[tuple[LiteralString, tuple[Any, ...]], ...] = (
        (
            ARCHIVE_MODEL_SQL,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                created["model_id"],
                999,
            ),
        ),
        (
            REPLACE_MODEL_SCOPE_SQL,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                created["model_id"],
                999,
                [object_id],
            ),
        ),
    )
    for statement, parameters in calls:
        with (
            _connect_web(postgres_database) as connection,
            pytest.raises(RaiseException, match="stale_model_revision"),
        ):
            connection.execute(statement, parameters)

    with postgres_database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                """
                SELECT is_active, model_revision
                  FROM model.model
                 WHERE model_id = %s
                """,
                (created["model_id"],),
            ).fetchone()
        )

    assert stored == {"is_active": True, "model_revision": 1}


def test_scope_replacement_rejects_a_null_expected_revision(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)
    object_id, _, _ = _seed_scope_objects(
        postgres_database,
        context,
        model_id=int(created["model_id"]),
    )

    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="stale_model_revision"),
    ):
        connection.execute(
            REPLACE_MODEL_SCOPE_SQL,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                created["model_id"],
                None,
                [object_id],
            ),
        )


def test_web_can_replace_scope_with_cross_tenant_any_zone_objects(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)
    source_object_id, cross_tenant_gold_object_id, removed_object_id = (
        _seed_scope_objects(
            postgres_database,
            context,
            model_id=int(created["model_id"]),
        )
    )

    with _connect_web(postgres_database) as connection:
        result = require_row(
            connection.execute(
                REPLACE_MODEL_SCOPE_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    created["model_revision"],
                    [cross_tenant_gold_object_id, source_object_id],
                ),
            ).fetchone()
        )

    with postgres_database.connect_owner() as connection:
        scope_rows = connection.execute(
            """
            SELECT object_id, model_scope_is_locked, is_active
              FROM model.model_scope
             WHERE model_id = %s
             ORDER BY object_id
            """,
            (created["model_id"],),
        ).fetchall()
        revision_kinds = connection.execute(
            """
            SELECT change_kind
              FROM model.model_revision_transaction
             WHERE model_id = %s
             ORDER BY transaction_id
            """,
            (created["model_id"],),
        ).fetchall()

    scope_by_object = {row["object_id"]: row for row in scope_rows}
    assert result == {
        "changed": True,
        "model_id": created["model_id"],
        "model_revision": 2,
        "active_scope_count": 2,
        "updated_time": result["updated_time"],
    }
    assert scope_by_object[source_object_id]["is_active"] is True
    assert scope_by_object[cross_tenant_gold_object_id] == {
        "object_id": cross_tenant_gold_object_id,
        "model_scope_is_locked": True,
        "is_active": True,
    }
    assert scope_by_object[removed_object_id]["is_active"] is False
    assert [row["change_kind"] for row in revision_kinds] == [
        "web_model_create",
        "web_model_scope_replace",
    ]


def test_scope_replacement_rejects_active_object_outside_visible_closure(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)
    source_object_id, cross_tenant_gold_object_id, current_scope_object_id = (
        _seed_scope_objects(
            postgres_database,
            context,
            model_id=int(created["model_id"]),
        )
    )
    with postgres_database.connect_owner() as connection:
        discovered_schema = f"discovered_schema_{uuid4().hex}"
        discovered_zone_id = require_row(
            connection.execute(
                """
                INSERT INTO reference.zone (zone_code, zone_name)
                VALUES ('gold', %s)
                RETURNING zone_id
                """,
                (f"Discovered Gold {uuid4().hex}",),
            ).fetchone()
        )["zone_id"]
        gds_connection_id = require_row(
            connection.execute(
                """
                INSERT INTO core.connection (
                    tenant_id,
                    system_id,
                    connection_code,
                    connection_name,
                    connection_type_id,
                    is_global_data_store
                )
                SELECT source_connection.tenant_id,
                       source_connection.system_id,
                       %s,
                       %s,
                       source_connection.connection_type_id,
                       TRUE
                  FROM core.object AS object_record
                  JOIN core.connection AS source_connection
                    ON source_connection.connection_id = object_record.connection_id
                 WHERE object_record.object_id = %s
                RETURNING connection_id
                """,
                (
                    f"scope_gds_{uuid4().hex}",
                    f"Scope GDS {uuid4().hex}",
                    cross_tenant_gold_object_id,
                ),
            ).fetchone()
        )["connection_id"]
        connection.execute(
            """
            INSERT INTO core.tenant_metadata_discovery_scope (
                tenant_id,
                gds_connection_id,
                zone_id,
                object_schema
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                context.tenant_id,
                gds_connection_id,
                discovered_zone_id,
                discovered_schema,
            ),
        )
        discovered_object_id = require_row(
            connection.execute(
                """
                INSERT INTO core.object (
                    connection_id,
                    object_schema,
                    object_name,
                    object_type_id,
                    zone_id
                )
                SELECT %s,
                       %s,
                       %s,
                       object_record.object_type_id,
                       %s
                  FROM core.object AS object_record
                 WHERE object_record.object_id = %s
                RETURNING object_id
                """,
                (
                    gds_connection_id,
                    discovered_schema,
                    f"discovered_object_{uuid4().hex}",
                    discovered_zone_id,
                    cross_tenant_gold_object_id,
                ),
            ).fetchone()
        )["object_id"]
        hidden_object_id = require_row(
            connection.execute(
                """
                INSERT INTO core.object (
                    connection_id,
                    object_schema,
                    object_name,
                    object_type_id,
                    zone_id
                )
                SELECT object_record.connection_id,
                       'hidden_schema',
                       %s,
                       object_record.object_type_id,
                       object_record.zone_id
                  FROM core.object AS object_record
                 WHERE object_record.object_id = %s
                RETURNING object_id
                """,
                (f"hidden_object_{uuid4().hex}", cross_tenant_gold_object_id),
            ).fetchone()
        )["object_id"]

    with _connect_web(postgres_database) as connection:
        current_scope = require_row(
            connection.execute(
                REPLACE_MODEL_SCOPE_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    created["model_revision"],
                    [current_scope_object_id],
                ),
            ).fetchone()
        )

    assert current_scope["changed"] is False
    assert current_scope["model_revision"] == created["model_revision"]

    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(RaiseException, match="unavailable"),
    ):
        connection.execute(
            REPLACE_MODEL_SCOPE_SQL,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                created["model_id"],
                created["model_revision"],
                [
                    source_object_id,
                    cross_tenant_gold_object_id,
                    discovered_object_id,
                    current_scope_object_id,
                    hidden_object_id,
                ],
            ),
        )

    with postgres_database.connect_owner() as connection:
        unchanged = require_row(
            connection.execute(
                """
                SELECT target_model.model_revision,
                       array_agg(scope.object_id ORDER BY scope.object_id)
                           FILTER (WHERE scope.is_active) AS active_object_ids
                  FROM model.model AS target_model
                  LEFT JOIN model.model_scope AS scope
                    ON scope.model_id = target_model.model_id
                 WHERE target_model.model_id = %s
                 GROUP BY target_model.model_revision
                """,
                (created["model_id"],),
            ).fetchone()
        )

    assert unchanged == {
        "model_revision": created["model_revision"],
        "active_object_ids": [current_scope_object_id],
    }

    with _connect_web(postgres_database) as connection:
        valid = require_row(
            connection.execute(
                REPLACE_MODEL_SCOPE_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    created["model_revision"],
                    [
                        source_object_id,
                        cross_tenant_gold_object_id,
                        discovered_object_id,
                        current_scope_object_id,
                    ],
                ),
            ).fetchone()
        )

    assert valid["changed"] is True
    assert valid["active_scope_count"] == 4


def test_equivalent_scope_replacement_is_a_revision_stable_noop(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)
    source_object_id, cross_tenant_gold_object_id, _ = _seed_scope_objects(
        postgres_database,
        context,
        model_id=int(created["model_id"]),
    )

    with _connect_web(postgres_database) as connection:
        first = require_row(
            connection.execute(
                REPLACE_MODEL_SCOPE_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    created["model_revision"],
                    [source_object_id, cross_tenant_gold_object_id],
                ),
            ).fetchone()
        )
    with _connect_web(postgres_database) as connection:
        replay = require_row(
            connection.execute(
                REPLACE_MODEL_SCOPE_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    first["model_revision"],
                    [cross_tenant_gold_object_id, source_object_id],
                ),
            ).fetchone()
        )

    with postgres_database.connect_owner() as connection:
        revision_count = require_row(
            connection.execute(
                """
                SELECT count(*) AS count
                  FROM model.model_revision_transaction
                 WHERE model_id = %s
                """,
                (created["model_id"],),
            ).fetchone()
        )["count"]

    assert first["changed"] is True
    assert replay["changed"] is False
    assert replay["model_revision"] == 2
    assert replay["updated_time"] == first["updated_time"]
    assert revision_count == 2


def test_web_can_replace_active_scope_with_empty_set(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)
    _seed_scope_objects(
        postgres_database,
        context,
        model_id=int(created["model_id"]),
    )

    with _connect_web(postgres_database) as connection:
        cleared = require_row(
            connection.execute(
                REPLACE_MODEL_SCOPE_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    created["model_revision"],
                    [],
                ),
            ).fetchone()
        )

    with postgres_database.connect_owner() as connection:
        active_count = require_row(
            connection.execute(
                """
                SELECT count(*) AS count
                  FROM model.model_scope
                 WHERE model_id = %s
                   AND is_active
                """,
                (created["model_id"],),
            ).fetchone()
        )["count"]

    assert cleared["changed"] is True
    assert cleared["model_revision"] == 2
    assert cleared["active_scope_count"] == 0
    assert active_count == 0


def test_invalid_scope_replacement_is_atomic(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)
    source_object_id, _, unavailable_object_id = _seed_scope_objects(
        postgres_database,
        context,
        model_id=int(created["model_id"]),
    )
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE core.object SET is_active = FALSE WHERE object_id = %s",
            (unavailable_object_id,),
        )

    invalid_selections = (
        ([source_object_id, source_object_id], "unique"),
        ([source_object_id, unavailable_object_id], "unavailable"),
    )
    for selected_object_ids, error in invalid_selections:
        with (
            _connect_web(postgres_database) as connection,
            pytest.raises(RaiseException, match=error),
        ):
            connection.execute(
                REPLACE_MODEL_SCOPE_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["model_id"],
                    created["model_revision"],
                    selected_object_ids,
                ),
            )

    with postgres_database.connect_owner() as connection:
        state = require_row(
            connection.execute(
                """
                SELECT target_model.model_revision,
                       count(*) FILTER (WHERE scope.is_active) AS active_count,
                       count(DISTINCT revision.transaction_id) AS revision_count
                  FROM model.model AS target_model
                  LEFT JOIN model.model_scope AS scope
                    ON scope.model_id = target_model.model_id
                  LEFT JOIN model.model_revision_transaction AS revision
                    ON revision.model_id = target_model.model_id
                 WHERE target_model.model_id = %s
                 GROUP BY target_model.model_revision
                """,
                (created["model_id"],),
            ).fetchone()
        )

    assert state == {
        "model_revision": 1,
        "active_count": 1,
        "revision_count": 1,
    }


def test_web_role_has_no_direct_model_or_scope_mutation(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_model_mutation_context(postgres_database)
    created = _create_model(postgres_database, context)
    object_id, _, _ = _seed_scope_objects(
        postgres_database,
        context,
        model_id=int(created["model_id"]),
    )

    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute(
            "INSERT INTO model.model (tenant_id, model_name) VALUES (%s, %s)",
            (context.tenant_id, "Direct Model"),
        )

    with (
        _connect_web(postgres_database) as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute(
            """
            INSERT INTO model.model_scope (model_id, object_id)
            VALUES (%s, %s)
            """,
            (created["model_id"], object_id),
        )
