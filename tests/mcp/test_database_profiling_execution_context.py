from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import TYPE_CHECKING
from uuid import uuid4

import psycopg
import pytest
from tests.mcp.database_test_support import require_row
from psycopg.errors import InsufficientPrivilege, RaiseException
from psycopg.rows import dict_row
from tests.mcp.test_database_profiling_persistence import (
    _create_run,
    _seed_attributes,
)
from tests.mcp.test_database_workflow_run_lifecycle import (
    WorkflowContext,
    seed_workflow_context,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres


GET_PROFILING_EXECUTION_CONTEXT_SQL = """
    SELECT *
      FROM application.get_profiling_execution_context(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT
      )
"""

GET_PROFILING_CONNECTION_VALUES_SQL = """
    SELECT *
      FROM application.get_profiling_connection_values(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::VARCHAR
      )
"""


@dataclass(frozen=True, slots=True)
class ProfilingExecutionSeed:
    context: WorkflowContext
    workflow_run_id: int
    connection_id: int
    environment_code: str
    relation_catalog: str
    relation_schema: str
    attributes: tuple[tuple[int, int, str], ...]
    server_hostname: str = field(repr=False)
    http_path: str = field(repr=False)
    access_token: str = field(repr=False)


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def _seed_profiling_execution(
    postgres_database: DisposablePostgres,
    *,
    workflow: str = "profiling",
    start: bool = True,
) -> ProfilingExecutionSeed:
    context = seed_workflow_context(postgres_database)
    _seed_attributes(postgres_database, context)
    environment_code = f"PROFILE_ENV_{uuid4().hex}"
    server_hostname = f"{uuid4().hex}.example.invalid"
    http_path = f"/sql/1.0/warehouses/{uuid4()}"
    access_token = uuid4().hex

    with postgres_database.connect_owner() as connection:
        object_rows = connection.execute(
            """
            SELECT object_record.object_id,
                   object_record.connection_id,
                   object_record.zone_id,
                   object_record.object_schema,
                   attribute.attribute_id,
                   attribute.attribute_name,
                   source_tenant.tenant_catalog
              FROM core.object AS object_record
              JOIN core.attribute AS attribute
                ON attribute.object_id = object_record.object_id
               AND attribute.is_active
              JOIN core.connection AS gds_connection
                ON gds_connection.connection_id = object_record.connection_id
              JOIN core.tenant AS source_tenant
                ON source_tenant.tenant_id = object_record.source_tenant_id
             WHERE object_record.object_id = ANY(%s::BIGINT[])
             ORDER BY object_record.object_id, attribute.attribute_id
            """,
            (list(context.selected_object_ids),),
        ).fetchall()
        assert len(object_rows) == len(context.selected_object_ids)
        connection_id = int(object_rows[0]["connection_id"])
        relation_schema = str(object_rows[0]["object_schema"])
        relation_catalog = str(object_rows[0]["tenant_catalog"])
        connection.execute(
            """
            UPDATE core.connection
               SET is_global_data_store = TRUE
             WHERE connection_id = %s
            """,
            (connection_id,),
        )
        connection.execute(
            """
            UPDATE core.tenant
               SET gds_connection_id = %s
             WHERE tenant_id = %s
            """,
            (connection_id, context.tenant_id),
        )
        for row in object_rows:
            connection.execute(
                """
                UPDATE core.object
                   SET batch_attribute_name = %s
                 WHERE object_id = %s
                """,
                (row["attribute_name"], row["object_id"]),
            )

        environment_id = require_row(
            connection.execute(
                """
                INSERT INTO reference.environment (
                    environment_code,
                    environment_name
                ) VALUES (%s, %s)
                RETURNING environment_id
                """,
                (environment_code, f"Profiling Environment {uuid4().hex}"),
            ).fetchone()
        )["environment_id"]
        connection.execute(
            """
            INSERT INTO reference.connection_parameter (
                connection_parameter_code,
                connection_parameter_name
            ) VALUES
                ('databricks_host_name', 'Databricks Host Name'),
                ('databricks_http_path', 'Databricks HTTP Path'),
                ('databricks_token', 'Databricks Token')
            ON CONFLICT DO NOTHING
            """
        )
        parameters = connection.execute(
            """
            SELECT connection_parameter_id, connection_parameter_code
              FROM reference.connection_parameter
             WHERE lower(btrim(connection_parameter_code)) IN (
                       'databricks_host_name',
                       'databricks_http_path',
                       'databricks_token'
                   )
            """
        ).fetchall()
        parameter_ids = {
            str(row["connection_parameter_code"]).strip().lower(): int(
                row["connection_parameter_id"]
            )
            for row in parameters
        }
        connection.execute(
            """
            INSERT INTO core.connection_value (
                environment_id,
                connection_id,
                connection_parameter_id,
                connection_value
            ) VALUES
                (%s, %s, %s, %s),
                (%s, %s, %s, %s),
                (%s, %s, %s, %s)
            """,
            (
                environment_id,
                connection_id,
                parameter_ids["databricks_host_name"],
                server_hostname,
                environment_id,
                connection_id,
                parameter_ids["databricks_http_path"],
                http_path,
                environment_id,
                connection_id,
                parameter_ids["databricks_token"],
                access_token,
            ),
        )

    workflow_run_id = _create_run(
        postgres_database,
        context,
        workflow=workflow,
        start=start,
    )
    return ProfilingExecutionSeed(
        context=context,
        workflow_run_id=workflow_run_id,
        connection_id=connection_id,
        environment_code=environment_code,
        relation_catalog=relation_catalog,
        relation_schema=relation_schema,
        attributes=tuple(
            (
                int(row["object_id"]),
                int(row["attribute_id"]),
                str(row["attribute_name"]),
            )
            for row in object_rows
        ),
        server_hostname=server_hostname,
        http_path=http_path,
        access_token=access_token,
    )


def _execution_parameters(seed: ProfilingExecutionSeed) -> tuple[object, ...]:
    return (
        seed.context.entra_tenant_id,
        seed.context.entra_object_id,
        seed.workflow_run_id,
        seed.context.model_revision,
    )


def test_running_profiling_context_returns_scope_metadata_and_one_secret_row(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(postgres_database)

    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        context_rows = connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            _execution_parameters(seed),
        ).fetchall()
        connection_rows = connection.execute(
            GET_PROFILING_CONNECTION_VALUES_SQL,
            (*_execution_parameters(seed), seed.environment_code.lower()),
        ).fetchall()

    assert len(context_rows) == len(seed.attributes)
    assert [
        (row["object_id"], row["attribute_id"], row["attribute_name"])
        for row in context_rows
    ] == list(seed.attributes)
    assert all(row["workflow_run_id"] == seed.workflow_run_id for row in context_rows)
    assert all(row["model_id"] == seed.context.model_id for row in context_rows)
    assert all(
        row["model_revision"] == seed.context.model_revision for row in context_rows
    )
    assert all(row["relation_catalog"] == seed.relation_catalog for row in context_rows)
    assert all(row["relation_schema"] == seed.relation_schema for row in context_rows)
    assert all(row["gds_connection_id"] == seed.connection_id for row in context_rows)
    assert all(row["is_batch_attribute"] for row in context_rows)

    assert len(connection_rows) == 1
    connection_row = connection_rows[0]
    assert connection_row["failure_code"] is None
    assert connection_row["failure_message"] is None
    assert connection_row["gds_connection_id"] == seed.connection_id
    assert connection_row["environment_code"] == seed.environment_code
    assert _digest(connection_row["databricks_host_name"]) == _digest(
        seed.server_hostname
    )
    assert _digest(connection_row["databricks_http_path"]) == _digest(seed.http_path)
    assert _digest(connection_row["databricks_token"]) == _digest(seed.access_token)


def test_source_profiling_uses_only_foreign_catalog_coordinates(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(postgres_database)
    foreign_catalog = f"foreign_{uuid4().hex}"
    foreign_schema = f"source_{uuid4().hex}"
    with postgres_database.connect_owner() as connection:
        source_zone = connection.execute(
            "SELECT zone_id FROM reference.zone WHERE lower(btrim(zone_code)) = 'source'"
        ).fetchone()
        if source_zone is None:
            source_zone = require_row(
                connection.execute(
                    """
                    INSERT INTO reference.zone (zone_code, zone_name)
                    VALUES ('source', 'Source')
                    RETURNING zone_id
                    """
                ).fetchone()
            )
        connection.execute(
            """
            UPDATE core.connection
               SET has_foreign_catalog = TRUE,
                   foreign_catalog = %s
             WHERE connection_id = %s
            """,
            (foreign_catalog, seed.connection_id),
        )
        connection.execute(
            """
            UPDATE core.object
               SET zone_id = %s,
                   fc_object_schema = %s,
                   fc_object_name = 'fc_' || object_name
             WHERE object_id = ANY(%s::BIGINT[])
            """,
            (
                source_zone["zone_id"],
                foreign_schema,
                [row[0] for row in seed.attributes],
            ),
        )
        connection.execute(
            """
            UPDATE core.attribute
               SET fc_attribute_name = 'fc_' || attribute_name
             WHERE object_id = ANY(%s::BIGINT[])
            """,
            ([row[0] for row in seed.attributes],),
        )

    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        rows = connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            _execution_parameters(seed),
        ).fetchall()

    assert rows
    assert all(row["zone_code"] == "source" for row in rows)
    assert all(row["relation_catalog"] == foreign_catalog for row in rows)
    assert all(row["relation_schema"] == foreign_schema for row in rows)
    assert all(row["relation_object"] == row["fc_object_name"] for row in rows)
    assert all(row["relation_attribute"] == row["fc_attribute_name"] for row in rows)
    assert all(row["relation_object"] != row["object_name"] for row in rows)


def test_source_profiling_rejects_missing_foreign_catalog_metadata(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(postgres_database)
    with postgres_database.connect_owner() as connection:
        source_zone = connection.execute(
            "SELECT zone_id FROM reference.zone WHERE lower(btrim(zone_code)) = 'source'"
        ).fetchone()
        if source_zone is None:
            source_zone = require_row(
                connection.execute(
                    """
                    INSERT INTO reference.zone (zone_code, zone_name)
                    VALUES ('source', 'Source')
                    RETURNING zone_id
                    """
                ).fetchone()
            )
        connection.execute(
            """
            UPDATE core.connection
               SET has_foreign_catalog = TRUE,
                   foreign_catalog = 'foreign_catalog'
             WHERE connection_id = %s
            """,
            (seed.connection_id,),
        )
        connection.execute(
            """
            UPDATE core.object
               SET zone_id = %s,
                   fc_object_schema = NULL,
                   fc_object_name = 'foreign_object'
             WHERE object_id = ANY(%s::BIGINT[])
            """,
            (source_zone["zone_id"], [row[0] for row in seed.attributes]),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="profiling_relation_unavailable"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            _execution_parameters(seed),
        ).fetchall()


def test_profiling_context_requires_objects_to_belong_to_model_tenant(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(postgres_database)
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE core.object
               SET source_tenant_id = (
                       SELECT tenant_id
                         FROM core.tenant
                        WHERE tenant_id <> %s
                        ORDER BY tenant_id
                        LIMIT 1
                   )
             WHERE object_id = %s
            """,
            (seed.context.tenant_id, seed.attributes[0][0]),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="profiling_relation_unavailable"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            _execution_parameters(seed),
        ).fetchall()


def test_profiling_context_requires_active_attribute_for_every_object(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(postgres_database)
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE core.attribute
               SET is_active = FALSE
             WHERE object_id = %s
            """,
            (seed.attributes[-1][0],),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="profiling_attributes_missing"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            _execution_parameters(seed),
        ).fetchall()


def test_profiling_context_denies_another_tenant_principal(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(postgres_database)
    other_context = seed_workflow_context(postgres_database)

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(
            RaiseException,
            match="profiling_execution_denied: authorization_denied",
        ),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            (
                other_context.entra_tenant_id,
                other_context.entra_object_id,
                seed.workflow_run_id,
                seed.context.model_revision,
            ),
        ).fetchall()


@pytest.mark.parametrize(
    ("workflow", "start"),
    (("profiling", False), ("analysis", True)),
)
def test_profiling_context_requires_running_profiling_run(
    postgres_database: DisposablePostgres,
    workflow: str,
    start: bool,
) -> None:
    seed = _seed_profiling_execution(
        postgres_database,
        workflow=workflow,
        start=start,
    )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="profiling_run_not_running"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            _execution_parameters(seed),
        ).fetchall()


def test_profiling_context_requires_current_revision_and_owned_lock(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(postgres_database)

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="stale_model_revision"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            (
                seed.context.entra_tenant_id,
                seed.context.entra_object_id,
                seed.workflow_run_id,
                seed.context.model_revision + 1,
            ),
        ).fetchall()

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE security.tenant_lock
               SET tenant_lock_acquired_time =
                       CURRENT_TIMESTAMP - INTERVAL '2 minutes',
                   tenant_lock_expires_time =
                       CURRENT_TIMESTAMP - INTERVAL '1 minute'
             WHERE tenant_id = %s
            """,
            (seed.context.tenant_id,),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(
            RaiseException,
            match="profiling_execution_denied: tenant_lock_required",
        ),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            _execution_parameters(seed),
        ).fetchall()


def test_profiling_connection_gaps_return_fixed_failures_without_secrets(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(postgres_database)

    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        missing_environment = require_row(
            connection.execute(
                GET_PROFILING_CONNECTION_VALUES_SQL,
                (*_execution_parameters(seed), f"missing_{uuid4().hex}"),
            ).fetchone()
        )

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE core.connection_value AS connection_value
               SET connection_value = NULL
              FROM reference.connection_parameter AS parameter
             WHERE parameter.connection_parameter_id =
                   connection_value.connection_parameter_id
               AND connection_value.connection_id = %s
               AND lower(btrim(parameter.connection_parameter_code)) =
                   'databricks_token'
            """,
            (seed.connection_id,),
        )

    with psycopg.connect(
        postgres_database.web_runtime_dsn(),
        row_factory=dict_row,
    ) as connection:
        connection.execute("SET ROLE gds_web_write")
        missing_values = require_row(
            connection.execute(
                GET_PROFILING_CONNECTION_VALUES_SQL,
                (*_execution_parameters(seed), seed.environment_code),
            ).fetchone()
        )

    assert missing_environment["failure_code"] == "environment_not_found"
    assert missing_environment["failure_message"] == (
        "Profiling Environment is unavailable."
    )
    assert missing_values["failure_code"] == "connection_values_missing"
    assert missing_values["failure_message"] == (
        "Profiling GDS connection values are incomplete."
    )
    for failure in (missing_environment, missing_values):
        assert failure["gds_connection_id"] is None
        assert failure["databricks_host_name"] is None
        assert failure["databricks_http_path"] is None
        assert failure["databricks_token"] is None


def test_no_batch_context_rejects_multiple_source_tenants(
    postgres_database: DisposablePostgres,
) -> None:
    seed = _seed_profiling_execution(postgres_database)
    moved_object_id = seed.attributes[-1][0]
    second_schema = f"second_bronze_{uuid4().hex}"
    second_catalog = f"second_catalog_{uuid4().hex}"
    second_host = f"{uuid4().hex}.example.invalid"
    second_path = f"/sql/1.0/warehouses/{uuid4()}"
    second_token = uuid4().hex

    with postgres_database.connect_owner() as connection:
        physical = require_row(
            connection.execute(
                """
                SELECT source_tenant.project_id,
                       source_system.system_type_id,
                       source_connection.connection_type_id,
                       object_record.zone_id
                  FROM core.object AS object_record
                  JOIN core.connection AS source_connection
                    ON source_connection.connection_id = object_record.connection_id
                  JOIN core.tenant AS source_tenant
                    ON source_tenant.tenant_id = object_record.source_tenant_id
                  JOIN core.system AS source_system
                    ON source_system.system_id = source_connection.system_id
                 WHERE object_record.object_id = %s
                """,
                (moved_object_id,),
            ).fetchone()
        )
        second_tenant_id = require_row(
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
                    physical["project_id"],
                    f"second_source_{uuid4().hex}",
                    f"Second Source {uuid4().hex}",
                    second_catalog,
                    f"second_admin_{uuid4().hex}",
                ),
            ).fetchone()
        )["tenant_id"]
        second_system_id = require_row(
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
                    f"second_system_{uuid4().hex}",
                    f"Second System {uuid4().hex}",
                    physical["system_type_id"],
                ),
            ).fetchone()
        )["system_id"]
        second_connection_id = require_row(
            connection.execute(
                """
                INSERT INTO core.connection (
                    tenant_id,
                    system_id,
                    connection_code,
                    connection_name,
                    connection_type_id,
                    is_global_data_store
                ) VALUES (%s, %s, %s, %s, %s, TRUE)
                RETURNING connection_id
                """,
                (
                    second_tenant_id,
                    second_system_id,
                    f"second_gds_{uuid4().hex}",
                    f"Second GDS {uuid4().hex}",
                    physical["connection_type_id"],
                ),
            ).fetchone()
        )["connection_id"]
        connection.execute(
            """
            UPDATE core.object
               SET connection_id = %s,
                   source_tenant_id = %s,
                   object_schema = %s
             WHERE object_id = %s
            """,
            (second_connection_id, second_tenant_id, second_schema, moved_object_id),
        )
        environment_id = require_row(
            connection.execute(
                """
                SELECT environment_id
                  FROM reference.environment
                 WHERE environment_code = %s
                """,
                (seed.environment_code,),
            ).fetchone()
        )["environment_id"]
        parameter_ids = {
            str(row["connection_parameter_code"]).strip().lower(): int(
                row["connection_parameter_id"]
            )
            for row in connection.execute(
                """
                SELECT connection_parameter_id, connection_parameter_code
                  FROM reference.connection_parameter
                 WHERE lower(btrim(connection_parameter_code)) IN (
                           'databricks_host_name',
                           'databricks_http_path',
                           'databricks_token'
                       )
                """
            ).fetchall()
        }
        connection.execute(
            """
            INSERT INTO core.connection_value (
                environment_id,
                connection_id,
                connection_parameter_id,
                connection_value
            ) VALUES
                (%s, %s, %s, %s),
                (%s, %s, %s, %s),
                (%s, %s, %s, %s)
            """,
            (
                environment_id,
                second_connection_id,
                parameter_ids["databricks_host_name"],
                second_host,
                environment_id,
                second_connection_id,
                parameter_ids["databricks_http_path"],
                second_path,
                environment_id,
                second_connection_id,
                parameter_ids["databricks_token"],
                second_token,
            ),
        )

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(RaiseException, match="profiling_relation_unavailable"),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            _execution_parameters(seed),
        ).fetchall()


def test_web_role_has_function_only_profiling_credential_surface(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        privileges = require_row(
            connection.execute(
                """
                SELECT has_function_privilege(
                           'gds_web_write',
                           'application.get_profiling_execution_context(uuid,uuid,character varying,bigint,bigint)',
                           'EXECUTE'
                       ) AS web_context_execute,
                       has_function_privilege(
                           'gds_web_write',
                           'application.get_profiling_connection_values(uuid,uuid,character varying,bigint,bigint,character varying)',
                           'EXECUTE'
                       ) AS web_values_execute,
                       has_function_privilege(
                           'gds_app_write',
                           'application.get_profiling_execution_context(uuid,uuid,character varying,bigint,bigint)',
                           'EXECUTE'
                       ) AS mcp_context_execute,
                       has_function_privilege(
                           'gds_app_write',
                           'application.get_profiling_connection_values(uuid,uuid,character varying,bigint,bigint,character varying)',
                           'EXECUTE'
                       ) AS mcp_values_execute,
                       has_table_privilege(
                           'gds_web_write',
                           'core.connection_value',
                           'SELECT'
                       ) AS web_connection_value_select
                """
            ).fetchone()
        )

    assert privileges == {
        "web_context_execute": True,
        "web_values_execute": True,
        "mcp_context_execute": False,
        "mcp_values_execute": False,
        "web_connection_value_select": False,
    }

    with (
        psycopg.connect(
            postgres_database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection,
        pytest.raises(InsufficientPrivilege),
        connection.transaction(),
    ):
        connection.execute("SET ROLE gds_web_write")
        connection.execute("SELECT connection_value FROM core.connection_value")

    with (
        postgres_database.connect_runtime() as connection,
        pytest.raises(InsufficientPrivilege),
        connection.transaction(),
    ):
        connection.execute(
            GET_PROFILING_EXECUTION_CONTEXT_SQL,
            (uuid4(), uuid4(), 1, 1),
        )
