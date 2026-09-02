# pyright: reportPrivateUsage=false

from gds_workbench_api.features.conceptual import (
    CONCEPTUAL_OBJECT_SUPPORT_SQL,
    CONCEPTUAL_RELATIONSHIP_SUPPORT_SQL,
)
from gds_workbench_api.features.dimensional import (
    DIMENSIONAL_ATTRIBUTE_SOURCES_SQL,
    DIMENSIONAL_OBJECT_SOURCES_SQL,
)
from gds_workbench_api.features.code_generation.read_service import (
    _CODE_GENERATION_TARGETS_SQL,
    _GENERATED_SQL_ARTIFACT_DETAIL_SQL,
    _GENERATED_SQL_DOWNLOAD_SQL,
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
        assert (
            "source_placement_tenant.tenant_id = source_connection.tenant_id" in compact
        )
        assert "source_eligibility.object_id IS NOT NULL" in compact
        assert "source_eligibility.object_tenant_id" not in compact


def test_logical_source_keys_use_physical_connection_tenant() -> None:
    entity_query = _compact(LOGICAL_ENTITY_SOURCES_SQL)
    attribute_query = _compact(LOGICAL_ATTRIBUTE_SOURCES_SQL)

    assert "workflow.list_model_object_eligibility(" in entity_query
    assert "source_eligibility.is_model_input_eligible" in entity_query
    assert (
        "source_placement_tenant.tenant_id = source_connection.tenant_id"
        in entity_query
    )
    assert "source_eligibility.object_id IS NOT NULL" in entity_query
    assert "source_eligibility.object_tenant_id" not in entity_query
    assert "workflow.list_model_attribute_eligibility(" in attribute_query
    assert "source_eligibility.is_model_input_eligible" in attribute_query
    assert (
        "source_placement_tenant.tenant_id = source_connection.tenant_id"
        in attribute_query
    )
    assert "source_eligibility.attribute_id IS NOT NULL" in attribute_query
    assert "source_eligibility.object_tenant_id" not in attribute_query


def test_dimensional_source_keys_use_physical_connection_tenant() -> None:
    entity_query = _compact(DIMENSIONAL_OBJECT_SOURCES_SQL)
    attribute_query = _compact(DIMENSIONAL_ATTRIBUTE_SOURCES_SQL)

    assert "workflow.list_model_object_eligibility(" in entity_query
    assert "source_eligibility.is_dimensional_source_eligible" in entity_query
    assert (
        "source_placement_tenant.tenant_id = source_connection.tenant_id"
        in entity_query
    )
    assert "source_eligibility.object_id IS NOT NULL" in entity_query
    assert "source_eligibility.object_tenant_id" not in entity_query
    assert "workflow.list_model_attribute_eligibility(" in attribute_query
    assert "source_eligibility.is_dimensional_source_eligible" in attribute_query
    assert (
        "source_placement_tenant.tenant_id = source_connection.tenant_id"
        in attribute_query
    )
    assert "source_eligibility.attribute_id IS NOT NULL" in attribute_query
    assert "source_eligibility.object_tenant_id" not in attribute_query


def test_mapping_target_keys_use_physical_connection_tenant() -> None:
    queries = (
        MAPPING_OBJECTS_SQL,
        MAPPING_OBJECT_DETAIL_SQL,
        MAPPING_ATTRIBUTES_SQL,
        MAPPING_ATTRIBUTE_DETAIL_SQL,
    )
    for sql in queries:
        compact = _compact(sql)
        assert "target_tenant.tenant_id = target_connection.tenant_id" in compact
        assert "target_object.source_tenant_id" not in compact


def test_code_generation_target_keys_use_physical_connection_tenant() -> None:
    target_collection = _compact(_CODE_GENERATION_TARGETS_SQL)
    assert "workflow.list_code_generation_target_context(" in target_collection
    assert "context.source_context -> 'target' AS target" in target_collection
    assert (
        "context.source_context -> 'target' - 'source_tenant_id'"
        not in target_collection
    )

    for sql in (
        _GENERATED_SQL_ARTIFACT_DETAIL_SQL,
        _GENERATED_SQL_DOWNLOAD_SQL,
    ):
        compact = _compact(sql)
        assert "target_tenant.tenant_id = target_connection.tenant_id" in compact
        assert (
            "target_source_tenant.tenant_id = target_object.source_tenant_id" in compact
        )
