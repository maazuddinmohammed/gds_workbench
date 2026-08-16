"""ID-free Metadata Snapshot dataset registry."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath

from gds_etl_workbench.domain.metadata_records import (
    AttributeRecord,
    ChunkTypeRecord,
    ConnectionRecord,
    ConnectionTypeRecord,
    CopyGroupControlRecord,
    CopyGroupRecord,
    CopyRecord,
    DataOperationRecord,
    FileTypeRecord,
    IngestionAttributeMappingRecord,
    IngestionObjectMappingRecord,
    MemberGroupRecord,
    MetadataRecord,
    ObjectRecord,
    ObjectTypeRecord,
    ProcessGroupRecord,
    ProcessRecord,
    ProcessTypeRecord,
    ProjectRecord,
    SystemRecord,
    SystemTypeRecord,
    TenantMetadataDiscoveryScopeRecord,
    TenantRecord,
    ZoneRecord,
)

NATURAL_KEY_STRING_FIELD_SUFFIXES = ("_code", "_name", "_schema")


def natural_key_normalization_document() -> dict[str, object]:
    """Return the portable normalization contract published with every dataset."""
    return {
        "version": "1.0",
        "string_field_suffixes": list(NATURAL_KEY_STRING_FIELD_SUFFIXES),
        "trim_code_points": ["U+0020"],
        "case": "unicode-lowercase",
        "unicode_normalization": "none",
        "other_values": "identity",
    }


def normalize_natural_key_value(column: str, value: object) -> object:
    """Apply the Snapshot's published natural-key normalization contract."""
    if isinstance(value, str) and column.endswith(NATURAL_KEY_STRING_FIELD_SUFFIXES):
        return value.strip(" ").lower()
    return value


class SnapshotSection(StrEnum):
    FOUNDATIONAL = "foundational"
    REFERENCE = "reference"
    OPERATIONAL = "operational"


@dataclass(frozen=True, slots=True)
class ReferenceDefinition:
    columns: tuple[str, ...]
    target_record_type: str
    target_columns: tuple[str, ...]
    nullable: bool = False


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    name: str
    label: str
    database_table: str
    record_type: str
    section: SnapshotSection
    change_set_eligible: bool
    row_model: type[MetadataRecord]
    canonical_key: tuple[str, ...]
    unique_constraints: tuple[tuple[str, ...], ...]
    references: tuple[ReferenceDefinition, ...] = ()
    lookup_fields: tuple[str, ...] = ()
    fixed_values: tuple[tuple[str, object], ...] = ()

    @property
    def data_directory(self) -> PurePosixPath:
        return PurePosixPath("data", self.section.value, self.name)

    @property
    def rows_path(self) -> str:
        return (self.data_directory / "rows.jsonl").as_posix()

    @property
    def lookup_path(self) -> str | None:
        if not self.lookup_fields:
            return None
        return (self.data_directory / "lookup.jsonl").as_posix()

    @property
    def search_path(self) -> str:
        return self.lookup_path or self.rows_path

    @property
    def schema_path(self) -> str:
        return PurePosixPath("schemas", f"{self.name}.schema.json").as_posix()

    @property
    def search_fields(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*self.canonical_key, *self.lookup_fields)))


PROJECT_KEY = ("project_code",)
TENANT_KEY = ("tenant_code",)
SYSTEM_KEY = ("system_code",)
CONNECTION_KEY = ("tenant_code", "system_code", "connection_code")
OBJECT_KEY = (*CONNECTION_KEY, "object_schema", "object_name")
ATTRIBUTE_KEY = (*OBJECT_KEY, "attribute_name")
COPY_GROUP_KEY = ("tenant_code", "system_code", "copy_group_name")
MEMBER_GROUP_KEY = ("tenant_code", "system_code", "member_group_name")
PROCESS_GROUP_KEY = (
    "tenant_code",
    "system_code",
    "zone_code",
    "process_group_name",
)


def _prefixed(prefix: str, columns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"{prefix}_{column}" for column in columns)


SOURCE_OBJECT_KEY = _prefixed("source", OBJECT_KEY)
TARGET_OBJECT_KEY = _prefixed("target", OBJECT_KEY)
SOURCE_ATTRIBUTE_KEY = _prefixed("source", ATTRIBUTE_KEY)
TARGET_ATTRIBUTE_KEY = _prefixed("target", ATTRIBUTE_KEY)
OBJECT_MAPPING_KEY = (*SOURCE_OBJECT_KEY, *TARGET_OBJECT_KEY)
ATTRIBUTE_MAPPING_KEY = (*SOURCE_ATTRIBUTE_KEY, *TARGET_ATTRIBUTE_KEY)
COPY_KEY = (*COPY_GROUP_KEY, *SOURCE_OBJECT_KEY, *TARGET_OBJECT_KEY)
COPY_GROUP_CONTROL_KEY = (*COPY_GROUP_KEY, "member_group_name")
PROCESS_KEY = (
    *PROCESS_GROUP_KEY,
    "process_execution_order",
    "process_location",
    "process_executable",
)


def _reference(
    columns: tuple[str, ...],
    target_record_type: str,
    target_columns: tuple[str, ...],
    *,
    nullable: bool = False,
) -> ReferenceDefinition:
    return ReferenceDefinition(columns, target_record_type, target_columns, nullable)


def _dataset(
    name: str,
    label: str,
    database_table: str,
    record_type: str,
    section: SnapshotSection,
    change_set_eligible: bool,
    row_model: type[MetadataRecord],
    canonical_key: tuple[str, ...],
    *,
    unique_constraints: tuple[tuple[str, ...], ...] = (),
    references: tuple[ReferenceDefinition, ...] = (),
    lookup_fields: tuple[str, ...] = (),
    fixed_values: tuple[tuple[str, object], ...] = (),
) -> DatasetDefinition:
    return DatasetDefinition(
        name=name,
        label=label,
        database_table=database_table,
        record_type=record_type,
        section=section,
        change_set_eligible=change_set_eligible,
        row_model=row_model,
        canonical_key=canonical_key,
        unique_constraints=(canonical_key, *unique_constraints),
        references=references,
        lookup_fields=lookup_fields,
        fixed_values=fixed_values,
    )


DATASETS = (
    _dataset(
        "project",
        "Projects",
        "core.project",
        "project",
        SnapshotSection.FOUNDATIONAL,
        False,
        ProjectRecord,
        PROJECT_KEY,
    ),
    _dataset(
        "tenant",
        "Tenants",
        "core.tenant",
        "tenant",
        SnapshotSection.FOUNDATIONAL,
        False,
        TenantRecord,
        TENANT_KEY,
        references=(
            _reference(("project_code",), "project", PROJECT_KEY),
            _reference(
                (
                    "gds_connection_tenant_code",
                    "gds_connection_system_code",
                    "gds_connection_code",
                ),
                "connection",
                CONNECTION_KEY,
                nullable=True,
            ),
        ),
    ),
    _dataset(
        "system",
        "Systems",
        "core.system",
        "system",
        SnapshotSection.FOUNDATIONAL,
        False,
        SystemRecord,
        SYSTEM_KEY,
        references=(_reference(("system_type_code",), "system_type", ("system_type_code",)),),
    ),
    _dataset(
        "connection",
        "Connections",
        "core.connection",
        "connection",
        SnapshotSection.FOUNDATIONAL,
        False,
        ConnectionRecord,
        CONNECTION_KEY,
        references=(
            _reference(("tenant_code",), "tenant", TENANT_KEY),
            _reference(("system_code",), "system", SYSTEM_KEY),
            _reference(("connection_type_code",), "connection_type", ("connection_type_code",)),
        ),
    ),
    _dataset(
        "tenant_metadata_discovery_scope",
        "Tenant Metadata Discovery Scopes",
        "core.tenant_metadata_discovery_scope",
        "tenant_metadata_discovery_scope",
        SnapshotSection.FOUNDATIONAL,
        False,
        TenantMetadataDiscoveryScopeRecord,
        (
            "scope_tenant_code",
            "connection_tenant_code",
            "connection_system_code",
            "connection_code",
            "zone_code",
            "object_schema",
        ),
        references=(
            _reference(("scope_tenant_code",), "tenant", TENANT_KEY),
            _reference(
                ("connection_tenant_code", "connection_system_code", "connection_code"),
                "connection",
                CONNECTION_KEY,
            ),
            _reference(("zone_code",), "zone", ("zone_code",)),
        ),
    ),
    _dataset(
        "system_type",
        "System Types",
        "reference.system_type",
        "system_type",
        SnapshotSection.REFERENCE,
        False,
        SystemTypeRecord,
        ("system_type_code",),
    ),
    _dataset(
        "connection_type",
        "Connection Types",
        "reference.connection_type",
        "connection_type",
        SnapshotSection.REFERENCE,
        False,
        ConnectionTypeRecord,
        ("connection_type_code",),
    ),
    _dataset(
        "object_type",
        "Object Types",
        "reference.object_type",
        "object_type",
        SnapshotSection.REFERENCE,
        False,
        ObjectTypeRecord,
        ("object_type_code",),
    ),
    _dataset(
        "zone",
        "Zones",
        "reference.zone",
        "zone",
        SnapshotSection.REFERENCE,
        False,
        ZoneRecord,
        ("zone_code",),
        unique_constraints=(("zone_name",),),
    ),
    _dataset(
        "chunk_type",
        "Chunk Types",
        "reference.chunk_type",
        "chunk_type",
        SnapshotSection.REFERENCE,
        False,
        ChunkTypeRecord,
        ("chunk_type_name",),
    ),
    _dataset(
        "file_type",
        "File Types",
        "reference.file_type",
        "file_type",
        SnapshotSection.REFERENCE,
        False,
        FileTypeRecord,
        ("file_type_name",),
    ),
    _dataset(
        "data_operation",
        "Data Operations",
        "reference.data_operation",
        "data_operation",
        SnapshotSection.REFERENCE,
        False,
        DataOperationRecord,
        ("data_operation_name",),
    ),
    _dataset(
        "process_type",
        "Process Types",
        "reference.process_type",
        "process_type",
        SnapshotSection.REFERENCE,
        False,
        ProcessTypeRecord,
        ("process_type_name",),
    ),
    *(
        item
        for zone_code, label in (
            ("source", "Source"),
            ("bronze", "Bronze"),
            ("silver", "Silver"),
            ("gold", "Gold"),
        )
        for item in (
            _dataset(
                f"{zone_code}_object",
                f"{label} Objects",
                "core.object",
                "object",
                SnapshotSection.OPERATIONAL,
                True,
                ObjectRecord,
                OBJECT_KEY,
                references=(
                    _reference(CONNECTION_KEY, "connection", CONNECTION_KEY),
                    _reference(("object_type_code",), "object_type", ("object_type_code",)),
                    _reference(("zone_code",), "zone", ("zone_code",)),
                ),
                lookup_fields=("object_type_code", "zone_code", "is_locked", "is_active"),
                fixed_values=(("zone_code", zone_code),),
            ),
            _dataset(
                f"{zone_code}_attribute",
                f"{label} Attributes",
                "core.attribute",
                "attribute",
                SnapshotSection.OPERATIONAL,
                True,
                AttributeRecord,
                ATTRIBUTE_KEY,
                unique_constraints=((*OBJECT_KEY, "attribute_ordinal_position"),),
                references=(_reference(OBJECT_KEY, "object", OBJECT_KEY),),
                lookup_fields=(
                    "attribute_data_type",
                    "is_natural_key",
                    "is_active",
                ),
            ),
        )
    ),
    _dataset(
        "ingestion_object_mapping",
        "Ingestion Object Mappings",
        "core.ingestion_object_mapping",
        "ingestion_object_mapping",
        SnapshotSection.OPERATIONAL,
        True,
        IngestionObjectMappingRecord,
        OBJECT_MAPPING_KEY,
        references=(
            _reference(SOURCE_OBJECT_KEY, "object", OBJECT_KEY),
            _reference(TARGET_OBJECT_KEY, "object", OBJECT_KEY),
        ),
    ),
    _dataset(
        "ingestion_attribute_mapping",
        "Ingestion Attribute Mappings",
        "core.ingestion_attribute_mapping",
        "ingestion_attribute_mapping",
        SnapshotSection.OPERATIONAL,
        True,
        IngestionAttributeMappingRecord,
        ATTRIBUTE_MAPPING_KEY,
        references=(
            _reference(OBJECT_MAPPING_KEY, "ingestion_object_mapping", OBJECT_MAPPING_KEY),
            _reference(SOURCE_ATTRIBUTE_KEY, "attribute", ATTRIBUTE_KEY),
            _reference(TARGET_ATTRIBUTE_KEY, "attribute", ATTRIBUTE_KEY),
        ),
    ),
    _dataset(
        "copy_group",
        "Copy Groups",
        "core.copy_group",
        "copy_group",
        SnapshotSection.OPERATIONAL,
        True,
        CopyGroupRecord,
        COPY_GROUP_KEY,
        references=(
            _reference(("tenant_code",), "tenant", TENANT_KEY),
            _reference(("system_code",), "system", SYSTEM_KEY),
        ),
    ),
    _dataset(
        "member_group",
        "Member Groups",
        "core.member_group",
        "member_group",
        SnapshotSection.OPERATIONAL,
        True,
        MemberGroupRecord,
        MEMBER_GROUP_KEY,
        references=(
            _reference(("tenant_code",), "tenant", TENANT_KEY),
            _reference(("system_code",), "system", SYSTEM_KEY),
        ),
    ),
    _dataset(
        "copy_group_control",
        "Copy Group Controls",
        "core.copy_group_control",
        "copy_group_control",
        SnapshotSection.OPERATIONAL,
        True,
        CopyGroupControlRecord,
        COPY_GROUP_CONTROL_KEY,
        references=(
            _reference(COPY_GROUP_KEY, "copy_group", COPY_GROUP_KEY),
            _reference(MEMBER_GROUP_KEY, "member_group", MEMBER_GROUP_KEY, nullable=True),
        ),
        lookup_fields=("copy_group_control_last_run_time",),
    ),
    _dataset(
        "copy",
        "Copies",
        "core.copy",
        "copy",
        SnapshotSection.OPERATIONAL,
        True,
        CopyRecord,
        COPY_KEY,
        unique_constraints=((*COPY_GROUP_KEY, "copy_source_order"),),
        references=(
            _reference(COPY_GROUP_KEY, "copy_group", COPY_GROUP_KEY),
            _reference(OBJECT_MAPPING_KEY, "ingestion_object_mapping", OBJECT_MAPPING_KEY),
            _reference(("chunk_type_name",), "chunk_type", ("chunk_type_name",), nullable=True),
            _reference(("source_file_type_name",), "file_type", ("file_type_name",), nullable=True),
            _reference(("source_data_operation_name",), "data_operation", ("data_operation_name",)),
            _reference(("target_data_operation_name",), "data_operation", ("data_operation_name",)),
        ),
        lookup_fields=("copy_source_order", "is_active"),
    ),
    _dataset(
        "process_group",
        "Process Groups",
        "core.process_group",
        "process_group",
        SnapshotSection.OPERATIONAL,
        True,
        ProcessGroupRecord,
        PROCESS_GROUP_KEY,
        references=(
            _reference(("tenant_code",), "tenant", TENANT_KEY),
            _reference(("system_code",), "system", SYSTEM_KEY),
            _reference(("zone_code",), "zone", ("zone_code",)),
            _reference(COPY_GROUP_KEY, "copy_group", COPY_GROUP_KEY),
        ),
    ),
    _dataset(
        "process",
        "Processes",
        "core.process",
        "process",
        SnapshotSection.OPERATIONAL,
        True,
        ProcessRecord,
        PROCESS_KEY,
        references=(
            _reference(PROCESS_GROUP_KEY, "process_group", PROCESS_GROUP_KEY),
            _reference(
                (
                    "object_tenant_code",
                    "object_system_code",
                    "object_connection_code",
                    "object_schema",
                    "object_name",
                ),
                "object",
                OBJECT_KEY,
            ),
            _reference(("process_type_name",), "process_type", ("process_type_name",)),
        ),
    ),
)

DATASETS_BY_NAME = {dataset.name: dataset for dataset in DATASETS}
PHYSICAL_TABLE_COUNT = len({dataset.database_table for dataset in DATASETS})
