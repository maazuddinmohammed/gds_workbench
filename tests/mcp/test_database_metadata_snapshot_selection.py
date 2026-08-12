from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import pytest

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import TenantNotFoundError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from gds_etl_workbench.tools.snapshots.metadata.archive import (
    EncodedDataset,
    SnapshotArchive,
    SnapshotContractError,
)
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    SelectedMetadataSnapshot,
    create_metadata_snapshot,
    select_snapshot_datasets,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres
    from psycopg import Connection


@dataclass(frozen=True, slots=True)
class SelectionSeed:
    tenant_id: int
    tenant_code: str
    requested_connection_id: int
    global_connection_id: int
    object_type_id: int
    object_names_by_zone: dict[str, set[str]]
    excluded_object_names: set[str]


@pytest.mark.asyncio
async def test_selection_uses_all_approved_seeds_and_active_mapping_closure(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        seed = _seed_selection_graph(connection)

    selected = await _select(postgres_database, seed.tenant_id)
    encoded = selected.datasets
    assert selected.tenant_code == seed.tenant_code
    rows_by_dataset = {dataset.definition.name: _decode_rows(dataset) for dataset in encoded}

    assert list(rows_by_dataset) == [dataset.name for dataset in DATASETS]
    forbidden_columns = {"created_time", "created_by", "updated_time", "updated_by"}
    assert all(
        forbidden_columns.isdisjoint(row)
        and not any(column == "id" or column.endswith("_id") for column in row)
        for rows in rows_by_dataset.values()
        for row in rows
    )
    assert len(rows_by_dataset["project"]) == 1
    assert {row["tenant_code"] for row in rows_by_dataset["tenant"]} >= {seed.tenant_code}
    assert len(rows_by_dataset["system"]) == 1
    assert len(rows_by_dataset["connection"]) == 2
    assert len(rows_by_dataset["tenant_metadata_discovery_scope"]) == 1
    for dataset_name in (
        "system_type",
        "connection_type",
        "object_type",
        "zone",
        "chunk_type",
        "file_type",
        "data_operation",
        "process_type",
    ):
        assert dataset_name in rows_by_dataset
    for zone_code, expected_names in seed.object_names_by_zone.items():
        object_rows = rows_by_dataset[f"{zone_code}_object"]
        attribute_rows = rows_by_dataset[f"{zone_code}_attribute"]
        assert {row["object_name"] for row in object_rows} == expected_names
        assert {row["attribute_name"] for row in attribute_rows} == {
            f"{object_name}_attribute" for object_name in expected_names
        }
        assert all(row["zone_code"] == zone_code for row in object_rows)
        assert all("attributes" not in row for row in object_rows)

    all_object_names = {
        row["object_name"]
        for dataset_name, rows in rows_by_dataset.items()
        if dataset_name.endswith("_object")
        for row in rows
    }
    assert seed.excluded_object_names.isdisjoint(all_object_names)
    source_row = rows_by_dataset["source_object"][0]
    source_attribute = rows_by_dataset["source_attribute"][0]
    assert source_row["is_active"] is False
    assert source_attribute["is_active"] is False

    mapping_rows = rows_by_dataset["ingestion_object_mapping"]
    attribute_mapping_rows = rows_by_dataset["ingestion_attribute_mapping"]
    assert len(mapping_rows) == 4
    assert [row["is_active"] for row in mapping_rows].count(True) == 2
    assert [row["is_active"] for row in mapping_rows].count(False) == 2
    assert len(attribute_mapping_rows) == 2
    assert {row["is_active"] for row in attribute_mapping_rows} == {True, False}

    for dataset_name in (
        "copy_group",
        "member_group",
        "copy_group_control",
        "copy",
        "process_group",
        "process",
    ):
        assert len(rows_by_dataset[dataset_name]) == 1
    assert rows_by_dataset["copy_group"][0]["tenant_code"] == seed.tenant_code
    assert rows_by_dataset["copy_group"][0]["is_active"] is False
    assert rows_by_dataset["member_group"][0]["tenant_code"] == seed.tenant_code
    assert rows_by_dataset["member_group"][0]["is_active"] is False
    assert rows_by_dataset["copy_group_control"][0]["tenant_code"] == seed.tenant_code
    assert rows_by_dataset["copy"][0]["is_active"] is False
    assert rows_by_dataset["process_group"][0]["tenant_code"] == seed.tenant_code
    assert rows_by_dataset["process_group"][0]["is_active"] is False
    assert rows_by_dataset["process"][0]["is_active"] is False


@pytest.mark.asyncio
async def test_selection_rejects_invalid_active_discovery_configuration(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        seed = _seed_selection_graph(connection)
        connection.execute(
            """
            UPDATE core.connection
               SET is_global_data_store = FALSE
             WHERE connection_id = %s
            """,
            (seed.global_connection_id,),
        )

    with pytest.raises(SnapshotContractError, match="Discovery Scope configuration"):
        await _select(postgres_database, seed.tenant_id)


@pytest.mark.asyncio
async def test_selection_rejects_source_as_an_active_discovery_zone(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        seed = _seed_selection_graph(connection)
        source_zone_id = _ensure_zone(connection, "source")
        connection.execute(
            """
            UPDATE core.tenant_metadata_discovery_scope
               SET zone_id = %s
             WHERE tenant_id = %s
            """,
            (source_zone_id, seed.tenant_id),
        )

    with pytest.raises(SnapshotContractError, match="Discovery Scope configuration"):
        await _select(postgres_database, seed.tenant_id)


@pytest.mark.asyncio
async def test_selection_rejects_an_included_object_outside_the_four_zones(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        seed = _seed_selection_graph(connection)
        landing_zone_id = _ensure_zone(connection, "landing")
        _insert_object(
            connection,
            connection_id=seed.requested_connection_id,
            object_type_id=seed.object_type_id,
            zone_id=landing_zone_id,
            object_schema="landing_schema",
            object_name=f"SNAPSHOT_LANDING_{uuid4().hex[:12]}",
        )

    with pytest.raises(SnapshotContractError, match="unsupported or inactive Zone"):
        await _select(postgres_database, seed.tenant_id)


@pytest.mark.asyncio
async def test_selection_rejects_a_missing_tenant(
    postgres_database: DisposablePostgres,
) -> None:
    with pytest.raises(TenantNotFoundError):
        await _select(postgres_database, 9_223_372_036_854_775_000)


@pytest.mark.asyncio
async def test_complete_database_snapshot_builds_uploads_and_cleans_archive(
    postgres_database: DisposablePostgres,
) -> None:
    prefix = f"SNAPSHOT_EMPTY_{uuid4().hex[:12].upper()}"
    with postgres_database.connect_owner() as connection:
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
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING tenant_id
            """,
            (
                project["project_id"],
                f"{prefix}_TENANT",
                f"{prefix} Tenant",
                f"{prefix.lower()}_catalog",
                f"{prefix.lower()}_admin",
            ),
        ).fetchone()
        assert tenant is not None

    class ArchiveStore:
        def __init__(self) -> None:
            self.path: Path | None = None
            self.content = b""

        async def close(self) -> None:
            return None

        async def upload_archive(
            self,
            archive: SnapshotArchive,
            **_kwargs: Any,
        ) -> None:
            self.path = archive.path
            self.content = archive.path.read_bytes()

        async def create_read_url(self, **_kwargs: Any) -> str | None:
            raise AssertionError("not used")

    store = ArchiveStore()
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        ready = await create_metadata_snapshot(
            database,
            store,
            tenant_id=tenant["tenant_id"],
            request_principal=RequestPrincipal.development(),
            authorizer=AuthorizationService(),
            retention_hours=24,
            max_archive_bytes=268435456,
            created_at=datetime(2026, 8, 11, 16, 0, tzinfo=UTC),
            snapshot_id=UUID("7d7cc8ad-62b5-44ef-aeb0-c09c770ff233"),
        )
    finally:
        await database.close()

    assert ready.size_bytes == len(store.content)
    assert store.path is not None and not store.path.exists()
    with zipfile.ZipFile(BytesIO(store.content)) as archive:
        manifest = json.loads(archive.read("metadata-snapshot/manifest.json"))
    assert manifest["tenant_code"] == f"{prefix}_TENANT"
    assert manifest["counts"]["logical_dataset_count"] == 29
    assert manifest["counts"]["file_count"] == 70


async def _select(
    postgres_database: DisposablePostgres,
    tenant_id: int,
) -> SelectedMetadataSnapshot:
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        async with database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            return await select_snapshot_datasets(
                transaction,
                tenant_id=tenant_id,
                request_principal=RequestPrincipal.development(),
                authorizer=AuthorizationService(),
            )
    finally:
        await database.close()


def _decode_rows(dataset: EncodedDataset) -> list[dict[str, Any]]:
    return [
        cast(dict[str, Any], json.loads(line))
        for line in dataset.rows_jsonl.decode("utf-8").splitlines()
    ]


def _seed_selection_graph(connection: Connection[Any]) -> SelectionSeed:
    prefix = f"SNAPSHOT_{uuid4().hex[:12].upper()}"
    zone_ids = {
        zone_code: _ensure_zone(connection, zone_code)
        for zone_code in ("source", "bronze", "silver", "gold")
    }
    project = connection.execute(
        """
        INSERT INTO core.project (project_code, project_name)
        VALUES (%s, %s)
        RETURNING project_id
        """,
        (f"{prefix}_PROJECT", f"{prefix} Project"),
    ).fetchone()
    assert project is not None
    requested_tenant = connection.execute(
        """
        INSERT INTO core.tenant (
            project_id,
            tenant_code,
            tenant_name,
            tenant_catalog,
            gds_admin_catalog
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING tenant_id
        """,
        (
            project["project_id"],
            f"{prefix}_TENANT",
            f"{prefix} Tenant",
            f"{prefix.lower()}_catalog",
            f"{prefix.lower()}_admin",
        ),
    ).fetchone()
    global_tenant = connection.execute(
        """
        INSERT INTO core.tenant (
            project_id,
            tenant_code,
            tenant_name,
            tenant_catalog,
            gds_admin_catalog,
            tenant_visibility
        )
        VALUES (%s, %s, %s, %s, %s, 'global')
        RETURNING tenant_id
        """,
        (
            project["project_id"],
            f"{prefix}_GLOBAL_TENANT",
            f"{prefix} Global Tenant",
            f"{prefix.lower()}_global_catalog",
            f"{prefix.lower()}_global_admin",
        ),
    ).fetchone()
    assert requested_tenant is not None and global_tenant is not None

    system_type = connection.execute(
        """
        INSERT INTO reference.system_type (system_type_code, system_type_name)
        VALUES (%s, %s)
        RETURNING system_type_id
        """,
        (f"{prefix}_SYSTEM_TYPE", f"{prefix} System Type"),
    ).fetchone()
    assert system_type is not None
    system = connection.execute(
        """
        INSERT INTO core.system (system_code, system_name, system_type_id)
        VALUES (%s, %s, %s)
        RETURNING system_id
        """,
        (f"{prefix}_SYSTEM", f"{prefix} System", system_type["system_type_id"]),
    ).fetchone()
    assert system is not None
    connection_type = connection.execute(
        """
        INSERT INTO reference.connection_type (
            connection_type_code,
            connection_type_name
        )
        VALUES (%s, %s)
        RETURNING connection_type_id
        """,
        (f"{prefix}_CONNECTION_TYPE", f"{prefix} Connection Type"),
    ).fetchone()
    object_type = connection.execute(
        """
        INSERT INTO reference.object_type (object_type_code, object_type_name)
        VALUES (%s, %s)
        RETURNING object_type_id
        """,
        (f"{prefix}_OBJECT_TYPE", f"{prefix} Object Type"),
    ).fetchone()
    process_type = connection.execute(
        """
        INSERT INTO reference.process_type (process_type_name)
        VALUES (%s)
        RETURNING process_type_id
        """,
        (f"{prefix} Process Type",),
    ).fetchone()
    data_operation = connection.execute(
        """
        INSERT INTO reference.data_operation (data_operation_name)
        VALUES (%s)
        RETURNING data_operation_id
        """,
        (f"{prefix} Data Operation",),
    ).fetchone()
    assert connection_type is not None
    assert object_type is not None
    assert process_type is not None
    assert data_operation is not None

    requested_connection = connection.execute(
        """
        INSERT INTO core.connection (
            tenant_id,
            system_id,
            connection_code,
            connection_name,
            connection_type_id
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING connection_id
        """,
        (
            requested_tenant["tenant_id"],
            system["system_id"],
            f"{prefix}_REQUESTED",
            f"{prefix} Requested",
            connection_type["connection_type_id"],
        ),
    ).fetchone()
    global_connection = connection.execute(
        """
        INSERT INTO core.connection (
            tenant_id,
            system_id,
            connection_code,
            connection_name,
            connection_type_id,
            is_global_data_store
        )
        VALUES (%s, %s, %s, %s, %s, TRUE)
        RETURNING connection_id
        """,
        (
            global_tenant["tenant_id"],
            system["system_id"],
            f"{prefix}_GLOBAL",
            f"{prefix} Global",
            connection_type["connection_type_id"],
        ),
    ).fetchone()
    assert requested_connection is not None and global_connection is not None

    object_specs = (
        (
            "owned_source",
            "source",
            requested_connection["connection_id"],
            "owned",
            False,
        ),
        ("mapped_bronze", "bronze", global_connection["connection_id"], "mapped", True),
        ("mapped_silver", "silver", global_connection["connection_id"], "mapped", True),
        (
            "discovered_bronze",
            "bronze",
            global_connection["connection_id"],
            " risk_discovery ",
            True,
        ),
        ("copy_bronze", "bronze", global_connection["connection_id"], "copy", True),
        ("copy_gold", "gold", global_connection["connection_id"], "copy", True),
        ("process_gold", "gold", global_connection["connection_id"], "process", True),
        ("model_silver", "silver", global_connection["connection_id"], "model", True),
        (
            "inactive_model_gold",
            "gold",
            global_connection["connection_id"],
            "inactive_model",
            True,
        ),
        (
            "unrelated_bronze",
            "bronze",
            global_connection["connection_id"],
            "unrelated",
            True,
        ),
    )
    object_ids: dict[str, int] = {}
    object_names: dict[str, str] = {}
    for short_name, zone_code, connection_id, object_schema, is_active in object_specs:
        object_name = f"{prefix}_{short_name.upper()}"
        object_ids[short_name] = _insert_object(
            connection,
            connection_id=connection_id,
            object_type_id=object_type["object_type_id"],
            zone_id=zone_ids[zone_code],
            object_schema=object_schema,
            object_name=object_name,
            is_active=is_active,
        )
        object_names[short_name] = object_name

    connection.execute(
        """
        INSERT INTO core.attribute (
            object_id,
            attribute_name,
            attribute_ordinal_position,
            attribute_data_type,
            is_active
        )
        SELECT object_id,
               object_name || '_attribute',
               1,
               'BIGINT',
               FALSE
          FROM core.object
         WHERE object_id = ANY(%s::BIGINT[])
        """,
        (list(object_ids.values()),),
    )
    attribute_rows = connection.execute(
        """
        SELECT attribute_id, object_id
          FROM core.attribute
         WHERE object_id = ANY(%s::BIGINT[])
        """,
        (list(object_ids.values()),),
    ).fetchall()
    attribute_id_by_object_id = {row["object_id"]: row["attribute_id"] for row in attribute_rows}
    first_mapping = connection.execute(
        """
        INSERT INTO core.ingestion_object_mapping (
            source_object_id,
            target_object_id
        )
        VALUES (%s, %s)
        RETURNING ingestion_object_mapping_id
        """,
        (object_ids["owned_source"], object_ids["mapped_bronze"]),
    ).fetchone()
    second_mapping = connection.execute(
        """
        INSERT INTO core.ingestion_object_mapping (
            source_object_id,
            target_object_id
        )
        VALUES (%s, %s)
        RETURNING ingestion_object_mapping_id
        """,
        (object_ids["mapped_bronze"], object_ids["mapped_silver"]),
    ).fetchone()
    copy_mapping = connection.execute(
        """
        INSERT INTO core.ingestion_object_mapping (
            source_object_id,
            target_object_id,
            is_active
        )
        VALUES (%s, %s, FALSE)
        RETURNING ingestion_object_mapping_id
        """,
        (object_ids["copy_bronze"], object_ids["copy_gold"]),
    ).fetchone()
    inactive_unreferenced_mapping = connection.execute(
        """
        INSERT INTO core.ingestion_object_mapping (
            source_object_id,
            target_object_id,
            is_active
        )
        VALUES (%s, %s, FALSE)
        RETURNING ingestion_object_mapping_id
        """,
        (object_ids["discovered_bronze"], object_ids["model_silver"]),
    ).fetchone()
    unrelated_mapping = connection.execute(
        """
        INSERT INTO core.ingestion_object_mapping (
            source_object_id,
            target_object_id
        )
        VALUES (%s, %s)
        RETURNING ingestion_object_mapping_id
        """,
        (object_ids["unrelated_bronze"], object_ids["inactive_model_gold"]),
    ).fetchone()
    assert first_mapping is not None and second_mapping is not None and copy_mapping is not None
    assert inactive_unreferenced_mapping is not None and unrelated_mapping is not None
    connection.execute(
        """
        INSERT INTO core.ingestion_attribute_mapping (
            ingestion_object_mapping_id,
            source_object_id,
            target_object_id,
            source_attribute_id,
            target_attribute_id,
            is_active
        )
        VALUES (%s, %s, %s, %s, %s, TRUE),
               (%s, %s, %s, %s, %s, FALSE)
        """,
        (
            first_mapping["ingestion_object_mapping_id"],
            object_ids["owned_source"],
            object_ids["mapped_bronze"],
            attribute_id_by_object_id[object_ids["owned_source"]],
            attribute_id_by_object_id[object_ids["mapped_bronze"]],
            copy_mapping["ingestion_object_mapping_id"],
            object_ids["copy_bronze"],
            object_ids["copy_gold"],
            attribute_id_by_object_id[object_ids["copy_bronze"]],
            attribute_id_by_object_id[object_ids["copy_gold"]],
        ),
    )

    connection.execute(
        """
        INSERT INTO core.tenant_metadata_discovery_scope (
            tenant_id,
            connection_id,
            zone_id,
            object_schema
        )
        VALUES (%s, %s, %s, 'RISK_DISCOVERY')
        """,
        (
            requested_tenant["tenant_id"],
            global_connection["connection_id"],
            zone_ids["bronze"],
        ),
    )
    copy_group = connection.execute(
        """
        INSERT INTO core.copy_group (
            tenant_id,
            system_id,
            copy_group_name,
            is_active
        )
        VALUES (%s, %s, %s, FALSE)
        RETURNING copy_group_id
        """,
        (
            requested_tenant["tenant_id"],
            system["system_id"],
            f"{prefix} Copy Group",
        ),
    ).fetchone()
    assert copy_group is not None
    member_group = connection.execute(
        """
        INSERT INTO core.member_group (
            tenant_id,
            system_id,
            member_group_name,
            is_active
        )
        VALUES (%s, %s, %s, FALSE)
        RETURNING member_group_id
        """,
        (
            requested_tenant["tenant_id"],
            system["system_id"],
            f"{prefix} Member Group",
        ),
    ).fetchone()
    assert member_group is not None
    connection.execute(
        """
        INSERT INTO core.copy_group_control (
            copy_group_id,
            member_group_id,
            tenant_id,
            system_id
        )
        VALUES (%s, %s, %s, %s)
        """,
        (
            copy_group["copy_group_id"],
            member_group["member_group_id"],
            requested_tenant["tenant_id"],
            system["system_id"],
        ),
    )
    connection.execute(
        """
        INSERT INTO core.copy (
            copy_group_id,
            ingestion_object_mapping_id,
            copy_source_order,
            source_data_operation_id,
            target_data_operation_id,
            is_active
        )
        VALUES (%s, %s, 1, %s, %s, FALSE)
        """,
        (
            copy_group["copy_group_id"],
            copy_mapping["ingestion_object_mapping_id"],
            data_operation["data_operation_id"],
            data_operation["data_operation_id"],
        ),
    )
    process_group = connection.execute(
        """
        INSERT INTO core.process_group (
            tenant_id,
            system_id,
            zone_id,
            process_group_name,
            copy_group_id,
            is_active
        )
        VALUES (%s, %s, %s, %s, %s, FALSE)
        RETURNING process_group_id
        """,
        (
            requested_tenant["tenant_id"],
            system["system_id"],
            zone_ids["gold"],
            f"{prefix} Process Group",
            copy_group["copy_group_id"],
        ),
    ).fetchone()
    assert process_group is not None
    connection.execute(
        """
        INSERT INTO core.process (
            connection_id,
            object_id,
            process_execution_order,
            process_location,
            process_executable,
            process_type_id,
            process_group_id,
            is_active
        )
        VALUES (%s, %s, 1, %s, %s, %s, %s, FALSE)
        """,
        (
            global_connection["connection_id"],
            object_ids["process_gold"],
            f"/{prefix.lower()}/process",
            "run.py",
            process_type["process_type_id"],
            process_group["process_group_id"],
        ),
    )
    other_copy_group = connection.execute(
        """
        INSERT INTO core.copy_group (tenant_id, system_id, copy_group_name)
        VALUES (%s, %s, %s)
        RETURNING copy_group_id
        """,
        (
            global_tenant["tenant_id"],
            system["system_id"],
            f"{prefix} Other Copy Group",
        ),
    ).fetchone()
    other_member_group = connection.execute(
        """
        INSERT INTO core.member_group (tenant_id, system_id, member_group_name)
        VALUES (%s, %s, %s)
        RETURNING member_group_id
        """,
        (
            global_tenant["tenant_id"],
            system["system_id"],
            f"{prefix} Other Member Group",
        ),
    ).fetchone()
    assert other_copy_group is not None and other_member_group is not None
    connection.execute(
        """
        INSERT INTO core.copy_group_control (
            copy_group_id,
            member_group_id,
            tenant_id,
            system_id
        )
        VALUES (%s, %s, %s, %s)
        """,
        (
            other_copy_group["copy_group_id"],
            other_member_group["member_group_id"],
            global_tenant["tenant_id"],
            system["system_id"],
        ),
    )
    connection.execute(
        """
        INSERT INTO core.copy (
            copy_group_id,
            ingestion_object_mapping_id,
            copy_source_order,
            source_data_operation_id,
            target_data_operation_id
        )
        VALUES (%s, %s, 1, %s, %s)
        """,
        (
            other_copy_group["copy_group_id"],
            unrelated_mapping["ingestion_object_mapping_id"],
            data_operation["data_operation_id"],
            data_operation["data_operation_id"],
        ),
    )
    other_process_group = connection.execute(
        """
        INSERT INTO core.process_group (
            tenant_id,
            system_id,
            zone_id,
            process_group_name,
            copy_group_id
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING process_group_id
        """,
        (
            global_tenant["tenant_id"],
            system["system_id"],
            zone_ids["gold"],
            f"{prefix} Other Process Group",
            other_copy_group["copy_group_id"],
        ),
    ).fetchone()
    assert other_process_group is not None
    connection.execute(
        """
        INSERT INTO core.process (
            connection_id,
            object_id,
            process_execution_order,
            process_location,
            process_executable,
            process_type_id,
            process_group_id
        )
        VALUES (%s, %s, 1, %s, %s, %s, %s)
        """,
        (
            global_connection["connection_id"],
            object_ids["inactive_model_gold"],
            f"/{prefix.lower()}/other-process",
            "other.py",
            process_type["process_type_id"],
            other_process_group["process_group_id"],
        ),
    )
    active_model = connection.execute(
        """
        INSERT INTO model.model (tenant_id, model_name)
        VALUES (%s, %s)
        RETURNING model_id
        """,
        (requested_tenant["tenant_id"], f"{prefix} Active Model"),
    ).fetchone()
    inactive_model = connection.execute(
        """
        INSERT INTO model.model (tenant_id, model_name, is_active)
        VALUES (%s, %s, FALSE)
        RETURNING model_id
        """,
        (requested_tenant["tenant_id"], f"{prefix} Inactive Model"),
    ).fetchone()
    assert active_model is not None and inactive_model is not None
    connection.execute(
        """
        INSERT INTO model.model_scope (model_id, object_id)
        VALUES (%s, %s), (%s, %s)
        """,
        (
            active_model["model_id"],
            object_ids["model_silver"],
            inactive_model["model_id"],
            object_ids["inactive_model_gold"],
        ),
    )

    return SelectionSeed(
        tenant_id=requested_tenant["tenant_id"],
        tenant_code=f"{prefix}_TENANT",
        requested_connection_id=requested_connection["connection_id"],
        global_connection_id=global_connection["connection_id"],
        object_type_id=object_type["object_type_id"],
        object_names_by_zone={
            "source": {object_names["owned_source"]},
            "bronze": {
                object_names["mapped_bronze"],
                object_names["discovered_bronze"],
                object_names["copy_bronze"],
            },
            "silver": {
                object_names["mapped_silver"],
                object_names["model_silver"],
            },
            "gold": {
                object_names["copy_gold"],
                object_names["process_gold"],
            },
        },
        excluded_object_names={
            object_names["inactive_model_gold"],
            object_names["unrelated_bronze"],
        },
    )


def _ensure_zone(connection: Connection[Any], zone_code: str) -> int:
    connection.execute(
        """
        INSERT INTO reference.zone (zone_code, zone_name)
        VALUES (%s, initcap(%s))
        ON CONFLICT DO NOTHING
        """,
        (zone_code, zone_code),
    )
    row = connection.execute(
        """
        SELECT zone_id
          FROM reference.zone
         WHERE lower(btrim(zone_code)) = lower(btrim(%s))
        """,
        (zone_code,),
    ).fetchone()
    assert row is not None
    return row["zone_id"]


def _insert_object(
    connection: Connection[Any],
    *,
    connection_id: int,
    object_type_id: int,
    zone_id: int,
    object_schema: str,
    object_name: str,
    is_active: bool = True,
) -> int:
    row = connection.execute(
        """
        INSERT INTO core.object (
            connection_id,
            object_schema,
            object_name,
            object_type_id,
            zone_id,
            is_active
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING object_id
        """,
        (
            connection_id,
            object_schema,
            object_name,
            object_type_id,
            zone_id,
            is_active,
        ),
    ).fetchone()
    assert row is not None
    return row["object_id"]
