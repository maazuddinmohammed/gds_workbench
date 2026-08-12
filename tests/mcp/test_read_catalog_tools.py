from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from mcp import Client
from mcp.types import TextContent

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.mcp.server import create_mcp_server
from gds_etl_workbench.configuration import RuntimeSettings

if TYPE_CHECKING:
    from conftest import DisposablePostgres


@dataclass(frozen=True, slots=True)
class CatalogSeed:
    tenant_id: int
    source_connection_id: int
    gds_connection_id: int
    source_object_id: int
    bronze_object_id: int
    unmapped_bronze_object_id: int
    unrelated_bronze_object_id: int
    ingestion_mapping_id: int
    system_id: int
    copy_group_id: int
    copy_id: int
    process_group_id: int
    process_id: int


def _settings() -> RuntimeSettings:
    return RuntimeSettings.from_environment(
        {
            "GDS_ENVIRONMENT": "local",
            "GDS_DATABASE_DSN": "postgresql://app@db.example.invalid/workbench",
            "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_MCP_PUBLIC_URL": "https://testserver/mcp",
            "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": (
                "https://snapshot.blob.core.windows.net"
            ),
            "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
        }
    )


@pytest.fixture(scope="module")
def catalog_seed(postgres_database: DisposablePostgres) -> CatalogSeed:
    prefix = f"CATALOG_{uuid4().hex[:12].upper()}"
    with postgres_database.connect_owner() as connection, connection.transaction():
        system_type_id = _reference_id(
            connection,
            table="system_type",
            id_column="system_type_id",
            code_column="system_type_code",
            name_column="system_type_name",
            code=f"{prefix}_SYSTEM_TYPE",
            name=f"{prefix} System Type",
        )
        connection_type_id = _reference_id(
            connection,
            table="connection_type",
            id_column="connection_type_id",
            code_column="connection_type_code",
            name_column="connection_type_name",
            code=f"{prefix}_CONNECTION_TYPE",
            name=f"{prefix} Connection Type",
        )
        object_type_id = _reference_id(
            connection,
            table="object_type",
            id_column="object_type_id",
            code_column="object_type_code",
            name_column="object_type_name",
            code=f"{prefix}_OBJECT_TYPE",
            name=f"{prefix} Object Type",
        )
        source_zone_id = _zone_id(connection, "source", "Source")
        bronze_zone_id = _zone_id(connection, "bronze", "Bronze")

        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES (%s, %s)
            RETURNING project_id
            """,
            (f"{prefix}_PROJECT", f"{prefix} Project"),
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id, tenant_code, tenant_name, tenant_description,
                tenant_catalog, gds_admin_catalog
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING tenant_id
            """,
            (
                project["project_id"],
                f"{prefix}_TENANT",
                f"{prefix} Tenant",
                "Catalog tool integration Tenant",
                f"{prefix.lower()}_catalog",
                f"{prefix.lower()}_admin",
            ),
        ).fetchone()
        gds_tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id, tenant_code, tenant_name,
                tenant_catalog, gds_admin_catalog
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING tenant_id
            """,
            (
                project["project_id"],
                f"{prefix}_GDS_TENANT",
                f"{prefix} GDS Tenant",
                f"{prefix.lower()}_gds_catalog",
                f"{prefix.lower()}_gds_admin",
            ),
        ).fetchone()
        assert tenant is not None and gds_tenant is not None
        system = connection.execute(
            """
            INSERT INTO core.system (
                system_code, system_name, system_description, system_type_id
            )
            VALUES (%s, %s, %s, %s)
            RETURNING system_id
            """,
            (
                f"{prefix}_SYSTEM",
                f"{prefix} System",
                "Catalog tool integration System",
                system_type_id,
            ),
        ).fetchone()
        assert system is not None
        source_connection = connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id, is_global_data_store
            )
            VALUES (%s, %s, %s, %s, %s, FALSE)
            RETURNING connection_id
            """,
            (
                tenant["tenant_id"],
                system["system_id"],
                f"{prefix}_SOURCE",
                f"{prefix} Source",
                connection_type_id,
            ),
        ).fetchone()
        gds_connection = connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id, system_id, connection_code, connection_name,
                connection_type_id, is_global_data_store
            )
            VALUES (%s, %s, %s, %s, %s, TRUE)
            RETURNING connection_id
            """,
            (
                gds_tenant["tenant_id"],
                system["system_id"],
                f"{prefix}_GDS",
                f"{prefix} GDS",
                connection_type_id,
            ),
        ).fetchone()
        assert source_connection is not None and gds_connection is not None
        connection.execute(
            "UPDATE core.tenant SET gds_connection_id = %s WHERE tenant_id = %s",
            (gds_connection["connection_id"], tenant["tenant_id"]),
        )
        connection.execute(
            """
            INSERT INTO core.tenant_metadata_discovery_scope (
                tenant_id, connection_id, zone_id, object_schema
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                tenant["tenant_id"],
                gds_connection["connection_id"],
                bronze_zone_id,
                f"{prefix.lower()}_bronze",
            ),
        )
        objects = connection.execute(
            """
            INSERT INTO core.object (
                connection_id, object_schema, object_name, object_description,
                object_type_id, zone_id
            )
            VALUES
                (%s, %s, 'customer', 'Source customer', %s, %s),
                (%s, %s, 'customer', 'Bronze customer', %s, %s),
                (%s, %s, 'unmapped_customer', 'Unmapped Bronze customer', %s, %s),
                (%s, %s, 'private_other', 'Unrelated Bronze object', %s, %s)
            RETURNING object_id, zone_id, object_name
            """,
            (
                source_connection["connection_id"],
                f"{prefix.lower()}_source",
                object_type_id,
                source_zone_id,
                gds_connection["connection_id"],
                f"{prefix.lower()}_bronze",
                object_type_id,
                bronze_zone_id,
                gds_connection["connection_id"],
                f"{prefix.lower()}_bronze",
                object_type_id,
                bronze_zone_id,
                gds_connection["connection_id"],
                f"{prefix.lower()}_other_bronze",
                object_type_id,
                bronze_zone_id,
            ),
        ).fetchall()
        source_object_id = next(
            int(row["object_id"])
            for row in objects
            if row["object_name"] == "customer" and row["zone_id"] == source_zone_id
        )
        bronze_object_id = next(
            int(row["object_id"])
            for row in objects
            if row["object_name"] == "customer" and row["zone_id"] == bronze_zone_id
        )
        unmapped_bronze_object_id = next(
            int(row["object_id"])
            for row in objects
            if row["object_name"] == "unmapped_customer"
        )
        unrelated_bronze_object_id = next(
            int(row["object_id"])
            for row in objects
            if row["object_name"] == "private_other"
        )
        connection.execute(
            """
            INSERT INTO core.attribute (
                object_id, attribute_name, attribute_ordinal_position,
                attribute_description, attribute_data_type,
                attribute_nullability, is_natural_key
            )
            VALUES
                (%s, 'customer_id', 1, 'Source customer ID', 'BIGINT', FALSE, TRUE),
                (%s, 'customer_name', 2, 'Source customer name', 'VARCHAR(200)', TRUE, FALSE),
                (%s, 'customer_id', 1, 'Bronze customer ID', 'BIGINT', FALSE, TRUE)
            """,
            (source_object_id, source_object_id, bronze_object_id),
        )
        mapping = connection.execute(
            """
            INSERT INTO core.ingestion_object_mapping (
                source_object_id, target_object_id
            )
            VALUES (%s, %s)
            RETURNING ingestion_object_mapping_id
            """,
            (source_object_id, bronze_object_id),
        ).fetchone()
        assert mapping is not None
        connection.execute(
            """
            INSERT INTO core.ingestion_attribute_mapping (
                ingestion_object_mapping_id,
                source_object_id,
                target_object_id,
                source_attribute_id,
                target_attribute_id
            )
            SELECT %s, %s, %s, source.attribute_id, target.attribute_id
              FROM core.attribute AS source
              JOIN core.attribute AS target
                ON target.object_id = %s
               AND target.attribute_name = source.attribute_name
             WHERE source.object_id = %s
            """,
            (
                mapping["ingestion_object_mapping_id"],
                source_object_id,
                bronze_object_id,
                bronze_object_id,
                source_object_id,
            ),
        )
        chunk_type_id = _named_reference_id(
            connection,
            table="chunk_type",
            id_column="chunk_type_id",
            name_column="chunk_type_name",
            name=f"{prefix} Full",
        )
        file_type_id = _named_reference_id(
            connection,
            table="file_type",
            id_column="file_type_id",
            name_column="file_type_name",
            name=f"{prefix} Parquet",
        )
        read_operation_id = _named_reference_id(
            connection,
            table="data_operation",
            id_column="data_operation_id",
            name_column="data_operation_name",
            name=f"{prefix} Read",
        )
        write_operation_id = _named_reference_id(
            connection,
            table="data_operation",
            id_column="data_operation_id",
            name_column="data_operation_name",
            name=f"{prefix} Write",
        )
        process_type_id = _named_reference_id(
            connection,
            table="process_type",
            id_column="process_type_id",
            name_column="process_type_name",
            name=f"{prefix} Notebook",
        )
        silver_zone_id = _zone_id(connection, "silver", "Silver")
        copy_group = connection.execute(
            """
            INSERT INTO core.copy_group (
                tenant_id, system_id, copy_group_name,
                copy_group_description, is_member_group_required
            )
            VALUES (%s, %s, %s, %s, TRUE)
            RETURNING copy_group_id
            """,
            (
                tenant["tenant_id"],
                system["system_id"],
                f"{prefix} Copy Group",
                "Catalog tool integration Copy Group",
            ),
        ).fetchone()
        member_group = connection.execute(
            """
            INSERT INTO core.member_group (
                tenant_id, system_id, member_group_name, member_group_description
            )
            VALUES (%s, %s, %s, %s)
            RETURNING member_group_id
            """,
            (
                tenant["tenant_id"],
                system["system_id"],
                f"{prefix} Member Group",
                "Catalog tool integration Member Group",
            ),
        ).fetchone()
        assert copy_group is not None and member_group is not None
        connection.execute(
            """
            INSERT INTO core.copy_group_control (
                copy_group_id, member_group_id, tenant_id, system_id
            )
            VALUES (%s, %s, %s, %s)
            """,
            (
                copy_group["copy_group_id"],
                member_group["member_group_id"],
                tenant["tenant_id"],
                system["system_id"],
            ),
        )
        copy = connection.execute(
            """
            INSERT INTO core.copy (
                copy_group_id, ingestion_object_mapping_id,
                copy_source_record_limit, chunk_type_id,
                copy_source_initial_sql_script, copy_source_file_name,
                source_file_type_id, copy_source_order,
                source_data_operation_id, target_data_operation_id
            )
            VALUES (%s, %s, 1000, %s, 'sensitive sql', 'customer.parquet',
                    %s, 1, %s, %s)
            RETURNING copy_id
            """,
            (
                copy_group["copy_group_id"],
                mapping["ingestion_object_mapping_id"],
                chunk_type_id,
                file_type_id,
                read_operation_id,
                write_operation_id,
            ),
        ).fetchone()
        other_tenant_copy_group = connection.execute(
            """
            INSERT INTO core.copy_group (
                tenant_id, system_id, copy_group_name, is_member_group_required
            )
            VALUES (%s, %s, %s, FALSE)
            RETURNING copy_group_id
            """,
            (
                gds_tenant["tenant_id"],
                system["system_id"],
                f"{prefix} Other Tenant Copy Group",
            ),
        ).fetchone()
        assert other_tenant_copy_group is not None
        connection.execute(
            """
            INSERT INTO core.copy (
                copy_group_id, ingestion_object_mapping_id, copy_source_order,
                source_data_operation_id, target_data_operation_id
            )
            VALUES (%s, %s, 1, %s, %s)
            """,
            (
                other_tenant_copy_group["copy_group_id"],
                mapping["ingestion_object_mapping_id"],
                read_operation_id,
                write_operation_id,
            ),
        )
        process_group = connection.execute(
            """
            INSERT INTO core.process_group (
                tenant_id, system_id, zone_id, process_group_name,
                process_group_description, copy_group_id
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING process_group_id
            """,
            (
                tenant["tenant_id"],
                system["system_id"],
                silver_zone_id,
                f"{prefix} Process Group",
                "Catalog tool integration Process Group",
                copy_group["copy_group_id"],
            ),
        ).fetchone()
        assert copy is not None and process_group is not None
        process = connection.execute(
            """
            INSERT INTO core.process (
                connection_id, object_id, process_execution_order,
                process_location, process_executable, process_type_id,
                process_group_id
            )
            VALUES (%s, %s, 1, '/sensitive/path', 'sensitive_notebook', %s, %s)
            RETURNING process_id
            """,
            (
                gds_connection["connection_id"],
                bronze_object_id,
                process_type_id,
                process_group["process_group_id"],
            ),
        ).fetchone()
        assert process is not None

    return CatalogSeed(
        tenant_id=tenant["tenant_id"],
        source_connection_id=source_connection["connection_id"],
        gds_connection_id=gds_connection["connection_id"],
        source_object_id=source_object_id,
        bronze_object_id=bronze_object_id,
        unmapped_bronze_object_id=unmapped_bronze_object_id,
        unrelated_bronze_object_id=unrelated_bronze_object_id,
        ingestion_mapping_id=mapping["ingestion_object_mapping_id"],
        system_id=system["system_id"],
        copy_group_id=copy_group["copy_group_id"],
        copy_id=copy["copy_id"],
        process_group_id=process_group["process_group_id"],
        process_id=process["process_id"],
    )


@pytest.mark.asyncio
async def test_get_tenant_details_returns_connection_grain_zone_counts(
    postgres_database: DisposablePostgres,
    catalog_seed: CatalogSeed,
) -> None:
    database = postgres_database.create_runtime_adapter()
    settings = _settings()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        result = await client.call_tool(
            "get_tenant_details",
            {"tenant_id": catalog_seed.tenant_id},
        )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["tenant"]["tenant_id"] == catalog_seed.tenant_id
    connections = {
        item["connection_id"]: item for item in result.structured_content["connections"]
    }
    assert connections[catalog_seed.source_connection_id]["active_object_counts"] == {
        "source": 1,
        "bronze": 0,
        "silver": 0,
        "gold": 0,
    }
    assert connections[catalog_seed.gds_connection_id]["active_object_counts"] == {
        "source": 0,
        "bronze": 2,
        "silver": 0,
        "gold": 0,
    }
    assert (
        connections[catalog_seed.gds_connection_id]["is_tenant_gds_connection"] is True
    )
    assert (
        connections[catalog_seed.gds_connection_id]["is_discovery_connection"] is True
    )


@pytest.mark.asyncio
async def test_list_objects_includes_unmapped_discovery_scope_object(
    postgres_database: DisposablePostgres,
    catalog_seed: CatalogSeed,
) -> None:
    database = postgres_database.create_runtime_adapter()
    settings = _settings()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        result = await client.call_tool(
            "list_objects",
            {"tenant_id": catalog_seed.tenant_id, "zone": "bronze"},
        )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["next_cursor"] is None
    unmapped = next(
        item
        for item in result.structured_content["objects"]
        if item["object_id"] == catalog_seed.unmapped_bronze_object_id
    )
    assert unmapped["object_name"] == "unmapped_customer"
    assert unmapped["zone"] == "bronze"
    assert unmapped["connection_id"] == catalog_seed.gds_connection_id
    assert unmapped["attribute_count"] == 0
    assert unmapped["has_ingestion_mapping"] is False
    assert unmapped["is_owned_by_tenant"] is False
    assert unmapped["is_discovered_by_scope"] is True
    assert unmapped["is_copy_referenced"] is False
    assert unmapped["is_process_referenced"] is False


@pytest.mark.asyncio
async def test_get_objects_returns_batched_objects_and_attributes(
    postgres_database: DisposablePostgres,
    catalog_seed: CatalogSeed,
) -> None:
    database = postgres_database.create_runtime_adapter()
    settings = _settings()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        result = await client.call_tool(
            "get_objects",
            {
                "tenant_id": catalog_seed.tenant_id,
                "object_ids": [
                    catalog_seed.bronze_object_id,
                    catalog_seed.source_object_id,
                ],
            },
        )
        rejected = await client.call_tool(
            "get_objects",
            {
                "tenant_id": catalog_seed.tenant_id,
                "object_ids": [
                    catalog_seed.source_object_id,
                    catalog_seed.unrelated_bronze_object_id,
                ],
            },
        )

    assert result.is_error is False
    assert result.structured_content is not None
    objects = result.structured_content["objects"]
    assert [item["object_id"] for item in objects] == [
        catalog_seed.bronze_object_id,
        catalog_seed.source_object_id,
    ]
    assert [attribute["attribute_name"] for attribute in objects[0]["attributes"]] == [
        "customer_id"
    ]
    assert [attribute["attribute_name"] for attribute in objects[1]["attributes"]] == [
        "customer_id",
        "customer_name",
    ]
    assert objects[1]["attributes"][0]["is_natural_key"] is True

    assert rejected.is_error is True
    assert isinstance(rejected.content[0], TextContent)
    assert rejected.content[0].text.endswith(
        "invalid_request: One or more Objects were not found."
    )


@pytest.mark.asyncio
async def test_get_object_lineage_returns_direct_ingestion_mapping(
    postgres_database: DisposablePostgres,
    catalog_seed: CatalogSeed,
) -> None:
    database = postgres_database.create_runtime_adapter()
    settings = _settings()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        result = await client.call_tool(
            "get_object_lineage",
            {
                "tenant_id": catalog_seed.tenant_id,
                "object_id": catalog_seed.bronze_object_id,
                "direction": "upstream",
            },
        )

    assert result.is_error is False
    assert result.structured_content is not None
    mappings = result.structured_content["mappings"]
    assert len(mappings) == 1
    assert (
        mappings[0]["ingestion_object_mapping_id"] == catalog_seed.ingestion_mapping_id
    )
    assert mappings[0]["direction"] == "upstream"
    assert mappings[0]["source_object"]["object_id"] == catalog_seed.source_object_id
    assert mappings[0]["target_object"]["object_id"] == catalog_seed.bronze_object_id
    assert mappings[0]["attribute_mapping_count"] == 1
    assert mappings[0]["copy_count"] == 1


@pytest.mark.asyncio
async def test_copy_group_tools_resolve_tenant_owned_ingestion_configuration(
    postgres_database: DisposablePostgres,
    catalog_seed: CatalogSeed,
) -> None:
    database = postgres_database.create_runtime_adapter()
    settings = _settings()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        listed = await client.call_tool(
            "list_copy_groups",
            {"tenant_id": catalog_seed.tenant_id},
        )
        detailed = await client.call_tool(
            "get_copy_group",
            {
                "tenant_id": catalog_seed.tenant_id,
                "copy_group_id": catalog_seed.copy_group_id,
            },
        )

    assert listed.is_error is False
    assert listed.structured_content is not None
    group = next(
        item
        for item in listed.structured_content["copy_groups"]
        if item["copy_group_id"] == catalog_seed.copy_group_id
    )
    assert group["system_id"] == catalog_seed.system_id
    assert group["copy_count"] == 1
    assert group["control_count"] == 1
    assert group["process_group_count"] == 1

    assert detailed.is_error is False
    assert detailed.structured_content is not None
    assert detailed.structured_content["copy_group"]["copy_group_id"] == (
        catalog_seed.copy_group_id
    )
    assert detailed.structured_content["copy_group"]["process_group_count"] == 1
    assert detailed.structured_content["copies"][0]["copy_id"] == catalog_seed.copy_id
    assert detailed.structured_content["copies"][0]["has_initial_sql"] is True
    assert detailed.structured_content["copies"][0]["source_object"]["object_id"] == (
        catalog_seed.source_object_id
    )
    assert detailed.structured_content["controls"][0]["member_group_name"].endswith(
        "Member Group"
    )
    assert (
        "copy_source_initial_sql_script" not in detailed.structured_content["copies"][0]
    )
    assert (
        "copy_group_control_last_run_value"
        not in detailed.structured_content["controls"][0]
    )


@pytest.mark.asyncio
async def test_process_group_tools_resolve_through_tenant_copy_groups(
    postgres_database: DisposablePostgres,
    catalog_seed: CatalogSeed,
) -> None:
    database = postgres_database.create_runtime_adapter()
    settings = _settings()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        listed = await client.call_tool(
            "list_process_groups",
            {"tenant_id": catalog_seed.tenant_id},
        )
        detailed = await client.call_tool(
            "get_process_group",
            {
                "tenant_id": catalog_seed.tenant_id,
                "process_group_id": catalog_seed.process_group_id,
            },
        )

    assert listed.is_error is False
    assert listed.structured_content is not None
    group = next(
        item
        for item in listed.structured_content["process_groups"]
        if item["process_group_id"] == catalog_seed.process_group_id
    )
    assert group["copy_group_id"] == catalog_seed.copy_group_id
    assert group["process_count"] == 1
    assert group["declared_zone"] == "silver"

    assert detailed.is_error is False
    assert detailed.structured_content is not None
    process = detailed.structured_content["processes"][0]
    assert process["process_id"] == catalog_seed.process_id
    assert process["object"]["object_id"] == catalog_seed.bronze_object_id
    assert process["object"]["zone"] == "bronze"
    assert process["connection_id"] == catalog_seed.gds_connection_id
    assert "process_location" not in process
    assert "process_executable" not in process


@pytest.mark.asyncio
async def test_copy_and_process_group_ids_are_scoped_to_the_requested_tenant(
    postgres_database: DisposablePostgres,
    catalog_seed: CatalogSeed,
) -> None:
    database = postgres_database.create_runtime_adapter()
    settings = _settings()
    server = create_mcp_server(settings, database, IdentityProvider(settings.auth_mode))

    async with Client(server) as client:
        wrong_copy_tenant = await client.call_tool(
            "get_copy_group",
            {
                "tenant_id": catalog_seed.tenant_id + 1,
                "copy_group_id": catalog_seed.copy_group_id,
            },
        )
        wrong_process_tenant = await client.call_tool(
            "get_process_group",
            {
                "tenant_id": catalog_seed.tenant_id + 1,
                "process_group_id": catalog_seed.process_group_id,
            },
        )

    assert wrong_copy_tenant.is_error is True
    assert wrong_process_tenant.is_error is True


def _reference_id(
    connection: Any,
    *,
    table: str,
    id_column: str,
    code_column: str,
    name_column: str,
    code: str,
    name: str,
) -> int:
    row = connection.execute(
        f"""
        INSERT INTO reference.{table} ({code_column}, {name_column})
        VALUES (%s, %s)
        RETURNING {id_column}
        """,
        (code, name),
    ).fetchone()
    assert row is not None
    return int(row[id_column])


def _zone_id(connection: Any, code: str, name: str) -> int:
    row = connection.execute(
        "SELECT zone_id FROM reference.zone WHERE zone_code = %s",
        (code,),
    ).fetchone()
    if row is None:
        row = connection.execute(
            """
            INSERT INTO reference.zone (zone_code, zone_name)
            VALUES (%s, %s)
            RETURNING zone_id
            """,
            (code, name),
        ).fetchone()
    assert row is not None
    return int(row["zone_id"])


def _named_reference_id(
    connection: Any,
    *,
    table: str,
    id_column: str,
    name_column: str,
    name: str,
) -> int:
    row = connection.execute(
        f"""
        INSERT INTO reference.{table} ({name_column})
        VALUES (%s)
        RETURNING {id_column}
        """,
        (name,),
    ).fetchone()
    assert row is not None
    return int(row[id_column])
