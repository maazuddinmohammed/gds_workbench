# pyright: reportPrivateUsage=false

from gds_etl_workbench.tools.catalog.get_objects import _OBJECTS_SQL
from gds_etl_workbench.tools.catalog.list_objects import _LIST_OBJECTS_SQL

from gds_workbench_api.features.mapping.preparation_repository import (
    _MAPPING_SOURCE_CONTEXT_SQL,
    _MAPPING_TARGET_CONTEXT_SQL,
)
from gds_workbench_api.features.metadata.repository import (
    _ATTRIBUTE_ROWS_SQL,
    _COPY_ROWS_SQL,
    _INGESTION_ATTRIBUTE_MAPPING_ROWS_SQL,
    _INGESTION_OBJECT_MAPPING_ROWS_SQL,
    _OBJECT_ROWS_SQL,
    _PROCESS_ROWS_SQL,
)
from gds_workbench_api.features.workflows.authoring.context import (
    _SELECTED_ATTRIBUTES_SQL,
    _SELECTED_OBJECTS_SQL,
)


def _compact(sql: str) -> str:
    return " ".join(sql.split())


def test_metadata_object_records_separate_placement_and_source_tenants() -> None:
    objects = _compact(_OBJECT_ROWS_SQL)
    attributes = _compact(_ATTRIBUTE_ROWS_SQL)

    assert "placement_tenant.tenant_id = connection.tenant_id" in objects
    assert "source_tenant.tenant_id = object.source_tenant_id" in objects
    assert "source_tenant.tenant_code AS source_tenant_code" in objects
    assert "placement_tenant.tenant_id = connection.tenant_id" in attributes
    assert "visible_objects.object_tenant_id" not in objects
    assert "visible_objects.object_tenant_id" not in attributes


def test_metadata_nested_physical_keys_use_each_objects_connection_tenant() -> None:
    for sql in (
        _INGESTION_OBJECT_MAPPING_ROWS_SQL,
        _INGESTION_ATTRIBUTE_MAPPING_ROWS_SQL,
        _COPY_ROWS_SQL,
    ):
        compact = _compact(sql)
        assert "source_tenant.tenant_id = source_connection.tenant_id" in compact
        assert "target_tenant.tenant_id = target_connection.tenant_id" in compact
        assert ".object_tenant_id" not in compact

    process = _compact(_PROCESS_ROWS_SQL)
    assert "object_tenant.tenant_id = object_connection.tenant_id" in process
    assert "visible_objects.object_tenant_id" not in process


def test_authoring_context_separates_physical_and_source_tenants() -> None:
    objects = _compact(_SELECTED_OBJECTS_SQL)
    attributes = _compact(_SELECTED_ATTRIBUTES_SQL)

    assert "placement_tenant.tenant_id = connection.tenant_id" in objects
    assert "source_tenant.tenant_id = object_record.source_tenant_id" in objects
    assert "source_tenant.tenant_code AS source_tenant_code" in objects
    assert "placement_tenant.tenant_id = connection.tenant_id" in attributes
    assert "eligibility.object_tenant_id" not in objects
    assert "eligibility.object_tenant_id" not in attributes


def test_mapping_authoring_context_uses_connection_tenant_for_physical_keys() -> None:
    target = _compact(_MAPPING_TARGET_CONTEXT_SQL)
    source = _compact(_MAPPING_SOURCE_CONTEXT_SQL)

    assert "target_tenant.tenant_id = target_connection.tenant_id" in target
    assert "target_object.source_tenant_id" not in target
    assert "source_placement_tenant.tenant_id = source_connection.tenant_id" in source
    assert "source_object.source_tenant_id" not in source


def test_inspect_metadata_exposes_both_tenant_roles_explicitly() -> None:
    for sql in (_LIST_OBJECTS_SQL, _OBJECTS_SQL):
        compact = _compact(sql)
        assert "connection_tenant.tenant_id = connection.tenant_id" in compact
        assert "source_tenant.tenant_id = object.source_tenant_id" in compact
        assert "connection_tenant.tenant_code AS connection_tenant_code" in compact
        assert "source_tenant.tenant_code AS source_tenant_code" in compact
