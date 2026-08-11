"""Static Metadata Snapshot table and dataset contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal


class SnapshotSection(StrEnum):
    FOUNDATION = "foundation"
    METADATA = "metadata"


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    name: str
    label: str
    database_table: str
    section: SnapshotSection
    change_set_eligible: bool
    primary_key: tuple[str, ...]
    display_columns: tuple[str, ...]

    @property
    def directory(self) -> PurePosixPath:
        database_schema, _table_name = self.database_table.split(".", maxsplit=1)
        return PurePosixPath(self.section.value, database_schema, self.name)

    @property
    def data_path(self) -> str:
        return (self.directory / "rows.jsonl").as_posix()

    @property
    def index_path(self) -> str:
        return (self.directory / "index.jsonl").as_posix()


type ColumnType = Literal[
    "bigint",
    "bigint[]",
    "boolean",
    "date",
    "integer",
    "text",
    "timestamptz",
    "varchar",
]


@dataclass(frozen=True, slots=True)
class ColumnDefinition:
    name: str
    type: ColumnType
    nullable: bool = False
    generated: bool = False


@dataclass(frozen=True, slots=True)
class ForeignKeyDefinition:
    columns: tuple[str, ...]
    references_table: str
    references_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TableDefinition:
    database_table: str
    columns: tuple[ColumnDefinition, ...]
    unique_column_groups: tuple[tuple[str, ...], ...] = ()
    foreign_keys: tuple[ForeignKeyDefinition, ...] = ()


_AUDIT_COLUMNS = (
    ColumnDefinition("created_time", "timestamptz"),
    ColumnDefinition("created_by", "varchar"),
    ColumnDefinition("updated_time", "timestamptz"),
    ColumnDefinition("updated_by", "varchar"),
)


def _table(
    database_table: str,
    columns: tuple[ColumnDefinition, ...],
    *,
    unique_column_groups: tuple[tuple[str, ...], ...] = (),
    foreign_keys: tuple[ForeignKeyDefinition, ...] = (),
) -> TableDefinition:
    return TableDefinition(
        database_table=database_table,
        columns=(*columns, *_AUDIT_COLUMNS),
        unique_column_groups=unique_column_groups,
        foreign_keys=foreign_keys,
    )


TABLES = (
    _table(
        "core.project",
        (
            ColumnDefinition("project_id", "bigint", generated=True),
            ColumnDefinition("project_code", "varchar"),
            ColumnDefinition("project_name", "varchar"),
            ColumnDefinition("project_description", "text", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("project_code",),),
    ),
    _table(
        "core.tenant",
        (
            ColumnDefinition("tenant_id", "bigint", generated=True),
            ColumnDefinition("project_id", "bigint"),
            ColumnDefinition("tenant_code", "varchar"),
            ColumnDefinition("tenant_name", "varchar"),
            ColumnDefinition("tenant_description", "text", nullable=True),
            ColumnDefinition("tenant_catalog", "varchar"),
            ColumnDefinition("gds_admin_catalog", "varchar"),
            ColumnDefinition("gds_connection_id", "bigint", nullable=True),
            ColumnDefinition("tenant_visibility", "varchar"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("tenant_code",),),
        foreign_keys=(ForeignKeyDefinition(("project_id",), "core.project", ("project_id",)),),
    ),
    _table(
        "core.system",
        (
            ColumnDefinition("system_id", "bigint", generated=True),
            ColumnDefinition("system_code", "varchar"),
            ColumnDefinition("system_name", "varchar"),
            ColumnDefinition("system_description", "text", nullable=True),
            ColumnDefinition("system_type_id", "bigint"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("system_code",),),
        foreign_keys=(
            ForeignKeyDefinition(
                ("system_type_id",),
                "reference.system_type",
                ("system_type_id",),
            ),
        ),
    ),
    _table(
        "core.connection",
        (
            ColumnDefinition("connection_id", "bigint", generated=True),
            ColumnDefinition("tenant_id", "bigint"),
            ColumnDefinition("system_id", "bigint"),
            ColumnDefinition("connection_code", "varchar"),
            ColumnDefinition("connection_name", "varchar"),
            ColumnDefinition("connection_type_id", "bigint"),
            ColumnDefinition("has_foreign_catalog", "boolean"),
            ColumnDefinition("foreign_catalog", "varchar", nullable=True),
            ColumnDefinition("is_global_data_store", "boolean"),
            ColumnDefinition("test_initial_batch_id", "bigint", nullable=True),
            ColumnDefinition("test_incremental_batch_ids", "bigint[]", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(
            ("connection_id", "tenant_id"),
            ("system_id", "tenant_id", "connection_code"),
        ),
        foreign_keys=(
            ForeignKeyDefinition(("tenant_id",), "core.tenant", ("tenant_id",)),
            ForeignKeyDefinition(("system_id",), "core.system", ("system_id",)),
            ForeignKeyDefinition(
                ("connection_type_id",),
                "reference.connection_type",
                ("connection_type_id",),
            ),
        ),
    ),
    _table(
        "core.tenant_metadata_discovery_scope",
        (
            ColumnDefinition(
                "tenant_metadata_discovery_scope_id",
                "bigint",
                generated=True,
            ),
            ColumnDefinition("tenant_id", "bigint"),
            ColumnDefinition("connection_id", "bigint"),
            ColumnDefinition("zone_id", "bigint"),
            ColumnDefinition("object_schema", "varchar"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("tenant_id", "connection_id", "zone_id", "object_schema"),),
        foreign_keys=(
            ForeignKeyDefinition(("tenant_id",), "core.tenant", ("tenant_id",)),
            ForeignKeyDefinition(
                ("connection_id",),
                "core.connection",
                ("connection_id",),
            ),
            ForeignKeyDefinition(("zone_id",), "reference.zone", ("zone_id",)),
        ),
    ),
    _table(
        "reference.system_type",
        (
            ColumnDefinition("system_type_id", "bigint", generated=True),
            ColumnDefinition("system_type_code", "varchar"),
            ColumnDefinition("system_type_name", "varchar"),
            ColumnDefinition("system_type_description", "text", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("system_type_code",),),
    ),
    _table(
        "reference.connection_type",
        (
            ColumnDefinition("connection_type_id", "bigint", generated=True),
            ColumnDefinition("connection_type_code", "varchar"),
            ColumnDefinition("connection_type_name", "varchar"),
            ColumnDefinition("connection_type_description", "text", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("connection_type_code",),),
    ),
    _table(
        "reference.object_type",
        (
            ColumnDefinition("object_type_id", "bigint", generated=True),
            ColumnDefinition("object_type_code", "varchar"),
            ColumnDefinition("object_type_name", "varchar"),
            ColumnDefinition("object_type_description", "text", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("object_type_code",),),
    ),
    _table(
        "reference.zone",
        (
            ColumnDefinition("zone_id", "bigint", generated=True),
            ColumnDefinition("zone_code", "varchar"),
            ColumnDefinition("zone_name", "varchar"),
            ColumnDefinition("zone_description", "text", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("zone_code",), ("zone_name",)),
    ),
    _table(
        "reference.chunk_type",
        (
            ColumnDefinition("chunk_type_id", "bigint", generated=True),
            ColumnDefinition("chunk_type_name", "varchar"),
            ColumnDefinition("chunk_type_description", "text", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("chunk_type_name",),),
    ),
    _table(
        "reference.file_type",
        (
            ColumnDefinition("file_type_id", "bigint", generated=True),
            ColumnDefinition("file_type_name", "varchar"),
            ColumnDefinition("file_type_description", "text", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("file_type_name",),),
    ),
    _table(
        "reference.data_operation",
        (
            ColumnDefinition("data_operation_id", "bigint", generated=True),
            ColumnDefinition("data_operation_name", "varchar"),
            ColumnDefinition("data_operation_description", "text", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("data_operation_name",),),
    ),
    _table(
        "reference.process_type",
        (
            ColumnDefinition("process_type_id", "bigint", generated=True),
            ColumnDefinition("process_type_name", "varchar"),
            ColumnDefinition("process_type_description", "text", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("process_type_name",),),
    ),
    _table(
        "core.object",
        (
            ColumnDefinition("object_id", "bigint", generated=True),
            ColumnDefinition("connection_id", "bigint"),
            ColumnDefinition("object_schema", "varchar"),
            ColumnDefinition("object_name", "varchar"),
            ColumnDefinition("fc_object_schema", "varchar", nullable=True),
            ColumnDefinition("fc_object_name", "varchar", nullable=True),
            ColumnDefinition("object_transformation", "text", nullable=True),
            ColumnDefinition("object_description", "text", nullable=True),
            ColumnDefinition("batch_attribute_name", "varchar", nullable=True),
            ColumnDefinition("object_type_id", "bigint"),
            ColumnDefinition("zone_id", "bigint"),
            ColumnDefinition("is_locked", "boolean"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(
            ("object_id", "connection_id"),
            ("object_id", "zone_id"),
            ("connection_id", "object_schema", "object_name"),
        ),
        foreign_keys=(
            ForeignKeyDefinition(
                ("connection_id",),
                "core.connection",
                ("connection_id",),
            ),
            ForeignKeyDefinition(
                ("object_type_id",),
                "reference.object_type",
                ("object_type_id",),
            ),
            ForeignKeyDefinition(("zone_id",), "reference.zone", ("zone_id",)),
        ),
    ),
    _table(
        "core.attribute",
        (
            ColumnDefinition("attribute_id", "bigint", generated=True),
            ColumnDefinition("object_id", "bigint"),
            ColumnDefinition("attribute_name", "varchar"),
            ColumnDefinition("fc_attribute_name", "varchar", nullable=True),
            ColumnDefinition("attribute_ordinal_position", "integer"),
            ColumnDefinition("attribute_description", "text", nullable=True),
            ColumnDefinition("attribute_data_type", "varchar"),
            ColumnDefinition("attribute_nullability", "boolean"),
            ColumnDefinition("attribute_custom_code", "text", nullable=True),
            ColumnDefinition("business_glossary_id", "bigint", nullable=True),
            ColumnDefinition("is_surrogate_key", "boolean"),
            ColumnDefinition("is_natural_key", "boolean"),
            ColumnDefinition("is_meta_data", "boolean"),
            ColumnDefinition("is_masking_required", "boolean"),
            ColumnDefinition("is_mapped", "boolean"),
            ColumnDefinition("is_purge", "boolean"),
            ColumnDefinition("is_locked", "boolean"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(
            ("object_id", "attribute_ordinal_position"),
            ("attribute_id", "object_id"),
            ("object_id", "attribute_name"),
        ),
        foreign_keys=(ForeignKeyDefinition(("object_id",), "core.object", ("object_id",)),),
    ),
    _table(
        "core.ingestion_object_mapping",
        (
            ColumnDefinition("ingestion_object_mapping_id", "bigint", generated=True),
            ColumnDefinition("source_object_id", "bigint"),
            ColumnDefinition("target_object_id", "bigint"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(
            ("source_object_id", "target_object_id"),
            (
                "ingestion_object_mapping_id",
                "source_object_id",
                "target_object_id",
            ),
        ),
        foreign_keys=(
            ForeignKeyDefinition(("source_object_id",), "core.object", ("object_id",)),
            ForeignKeyDefinition(("target_object_id",), "core.object", ("object_id",)),
        ),
    ),
    _table(
        "core.ingestion_attribute_mapping",
        (
            ColumnDefinition(
                "ingestion_attribute_mapping_id",
                "bigint",
                generated=True,
            ),
            ColumnDefinition("ingestion_object_mapping_id", "bigint"),
            ColumnDefinition("source_object_id", "bigint"),
            ColumnDefinition("target_object_id", "bigint"),
            ColumnDefinition("source_attribute_id", "bigint"),
            ColumnDefinition("target_attribute_id", "bigint"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(
            (
                "ingestion_object_mapping_id",
                "source_attribute_id",
                "target_attribute_id",
            ),
        ),
        foreign_keys=(
            ForeignKeyDefinition(
                (
                    "ingestion_object_mapping_id",
                    "source_object_id",
                    "target_object_id",
                ),
                "core.ingestion_object_mapping",
                (
                    "ingestion_object_mapping_id",
                    "source_object_id",
                    "target_object_id",
                ),
            ),
            ForeignKeyDefinition(
                ("source_attribute_id", "source_object_id"),
                "core.attribute",
                ("attribute_id", "object_id"),
            ),
            ForeignKeyDefinition(
                ("target_attribute_id", "target_object_id"),
                "core.attribute",
                ("attribute_id", "object_id"),
            ),
        ),
    ),
    _table(
        "core.copy_group",
        (
            ColumnDefinition("copy_group_id", "bigint", generated=True),
            ColumnDefinition("tenant_id", "bigint"),
            ColumnDefinition("system_id", "bigint"),
            ColumnDefinition("copy_group_name", "varchar"),
            ColumnDefinition("copy_group_description", "text", nullable=True),
            ColumnDefinition("is_member_group_required", "boolean"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(
            ("copy_group_id", "tenant_id", "system_id"),
            ("tenant_id", "system_id", "copy_group_name"),
        ),
        foreign_keys=(
            ForeignKeyDefinition(("tenant_id",), "core.tenant", ("tenant_id",)),
            ForeignKeyDefinition(("system_id",), "core.system", ("system_id",)),
        ),
    ),
    _table(
        "core.member_group",
        (
            ColumnDefinition("member_group_id", "bigint", generated=True),
            ColumnDefinition("tenant_id", "bigint"),
            ColumnDefinition("system_id", "bigint"),
            ColumnDefinition("member_group_name", "varchar"),
            ColumnDefinition("member_group_description", "text", nullable=True),
            ColumnDefinition("member_group_initial_load_date", "date", nullable=True),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(
            ("member_group_id", "tenant_id", "system_id"),
            ("tenant_id", "system_id", "member_group_name"),
        ),
        foreign_keys=(
            ForeignKeyDefinition(("tenant_id",), "core.tenant", ("tenant_id",)),
            ForeignKeyDefinition(("system_id",), "core.system", ("system_id",)),
        ),
    ),
    _table(
        "core.copy_group_control",
        (
            ColumnDefinition("copy_group_control_id", "bigint", generated=True),
            ColumnDefinition("copy_group_id", "bigint"),
            ColumnDefinition("member_group_id", "bigint", nullable=True),
            ColumnDefinition("tenant_id", "bigint"),
            ColumnDefinition("system_id", "bigint"),
            ColumnDefinition(
                "copy_group_control_initial_load_date",
                "date",
                nullable=True,
            ),
            ColumnDefinition(
                "copy_group_control_last_run_time",
                "timestamptz",
                nullable=True,
            ),
            ColumnDefinition(
                "copy_group_control_last_run_value",
                "text",
                nullable=True,
            ),
        ),
        unique_column_groups=(("copy_group_id", "member_group_id"),),
        foreign_keys=(
            ForeignKeyDefinition(
                ("copy_group_id", "tenant_id", "system_id"),
                "core.copy_group",
                ("copy_group_id", "tenant_id", "system_id"),
            ),
            ForeignKeyDefinition(
                ("member_group_id", "tenant_id", "system_id"),
                "core.member_group",
                ("member_group_id", "tenant_id", "system_id"),
            ),
        ),
    ),
    _table(
        "core.copy",
        (
            ColumnDefinition("copy_id", "bigint", generated=True),
            ColumnDefinition("copy_group_id", "bigint"),
            ColumnDefinition("ingestion_object_mapping_id", "bigint"),
            ColumnDefinition("copy_source_record_limit", "bigint", nullable=True),
            ColumnDefinition(
                "copy_source_record_limit_attribute",
                "varchar",
                nullable=True,
            ),
            ColumnDefinition("chunk_type_id", "bigint", nullable=True),
            ColumnDefinition("copy_source_initial_sql_script", "text", nullable=True),
            ColumnDefinition(
                "copy_source_incremental_sql_script",
                "text",
                nullable=True,
            ),
            ColumnDefinition("copy_source_file_name", "text", nullable=True),
            ColumnDefinition("copy_source_file_pattern", "text", nullable=True),
            ColumnDefinition("copy_source_file_delimiter", "varchar", nullable=True),
            ColumnDefinition("source_file_type_id", "bigint", nullable=True),
            ColumnDefinition("copy_source_order", "integer"),
            ColumnDefinition("source_data_operation_id", "bigint"),
            ColumnDefinition("target_data_operation_id", "bigint"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(
            ("copy_group_id", "ingestion_object_mapping_id"),
            ("copy_group_id", "copy_source_order"),
        ),
        foreign_keys=(
            ForeignKeyDefinition(("copy_group_id",), "core.copy_group", ("copy_group_id",)),
            ForeignKeyDefinition(
                ("ingestion_object_mapping_id",),
                "core.ingestion_object_mapping",
                ("ingestion_object_mapping_id",),
            ),
            ForeignKeyDefinition(
                ("chunk_type_id",),
                "reference.chunk_type",
                ("chunk_type_id",),
            ),
            ForeignKeyDefinition(
                ("source_file_type_id",),
                "reference.file_type",
                ("file_type_id",),
            ),
            ForeignKeyDefinition(
                ("source_data_operation_id",),
                "reference.data_operation",
                ("data_operation_id",),
            ),
            ForeignKeyDefinition(
                ("target_data_operation_id",),
                "reference.data_operation",
                ("data_operation_id",),
            ),
        ),
    ),
    _table(
        "core.process_group",
        (
            ColumnDefinition("process_group_id", "bigint", generated=True),
            ColumnDefinition("tenant_id", "bigint"),
            ColumnDefinition("system_id", "bigint"),
            ColumnDefinition("zone_id", "bigint"),
            ColumnDefinition("process_group_name", "varchar"),
            ColumnDefinition("process_group_description", "text", nullable=True),
            ColumnDefinition("copy_group_id", "bigint"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(("tenant_id", "system_id", "zone_id", "process_group_name"),),
        foreign_keys=(
            ForeignKeyDefinition(("tenant_id",), "core.tenant", ("tenant_id",)),
            ForeignKeyDefinition(("system_id",), "core.system", ("system_id",)),
            ForeignKeyDefinition(("zone_id",), "reference.zone", ("zone_id",)),
            ForeignKeyDefinition(
                ("copy_group_id", "tenant_id", "system_id"),
                "core.copy_group",
                ("copy_group_id", "tenant_id", "system_id"),
            ),
        ),
    ),
    _table(
        "core.process",
        (
            ColumnDefinition("process_id", "bigint", generated=True),
            ColumnDefinition("connection_id", "bigint"),
            ColumnDefinition("object_id", "bigint"),
            ColumnDefinition("process_execution_order", "integer"),
            ColumnDefinition("process_location", "text"),
            ColumnDefinition("process_executable", "text"),
            ColumnDefinition("process_type_id", "bigint"),
            ColumnDefinition("process_group_id", "bigint"),
            ColumnDefinition("is_active", "boolean"),
        ),
        unique_column_groups=(
            (
                "process_group_id",
                "process_execution_order",
                "process_location",
                "process_executable",
            ),
        ),
        foreign_keys=(
            ForeignKeyDefinition(
                ("object_id", "connection_id"),
                "core.object",
                ("object_id", "connection_id"),
            ),
            ForeignKeyDefinition(
                ("process_type_id",),
                "reference.process_type",
                ("process_type_id",),
            ),
            ForeignKeyDefinition(
                ("process_group_id",),
                "core.process_group",
                ("process_group_id",),
            ),
        ),
    ),
)


DATASETS = (
    DatasetDefinition(
        "project",
        "Projects",
        "core.project",
        SnapshotSection.FOUNDATION,
        False,
        ("project_id",),
        ("project_code", "project_name"),
    ),
    DatasetDefinition(
        "tenant",
        "Tenants",
        "core.tenant",
        SnapshotSection.FOUNDATION,
        False,
        ("tenant_id",),
        ("tenant_code", "tenant_name"),
    ),
    DatasetDefinition(
        "system",
        "Systems",
        "core.system",
        SnapshotSection.FOUNDATION,
        False,
        ("system_id",),
        ("system_code", "system_name"),
    ),
    DatasetDefinition(
        "connection",
        "Connections",
        "core.connection",
        SnapshotSection.FOUNDATION,
        False,
        ("connection_id",),
        ("connection_code", "connection_name"),
    ),
    DatasetDefinition(
        "tenant_metadata_discovery_scope",
        "Tenant Metadata Discovery Scopes",
        "core.tenant_metadata_discovery_scope",
        SnapshotSection.FOUNDATION,
        False,
        ("tenant_metadata_discovery_scope_id",),
        ("object_schema",),
    ),
    DatasetDefinition(
        "system_type",
        "System Types",
        "reference.system_type",
        SnapshotSection.FOUNDATION,
        False,
        ("system_type_id",),
        ("system_type_code", "system_type_name"),
    ),
    DatasetDefinition(
        "connection_type",
        "Connection Types",
        "reference.connection_type",
        SnapshotSection.FOUNDATION,
        False,
        ("connection_type_id",),
        ("connection_type_code", "connection_type_name"),
    ),
    DatasetDefinition(
        "object_type",
        "Object Types",
        "reference.object_type",
        SnapshotSection.FOUNDATION,
        False,
        ("object_type_id",),
        ("object_type_code", "object_type_name"),
    ),
    DatasetDefinition(
        "zone",
        "Zones",
        "reference.zone",
        SnapshotSection.FOUNDATION,
        False,
        ("zone_id",),
        ("zone_code", "zone_name"),
    ),
    DatasetDefinition(
        "chunk_type",
        "Chunk Types",
        "reference.chunk_type",
        SnapshotSection.FOUNDATION,
        False,
        ("chunk_type_id",),
        ("chunk_type_name",),
    ),
    DatasetDefinition(
        "file_type",
        "File Types",
        "reference.file_type",
        SnapshotSection.FOUNDATION,
        False,
        ("file_type_id",),
        ("file_type_name",),
    ),
    DatasetDefinition(
        "data_operation",
        "Data Operations",
        "reference.data_operation",
        SnapshotSection.FOUNDATION,
        False,
        ("data_operation_id",),
        ("data_operation_name",),
    ),
    DatasetDefinition(
        "process_type",
        "Process Types",
        "reference.process_type",
        SnapshotSection.FOUNDATION,
        False,
        ("process_type_id",),
        ("process_type_name",),
    ),
    DatasetDefinition(
        "source_object",
        "Source Objects",
        "core.object",
        SnapshotSection.METADATA,
        True,
        ("object_id",),
        ("object_schema", "object_name"),
    ),
    DatasetDefinition(
        "source_attribute",
        "Source Attributes",
        "core.attribute",
        SnapshotSection.METADATA,
        True,
        ("attribute_id",),
        ("attribute_name",),
    ),
    DatasetDefinition(
        "bronze_object",
        "Bronze Objects",
        "core.object",
        SnapshotSection.METADATA,
        True,
        ("object_id",),
        ("object_schema", "object_name"),
    ),
    DatasetDefinition(
        "bronze_attribute",
        "Bronze Attributes",
        "core.attribute",
        SnapshotSection.METADATA,
        True,
        ("attribute_id",),
        ("attribute_name",),
    ),
    DatasetDefinition(
        "silver_object",
        "Silver Objects",
        "core.object",
        SnapshotSection.METADATA,
        True,
        ("object_id",),
        ("object_schema", "object_name"),
    ),
    DatasetDefinition(
        "silver_attribute",
        "Silver Attributes",
        "core.attribute",
        SnapshotSection.METADATA,
        True,
        ("attribute_id",),
        ("attribute_name",),
    ),
    DatasetDefinition(
        "gold_object",
        "Gold Objects",
        "core.object",
        SnapshotSection.METADATA,
        True,
        ("object_id",),
        ("object_schema", "object_name"),
    ),
    DatasetDefinition(
        "gold_attribute",
        "Gold Attributes",
        "core.attribute",
        SnapshotSection.METADATA,
        True,
        ("attribute_id",),
        ("attribute_name",),
    ),
    DatasetDefinition(
        "ingestion_object_mapping",
        "Ingestion Object Mappings",
        "core.ingestion_object_mapping",
        SnapshotSection.METADATA,
        True,
        ("ingestion_object_mapping_id",),
        ("source_object_id", "target_object_id"),
    ),
    DatasetDefinition(
        "ingestion_attribute_mapping",
        "Ingestion Attribute Mappings",
        "core.ingestion_attribute_mapping",
        SnapshotSection.METADATA,
        True,
        ("ingestion_attribute_mapping_id",),
        ("source_attribute_id", "target_attribute_id"),
    ),
    DatasetDefinition(
        "copy_group",
        "Copy Groups",
        "core.copy_group",
        SnapshotSection.METADATA,
        True,
        ("copy_group_id",),
        ("copy_group_name",),
    ),
    DatasetDefinition(
        "member_group",
        "Member Groups",
        "core.member_group",
        SnapshotSection.METADATA,
        True,
        ("member_group_id",),
        ("member_group_name",),
    ),
    DatasetDefinition(
        "copy_group_control",
        "Copy Group Controls",
        "core.copy_group_control",
        SnapshotSection.METADATA,
        True,
        ("copy_group_control_id",),
        ("copy_group_id", "member_group_id"),
    ),
    DatasetDefinition(
        "copy",
        "Copies",
        "core.copy",
        SnapshotSection.METADATA,
        True,
        ("copy_id",),
        ("copy_group_id", "ingestion_object_mapping_id"),
    ),
    DatasetDefinition(
        "process_group",
        "Process Groups",
        "core.process_group",
        SnapshotSection.METADATA,
        True,
        ("process_group_id",),
        ("process_group_name",),
    ),
    DatasetDefinition(
        "process",
        "Processes",
        "core.process",
        SnapshotSection.METADATA,
        True,
        ("process_id",),
        ("process_location", "process_executable"),
    ),
)

TABLES_BY_NAME = {table.database_table: table for table in TABLES}
DATASETS_BY_NAME = {dataset.name: dataset for dataset in DATASETS}
