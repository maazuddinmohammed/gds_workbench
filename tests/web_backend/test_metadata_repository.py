from __future__ import annotations

from pathlib import Path
from typing import Any, LiteralString, Protocol, cast
from uuid import uuid4

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.tools.snapshots.metadata.contracts import (
    DATASETS_BY_NAME,
    normalize_natural_key_value,
)
from psycopg import Connection

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata import (
    FOUNDATIONAL_DATASETS,
    METADATA_DATASETS,
    REFERENCE_DATASETS,
    MetadataFilter,
    ObjectCatalogFilters,
    OperationalDataset,
    PostgresMetadataRepository,
)


class DisposablePostgres(Protocol):
    def connect_owner(self) -> Connection[dict[str, Any]]: ...

    def web_runtime_dsn(self) -> str: ...


DEMO_METADATA_SEED = (
    Path(__file__).parents[2] / "database" / "seed" / "01_metadata_snapshot_demo.sql"
)


class RecordingTransaction:
    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        one_row: dict[str, Any] | None = None,
    ) -> None:
        self.queries: list[tuple[LiteralString, tuple[Any, ...]]] = []
        self.rows = rows or []
        self.one_row = one_row

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.queries.append((query, parameters))
        return self.one_row

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        self.queries.append((query, parameters))
        return self.rows


@pytest.mark.asyncio
async def test_source_object_rows_are_tenant_scoped_filtered_and_bounded() -> None:
    transaction = RecordingTransaction()
    repository = PostgresMetadataRepository()

    result = await repository.list_rows(
        transaction,
        tenant_id=7,
        dataset="source_object",
        filters=(MetadataFilter(field="system_code", value="crm"),),
        limit=51,
        offset=0,
    )

    assert result == []
    assert len(transaction.queries) == 1
    query, parameters = transaction.queries[0]
    assert "WHERE tenant_id = %s" in query
    assert "zone.zone_code = %s" in query
    assert "lower(btrim(system.system_code)) IS NOT DISTINCT FROM %s" in query
    assert "crm" not in query
    assert "connection_value" not in query
    assert parameters == (7, "source", "crm", 51, 0)


@pytest.mark.asyncio
async def test_reference_rows_are_global_but_fixed_filtered_and_secret_free() -> None:
    transaction = RecordingTransaction()
    repository = PostgresMetadataRepository()

    result = await repository.list_rows(
        transaction,
        tenant_id=7,
        dataset="zone",
        filters=(MetadataFilter(field="zone_code", value="bronze"),),
        limit=51,
        offset=0,
    )

    assert result == []
    assert len(transaction.queries) == 1
    query, parameters = transaction.queries[0]
    assert "FROM reference.zone AS zone" in query
    assert "lower(btrim(zone.zone_code)) IS NOT DISTINCT FROM %s" in query
    assert "connection_value" not in query
    assert "core." not in query
    assert parameters == ("bronze", 51, 0)


@pytest.mark.asyncio
async def test_all_eight_reference_datasets_use_the_closed_global_query_registry() -> None:
    transaction = RecordingTransaction()
    repository = PostgresMetadataRepository()

    for dataset in REFERENCE_DATASETS:
        await repository.list_rows(
            transaction,
            tenant_id=7,
            dataset=dataset,
            filters=(),
            limit=2,
            offset=3,
        )

    assert len(transaction.queries) == 8
    for dataset, (query, parameters) in zip(REFERENCE_DATASETS, transaction.queries, strict=True):
        assert f"FROM reference.{dataset} AS {dataset}" in query
        assert "connection_value" not in query
        assert "core." not in query
        assert parameters == (2, 3)


@pytest.mark.asyncio
async def test_foundational_connection_rows_use_only_the_tenant_visible_closure() -> None:
    transaction = RecordingTransaction()
    repository = PostgresMetadataRepository()

    await repository.list_rows(
        transaction,
        tenant_id=7,
        dataset="connection",
        filters=(MetadataFilter(field="connection_code", value="main"),),
        limit=21,
        offset=4,
    )

    query, parameters = transaction.queries[0]
    assert "WITH RECURSIVE requested_tenant AS" in query
    assert "visible_objects AS" in query
    assert "visible_connection_ids AS" in query
    assert "FROM visible_connection_ids" in query
    assert "connection.connection_value" not in query
    assert "lower(btrim(connection.connection_code)) IS NOT DISTINCT FROM %s" in query
    assert parameters == (7, "main", 21, 4)


@pytest.mark.asyncio
async def test_all_five_foundational_datasets_use_the_selected_tenant_closure() -> None:
    transaction = RecordingTransaction()
    repository = PostgresMetadataRepository()

    for dataset in FOUNDATIONAL_DATASETS:
        await repository.list_rows(
            transaction,
            tenant_id=7,
            dataset=dataset,
            filters=(),
            limit=2,
            offset=3,
        )

    assert len(transaction.queries) == 5
    for query, parameters in transaction.queries:
        assert "WITH RECURSIVE requested_tenant AS" in query
        assert "connection_value" not in query
        assert parameters == (7, 2, 3)

    discovery_query = transaction.queries[4][0]
    assert "FROM requested_tenant" in discovery_query
    assert "JOIN core.tenant_metadata_discovery_scope AS scope" in discovery_query
    assert "scope.tenant_id = requested_tenant.tenant_id" in discovery_query
    assert "scope.gds_connection_id" in discovery_query
    assert "scope.zone_id" in discovery_query
    assert "scope.object_schema" in discovery_query


@pytest.mark.asyncio
async def test_each_object_dataset_uses_its_backend_selected_zone() -> None:
    transaction = RecordingTransaction()
    repository = PostgresMetadataRepository()

    for zone in ("source", "bronze", "silver", "gold"):
        await repository.list_rows(
            transaction,
            tenant_id=7,
            dataset=cast(OperationalDataset, f"{zone}_object"),
            filters=(),
            limit=2,
            offset=3,
        )

    assert [parameters for _, parameters in transaction.queries] == [
        (7, "source", 2, 3),
        (7, "bronze", 2, 3),
        (7, "silver", 2, 3),
        (7, "gold", 2, 3),
    ]


@pytest.mark.asyncio
async def test_object_filters_must_be_allowed_sorted_unique_and_normalized() -> None:
    repository = PostgresMetadataRepository()

    for invalid_filters in (
        (MetadataFilter(field="system_code", value=" CRM "),),
        (MetadataFilter(field="attribute_name", value="customer_id"),),
        (
            MetadataFilter(field="system_code", value="crm"),
            MetadataFilter(field="object_schema", value="sales"),
        ),
        (
            MetadataFilter(field="system_code", value="crm"),
            MetadataFilter(field="system_code", value="crm"),
        ),
    ):
        with pytest.raises(InvalidRequestError):
            await repository.list_rows(
                RecordingTransaction(),
                tenant_id=7,
                dataset="source_object",
                filters=invalid_filters,
                limit=10,
                offset=0,
            )

    transaction = RecordingTransaction()
    await repository.list_rows(
        transaction,
        tenant_id=7,
        dataset="source_object",
        filters=(
            MetadataFilter(field="is_active", value=True),
            MetadataFilter(field="object_schema", value="sales"),
        ),
        limit=10,
        offset=0,
    )

    query, parameters = transaction.queries[0]
    assert "object.is_active IS NOT DISTINCT FROM %s" in query
    assert "lower(btrim(object.object_schema)) IS NOT DISTINCT FROM %s" in query
    assert parameters == (7, "source", True, "sales", 10, 0)


@pytest.mark.asyncio
async def test_repository_rejects_unbounded_paging_before_querying() -> None:
    repository = PostgresMetadataRepository()

    for tenant_id, limit, offset in (
        (0, 10, 0),
        (7, 0, 0),
        (7, 202, 0),
        (7, 10, -1),
        (7, 10, 10_000_001),
    ):
        transaction = RecordingTransaction()
        with pytest.raises(InvalidRequestError):
            await repository.list_rows(
                transaction,
                tenant_id=tenant_id,
                dataset="source_object",
                filters=(),
                limit=limit,
                offset=offset,
            )
        assert transaction.queries == []

    with pytest.raises(InvalidRequestError):
        await repository.list_objects(
            RecordingTransaction(),
            tenant_id=7,
            filters=ObjectCatalogFilters(),
            limit=10,
            offset=10_000_001,
        )


@pytest.mark.asyncio
async def test_dataset_input_cannot_select_a_table_or_query() -> None:
    transaction = RecordingTransaction()

    with pytest.raises(InvalidRequestError):
        await PostgresMetadataRepository().list_rows(
            transaction,
            tenant_id=7,
            dataset=cast(OperationalDataset, "core.connection_value; SELECT *"),
            filters=(),
            limit=10,
            offset=0,
        )

    assert transaction.queries == []


@pytest.mark.asyncio
async def test_attribute_datasets_project_only_visible_objects_and_exposed_filters() -> None:
    transaction = RecordingTransaction()
    repository = PostgresMetadataRepository()

    for zone in ("source", "bronze", "silver", "gold"):
        await repository.list_rows(
            transaction,
            tenant_id=7,
            dataset=cast(OperationalDataset, f"{zone}_attribute"),
            filters=(),
            limit=4,
            offset=1,
        )

    assert [parameters for _, parameters in transaction.queries] == [
        (7, "source", 4, 1),
        (7, "bronze", 4, 1),
        (7, "silver", 4, 1),
        (7, "gold", 4, 1),
    ]
    query = transaction.queries[0][0]
    assert "JOIN visible_objects" in query
    assert "attribute.attribute_custom_code" in query
    assert "business_glossary" not in query

    filtered_transaction = RecordingTransaction()
    await repository.list_rows(
        filtered_transaction,
        tenant_id=7,
        dataset="bronze_attribute",
        filters=(
            MetadataFilter(field="attribute_name", value="customer_id"),
            MetadataFilter(field="is_natural_key", value=True),
        ),
        limit=5,
        offset=0,
    )
    filtered_query, parameters = filtered_transaction.queries[0]
    assert "lower(btrim(attribute.attribute_name)) IS NOT DISTINCT FROM %s" in filtered_query
    assert "attribute.is_natural_key IS NOT DISTINCT FROM %s" in filtered_query
    assert parameters == (7, "bronze", "customer_id", True, 5, 0)


@pytest.mark.asyncio
async def test_ingestion_mapping_datasets_require_both_objects_in_tenant_visibility() -> None:
    transaction = RecordingTransaction()
    repository = PostgresMetadataRepository()

    await repository.list_rows(
        transaction,
        tenant_id=7,
        dataset="ingestion_object_mapping",
        filters=(
            MetadataFilter(field="source_system_code", value="crm"),
            MetadataFilter(field="target_object_name", value="customer_bronze"),
        ),
        limit=8,
        offset=2,
    )
    await repository.list_rows(
        transaction,
        tenant_id=7,
        dataset="ingestion_attribute_mapping",
        filters=(),
        limit=9,
        offset=3,
    )

    object_query, object_parameters = transaction.queries[0]
    assert "JOIN visible_objects AS source_visible" in object_query
    assert "JOIN visible_objects AS target_visible" in object_query
    assert "lower(btrim(source_system.system_code)) IS NOT DISTINCT FROM %s" in object_query
    assert "lower(btrim(target_object.object_name)) IS NOT DISTINCT FROM %s" in object_query
    assert object_parameters == (7, "crm", "customer_bronze", 8, 2)

    attribute_query, attribute_parameters = transaction.queries[1]
    assert "source_attribute.attribute_name AS source_attribute_name" in attribute_query
    assert "target_attribute.attribute_name AS target_attribute_name" in attribute_query
    assert attribute_parameters == (7, 9, 3)


@pytest.mark.asyncio
async def test_copy_configuration_datasets_are_scoped_through_their_owning_tenant() -> None:
    transaction = RecordingTransaction()
    repository = PostgresMetadataRepository()

    for dataset in ("copy_group", "member_group", "copy_group_control"):
        await repository.list_rows(
            transaction,
            tenant_id=7,
            dataset=cast(OperationalDataset, dataset),
            filters=(),
            limit=11,
            offset=4,
        )
    await repository.list_rows(
        transaction,
        tenant_id=7,
        dataset="copy",
        filters=(
            MetadataFilter(field="copy_source_order", value=1),
            MetadataFilter(field="is_active", value=True),
        ),
        limit=12,
        offset=5,
    )

    for query, parameters in transaction.queries[:3]:
        assert "tenant_id = %s" in query
        assert parameters == (7, 11, 4)

    copy_query, copy_parameters = transaction.queries[3]
    assert "JOIN visible_objects AS source_visible" in copy_query
    assert "JOIN visible_objects AS target_visible" in copy_query
    assert "copy_group.tenant_id = (SELECT tenant_id FROM requested_tenant)" in copy_query
    assert "copy.copy_source_record_limit::TEXT AS copy_source_record_limit" in copy_query
    assert "copy.copy_source_order IS NOT DISTINCT FROM %s" in copy_query
    assert "copy.is_active IS NOT DISTINCT FROM %s" in copy_query
    assert copy_parameters == (7, 1, True, 12, 5)


@pytest.mark.asyncio
async def test_process_datasets_are_scoped_through_their_owning_process_group() -> None:
    transaction = RecordingTransaction()
    repository = PostgresMetadataRepository()

    await repository.list_rows(
        transaction,
        tenant_id=7,
        dataset="process_group",
        filters=(),
        limit=13,
        offset=0,
    )
    await repository.list_rows(
        transaction,
        tenant_id=7,
        dataset="process",
        filters=(
            MetadataFilter(field="process_execution_order", value=3),
            MetadataFilter(field="process_location", value="/jobs/customer"),
        ),
        limit=13,
        offset=1,
    )

    group_query, group_parameters = transaction.queries[0]
    assert "process_group.tenant_id = %s" in group_query
    assert group_parameters == (7, 13, 0)

    process_query, process_parameters = transaction.queries[1]
    assert "JOIN visible_objects" in process_query
    assert "process_group.tenant_id = (SELECT tenant_id FROM requested_tenant)" in process_query
    assert "object_tenant.tenant_code AS object_tenant_code" in process_query
    assert "process.process_execution_order IS NOT DISTINCT FROM %s" in process_query
    assert "process.process_location IS NOT DISTINCT FROM %s" in process_query
    assert process_parameters == (7, 3, "/jobs/customer", 13, 1)


@pytest.mark.asyncio
async def test_object_list_is_tenant_visible_filtered_and_bounded() -> None:
    transaction = RecordingTransaction(
        rows=[
            {
                "object_id": 101,
                "object_schema": "sales",
                "object_name": "CustomerSilver",
                "object_type_code": "TABLE",
                "zone_code": "silver",
                "connection_id": 11,
                "connection_code": "MAIN",
                "system_id": 3,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
                "source_tenant_id": 8,
                "source_tenant_code": "GRDM",
                "source_tenant_name": "Global Reference Data",
                "attribute_count": 12,
                "batch_attribute_name": "UpdatedAt",
                "is_active": False,
            }
        ]
    )
    repository = PostgresMetadataRepository()

    result = await repository.list_objects(
        transaction,
        tenant_id=7,
        filters=ObjectCatalogFilters(
            zone="silver",
            system_code="crm",
            source_tenant_code="grdm",
            active_state="inactive",
        ),
        limit=21,
        offset=2,
    )

    assert result[0].object_id == 101
    query, parameters = transaction.queries[0]
    assert "FROM visible_objects" in query
    assert "connection_value" not in query
    assert "lower(btrim(zone.zone_code)) = %s" in query
    assert "lower(btrim(system.system_code)) = %s" in query
    assert "lower(btrim(source_tenant.tenant_code)) = %s" in query
    assert parameters == (
        7,
        "silver",
        "silver",
        "crm",
        "crm",
        "grdm",
        "grdm",
        "inactive",
        "inactive",
        21,
        2,
    )


@pytest.mark.asyncio
async def test_object_detail_rechecks_visibility_and_bounds_attributes() -> None:
    transaction = RecordingTransaction(
        one_row={
            "object_id": 101,
            "object_schema": "sales",
            "object_name": "CustomerSilver",
            "object_type_code": "TABLE",
            "object_type_name": "Table",
            "object_description": "Curated customers",
            "zone_code": "silver",
            "connection_id": 11,
            "connection_code": "MAIN",
            "connection_name": "Shared Silver",
            "system_id": 3,
            "system_code": "CRM",
            "system_name": "Customer Relationship Management",
            "source_tenant_id": 8,
            "source_tenant_code": "GRDM",
            "source_tenant_name": "Global Reference Data",
            "attribute_count": 1,
            "batch_attribute_name": "UpdatedAt",
            "is_locked": False,
            "is_active": True,
        },
        rows=[
            {
                "attribute_id": 501,
                "attribute_name": "CustomerId",
                "attribute_ordinal_position": 1,
                "attribute_description": "Customer key",
                "attribute_data_type": "BIGINT",
                "attribute_nullability": False,
                "is_surrogate_key": True,
                "is_natural_key": False,
                "is_meta_data": False,
                "is_masking_required": False,
                "is_mapped": True,
                "is_purge": False,
                "is_active": True,
            }
        ],
    )
    repository = PostgresMetadataRepository()

    result = await repository.get_object(
        transaction,
        tenant_id=7,
        object_id=101,
    )

    assert result is not None
    assert result.object_name == "CustomerSilver"
    assert result.attributes[0].attribute_name == "CustomerId"
    detail_query, detail_parameters = transaction.queries[0]
    attribute_query, attribute_parameters = transaction.queries[1]
    assert "FROM visible_objects" in detail_query
    assert "connection_value" not in detail_query
    assert detail_parameters == (7, 101)
    assert "FROM visible_objects" in attribute_query
    assert "LIMIT %s" in attribute_query
    assert attribute_parameters == (7, 101, 2001)


@pytest.mark.asyncio
async def test_all_repository_queries_execute_with_the_web_role(
    web_postgres_database: DisposablePostgres,
) -> None:
    suffix = uuid4().hex[:12]
    with web_postgres_database.connect_owner() as connection:
        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES (%s, %s)
            RETURNING project_id
            """,
            (f"WEB_META_PROJECT_{suffix}", f"Web Metadata Project {suffix}"),
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
                f"WEB_META_TENANT_{suffix}",
                f"Web Metadata Tenant {suffix}",
                f"web_meta_{suffix}",
                f"web_meta_admin_{suffix}",
            ),
        ).fetchone()
        assert tenant is not None
        tenant_id = tenant["tenant_id"]
        assert isinstance(tenant_id, int) and not isinstance(tenant_id, bool)

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    repository = PostgresMetadataRepository()
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            for dataset in METADATA_DATASETS:
                rows = await repository.list_rows(
                    transaction,
                    tenant_id=tenant_id,
                    dataset=dataset,
                    filters=(),
                    limit=1,
                    offset=0,
                )
                for row in rows:
                    DATASETS_BY_NAME[dataset].row_model.model_validate(dict(row), strict=True)
                    assert "connection_value" not in row
            assert (
                await repository.list_objects(
                    transaction,
                    tenant_id=tenant_id,
                    filters=ObjectCatalogFilters(active_state="all"),
                    limit=1,
                    offset=0,
                )
                == ()
            )
            assert (
                await repository.get_object(
                    transaction,
                    tenant_id=tenant_id,
                    object_id=9_223_372_036_854_775_000,
                )
                is None
            )
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_gds_object_tenant_comes_only_from_active_discovery_scope(
    web_postgres_database: DisposablePostgres,
) -> None:
    suffix = uuid4().hex[:12]
    unassigned_object_name = f"unassigned_customer_{suffix}"
    with web_postgres_database.connect_owner() as connection:
        existing = connection.execute(
            "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
        ).fetchone()
        if existing is None:
            connection.execute(cast(LiteralString, DEMO_METADATA_SEED.read_text(encoding="utf-8")))
        tenant = connection.execute(
            "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
        ).fetchone()
        source_object = connection.execute(
            """
            SELECT object.object_id
              FROM core.object AS object
              JOIN core.connection AS connection
                ON connection.connection_id = object.connection_id
             WHERE connection.connection_code = 'DEMO_SOURCE'
             ORDER BY object.object_id
             LIMIT 1
            """
        ).fetchone()
        unassigned_object = connection.execute(
            """
            INSERT INTO core.object (
                connection_id,
                object_schema,
                object_name,
                object_type_id,
                zone_id
            )
            SELECT connection.connection_id,
                   %s,
                   %s,
                   object_type.object_type_id,
                   zone.zone_id
              FROM core.connection AS connection
             CROSS JOIN reference.object_type AS object_type
             CROSS JOIN reference.zone AS zone
             WHERE connection.connection_code = 'DEMO_GDS'
               AND object_type.object_type_code = 'TABLE'
               AND zone.zone_code = 'bronze'
            RETURNING object_id
            """,
            (f"unassigned_{suffix}", unassigned_object_name),
        ).fetchone()
        assert tenant is not None
        assert source_object is not None
        assert unassigned_object is not None
        connection.execute(
            """
            INSERT INTO core.ingestion_object_mapping (
                source_object_id, target_object_id
            )
            VALUES (%s, %s)
            """,
            (source_object["object_id"], unassigned_object["object_id"]),
        )
        tenant_id = tenant["tenant_id"]
        assert isinstance(tenant_id, int) and not isinstance(tenant_id, bool)

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    repository = PostgresMetadataRepository()
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            bronze_objects = await repository.list_rows(
                transaction,
                tenant_id=tenant_id,
                dataset="bronze_object",
                filters=(),
                limit=200,
                offset=0,
            )
            bronze_attributes = await repository.list_rows(
                transaction,
                tenant_id=tenant_id,
                dataset="bronze_attribute",
                filters=(),
                limit=200,
                offset=0,
            )
            object_mappings = await repository.list_rows(
                transaction,
                tenant_id=tenant_id,
                dataset="ingestion_object_mapping",
                filters=(),
                limit=200,
                offset=0,
            )
            copies = await repository.list_rows(
                transaction,
                tenant_id=tenant_id,
                dataset="copy",
                filters=(),
                limit=200,
                offset=0,
            )
            processes = await repository.list_rows(
                transaction,
                tenant_id=tenant_id,
                dataset="process",
                filters=(),
                limit=200,
                offset=0,
            )
            objects = await repository.list_objects(
                transaction,
                tenant_id=tenant_id,
                filters=ObjectCatalogFilters(zone="bronze", active_state="all"),
                limit=200,
                offset=0,
            )
            detail = await repository.get_object(
                transaction,
                tenant_id=tenant_id,
                object_id=objects[0].object_id,
            )

        assert bronze_objects
        assert bronze_attributes
        assert object_mappings
        assert copies
        assert processes
        assert objects
        assert detail is not None
        assert {row["tenant_code"] for row in bronze_objects} == {"DEMO_TENANT"}
        assert {row["tenant_code"] for row in bronze_attributes} == {"DEMO_TENANT"}
        assert {row["source_tenant_code"] for row in object_mappings} == {"DEMO_TENANT"}
        assert {row["target_tenant_code"] for row in object_mappings} == {"DEMO_TENANT"}
        assert {row["source_tenant_code"] for row in copies} == {"DEMO_TENANT"}
        assert {row["target_tenant_code"] for row in copies} == {"DEMO_TENANT"}
        assert {row["object_tenant_code"] for row in processes} == {"DEMO_TENANT"}
        assert {row.source_tenant_code for row in objects} == {"DEMO_TENANT"}
        assert detail.source_tenant_code == "DEMO_TENANT"
        assert unassigned_object_name not in {str(row["object_name"]) for row in bronze_objects}
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_all_metadata_rows_and_object_details_match_shared_contracts(
    web_postgres_database: DisposablePostgres,
) -> None:
    hidden_suffix = uuid4().hex[:12]
    hidden_tenant_code = f"HIDDEN_TENANT_{hidden_suffix}"
    hidden_connection_code = f"HIDDEN_{hidden_suffix}"
    hidden_object_name = f"hidden_customer_{hidden_suffix}"
    with web_postgres_database.connect_owner() as connection:
        existing = connection.execute(
            "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
        ).fetchone()
        if existing is None:
            connection.execute(cast(LiteralString, DEMO_METADATA_SEED.read_text(encoding="utf-8")))
        tenant = connection.execute(
            "SELECT tenant_id FROM core.tenant WHERE tenant_code = 'DEMO_TENANT'"
        ).fetchone()
        assert tenant is not None
        tenant_id = tenant["tenant_id"]
        assert isinstance(tenant_id, int) and not isinstance(tenant_id, bool)
        hidden_tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog
            )
            SELECT project_id, %s, %s, %s, %s
              FROM core.project
             WHERE project_code = 'DEMO_PROJECT'
            RETURNING tenant_id
            """,
            (
                hidden_tenant_code,
                f"Hidden Tenant {hidden_suffix}",
                f"hidden_{hidden_suffix}",
                f"hidden_admin_{hidden_suffix}",
            ),
        ).fetchone()
        assert hidden_tenant is not None
        hidden_connection = connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id,
                system_id,
                connection_code,
                connection_name,
                connection_type_id
            )
            SELECT %s,
                   system.system_id,
                   %s,
                   %s,
                   connection_type.connection_type_id
              FROM core.system AS system
             CROSS JOIN reference.connection_type AS connection_type
             WHERE system.system_code = 'DEMO_CUSTOMER_SYSTEM'
               AND connection_type.connection_type_code = 'DEMO_POSTGRESQL'
            RETURNING connection_id
            """,
            (
                hidden_tenant["tenant_id"],
                hidden_connection_code,
                f"Hidden Connection {hidden_suffix}",
            ),
        ).fetchone()
        assert hidden_connection is not None
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
                   'hidden',
                   %s,
                   object_type.object_type_id,
                   zone.zone_id
              FROM reference.object_type AS object_type
             CROSS JOIN reference.zone AS zone
             WHERE object_type.object_type_code = 'TABLE'
               AND zone.zone_code = 'source'
            """,
            (hidden_connection["connection_id"], hidden_object_name),
        )

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    repository = PostgresMetadataRepository()
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            for dataset in METADATA_DATASETS:
                rows = await repository.list_rows(
                    transaction,
                    tenant_id=tenant_id,
                    dataset=dataset,
                    filters=(),
                    limit=200,
                    offset=0,
                )
                assert rows
                row_model = DATASETS_BY_NAME[dataset].row_model
                for row in rows:
                    document = dict(row)
                    row_model.model_validate(document, strict=True)
                    assert "connection_value" not in document
                    assert not any(column.endswith("_id") for column in document)
                if dataset == "source_object":
                    assert hidden_object_name not in {str(row["object_name"]) for row in rows}
                if dataset == "tenant":
                    assert hidden_tenant_code not in {str(row["tenant_code"]) for row in rows}
                if dataset == "connection":
                    assert hidden_connection_code not in {
                        str(row["connection_code"]) for row in rows
                    }
                first = dict(rows[0])
                all_filters = tuple(
                    MetadataFilter.model_validate(
                        {
                            "field": field,
                            "value": normalize_natural_key_value(field, first[field]),
                        },
                        strict=True,
                    )
                    for field in sorted(DATASETS_BY_NAME[dataset].search_fields)
                )
                filtered_rows = await repository.list_rows(
                    transaction,
                    tenant_id=tenant_id,
                    dataset=dataset,
                    filters=all_filters,
                    limit=200,
                    offset=0,
                )
                assert len(filtered_rows) == 1

            objects = await repository.list_objects(
                transaction,
                tenant_id=tenant_id,
                filters=ObjectCatalogFilters(active_state="all"),
                limit=200,
                offset=0,
            )
            assert len(objects) == 4
            detail = await repository.get_object(
                transaction,
                tenant_id=tenant_id,
                object_id=objects[0].object_id,
            )
            assert detail is not None
            assert detail.attribute_count == 2
            assert len(detail.attributes) == 2
    finally:
        await database.close()
