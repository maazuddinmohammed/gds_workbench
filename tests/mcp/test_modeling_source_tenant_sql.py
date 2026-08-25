from gds_etl_workbench.tools.modeling.conceptual import CONCEPTUAL_OBJECTS_SQL
from gds_etl_workbench.tools.modeling.mapping import (
    MAPPING_ATTRIBUTES_SQL,
    MAPPING_OBJECTS_SQL,
)
from gds_etl_workbench.tools.modeling.modeled_layer_common import (
    DIMENSIONAL,
    LOGICAL,
    attributes_sql,
    entities_sql,
)
from gds_etl_workbench.tools.modeling.profiling_analysis import (
    ANALYSIS_SQL,
    PROFILING_SQL,
)


def _compact(sql: str) -> str:
    return " ".join(sql.split())


def test_profiling_and_analysis_labels_use_eligible_object_tenants() -> None:
    profiling = _compact(PROFILING_SQL)
    analysis = _compact(ANALYSIS_SQL)

    assert "tenant.tenant_id = eligible_attribute.object_tenant_id" in profiling
    assert "tenant.tenant_id = connection.tenant_id" not in profiling
    assert (
        "from_tenant.tenant_id = eligible_from_attribute.object_tenant_id" in analysis
    )
    assert "to_tenant.tenant_id = eligible_to_attribute.object_tenant_id" in analysis
    assert "tenant_id = from_connection.tenant_id" not in analysis
    assert "tenant_id = to_connection.tenant_id" not in analysis


def test_mapping_labels_use_eligible_object_tenants() -> None:
    for sql in (MAPPING_OBJECTS_SQL, MAPPING_ATTRIBUTES_SQL):
        compact = _compact(sql)
        assert "tenant.tenant_id = eligibility.object_tenant_id" in compact
        assert "tenant.tenant_id = connection.tenant_id" not in compact


def test_conceptual_support_labels_use_eligible_object_tenants() -> None:
    compact = _compact(CONCEPTUAL_OBJECTS_SQL)

    assert "LEFT JOIN eligible_objects AS source_eligibility" in compact
    assert "source_tenant.tenant_id = source_eligibility.object_tenant_id" in compact
    assert "source_tenant.tenant_id = source_connection.tenant_id" not in compact


def test_modeled_layer_source_labels_use_eligible_object_tenants() -> None:
    for config in (LOGICAL, DIMENSIONAL):
        entity_query = _compact(entities_sql(config))
        attribute_query = _compact(attributes_sql(config))

        assert "LEFT JOIN eligible_objects AS source_eligibility" in entity_query
        assert (
            "source_tenant.tenant_id = source_eligibility.object_tenant_id"
            in entity_query
        )
        assert (
            "source_tenant.tenant_id = source_connection.tenant_id" not in entity_query
        )
        assert "LEFT JOIN eligible_attributes AS source_eligibility" in attribute_query
        assert (
            "source_tenant.tenant_id = source_eligibility.object_tenant_id"
            in attribute_query
        )
        assert (
            "source_tenant.tenant_id = source_connection.tenant_id"
            not in attribute_query
        )
