from gds_etl_workbench.tools.modeling.model_input_scope import (
    _MODEL_INPUT_SCOPE_SQL as MODEL_INPUT_SCOPE_TOOL_SQL,
)
from gds_etl_workbench.application.modeling.profiling_analysis import (
    ANALYSIS_SQL,
    PROFILING_SQL,
)
from gds_etl_workbench.application.model_snapshot import (
    _MAPPING_ATTRIBUTE_SQL,
    _MAPPING_OBJECT_SQL,
    _MODEL_ATTRIBUTE_BINDING_SQL,
    _MODEL_INPUT_SCOPE_SQL,
    _MODEL_OBJECT_BINDING_SQL,
)


def compact(sql: str) -> str:
    return " ".join(sql.split())


def test_profiling_and_analysis_use_physical_connection_placement_keys() -> None:
    profiling = compact(PROFILING_SQL)
    analysis = compact(ANALYSIS_SQL)

    assert "eligible_attribute.is_model_input_eligible" in profiling
    assert "tenant.tenant_id = connection.tenant_id" in profiling
    assert "eligible_attribute.object_tenant_id" not in profiling
    assert "eligible_from_attribute.is_model_input_eligible" in analysis
    assert "eligible_to_attribute.is_model_input_eligible" in analysis
    assert "from_tenant.tenant_id = from_connection.tenant_id" in analysis
    assert "to_tenant.tenant_id = to_connection.tenant_id" in analysis
    assert "object_tenant_id" not in analysis


def test_model_input_scope_snapshot_uses_connection_placement_natural_key() -> None:
    sql = compact(_MODEL_INPUT_SCOPE_SQL)

    assert "placement_tenant.tenant_code" in sql
    assert "placement_tenant.tenant_id = connection.tenant_id" in sql
    assert "scope.model_input_scope_is_locked" in sql
    assert "object.source_tenant_id" not in sql


def test_model_input_scope_reader_exposes_source_owner_and_foreign_catalog() -> None:
    sql = compact(MODEL_INPUT_SCOPE_TOOL_SQL)

    assert "object.source_tenant_id = model.tenant_id" in sql
    assert "source_tenant.tenant_code AS source_tenant_code" in sql
    assert "placement_tenant.tenant_code AS placement_tenant_code" in sql
    assert "connection.foreign_catalog" in sql
    assert "object.fc_object_schema" in sql
    assert "object.fc_object_name" in sql
    assert "zone.zone_code IN ('source', 'bronze')" in sql


def test_binding_snapshot_projects_target_placement_through_bindings() -> None:
    object_sql = compact(_MODEL_OBJECT_BINDING_SQL)
    attribute_sql = compact(_MODEL_ATTRIBUTE_BINDING_SQL)

    assert "workflow.model_object_binding AS binding" in object_sql
    assert "placement_tenant.tenant_id = connection.tenant_id" in object_sql
    assert "binding.modeled_entity_type" in object_sql
    assert "workflow.model_attribute_binding AS attribute_binding" in attribute_sql
    assert "attribute_binding.model_object_binding_id" in attribute_sql
    assert "attribute.attribute_name" in attribute_sql


def test_mapping_snapshot_uses_binding_identity_not_repeated_physical_keys() -> None:
    object_sql = compact(_MAPPING_OBJECT_SQL)
    attribute_sql = compact(_MAPPING_ATTRIBUTE_SQL)

    assert "mapping.model_object_binding_id" in object_sql
    assert "mapping.mapping_transformation_document" in object_sql
    assert "mapping_profile_key" not in object_sql
    assert "mapping_package_document" not in object_sql
    assert "mapping_attribute.model_attribute_binding_id" in attribute_sql
    assert (
        "mapping_attribute.attribute_mapping_transformation_document" in attribute_sql
    )
