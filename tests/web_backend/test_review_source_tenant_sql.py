# pyright: reportPrivateUsage=false

from gds_workbench_api.features.code_generation.read_service import (
    _CODE_GENERATION_TARGETS_SQL,
    _GENERATED_SQL_ARTIFACT_DETAIL_SQL,
    _GENERATED_SQL_DOWNLOAD_SQL,
)
from gds_workbench_api.features.conceptual import (
    CONCEPTUAL_OBJECT_SUPPORT_SQL,
    CONCEPTUAL_RELATIONSHIP_SUPPORT_SQL,
)
from gds_workbench_api.features.dimensional import (
    DIMENSIONAL_ATTRIBUTE_SOURCES_SQL,
    DIMENSIONAL_OBJECT_SOURCES_SQL,
)
from gds_workbench_api.features.logical import (
    LOGICAL_ATTRIBUTE_SOURCES_SQL,
    LOGICAL_ENTITY_SOURCES_SQL,
)
from gds_workbench_api.features.mapping import (
    MAPPING_ATTRIBUTE_DETAIL_SQL,
    MAPPING_ATTRIBUTES_SQL,
    MAPPING_OBJECT_DETAIL_SQL,
    MAPPING_OBJECTS_SQL,
)


def _compact(sql: str) -> str:
    return " ".join(sql.split())


def test_conceptual_support_uses_physical_connection_tenant() -> None:
    for sql in (CONCEPTUAL_OBJECT_SUPPORT_SQL, CONCEPTUAL_RELATIONSHIP_SUPPORT_SQL):
        compact = _compact(sql)
        assert "workflow.list_model_object_eligibility(" in compact
        assert "source_eligibility.is_model_input_eligible" in compact
        assert "source_placement_tenant.tenant_id = source_connection.tenant_id" in compact
        assert "source_eligibility.object_id IS NOT NULL" in compact
        assert "source_eligibility.object_tenant_id" not in compact


def test_logical_source_keys_use_physical_connection_tenant() -> None:
    entity_query = _compact(LOGICAL_ENTITY_SOURCES_SQL)
    attribute_query = _compact(LOGICAL_ATTRIBUTE_SOURCES_SQL)

    assert "workflow.list_model_object_eligibility(" in entity_query
    assert "source_eligibility.is_model_input_eligible" in entity_query
    assert "source_placement_tenant.tenant_id = source_connection.tenant_id" in entity_query
    assert "source_eligibility.object_id IS NOT NULL" in entity_query
    assert "source_eligibility.object_tenant_id" not in entity_query
    assert "workflow.list_model_attribute_eligibility(" in attribute_query
    assert "source_eligibility.is_model_input_eligible" in attribute_query
    assert "source_placement_tenant.tenant_id = source_connection.tenant_id" in attribute_query
    assert "source_eligibility.attribute_id IS NOT NULL" in attribute_query
    assert "source_eligibility.object_tenant_id" not in attribute_query


def test_dimensional_source_keys_are_model_owned_logical_entities() -> None:
    entity_query = _compact(DIMENSIONAL_OBJECT_SOURCES_SQL)
    attribute_query = _compact(DIMENSIONAL_ATTRIBUTE_SOURCES_SQL)
    for query in (entity_query, attribute_query):
        assert "workflow.logical_entity AS logical_source" in query
        assert "logical_source.model_id = source.model_id" in query
        assert "source_logical_entity_schema_name" in query
        assert "list_model_object_eligibility" not in query
    assert "source_logical_attribute_id" in attribute_query


def test_mapping_targets_are_model_owned_entities() -> None:
    for sql in (MAPPING_OBJECTS_SQL, MAPPING_OBJECT_DETAIL_SQL, MAPPING_ATTRIBUTES_SQL, MAPPING_ATTRIBUTE_DETAIL_SQL):
        compact = _compact(sql)
        assert "workflow.modeled_entity AS entity" in compact
        assert "entity.model_id" in compact
        assert "entity_schema_name" in compact
        assert "core.object" not in compact


def test_code_generation_targets_are_model_owned_entities() -> None:
    target_collection = _compact(_CODE_GENERATION_TARGETS_SQL)
    assert "workflow.list_code_generation_target_context(" in target_collection
    assert "context.modeled_entity_schema_name" in target_collection
    assert "context.modeled_entity_id" in target_collection
    for sql in (_GENERATED_SQL_ARTIFACT_DETAIL_SQL, _GENERATED_SQL_DOWNLOAD_SQL):
        compact = _compact(sql)
        assert "workflow.modeled_entity AS entity" in compact
        assert "entity.modeled_entity_schema_name" in compact
        assert "entity.model_id = artifact.model_id" in compact
        assert "core.object" not in compact
