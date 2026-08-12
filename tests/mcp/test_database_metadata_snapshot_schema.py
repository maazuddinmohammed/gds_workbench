from __future__ import annotations

from typing import TYPE_CHECKING

from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS

if TYPE_CHECKING:
    from conftest import DisposablePostgres


PHYSICAL_NATURAL_KEYS = {
    "core.project": ("project_code",),
    "core.tenant": ("tenant_code",),
    "core.system": ("system_code",),
    "core.connection": ("tenant_id", "system_id", "connection_code"),
    "core.tenant_metadata_discovery_scope": (
        "tenant_id",
        "connection_id",
        "zone_id",
        "object_schema",
    ),
    "reference.system_type": ("system_type_code",),
    "reference.connection_type": ("connection_type_code",),
    "reference.object_type": ("object_type_code",),
    "reference.zone": ("zone_code",),
    "reference.chunk_type": ("chunk_type_name",),
    "reference.file_type": ("file_type_name",),
    "reference.data_operation": ("data_operation_name",),
    "reference.process_type": ("process_type_name",),
    "core.object": ("connection_id", "object_schema", "object_name"),
    "core.attribute": ("object_id", "attribute_name"),
    "core.ingestion_object_mapping": ("source_object_id", "target_object_id"),
    "core.ingestion_attribute_mapping": (
        "ingestion_object_mapping_id",
        "source_attribute_id",
        "target_attribute_id",
    ),
    "core.copy_group": ("tenant_id", "system_id", "copy_group_name"),
    "core.member_group": ("tenant_id", "system_id", "member_group_name"),
    "core.copy_group_control": ("copy_group_id", "member_group_id"),
    "core.copy": ("copy_group_id", "ingestion_object_mapping_id"),
    "core.process_group": (
        "tenant_id",
        "system_id",
        "zone_id",
        "process_group_name",
    ),
    "core.process": (
        "process_group_id",
        "process_execution_order",
        "process_location",
        "process_executable",
    ),
}


def test_snapshot_natural_keys_still_have_database_unique_indexes(
    postgres_database: DisposablePostgres,
) -> None:
    physical_tables = {dataset.database_table for dataset in DATASETS}
    assert physical_tables == set(PHYSICAL_NATURAL_KEYS)

    with postgres_database.connect_owner() as connection:
        for database_table, physical_key in PHYSICAL_NATURAL_KEYS.items():
            database_schema, table_name = database_table.split(".", maxsplit=1)
            unique_indexes = connection.execute(
                """
                SELECT pg_get_indexdef(index_record.indexrelid) AS definition
                  FROM pg_index AS index_record
                  JOIN pg_class AS table_record
                    ON table_record.oid = index_record.indrelid
                  JOIN pg_namespace AS table_namespace
                    ON table_namespace.oid = table_record.relnamespace
                 WHERE table_namespace.nspname = %s
                   AND table_record.relname = %s
                   AND index_record.indisunique
                 ORDER BY index_record.indexrelid::REGCLASS::TEXT
                """,
                (database_schema, table_name),
            ).fetchall()
            assert any(
                all(column_name in row["definition"] for column_name in physical_key)
                for row in unique_indexes
            ), (database_table, physical_key)
