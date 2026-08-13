"""ID-free metadata records shared by snapshots and Metadata Change Sets."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Code100 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100, pattern=r"\S"),
]
Name200 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=200, pattern=r"\S"),
]
Name400 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=400, pattern=r"\S"),
]
OptionalText20 = Annotated[str, StringConstraints(max_length=20)] | None
OptionalText100 = Annotated[str, StringConstraints(max_length=100)] | None
OptionalText255 = Annotated[str, StringConstraints(max_length=255)] | None
OptionalText400 = Annotated[str, StringConstraints(max_length=400)] | None
BigIntText = Annotated[str, StringConstraints(pattern=r"^-?[0-9]+$")]


class MetadataRecord(BaseModel):
    """Exact metadata row contract. Database IDs are never fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProjectRecord(MetadataRecord):
    project_code: Code100
    project_name: Name200
    project_description: str | None
    is_active: bool


class TenantRecord(MetadataRecord):
    tenant_code: Code100
    project_code: Code100
    tenant_name: Name200
    tenant_description: str | None
    tenant_catalog: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    gds_admin_catalog: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    gds_connection_tenant_code: Code100 | None
    gds_connection_system_code: Code100 | None
    gds_connection_code: Code100 | None
    tenant_visibility: Literal["global", "private"]
    is_active: bool

    @model_validator(mode="after")
    def validate_gds_connection_key(self) -> TenantRecord:
        connection_key = (
            self.gds_connection_tenant_code,
            self.gds_connection_system_code,
            self.gds_connection_code,
        )
        if any(value is None for value in connection_key) and any(
            value is not None for value in connection_key
        ):
            raise ValueError("GDS Connection key must be entirely present or absent")
        return self


class SystemRecord(MetadataRecord):
    system_code: Code100
    system_name: Name200
    system_description: str | None
    system_type_code: Code100
    is_active: bool


class ConnectionRecord(MetadataRecord):
    tenant_code: Code100
    system_code: Code100
    connection_code: Code100
    connection_name: Name200
    connection_type_code: Code100
    has_foreign_catalog: bool
    foreign_catalog: OptionalText255
    is_global_data_store: bool
    is_active: bool


class TenantMetadataDiscoveryScopeRecord(MetadataRecord):
    scope_tenant_code: Code100
    connection_tenant_code: Code100
    connection_system_code: Code100
    connection_code: Code100
    zone_code: Annotated[str, StringConstraints(min_length=1, max_length=30)]
    object_schema: Name400
    is_active: bool


class SystemTypeRecord(MetadataRecord):
    system_type_code: Code100
    system_type_name: Name200
    system_type_description: str | None
    is_active: bool


class ConnectionTypeRecord(MetadataRecord):
    connection_type_code: Code100
    connection_type_name: Name200
    connection_type_description: str | None
    is_active: bool


class ObjectTypeRecord(MetadataRecord):
    object_type_code: Code100
    object_type_name: Name200
    object_type_description: str | None
    is_active: bool


class ZoneRecord(MetadataRecord):
    zone_code: Annotated[
        str,
        StringConstraints(min_length=1, max_length=30, pattern=r"\S"),
    ]
    zone_name: Name200
    zone_description: str | None
    is_active: bool


class ChunkTypeRecord(MetadataRecord):
    chunk_type_name: Name200
    chunk_type_description: str | None
    is_active: bool


class FileTypeRecord(MetadataRecord):
    file_type_name: Name200
    file_type_description: str | None
    is_active: bool


class DataOperationRecord(MetadataRecord):
    data_operation_name: Name200
    data_operation_description: str | None
    is_active: bool


class ProcessTypeRecord(MetadataRecord):
    process_type_name: Name200
    process_type_description: str | None
    is_active: bool


class ObjectRecord(MetadataRecord):
    tenant_code: Code100
    system_code: Code100
    connection_code: Code100
    object_schema: Name400
    object_name: Name400
    fc_object_schema: OptionalText400
    fc_object_name: OptionalText400
    object_transformation: str | None
    object_description: str | None
    batch_attribute_name: OptionalText400
    object_type_code: Code100
    zone_code: Literal["source", "bronze", "silver", "gold"]
    is_locked: bool
    is_active: bool


class AttributeRecord(MetadataRecord):
    tenant_code: Code100
    system_code: Code100
    connection_code: Code100
    object_schema: Name400
    object_name: Name400
    attribute_name: Name400
    fc_attribute_name: OptionalText400
    attribute_ordinal_position: Annotated[int, Field(gt=0, le=2_147_483_647)]
    attribute_description: str | None
    attribute_data_type: Annotated[
        str,
        StringConstraints(min_length=1, max_length=100),
    ]
    attribute_nullability: bool
    attribute_custom_code: str | None
    is_surrogate_key: bool
    is_natural_key: bool
    is_meta_data: bool
    is_masking_required: bool
    is_mapped: bool
    is_purge: bool
    is_locked: bool
    is_active: bool


class IngestionObjectMappingRecord(MetadataRecord):
    source_tenant_code: Code100
    source_system_code: Code100
    source_connection_code: Code100
    source_object_schema: Name400
    source_object_name: Name400
    target_tenant_code: Code100
    target_system_code: Code100
    target_connection_code: Code100
    target_object_schema: Name400
    target_object_name: Name400
    is_active: bool


class IngestionAttributeMappingRecord(MetadataRecord):
    source_tenant_code: Code100
    source_system_code: Code100
    source_connection_code: Code100
    source_object_schema: Name400
    source_object_name: Name400
    source_attribute_name: Name400
    target_tenant_code: Code100
    target_system_code: Code100
    target_connection_code: Code100
    target_object_schema: Name400
    target_object_name: Name400
    target_attribute_name: Name400
    is_active: bool


class CopyGroupRecord(MetadataRecord):
    tenant_code: Code100
    system_code: Code100
    copy_group_name: Name200
    copy_group_description: str | None
    is_member_group_required: bool
    is_active: bool


class MemberGroupRecord(MetadataRecord):
    tenant_code: Code100
    system_code: Code100
    member_group_name: Name200
    member_group_description: str | None
    member_group_initial_load_date: date | None
    is_active: bool


class CopyGroupControlRecord(MetadataRecord):
    tenant_code: Code100
    system_code: Code100
    copy_group_name: Name200
    member_group_name: Name200 | None
    copy_group_control_initial_load_date: date | None
    copy_group_control_last_run_time: datetime | None
    copy_group_control_last_run_value: str | None


class CopyRecord(MetadataRecord):
    tenant_code: Code100
    system_code: Code100
    copy_group_name: Name200
    source_tenant_code: Code100
    source_system_code: Code100
    source_connection_code: Code100
    source_object_schema: Name400
    source_object_name: Name400
    target_tenant_code: Code100
    target_system_code: Code100
    target_connection_code: Code100
    target_object_schema: Name400
    target_object_name: Name400
    copy_source_record_limit: BigIntText | None
    copy_source_record_limit_attribute: OptionalText400
    chunk_type_name: Name200 | None
    copy_source_initial_sql_script: str | None
    copy_source_incremental_sql_script: str | None
    copy_source_file_name: str | None
    copy_source_file_pattern: str | None
    copy_source_file_delimiter: OptionalText20
    source_file_type_name: Name200 | None
    copy_source_order: Annotated[int, Field(gt=0, le=2_147_483_647)]
    source_data_operation_name: Name200
    target_data_operation_name: Name200
    is_active: bool


class ProcessGroupRecord(MetadataRecord):
    tenant_code: Code100
    system_code: Code100
    zone_code: Annotated[str, StringConstraints(min_length=1, max_length=30)]
    process_group_name: Name200
    process_group_description: str | None
    copy_group_name: Name200
    is_active: bool


class ProcessRecord(MetadataRecord):
    tenant_code: Code100
    system_code: Code100
    zone_code: Annotated[str, StringConstraints(min_length=1, max_length=30)]
    process_group_name: Name200
    process_execution_order: Annotated[int, Field(gt=0, le=2_147_483_647)]
    process_location: Annotated[
        str,
        StringConstraints(min_length=1, pattern=r"\S"),
    ]
    process_executable: Annotated[
        str,
        StringConstraints(min_length=1, pattern=r"\S"),
    ]
    object_tenant_code: Code100
    object_system_code: Code100
    object_connection_code: Code100
    object_schema: Name400
    object_name: Name400
    process_type_name: Name200
    is_active: bool
