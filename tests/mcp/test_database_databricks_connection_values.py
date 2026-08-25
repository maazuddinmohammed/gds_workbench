from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from conftest import DisposablePostgres


@dataclass(frozen=True, slots=True)
class DatabricksConnectionSeed:
    source_connection_id: int
    no_gds_source_connection_id: int
    gds_connection_id: int
    tenant_id: int
    environment_code: str
    missing_environment_code: str
    server_hostname: str = field(repr=False)
    http_path: str = field(repr=False)
    access_token: str = field(repr=False)


@pytest.fixture(scope="module")
def databricks_connection_seed(
    postgres_database: DisposablePostgres,
) -> DatabricksConnectionSeed:
    prefix = f"DBSQL_{uuid4().hex[:12].upper()}"
    server_hostname = f"{uuid4().hex}.example.invalid"
    http_path = f"/sql/1.0/warehouses/{uuid4()}"
    access_token = uuid4().hex

    with postgres_database.connect_owner() as connection, connection.transaction():
        environment_rows = connection.execute(
            """
            INSERT INTO reference.environment (environment_code, environment_name)
            VALUES (%s, %s), (%s, %s)
            RETURNING environment_id, environment_code
            """,
            (
                f"{prefix}_ENV_1",
                f"{prefix} Environment 1",
                f"{prefix}_ENV_2",
                f"{prefix} Environment 2",
            ),
        ).fetchall()
        system_type = connection.execute(
            """
            INSERT INTO reference.system_type (system_type_code, system_type_name)
            VALUES (%s, %s)
            RETURNING system_type_id
            """,
            (f"{prefix}_SYSTEM_TYPE", f"{prefix} System Type"),
        ).fetchone()
        connection_type = connection.execute(
            """
            INSERT INTO reference.connection_type (
                connection_type_code, connection_type_name
            )
            VALUES (%s, %s)
            RETURNING connection_type_id
            """,
            (f"{prefix}_CONNECTION_TYPE", f"{prefix} Connection Type"),
        ).fetchone()
        connection.execute(
            """
            INSERT INTO reference.connection_parameter (
                connection_parameter_code, connection_parameter_name
            )
            VALUES
                ('DATABRICKS_HOST_NAME', 'Databricks Host Name'),
                ('Databricks_HTTP_Path', 'Databricks HTTP Path'),
                ('databricks_token', 'Databricks Token')
            ON CONFLICT DO NOTHING
            """
        )
        parameter_rows = connection.execute(
            """
            SELECT connection_parameter_id, connection_parameter_code
              FROM reference.connection_parameter
             WHERE lower(btrim(connection_parameter_code)) IN (
                       'databricks_host_name',
                       'databricks_http_path',
                       'databricks_token'
                   )
             ORDER BY lower(btrim(connection_parameter_code))
            """
        ).fetchall()
        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES (%s, %s)
            RETURNING project_id
            """,
            (f"{prefix}_PROJECT", f"{prefix} Project"),
        ).fetchone()
        assert system_type is not None
        assert connection_type is not None
        assert project is not None
        assert len(environment_rows) == 2
        assert len(parameter_rows) == 3

        tenant_rows = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id, tenant_code, tenant_name,
                tenant_catalog, gds_admin_catalog
            )
            VALUES
                (%s, %s, %s, %s, %s),
                (%s, %s, %s, %s, %s)
            RETURNING tenant_id
            """,
            (
                project["project_id"],
                f"{prefix}_TENANT",
                f"{prefix} Tenant",
                f"{prefix.lower()}_catalog",
                f"{prefix.lower()}_admin",
                project["project_id"],
                f"{prefix}_NO_GDS_TENANT",
                f"{prefix} No GDS Tenant",
                f"{prefix.lower()}_no_gds_catalog",
                f"{prefix.lower()}_no_gds_admin",
            ),
        ).fetchall()
        system = connection.execute(
            """
            INSERT INTO core.system (
                system_code, system_name, system_type_id
            )
            VALUES (%s, %s, %s)
            RETURNING system_id
            """,
            (
                f"{prefix}_SYSTEM",
                f"{prefix} System",
                system_type["system_type_id"],
            ),
        ).fetchone()
        assert len(tenant_rows) == 2 and system is not None
        tenant = tenant_rows[0]
        no_gds_tenant = tenant_rows[1]

        connection_rows = connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id, is_global_data_store
            )
            VALUES
                (%s, %s, %s, %s, %s, FALSE),
                (%s, %s, %s, %s, %s, TRUE),
                (%s, %s, %s, %s, %s, FALSE)
            RETURNING connection_id
            """,
            (
                tenant["tenant_id"],
                system["system_id"],
                f"{prefix}_SOURCE",
                f"{prefix} Source",
                connection_type["connection_type_id"],
                tenant["tenant_id"],
                system["system_id"],
                f"{prefix}_GDS",
                f"{prefix} GDS",
                connection_type["connection_type_id"],
                no_gds_tenant["tenant_id"],
                system["system_id"],
                f"{prefix}_NO_GDS_SOURCE",
                f"{prefix} No GDS Source",
                connection_type["connection_type_id"],
            ),
        ).fetchall()
        assert len(connection_rows) == 3
        parameter_ids = {
            str(row["connection_parameter_code"]).strip().lower(): int(
                row["connection_parameter_id"]
            )
            for row in parameter_rows
        }
        environment_ids = [int(row["environment_id"]) for row in environment_rows]
        source_connection_id = int(connection_rows[0]["connection_id"])
        gds_connection_id = int(connection_rows[1]["connection_id"])

        connection.execute(
            "UPDATE core.tenant SET gds_connection_id = %s WHERE tenant_id = %s",
            (gds_connection_id, tenant["tenant_id"]),
        )

        _insert_connection_values(
            connection,
            connection_id=gds_connection_id,
            environment_id=environment_ids[0],
            parameter_ids=parameter_ids,
            values=(server_hostname, http_path, access_token),
        )

    return DatabricksConnectionSeed(
        source_connection_id=source_connection_id,
        no_gds_source_connection_id=int(connection_rows[2]["connection_id"]),
        gds_connection_id=gds_connection_id,
        tenant_id=int(tenant["tenant_id"]),
        environment_code=str(environment_rows[0]["environment_code"]),
        missing_environment_code=str(environment_rows[1]["environment_code"]),
        server_hostname=server_hostname,
        http_path=http_path,
        access_token=access_token,
    )


def _insert_connection_values(
    connection: Any,
    *,
    connection_id: int,
    environment_id: int,
    parameter_ids: dict[str, int],
    values: tuple[str, str, str],
) -> None:
    connection.execute(
        """
        INSERT INTO core.connection_value (
            environment_id, connection_id, connection_parameter_id,
            connection_value
        )
        VALUES (%s, %s, %s, %s), (%s, %s, %s, %s), (%s, %s, %s, %s)
        """,
        (
            environment_id,
            connection_id,
            parameter_ids["databricks_host_name"],
            values[0],
            environment_id,
            connection_id,
            parameter_ids["databricks_http_path"],
            values[1],
            environment_id,
            connection_id,
            parameter_ids["databricks_token"],
            values[2],
        ),
    )


@pytest.mark.asyncio
async def test_runtime_adapter_derives_gds_values_for_requested_environment(
    postgres_database: DisposablePostgres,
    databricks_connection_seed: DatabricksConnectionSeed,
) -> None:
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        complete = await database.read_databricks_connection_values(
            databricks_connection_seed.source_connection_id,
            databricks_connection_seed.environment_code.lower(),
        )
        missing = await database.read_databricks_connection_values(
            databricks_connection_seed.source_connection_id,
            databricks_connection_seed.missing_environment_code,
        )
        environment_not_found = await database.read_databricks_connection_values(
            databricks_connection_seed.source_connection_id,
            "environment-that-does-not-exist",
        )
        submitted_gds = await database.read_databricks_connection_values(
            databricks_connection_seed.gds_connection_id,
            databricks_connection_seed.environment_code,
        )
        no_gds = await database.read_databricks_connection_values(
            databricks_connection_seed.no_gds_source_connection_id,
            databricks_connection_seed.environment_code,
        )
    finally:
        await database.close()

    assert complete.tenant_id == databricks_connection_seed.tenant_id
    assert complete.gds_connection_id == databricks_connection_seed.gds_connection_id
    assert complete.environment_code == databricks_connection_seed.environment_code
    assert complete.failure_code is None
    assert complete.server_hostname == databricks_connection_seed.server_hostname
    assert complete.http_path == databricks_connection_seed.http_path
    assert complete.access_token == databricks_connection_seed.access_token
    assert databricks_connection_seed.server_hostname not in repr(complete)
    assert databricks_connection_seed.http_path not in repr(complete)
    assert databricks_connection_seed.access_token not in repr(complete)

    assert missing.failure_code == "connection_values_missing"
    assert missing.server_hostname is None
    assert missing.http_path is None
    assert missing.access_token is None
    assert environment_not_found.failure_code == "environment_not_found"
    assert submitted_gds.failure_code == "connection_not_found"
    assert no_gds.failure_code == "gds_connection_not_found"
